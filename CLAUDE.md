# A 股智能分析 Agent

基于 akshare + LLM 的 A 股技术分析报告自动生成系统。三种使用形态：

| 入口 | 启动方式 | 用途 |
|------|---------|------|
| `web.py` | `streamlit run web.py --server.port 8501` | Web 界面（K线图+AI报告） |
| `app.py` | `python app.py` | Rich 交互式 CLI（菜单导航） |
| `main.py` | `python main.py 600000 -d 30` | 命令行单次模式 |

线上公开版：https://depr1ve-stock.streamlit.app

## 架构

```
main.py / app.py / web.py (入口)
    └── agent/orchestrator.py       # Pipeline 编排器
        ├── models/schemas.py       # StockRequest → MarketData → IndicatorResult → AnalysisReport
        ├── data/fetcher.py         # akshare 双源容灾 (新浪 stock_zh_a_daily / 东方财富 stock_zh_a_hist)
        ├── indicators/calculator.py # MA/MACD/RSI/布林带/ATR/量比 (纯 numpy)
        ├── agent/analyzer.py       # LLM 调用 → 结构化分析报告
        │   └── agent/prompts.py    # System Prompt (投资顾问角色) + User Prompt (数据注入)
        └── report/generator.py     # Markdown 报告渲染
```

**设计原则：确定性计算归代码，模糊判断归 LLM。** 只有 `agent/analyzer.py` 调用大模型，其余全是代码逻辑。

## 关键文件路径

- 配置：`config/settings.py`（LLMConfig / AnalysisConfig）
- 环境变量：`.env`（本地上报）或 Streamlit Secrets（云部署）
- API Key 内置回退：`web.py` 的 `FALLBACK_CONFIG`
- 历史报告：`history/` 目录

## 数据流

```
用户输入 (600000, 30天)
  → StockRequest 校验 (自动补全 sh/sz/bj 前缀)
  → DataFetcher.fetch() (akshare → pandas → list[MarketRow])
  → IndicatorCalculator.compute() (numpy → IndicatorResult)
  → LLMAnalyzer.analyze() (Prompt注入 → LLM → AnalysisReport)
  → ReportGenerator.render() (Markdown)
```

## 测试

```bash
# 真实数据跑全流程（需要 Key）
python -c "
import asyncio; from dotenv import load_dotenv; load_dotenv()
from agent.orchestrator import StockAnalysisOrchestrator
report = asyncio.run(StockAnalysisOrchestrator().run('600000', 30))
print(report)
"
```

## 注意事项

- Python 解释器路径：`E:/Anaconda/python.exe`
- Windows 终端 GBK 编码不支持 emoji，`analyzer.py` 有 `_sanitize()` 过滤
- 7天数据时 RSI/MACD/布林/ATR 均为 N/A（窗口期不足），LLM 自适应降级
- akshare 东方财富源可能被墙，fetcher 优先走新浪源
