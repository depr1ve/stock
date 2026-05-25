# A 股智能分析 Agent

基于 akshare + LLM 的 A 股技术分析报告自动生成系统。

线上公开版：https://depr1ve-stock.streamlit.app

## 快速开始

```bash
pip install -r requirements.txt
# 创建 .env 文件，填入 LLM_API_KEY（详见下方环境变量说明）
```

### 两种启动方式

```bash
# 命令行
python -m agent.cli 600000          # 浦发银行，默认60天
python -m agent.cli 000001 -d 30    # 平安银行，30天
python -m agent.cli 300750 -o a.md  # 宁德时代，输出到文件

# Web 界面
streamlit run web.py --server.port 8501
```

不配置 LLM_API_KEY 时，Web 界面仍可展示 K 线图和技术指标，仅 AI 报告不可用。

## 项目结构

```
Stock/
├── web.py                         # Web 入口 (Streamlit)
├── requirements.txt
└── agent/                         # 核心包
    ├── cli.py                     # CLI 入口 (python -m agent.cli)
    ├── orchestrator.py            # Pipeline 编排
    ├── analyzer.py / prompts.py   # LLM 调用 + Prompt
    ├── searcher.py                # Tavily 搜索 + 来源分类 (可选)
    ├── sentiment.py               # FinBERT 情绪分析 (可选)
    ├── config/settings.py         # 所有配置
    ├── data/fetcher.py            # akshare 行情获取 (新浪→东方财富双源容灾)
    ├── indicators/calculator.py   # 技术指标 (numpy: MA/MACD/RSI/布林带/ATR/量比)
    ├── models/schemas.py          # 数据模型
    ├── report/generator.py        # Markdown 报告渲染
    └── utils/http_utils.py        # HTTP 安全抓取 (apparent_encoding)
```

**原则：确定性计算归代码，模糊判断归 LLM。**

## 分析维度

| # | 维度 | 数据来源 |
|---|------|---------|
| 1 | 趋势判断 | 均线排列 + MACD + 涨跌幅 |
| 2 | 波动率分析 | ATR + 布林带宽 + 振幅 |
| 3 | 量价配合 | 涨跌天数 + 量能变化 |
| 4 | 关键价位 | 均线 + 布林轨 + 高低点 |
| 5 | 消息面分析 | Tavily 网络情报 + FinBERT 量化情绪 |
| 6 | 风险提示 | 综合以上 |

## FinBERT 情绪分析

- 模型：`ProsusAI/finbert`，首次使用自动下载，transformers/torch 不可用时静默降级
- 按来源权威性加权汇总：交易所公告(0.40) > 公司财报(0.30) > 权威媒体(0.20) > 普通新闻(0.10)
- cninfo.com.cn 域名按标题关键词细分公告/财报
- Tavily 摘要短于 100 字时自动抓取完整正文

## 支持的股票代码

| 输入 | 自动识别 | 市场 |
|------|---------|------|
| `600000` | sh.600000 | 上交所主板 |
| `000001` | sz.000001 | 深交所主板 |
| `300750` | sz.300750 | 创业板 |
| `sh.688111` | 原样保留 | 科创板 |
| `bj.430047` | 原样保留 | 北交所 |

## 环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `LLM_BASE_URL` | LLM API 地址 | 否 |
| `LLM_API_KEY` | LLM API 密钥 | 是(CLI) / 否(Web图表模式) |
| `LLM_MODEL` | 模型名称 | 否 |
| `TAVILY_API_KEY` | Tavily 搜索密钥 | 否 |

使用 OpenAI 兼容协议，支持 DeepSeek/Qwen/GPT/Claude。

## 依赖

| 包 | 用途 |
|----|------|
| akshare | A 股免费行情数据 |
| pandas / numpy | 数据处理与指标计算 |
| pydantic | 数据校验 |
| openai | LLM 调用 |
| tavily-python | 网页搜索 |
| streamlit | Web 界面 |
| plotly | K 线图可视化 |
| requests | HTTP 抓取 |
| transformers / torch | FinBERT 情绪分析 (可选) |
| python-dotenv | 环境变量加载 |
