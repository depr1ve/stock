# agent/ 模块说明

```
agent/
├── orchestrator.py       # Pipeline 编排，对外唯一入口 run()
├── cli.py                # CLI 命令行入口 (python -m agent.cli)
├── analyzer.py           # LLM 调用，生成结构化分析报告
├── prompts.py            # System/User Prompt 模板
├── searcher.py           # Tavily 网络搜索 + 来源分类 (可选)
├── sentiment.py          # FinBERT 情绪分析，按来源权重加权 (可选)
├── config/settings.py    # 全局配置 (LLM/搜索/情绪/分析参数)
├── data/fetcher.py       # akshare 行情获取 (新浪→东方财富双源容灾)
├── indicators/calculator.py  # 技术指标计算 (numpy: MA/MACD/RSI/布林/ATR/量比)
├── models/schemas.py     # Pydantic 数据模型，全链路类型安全
├── report/generator.py   # Markdown 报告渲染
└── utils/http_utils.py   # 编码安全 HTTP 抓取 (apparent_encoding)
```
