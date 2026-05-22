"""
A 股智能分析 — Web 界面
Streamlit + Plotly 构建，支持 K 线图、指标可视化、AI 分析报告。
启动: streamlit run web.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta
from dotenv import load_dotenv

from models.schemas import StockRequest
from data.fetcher import DataFetcher, FetchError
from indicators.calculator import IndicatorCalculator
from agent.analyzer import LLMAnalyzer
from agent.searcher import WebSearcher
from agent.sentiment import SentimentAnalyzer
from config.settings import Config, default_config
from report.generator import ReportGenerator

# 优先级：环境变量 > st.secrets > 内置默认值
load_dotenv()

FALLBACK_CONFIG = {
    "LLM_BASE_URL": "https://api.deepseek.com/v1",
    "LLM_API_KEY": "sk-e623fb6d88ef4568b45968f4032dd10d",
    "LLM_MODEL": "deepseek-chat",
}

for key in ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "TAVILY_API_KEY"]:
    if not os.getenv(key):
        try:
            if key in st.secrets and st.secrets[key]:
                os.environ[key] = st.secrets[key]
            elif key in FALLBACK_CONFIG:
                os.environ[key] = FALLBACK_CONFIG.get(key, "")
        except Exception:
            if key in FALLBACK_CONFIG:
                os.environ[key] = FALLBACK_CONFIG.get(key, "")

# default_config 在 import 时已创建，需要把后续注入的环境变量同步回去
default_config.web_search.api_key = os.getenv("TAVILY_API_KEY", "")

# ── 页面配置 ──────────────────────────────────────────

st.set_page_config(
    page_title="A 股智能分析",
    page_icon="chart_with_upwards_trend",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stApp { max-width: 1400px; margin: 0 auto; }
    .main-header { font-size: 1.8rem; font-weight: 700; color: #1f77b4; }
    section[data-testid="stSidebar"] { width: 320px !important; }
</style>
""", unsafe_allow_html=True)


# ── 预设标的 ──────────────────────────────────────────

PRESETS = {
    "浦发银行": "600000",
    "平安银行": "000001",
    "贵州茅台": "600519",
    "宁德时代": "300750",
    "金山办公": "sh.688111",
    "东阳光": "600673",
}


# ── Session 初始化 ────────────────────────────────────

def init_session():
    defaults = {
        "stock_code": "600000",
        "stock_name": "",
        "days": 30,
        "market_data": None,
        "indicators": None,
        "web_intel": None,
        "analysis_report": None,
        "raw_md": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── 数据加载 ──────────────────────────────────────────

def load_data(code: str, days: int):
    """拉取行情 + 计算指标（不调用 LLM）"""
    req = StockRequest(raw_code=code, days=days)
    fetcher = DataFetcher()
    data = asyncio.run(fetcher.fetch(req))
    calc = IndicatorCalculator()
    indicators = calc.compute(data)
    return data, indicators


def run_web_search(code: str, name: str):
    """搜索网络情报"""
    cfg = default_config
    searcher = WebSearcher(cfg.web_search)
    if searcher.available:
        return asyncio.run(searcher.search(code, name))
    return None


def run_llm_analysis(data, indicators, web_intel=None, sentiment=None):
    """调用 LLM 分析"""
    cfg = default_config
    analyzer = LLMAnalyzer(cfg.llm)
    return asyncio.run(analyzer.analyze(data, indicators, web_intel, sentiment))


# ── K 线图 ────────────────────────────────────────────

def plot_kline(data, indicators):
    """绘制 K 线 + 均线 + 成交量"""
    df = data.df
    s = indicators.latest_snapshot
    ps = indicators.period_stats

    close = df["close"].values
    dates = pd.to_datetime(df["date"])

    # 计算均线
    def sma(s, p):
        return pd.Series(s).rolling(p).mean().values

    ma5 = sma(close, 5)
    ma10 = sma(close, 10)
    ma20 = sma(close, 20)
    ma60 = sma(close, 60)

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.55, 0.22, 0.23],
        subplot_titles=(
            f"{data.stock_name} ({data.stock_code})  —  {ps.start_date} ~ {ps.end_date}  |  "
            f"涨跌幅 [color_red]{ps.total_change_pct:+.2f}%[/color_red]  |  "
            f"振幅均值 {ps.avg_amplitude_pct:.2f}%",
            "成交量",
            "MACD & RSI",
        ),
    )

    # K 线
    colors = ["red" if close[i] >= df["open"].values[i] else "green" for i in range(len(df))]
    fig.add_trace(
        go.Candlestick(
            x=dates, open=df["open"], high=df["high"], low=df["low"], close=close,
            name="K线",
            increasing=dict(line=dict(color="red"), fillcolor="red"),
            decreasing=dict(line=dict(color="green"), fillcolor="green"),
            showlegend=True,
        ),
        row=1, col=1,
    )
    # 均线
    for ma, period, color in [(ma5, 5, "blue"), (ma10, 10, "orange"), (ma20, 20, "purple"), (ma60, 60, "gray")]:
        visible = ~np.isnan(ma)
        if visible.any():
            fig.add_trace(
                go.Scatter(x=dates[visible], y=ma[visible], mode="lines",
                           line=dict(width=1.2, color=color), name=f"MA{period}"),
                row=1, col=1,
            )

    # 布林带
    if s.boll_upper and s.boll_mid and s.boll_lower:
        boll = IndicatorCalculator()
        upper, mid, lower, _ = boll._bollinger(close, 20, 2)
        for arr, name, clr in [(upper, "上轨", "rgba(128,128,128,0.3)"), (mid, "中轨", "rgba(128,128,128,0.5)"), (lower, "下轨", "rgba(128,128,128,0.3)")]:
            vis = ~np.isnan(arr)
            if vis.any():
                fig.add_trace(
                    go.Scatter(x=dates[vis], y=arr[vis], mode="lines",
                               line=dict(width=0.8, color="gray", dash="dash"), name=f"BB {name}"),
                    row=1, col=1,
                )

    # 成交量
    vol_colors = ["red" if close[i] >= close[i - 1] else "green" for i in range(len(close))]
    fig.add_trace(
        go.Bar(x=dates, y=df["volume"], marker_color=vol_colors, name="成交量", showlegend=False),
        row=2, col=1,
    )

    # MACD
    dif, dea, hist = IndicatorCalculator._macd(close, 12, 26, 9)
    fig.add_trace(go.Bar(x=dates, y=hist, marker_color="rgba(100,100,255,0.6)", name="MACD柱"), row=3, col=1)
    fig.add_trace(go.Scatter(x=dates, y=dif, mode="lines", line=dict(width=1, color="blue"), name="DIF"), row=3, col=1)
    fig.add_trace(go.Scatter(x=dates, y=dea, mode="lines", line=dict(width=1, color="orange"), name="DEA"), row=3, col=1)

    # RSI 叠加在副y轴
    rsi = IndicatorCalculator._rsi(close, 14)
    fig.add_trace(
        go.Scatter(x=dates, y=rsi, mode="lines", line=dict(width=1, color="purple"), name="RSI(14)",
                   yaxis="y4"),
        row=3, col=1,
    )

    fig.update_layout(
        height=700,
        template="plotly_white",
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=10)),
        margin=dict(t=60, b=20, l=20, r=20),
    )

    # RSI 副轴
    fig.update_layout(
        yaxis4=dict(domain=[0, 1], range=[0, 100], tickmode="array",
                     tickvals=[20, 30, 50, 70, 80], showgrid=False, overlaying="y3", side="right",
                     title="RSI"),
    )

    # 添加 RSI 参考线
    for level, color in [(30, "green"), (70, "red")]:
        fig.add_hline(y=level, line_dash="dash", line_color=color, opacity=0.4, row=3, col=1)

    fig.add_hline(y=0, line_color="gray", opacity=0.3, row=3, col=1)

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})


# ── 侧边栏 ────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("##  A 股智能分析")
        st.markdown("---")

        # 预设选择
        st.markdown("###  快速选择")
        cols = st.columns(3)
        presets_list = list(PRESETS.items())
        for i, (name, code) in enumerate(presets_list):
            col_idx = i % 3
            with cols[col_idx]:
                if st.button(name, key=f"preset_{code}", use_container_width=True,
                             type="secondary" if st.session_state.stock_code != code else "primary"):
                    st.session_state.stock_code = code
                    st.session_state.stock_name = name

        st.markdown("---")

        # 自定义输入
        st.markdown("###  自定义标的")
        code_input = st.text_input(
            "股票代码",
            value=st.session_state.stock_code,
            placeholder="600000 / sh.600000",
            label_visibility="collapsed",
        )
        if code_input:
            st.session_state.stock_code = code_input

        st.session_state.days = st.slider("统计天数", 5, 365, st.session_state.days, step=5)

        st.markdown("---")

        # LLM 状态
        api_key = os.getenv("LLM_API_KEY", "")
        if api_key and api_key != "在此填入你的DeepSeek_API_Key":
            st.success("LLM 已配置")
        else:
            st.warning("LLM 未配置 — 仅展示图表")

        # 分析按钮
        st.markdown("---")
        analyze_btn = st.button(" 开始分析", type="primary", use_container_width=True)

    return analyze_btn


# ── 主页面 ────────────────────────────────────────────

def main():
    init_session()

    st.markdown('<div class="main-header">A 股智能分析 Agent</div>', unsafe_allow_html=True)
    st.caption("基于 akshare 行情数据 + LLM 技术分析，自动生成专业分析报告")

    analyze_clicked = render_sidebar()

    # ── 执行分析 ────────────────────────────────────
    if analyze_clicked:
        code = st.session_state.stock_code.strip()
        days = st.session_state.days

        try:
            StockRequest(raw_code=code, days=days)
        except ValueError as e:
            st.error(f"代码格式错误: {e}")
            return

        with st.spinner("正在拉取行情数据..."):
            try:
                data, indicators = load_data(code, days)
                st.session_state.market_data = data
                st.session_state.indicators = indicators
            except FetchError as e:
                st.error(f"数据拉取失败: {e}")
                return

        # 网络情报搜索
        with st.spinner("正在搜索相关情报..."):
            web_intel = run_web_search(data.stock_code, data.stock_name)
            st.session_state.web_intel = web_intel

        # FinBERT 情绪分析
        sentiment = None
        if web_intel and web_intel.results:
            sentiment_cfg = default_config.sentiment
            sa = SentimentAnalyzer(sentiment_cfg)
            if sa.available:
                with st.spinner("正在进行 FinBERT 情绪分析..."):
                    try:
                        sentiment = sa.analyze(web_intel)
                        if sentiment:
                            web_intel.sentiment_analysis = sentiment
                    except Exception:
                        pass
            else:
                sentiment = None

        api_key = os.getenv("LLM_API_KEY", "")
        has_llm = api_key and api_key != "在此填入你的DeepSeek_API_Key"

        if has_llm:
            with st.spinner("正在调用 AI 分析..."):
                try:
                    report = run_llm_analysis(data, indicators, web_intel, sentiment)
                    st.session_state.analysis_report = report
                    gen = ReportGenerator()
                    st.session_state.raw_md = gen.render(indicators, report, sentiment)
                except Exception as e:
                    st.warning(f"AI 分析失败: {e}，仅展示图表数据")
                    st.session_state.analysis_report = None
                    st.session_state.raw_md = ""
        else:
            # 无 LLM 时生成纯数据报告
            gen = ReportGenerator()
            from models.schemas import AnalysisReport
            dummy = AnalysisReport(
                stock_code=data.stock_code, stock_name=data.stock_name,
                days=data.count, trend="", volatility="", volume_price="",
                key_levels="", risk="", news_sentiment=""
            )
            st.session_state.raw_md = gen.render(indicators, dummy, sentiment)

    # ── 展示结果 ────────────────────────────────────
    if st.session_state.indicators is not None:
        indicators = st.session_state.indicators
        data = st.session_state.market_data

        st.markdown("---")

        # 指标卡片
        s = indicators.latest_snapshot
        ps = indicators.period_stats

        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.metric("最新价", f"{s.close:.2f}" if s.close else "N/A")
        with col2:
            delta = f"{ps.total_change_pct:+.2f}%"
            st.metric("区间涨跌", f"{delta}", delta=ps.total_change_pct)
        with col3:
            st.metric("日均振幅", f"{ps.avg_amplitude_pct:.2f}%")
        with col4:
            ratio = f"{ps.up_days}:{ps.down_days}"
            st.metric("涨跌天数比", ratio)
        with col5:
            st.metric("RSI(14)", f"{s.rsi:.1f}" if s.rsi else "N/A")
        with col6:
            st.metric("ATR(14)", f"{s.atr:.2f}" if s.atr else "N/A")

        st.markdown("---")

        # K 线图
        plot_kline(data, indicators)

        # 指标表格
        st.markdown("###  技术指标详情")
        with st.expander("展开查看", expanded=False):
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"""
                | 均线 | 数值 |
                |------|------|
                | MA5 | {_fmt(s.ma5)} |
                | MA10 | {_fmt(s.ma10)} |
                | MA20 | {_fmt(s.ma20)} |
                | MA60 | {_fmt(s.ma60)} |
                """)
                st.markdown(f"""
                | 布林带 | 数值 |
                |------|------|
                | 上轨 | {_fmt(s.boll_upper)} |
                | 中轨 | {_fmt(s.boll_mid)} |
                | 下轨 | {_fmt(s.boll_lower)} |
                | 带宽 | {_fmt(s.boll_width, 4)} |
                """)
            with col_b:
                st.markdown(f"""
                | MACD | 数值 |
                |------|------|
                | DIF | {_fmt(s.macd_dif, 4)} |
                | DEA | {_fmt(s.macd_dea, 4)} |
                | 柱 | {_fmt(s.macd_hist, 4)} |
                """)
                st.markdown(f"""
                | 信号 | 状态 |
                |------|------|
                | 均线排列 | {indicators.ma_arrangement} |
                | MACD | {indicators.ma_cross} |
                | RSI | {indicators.rsi_zone} |
                | 布林位置 | {indicators.boll_position} |
                """)

        # 网络情报
        if st.session_state.web_intel and st.session_state.web_intel.results:
            st.markdown("---")
            st.markdown("###  网络情报")
            with st.expander("展开查看最新相关消息", expanded=False):
                # 显示 FinBERT 情绪总结
                if st.session_state.web_intel.sentiment_analysis:
                    agg = st.session_state.web_intel.sentiment_analysis
                    st.markdown("####  情绪量化分析 (FinBERT)")
                    col_p, col_n, col_neg = st.columns(3)
                    with col_p:
                        st.metric("正面概率", f"{agg.overall.positive:.1%}")
                    with col_n:
                        st.metric("中性概率", f"{agg.overall.neutral:.1%}")
                    with col_neg:
                        st.metric("负面概率", f"{agg.overall.negative:.1%}")
                    st.markdown("---")

                for item in st.session_state.web_intel.results:
                    date_str = f" ({item.published_date})" if item.published_date else ""

                    source_badge = ""
                    if item.source_label:
                        badge_color = {
                            "交易所公告": "#d9534f",
                            "公司财报": "#f0ad4e",
                            "权威媒体": "#5bc0de",
                            "普通新闻": "#999999",
                        }.get(item.source_label, "#999999")
                        source_badge = (
                            f' <span style="background:{badge_color};color:white;padding:1px 6px;'
                            f'border-radius:3px;font-size:0.75rem;">{item.source_label}</span>'
                        )

                    # 来源标签 + FinBERT 情绪分数
                    sentiment_text = ""
                    if st.session_state.web_intel.sentiment_analysis:
                        for si in st.session_state.web_intel.sentiment_analysis.items:
                            if si.url == item.url:
                                s = si.sentiment
                                sentiment_text = (
                                    f" :green[正面 {s.positive:.1%}] | "
                                    f":gray[中性 {s.neutral:.1%}] | "
                                    f":red[负面 {s.negative:.1%}]"
                                )
                                break

                    st.markdown(
                        f"{source_badge}{sentiment_text}  "
                        f"[阅读原文]({item.url}){date_str}",
                        unsafe_allow_html=True,
                    )

        # AI 分析报告
        if st.session_state.raw_md:
            st.markdown("---")
            st.markdown("###  AI 分析报告")
            st.markdown(st.session_state.raw_md)

            # 导出
            st.download_button(
                " 下载报告 (Markdown)",
                data=st.session_state.raw_md,
                file_name=f"analysis_{st.session_state.stock_code.replace('.','_')}_{date.today()}.md",
                mime="text/markdown",
            )


def _fmt(val, precision: int = 2) -> str:
    if val is None:
        return "N/A"
    try:
        import math
        if math.isnan(val):
            return "N/A"
    except Exception:
        pass
    return f"{val:.{precision}f}"


if __name__ == "__main__":
    main()
