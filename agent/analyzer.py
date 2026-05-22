"""
LLM 分析器：将结构化指标数据注入 Prompt，调用 LLM 生成分析报告。
"""

import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from config.settings import LLMConfig
from models.schemas import IndicatorResult, MarketData, AnalysisReport, WebIntel, AggregatedSentiment
from agent.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from agent.searcher import WebSearcher
from agent.sentiment import SentimentAnalyzer

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    """LLM 分析器 — 唯一使用 LLM 的环节"""

    def __init__(self, config: LLMConfig):
        self.client = AsyncOpenAI(base_url=config.base_url, api_key=config.api_key)
        self.model = config.model
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens
        self.timeout = config.timeout

    async def analyze(
        self,
        market_data: MarketData,
        indicators: IndicatorResult,
        web_intel: WebIntel = None,
        sentiment: AggregatedSentiment = None,
    ) -> AnalysisReport:
        """
        将行情数据、指标结果、网络情报和 FinBERT 情绪分析注入 prompt，调用 LLM 生成分析报告。
        """
        s = indicators.latest_snapshot
        ps = indicators.period_stats

        # 构造近5日明细表
        recent_rows = market_data.rows[-5:]
        recent_table = self._build_recent_table(recent_rows)

        # 格式化数值
        def fmt(v: Optional[float], precision: int = 2) -> str:
            if v is None:
                return "N/A"
            return f"{v:.{precision}f}"

        user_prompt = USER_PROMPT_TEMPLATE.format(
            days=len(market_data.rows),
            stock_code=market_data.stock_code,
            stock_name=market_data.stock_name or "未知",
            start_date=ps.start_date,
            end_date=ps.end_date,
            total_change=f"{ps.total_change_pct:+.2f}",
            up_days=ps.up_days,
            down_days=ps.down_days,
            max_up=fmt(ps.max_up_pct),
            max_down=fmt(ps.max_down_pct),
            avg_amp=fmt(ps.avg_amplitude_pct),
            max_amp=fmt(ps.max_amplitude_pct),
            avg_vol=f"{ps.avg_volume:,.0f}",
            latest_date=s.date,
            close=fmt(s.close),
            ma5=fmt(s.ma5),
            ma10=fmt(s.ma10),
            ma20=fmt(s.ma20),
            ma60=fmt(s.ma60),
            rsi=fmt(s.rsi, 1),
            dif=fmt(s.macd_dif, 4),
            dea=fmt(s.macd_dea, 4),
            hist=fmt(s.macd_hist, 4),
            boll_u=fmt(s.boll_upper),
            boll_m=fmt(s.boll_mid),
            boll_l=fmt(s.boll_lower),
            boll_w=fmt(s.boll_width, 4),
            atr=fmt(s.atr),
            vol_ratio=fmt(s.volume_ratio),
            ma_arrangement=indicators.ma_arrangement,
            ma_cross=indicators.ma_cross,
            rsi_zone=indicators.rsi_zone,
            boll_position=indicators.boll_position,
            recent_table=recent_table,
            web_intel=WebSearcher.format_for_prompt(web_intel) if web_intel else "（未提供网络情报）",
            sentiment_analysis=SentimentAnalyzer.format_for_prompt(sentiment),
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
            raw = response.choices[0].message.content or ""
            raw = self._sanitize(raw)
        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            raw = f"LLM 调用失败: {e}"

        return AnalysisReport(
            stock_code=market_data.stock_code,
            stock_name=market_data.stock_name,
            days=len(market_data.rows),
            trend=self._extract_section(raw, "趋势判断"),
            volatility=self._extract_section(raw, "波动率分析"),
            volume_price=self._extract_section(raw, "量价配合分析"),
            key_levels=self._extract_section(raw, "关键价位"),
            risk=self._extract_section(raw, "风险提示"),
            news_sentiment=self._extract_section(raw, "消息面"),
            raw_text=raw,
        )

    @staticmethod
    def _build_recent_table(rows: list) -> str:
        """构造近5日行情明细 Markdown 表格"""
        header = "| 日期 | 开盘 | 收盘 | 最高 | 最低 | 涨跌幅 | 振幅 | 成交量(手) |"
        sep = "|------|------|------|------|------|--------|------|------------|"
        lines = []
        for r in rows:
            lines.append(
                f"| {r.date} | {r.open:.2f} | {r.close:.2f} | {r.high:.2f} | "
                f"{r.low:.2f} | {r.change_pct:+.2f}% | {r.amplitude_pct:.2f}% | {r.volume:,} |"
            )
        return "\n".join([header, sep] + lines)

    @staticmethod
    def _extract_section(text: str, section_name: str) -> str:
        """从 LLM 输出中提取指定章节的内容，支持精确和模糊匹配"""
        # 先精确匹配
        for marker_level in ["###", "##", "#"]:
            for prefix in [f"{marker_level} {section_name}"]:
                idx = text.find(prefix)
                if idx != -1:
                    start = idx + len(prefix)
                    rest = text[start:]
                    end_pos = len(rest)
                    for end_marker in ["###", "##", "免责声明"]:
                        pos = rest.find(end_marker)
                        if pos != -1 and pos < end_pos:
                            end_pos = pos
                    return rest[:end_pos].strip()

        # 模糊匹配：搜索包含 section_name 的标题行
        for line in text.split("\n"):
            if line.startswith("#") and section_name in line:
                idx = text.find(line)
                start = idx + len(line)
                rest = text[start:]
                end_pos = len(rest)
                for end_marker in ["###", "##", "免责声明"]:
                    pos = rest.find(end_marker)
                    if pos != -1 and pos < end_pos:
                        end_pos = pos
                result = rest[:end_pos].strip()
                if result:
                    return result

        return text.strip() if len(text) < 200 else ""

    @staticmethod
    def _sanitize(text: str) -> str:
        """移除 GBK 不支持的 emoji，避免 Windows 终端报错"""
        result = []
        for ch in text:
            try:
                ch.encode("gbk")
                result.append(ch)
            except UnicodeEncodeError:
                result.append("")
        return "".join(result)
