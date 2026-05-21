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
        ├── agent/searcher.py          # Tavily 网页搜索（新闻/公告/研报）← 可选，未配 Key 静默跳过
        ├── agent/analyzer.py          # LLM 调用 → 结构化分析报告
        │   └── agent/prompts.py       # System Prompt (投资顾问角色) + User Prompt (数据+情报注入)
        └── report/generator.py        # Markdown 报告渲染
```

**设计原则：确定性计算归代码，模糊判断归 LLM。** 只有 `agent/analyzer.py` 调用大模型，其余全是代码逻辑。

## 关键文件路径

- 配置：`config/settings.py`（LLMConfig / WebSearchConfig / AnalysisConfig）
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
  → LLMAnalyzer.analyze() (Prompt注入 + 网络情报 → LLM → AnalysisReport)
  → ReportGenerator.render() (Markdown)
```

## 分析维度

| # | 维度 | 数据来源 |
|---|------|---------|
| 1 | 趋势判断 | 均线排列 + MACD + 涨跌幅 |
| 2 | 波动率分析 | ATR + 布林带宽 + 振幅 |
| 3 | 量价配合 | 涨跌天数 + 量能变化 |
| 4 | 关键价位 | 均线 + 布林轨 + 高低点 |
| 5 | 消息面分析 | Tavily 网络情报 |
| 6 | 风险提示 | 综合以上 |

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

## 重要约束

- Python 解释器路径：`E:/Anaconda/python.exe`
- Windows 终端 GBK 编码不支持 emoji，`analyzer.py` 有 `_sanitize()` 过滤
- 7天数据时 RSI/MACD/布林/ATR 均为 N/A（窗口期不足），LLM 自适应降级
- akshare 东方财富源可能被墙，fetcher 优先走新浪源
- `_extract_section()` 支持精确匹配 + 模糊匹配，能解析带编号的标题（如 `### 五、消息面与情绪分析`）
- WebSearcher 为可选组件，Tavily API 不可用时静默降级，不影响核心流程
- `.env` 已加入 `.gitignore`，API Key 不会被提交

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
