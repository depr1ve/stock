# A 股智能分析 Agent

基于 akshare + LLM 的 A 股技术分析报告自动生成系统。

| 入口 | 启动方式 | 用途 |
|------|---------|------|
| `web.py` | `streamlit run web.py --server.port 8501` | Web 界面 |
| `main.py` | `python main.py 600000 -d 30` | 命令行单次 |

线上：https://depr1ve-stock.streamlit.app

## 结构

```
root/
├── main.py / web.py                   # 两个入口
└── agent/                             # 核心包
    ├── orchestrator.py                # Pipeline 编排
    ├── analyzer.py / prompts.py       # LLM 调用 + Prompt
    ├── searcher.py                    # Tavily 搜索 (可选)
    ├── sentiment.py                   # FinBERT 情绪 (可选)
    ├── config/settings.py             # 所有配置
    ├── data/fetcher.py                # akshare 数据获取
    ├── indicators/calculator.py       # 技术指标 (numpy)
    ├── models/schemas.py              # 数据模型
    ├── report/generator.py            # Markdown 报告
    └── utils/http_utils.py            # HTTP 安全抓取
```

**原则：确定性计算归代码，模糊判断归 LLM。**

## 环境变量

```
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-chat
TAVILY_API_KEY=tvly-xxx    # 可选
```

使用 OpenAI 兼容协议，支持 DeepSeek/Qwen/GPT/Claude。

## 数据流

```
StockRequest (自动补全 sh/sz/bj 前缀)
  → DataFetcher (新浪优先，东方财富fallback)
  → IndicatorCalculator (numpy)
  → WebSearcher (Tavily, 域名+关键词分类来源权重) [可选]
  → SentimentAnalyzer (FinBERT, 按来源权重加权汇总) [可选]
  → LLMAnalyzer (Prompt注入 + 网络情报 + 情绪分数)
  → ReportGenerator (Markdown)
```

## 来源分类权重

交易所公告(0.40) > 公司财报(0.30) > 权威媒体(0.20) > 普通新闻(0.10)。cninfo.com.cn 按标题关键词细分公告/财报。

## 重要约束

- Python：`E:/Anaconda/python.exe`，Windows 11，torch 2.6.0 + transformers 5.9.0
- transformers 5.x 用 `top_k=None`（非 `return_all_scores`）
- HTTP 抓取必须走 `resp.encoding = resp.apparent_encoding`（自动检测 GBK/UTF-8）
- Windows 终端 GBK 不支持 emoji，`analyzer.py` 有 `_sanitize()`
- 不足14天数据时 RSI/MACD/布林/ATR 为 N/A，LLM 自适应降级
- akshare 优先新浪源（东方财富可能被墙）
- WebSearcher/SentimentAnalyzer 不可用时静默降级
- `web.py` 有 `FALLBACK_CONFIG` 兜底，Streamlit Cloud 无 secrets 也能跑
