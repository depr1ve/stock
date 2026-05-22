# A 股智能分析 Agent

基于 akshare + LLM 的 A 股技术分析报告自动生成系统。三种使用形态：

| 入口 | 启动方式 | 用途 |
|------|---------|------|
| `web.py` | `streamlit run web.py --server.port 8501` | Web 界面（K线图+AI报告+网络情报） |
| `app.py` | `python app.py` | Rich 交互式 CLI（菜单导航+历史记录） |
| `main.py` | `python main.py 600000 -d 30` | 命令行单次模式 |

线上公开版：https://depr1ve-stock.streamlit.app

## 架构

```
main.py / app.py / web.py (入口)
    └── agent/orchestrator.py          # Pipeline 编排器
        ├── models/schemas.py          # StockRequest → MarketData → IndicatorResult → WebIntel → AnalysisReport
        ├── data/fetcher.py            # akshare 双源容灾 (新浪 → 东方财富)
        ├── indicators/calculator.py   # MA/MACD/RSI/布林带/ATR/量比 (纯 numpy)
        ├── agent/searcher.py          # Tavily 网页搜索 + 来源自动分类 ← 可选
        ├── agent/sentiment.py         # FinBERT 情绪分析 (ProsusAI/finbert) ← 可选
        │   └── utils/http_utils.py    # 编码安全 HTTP 抓取 (apparent_encoding + 提取式摘要)
        ├── agent/analyzer.py          # LLM 调用 → 结构化分析报告
        │   └── agent/prompts.py       # System Prompt + User Prompt (含 FinBERT 情绪分数注入)
        └── report/generator.py        # Markdown 报告渲染 (含情绪量化表)
```

**设计原则：确定性计算归代码，模糊判断归 LLM。** `agent/analyzer.py` 调用大模型，`agent/sentiment.py` 是确定性 ML 推理，其余全是代码逻辑。

## 关键文件路径

- 配置：`config/settings.py`（LLMConfig / WebSearchConfig / SentimentConfig / AnalysisConfig）
- 环境变量：`.env`（本地上报）或 Streamlit Secrets（云部署）
- API Key 内置回退：`web.py` 中 `FALLBACK_CONFIG` 提供 DeepSeek 默认 Key
- 历史报告：`history/` 目录（通过 app.py 保存）

## 数据流

```
用户输入 (600000, 30天)
  → StockRequest 校验 (自动补全 sh/sz/bj 前缀)
  → DataFetcher.fetch() (akshare → pandas → list[MarketRow])
  → IndicatorCalculator.compute() (numpy → IndicatorResult)
  → WebSearcher.search() (Tavily → 新闻/公告/研报 → WebIntel) [可选]
      └── _classify_source() 自动标注来源: 交易所公告/公司财报/权威媒体/普通新闻
  → SentimentAnalyzer.analyze() (FinBERT → 每条情绪分数 → 加权汇总) [可选]
      └── snippet < 100 字时 fetch_text() 抓取完整正文 → summarize_text() 提取摘要
  → LLMAnalyzer.analyze() (Prompt注入 + 网络情报 + FinBERT情绪 → LLM → AnalysisReport)
  → ReportGenerator.render() (Markdown + 情绪量化表)
```

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

- 模型：`ProsusAI/finbert`，懒加载，transformers pipeline (text-classification, top_k=None)
- WebSearcher._classify_source() 按域名+标题关键词分类，SearchItem 带 source_type/source_label
- SentimentAnalyzer 对每条结果调用 FinBERT，按来源权重加权汇总
- 来源权重：交易所公告 0.40 > 公司财报 0.30 > 权威媒体 0.20 > 普通新闻 0.10
- 公告/财报细分：cninfo.com.cn 域名下，标题含"年报/季报/业绩"→财报，含"公告/披露"→公告
- `format_for_prompt()` 生成量化情绪文本注入 LLM prompt
- `utils/http_utils.py`：`fetch_text()` 使用 `resp.encoding = resp.apparent_encoding` 自动检测 GBK/UTF-8
- `summarize_text()`：按块级标签分段落，跳过 <15 字符碎片，截取前 500 字符
- transformers/torch 不可用时静默降级，不影响核心流程

## 来源分类规则

| 来源类型 | 域名 | 标题关键词 | 权重 |
|---------|------|-----------|------|
| 交易所公告 | cninfo.com.cn | 公告、披露、停牌、复牌、重组、增持、减持、质押 | 0.40 |
| 公司财报 | cninfo.com.cn | 年度报告、季度报告、年报、季报、财报、业绩、营收、净利润 | 0.30 |
| 权威媒体 | eastmoney.com / 10jqka.com.cn / cls.cn | — | 0.20 |
| 普通新闻 | sina.com.cn 及其他 | — | 0.10 |

## 配置

### .env 环境变量

```
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-chat
TAVILY_API_KEY=tvly-xxx    # 可选，不配则跳过网络搜索
```

### LLM 协议兼容

使用 OpenAI 兼容协议，支持：DeepSeek / Qwen / GPT / Claude / 本地模型。修改 `LLM_BASE_URL` + `LLM_MODEL` 即可切换。

### Tavily 搜索配置

默认聚焦 5 个财经信息源：东方财富、新浪财经、同花顺、巨潮资讯、财联社。可在 `WebSearchConfig.include_domains` 修改。

### SentimentConfig 可调参数

`sentiment.py` 中 `SentimentConfig` 控制：`fetch_full_content`（snippet 太短时抓取完整正文）、`fetch_timeout`（抓取超时秒数）、`min_content_length`（触发抓取的阈值）、`source_weights`（各来源权重）。

## 重要约束

- **Python 解释器**：`E:/Anaconda/python.exe`（E 盘 Anaconda 环境，预装 torch 2.6.0 + transformers 5.9.0）
- **编译/运行环境**：Windows 11，bash 终端，E:/Anaconda 为默认 Python
- 新版 transformers 5.x `return_all_scores` 已废弃，改用 `top_k=None`
- transformers 5.9.0 要求 torch >= 2.6.0，需同时升级 torchvision/torchaudio
- `requests.get(url).text` 不可直接使用，必须走 `resp.encoding = resp.apparent_encoding`
- Windows 终端 GBK 编码不支持 emoji，`analyzer.py` 有 `_sanitize()` 过滤
- 7天数据时 RSI/MACD/布林/ATR 均为 N/A（窗口期不足），LLM 自适应降级
- akshare 东方财富源可能被墙，fetcher 优先走新浪源
- `_extract_section()` 支持精确匹配 + 模糊匹配，能解析带编号的标题（如 `### 五、消息面与情绪分析`）
- WebSearcher / SentimentAnalyzer 为可选组件，不可用时静默降级，不影响核心流程
- `.env` 已加入 `.gitignore`，API Key 不会被提交
- `web.py` 网络情报区只展示来源标签 + FinBERT 情绪分数 + 原文链接，不展示标题和内容摘要

## 报告格式

LLM 输出标准 Markdown 结构：

```
### 一、趋势判断
### 二、波动率分析
### 三、量价配合分析
### 四、关键价位
### 五、消息面与情绪分析
### 六、风险提示
免责声明：本分析仅基于技术指标，不构成投资建议...
```

## 注意事项

- `web.py` 内置 DeepSeek API Key 回退（`FALLBACK_CONFIG`），Streamlit Cloud 无 secrets 时自动使用
- `main.py` 需要环境变量配置 LLM_API_KEY，否则直接退出
- `app.py` 的 config_page 编辑 `.env` 文件时保留非 LLM 变量
- `agent/__init__.py` 可能为空文件，仅用于 Python package 结构
- 历史记录由 `app.py` 保存到 `history/`，文件命名格式 `{code}_{timestamp}.md`
