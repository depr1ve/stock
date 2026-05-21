# A 股智能分析 Agent

基于 akshare + LLM 的 A 股技术分析报告自动生成系统。支持本地命令行、交互式终端、Web 界面三种使用方式。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY（必填）和 TAVILY_API_KEY（可选，用于消息面分析）
```

### 三种启动方式

```bash
# 方式一：命令行单次（最简单）
python main.py 600000              # 浦发银行，默认60天
python main.py 000001 -d 30        # 平安银行，30天
python main.py 300750 -o a.md      # 宁德时代，输出到文件

# 方式二：交互式终端（菜单导航 + 历史记录）
python app.py

# 方式三：Web 界面（图表可视化 + AI 报告）
streamlit run web.py --server.port 8501
```

### 离线使用

不配置 LLM_API_KEY 时，Web 界面仍可正常展示 K 线图和技术指标，仅 AI 分析报告不可用。命令行模式需要 Key。

## 架构

```
用户输入 (A股代码 + 天数)
  │
  ▼
┌─────────────────┐
│  StockRequest    │  Pydantic 校验 + 市场前缀自动补全 (600000 → sh.600000)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  DataFetcher     │  akshare 双源容灾 (新浪 → 东方财富)，自动重试
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  IndicatorCalc   │  纯 numpy/pandas 确定性计算，无 LLM 依赖
│  · MA5/10/20/60  │
│  · MACD (DIF/DEA/柱) │
│  · RSI(14)       │
│  · 布林带(20,2)   │
│  · ATR(14)       │
│  · 量比          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  WebSearcher     │  Tavily API 搜索标的新闻/公告/研报（可选）
│  默认聚焦:        │  未配置 Key 时静默跳过
│  东方财富/新浪/同花顺 │
│  巨潮资讯/财联社   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  LLMAnalyzer     │  结构化 prompt 注入 → 多维度分析
│  ① 趋势判断       │  OpenAI 协议 (兼容 GPT/DeepSeek/Qwen/Claude)
│  ② 波动率分析     │
│  ③ 量价配合       │
│  ④ 关键价位       │
│  ⑤ 消息面分析     │  ← 结合网络情报
│  ⑥ 风险提示       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ReportGenerator  │  Markdown 报告输出
└─────────────────┘
```

**核心思想：确定性计算归代码，模糊判断归 LLM。** 只有 `agent/analyzer.py` 调用大模型，其余全是代码逻辑。

## 项目结构

```
Stock/
├── main.py                  # CLI 单次入口 (python main.py 600000)
├── app.py                   # 交互式终端 (Rich 菜单)
├── web.py                   # Web 界面 (Streamlit + Plotly K线图)
├── requirements.txt         # Python 依赖
├── Dockerfile               # Docker 镜像
├── docker-compose.yml       # 一键部署
├── .env.example             # 环境变量模板
│
├── config/
│   └── settings.py          # LLM / WebSearch / Analysis 配置
│
├── models/
│   └── schemas.py           # 数据模型 (StockRequest → MarketData → IndicatorResult → AnalysisReport → WebIntel)
│
├── data/
│   └── fetcher.py           # akshare 行情拉取（新浪+东方财富双源容灾）
│
├── indicators/
│   └── calculator.py        # 技术指标计算 (MA/MACD/RSI/布林带/ATR/量比)
│
├── agent/
│   ├── prompts.py           # System Prompt + User Prompt 模板
│   ├── searcher.py          # Tavily 网页搜索（新闻/公告/研报）
│   ├── analyzer.py          # LLM 分析器（prompt 注入 + 结果解析）
│   └── orchestrator.py      # Pipeline 编排器（串联全部步骤）
│
└── report/
    └── generator.py         # Markdown 报告渲染
```

## 各模块用途

| 模块 | 文件 | 功能 |
|------|------|------|
| **入口层** | `main.py` | 命令行单次分析，支持 `-d` 天数、`-o` 输出文件 |
| | `app.py` | 交互式终端，Rich 菜单导航，支持历史记录和配置管理 |
| | `web.py` | Web 界面，Plotly K线图 + 指标可视化 + AI 报告 + 网络情报卡片 |
| **配置** | `config/settings.py` | 管理 LLM 连接参数、Tavily 搜索参数、分析参数，从 `.env` 加载 |
| **数据模型** | `models/schemas.py` | `StockRequest` → `MarketData` → `IndicatorResult` → `WebIntel` → `AnalysisReport`，全链路类型安全 |
| **数据层** | `data/fetcher.py` | akshare 行情拉取，新浪源优先，东方财富源兜底，自动重试 |
| **指标层** | `indicators/calculator.py` | 纯 numpy 计算 MA/MACD/RSI/布林带/ATR/量比，不依赖 LLM |
| **搜索层** | `agent/searcher.py` | Tavily API 搜索标的相关新闻/公告/研报，默认聚焦 5 个财经站点 |
| **分析层** | `agent/prompts.py` | System Prompt（角色设定）+ User Prompt（数据注入模板） |
| | `agent/analyzer.py` | 将指标数据 + 网络情报注入 prompt，调用 LLM，解析结构化结果 |
| | `agent/orchestrator.py` | 编排完整流水线：校验 → 拉取 → 指标 → 搜索 → LLM → 报告 |
| **报告层** | `report/generator.py` | 将指标摘要 + LLM 分析结果渲染为 Markdown 报告 |

## LLM 分析维度

| 维度 | 说明 |
|------|------|
| 趋势判断 | 均线排列 + MACD + 涨跌幅 → 偏多/偏空/震荡 + 置信度 |
| 波动率分析 | ATR + 布林带宽 + 振幅 → 波动水平与收敛/发散趋势 |
| 量价配合 | 涨跌天数分布 + 放量/缩量与价格方向配合关系 |
| 关键价位 | 均线位置 + 布林轨 + 近期高低点 → 支撑位/压力位 |
| 消息面分析 | 结合网络情报分析近期消息影响，判断情绪偏正面/负面/中性 |
| 风险提示 | 综合技术面 + 消息面，列出 2-3 条短期风险 |

## 技术指标

| 指标 | 参数 | 说明 |
|------|------|------|
| MA | 5/10/20/60 | 简单移动均线，判断多头/空头排列 |
| MACD | 12/26/9 | DIF/DEA/柱，金叉死叉信号 |
| RSI | 14 | 超买(>70)/超卖(<30)判断 |
| 布林带 | 20, 2σ | 上中下轨 + 带宽，价格相对位置 |
| ATR | 14 | 平均真实波幅，波动率度量 |
| 量比 | 5日均量 | 当日成交量与5日均量比值 |

## 支持的股票代码

| 输入 | 自动识别 | 市场 |
|------|---------|------|
| `600000` | sh.600000 | 上交所主板 |
| `000001` | sz.000001 | 深交所主板 |
| `300750` | sz.300750 | 创业板 |
| `sh.688111` | 原样保留 | 科创板 |
| `bj.430047` | 原样保留 | 北交所 |

## 远程部署

### Docker 一键部署

```bash
docker compose up -d
# 访问 http://你的服务器IP:8501
```

### 内网穿透（临时分享）

```bash
# ngrok
ngrok http 8501

# localtunnel
npx localtunnel --port 8501
```

## 环境变量

| 变量 | 说明 | 默认值 | 必填 |
|------|------|--------|------|
| `LLM_BASE_URL` | LLM API 地址 | `https://api.openai.com/v1` | 否 |
| `LLM_API_KEY` | LLM API 密钥 | — | 是（CLI）/ 否（Web 图表模式） |
| `LLM_MODEL` | 模型名称 | `gpt-4o` | 否 |
| `TAVILY_API_KEY` | Tavily 搜索密钥 | — | 否（不配则跳过消息面分析） |

## 依赖

| 包 | 用途 |
|----|------|
| akshare | A 股免费行情数据 |
| pandas / numpy | 数据处理与指标计算 |
| pydantic | 数据校验与模型定义 |
| openai | LLM 调用（兼容 DeepSeek/Qwen/GPT/Claude） |
| tavily-python | 网页搜索（新闻/公告/研报） |
| streamlit | Web 界面 |
| plotly | K 线图与指标可视化 |
| rich | 交互式终端美化 |
| python-dotenv | 环境变量加载 |
