# A 股智能分析 Agent

基于 akshare + LLM 的 A 股技术分析报告自动生成系统。线上：https://depr1ve-stock.streamlit.app

## 项目结构

```
Stock/
├── web.py                         # Streamlit 入口
├── requirements.txt
└── agent/                         # 核心包 (详见 statement.txt)
    ├── cli.py                     # CLI 入口: python -m agent.cli 600000
    ├── orchestrator.py            # Pipeline 编排
    ├── analyzer.py / prompts.py   # LLM 调用
    ├── searcher.py                # Tavily 搜索 (可选)
    ├── sentiment.py               # FinBERT 情绪 (可选)
    ├── config/settings.py
    ├── data/fetcher.py            # akshare 新浪→东方财富双源
    ├── indicators/calculator.py   # numpy 指标
    ├── models/schemas.py
    ├── report/generator.py
    └── utils/http_utils.py
```

**原则：确定性计算归代码，模糊判断归 LLM。**

## 数据流

```
StockRequest → DataFetcher → IndicatorCalculator → WebSearcher[可选] → SentimentAnalyzer[可选] → LLMAnalyzer → ReportGenerator
```

## 启动

```bash
streamlit run web.py --server.port 8501   # Web
python -m agent.cli 600000 -d 30          # CLI
```

## 环境变量 (.env)

```
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-chat
TAVILY_API_KEY=tvly-xxx    # 可选
```

OpenAI 兼容协议，支持 DeepSeek/Qwen/GPT/Claude。

## 重要约束

- **Python**: `E:/Anaconda/python.exe`，Windows 11，torch 2.6.0 + transformers 5.9.0
- transformers 5.x 用 `top_k=None`（非 `return_all_scores`）
- HTTP 抓取必须 `resp.encoding = resp.apparent_encoding`（GBK/UTF-8 自动检测）
- `analyzer.py` 有 `_sanitize()` 过滤 GBK 不支持的字符
- 数据不足14天时 RSI/MACD/布林/ATR 返回 N/A，LLM 自适应降级
- akshare 新浪源优先，东方财富可能被墙
- WebSearcher/SentimentAnalyzer 不可用时静默降级
- `web.py` 有 `FALLBACK_CONFIG` 兜底，Streamlit Cloud 无 secrets 也能跑
- `.env` 在 `.gitignore`，API Key 不上传
- Tavily 搜索聚焦 5 个财经源，来源权重：公告(0.40) > 财报(0.30) > 媒体(0.20) > 新闻(0.10)
- CLI 运行需 `PYTHONIOENCODING=utf-8` 避免 Windows GBK 乱码
