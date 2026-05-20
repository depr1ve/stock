# A 股智能分析 Agent

基于 akshare + LLM 的 A 股技术分析报告自动生成系统。

## 架构

```
用户输入 (A股代码 + 天数)
  │
  ▼
┌─────────────────┐
│  InputGate       │  Pydantic 校验 + 市场前缀自动补全
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  DataFetcher     │  akshare 双源容灾 (新浪 → 东方财富) + 重试
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  IndicatorCalc   │  纯 numpy/pandas 确定性计算
│  · 均线 MA       │  无 LLM 依赖
│  · MACD          │
│  · RSI           │
│  · 布林带        │
│  · ATR           │
│  · 量比          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  LLMAnalyzer    │  结构化 prompt 注入 → 多维度分析
│  ① 趋势判断      │  OpenAI 协议 (兼容 GPT/DeepSeek/Qwen/Claude)
│  ② 波动率分析    │
│  ③ 量价配合      │
│  ④ 关键价位      │
│  ⑤ 风险提示      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ReportGenerator │  Markdown 报告输出
└─────────────────┘
```

**核心思想：确定性计算归代码，模糊判断归 LLM。**

## 项目结构

```
Stock/
├── main.py                       # CLI 入口
├── requirements.txt              # 依赖清单
├── .env.example                  # 环境变量模板
├── config/
│   └── settings.py               # LLM + 分析参数配置
├── models/
│   └── schemas.py                # Pydantic 数据模型
├── data/
│   └── fetcher.py                # akshare 行情拉取
├── indicators/
│   └── calculator.py             # 技术指标计算
├── agent/
│   ├── prompts.py                # Prompt 模板
│   ├── analyzer.py               # LLM 分析器
│   └── orchestrator.py           # Pipeline 编排器
└── report/
    └── generator.py              # 报告渲染
```

## 快速开始

```bash
# 1. 配置
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行
python main.py 600000              # 浦发银行，默认60天
python main.py 000001 -d 30        # 平安银行，30天
python main.py 300750 -o a.md      # 宁德时代，输出到文件
```

## 支持的股票代码格式

| 输入 | 自动识别 |
|------|---------|
| `600000` | sh.600000 (上交所) |
| `000001` | sz.000001 (深交所主板) |
| `300750` | sz.300750 (创业板) |
| `sh.688111` | sh.688111 (科创板，原样保留) |
| `bj.430047` | bj.430047 (北交所) |

## 技术指标

| 指标 | 说明 |
|------|------|
| MA5/10/20/60 | 简单移动均线，判断排列状态 |
| MACD | DIF/DEA/柱，识别金叉死叉 |
| RSI(14) | 超买超卖判断 |
| 布林带(20,2) | 上下轨/带宽，价格相对位置 |
| ATR(14) | 平均真实波幅，衡量波动 |
| 量比(5日) | 当日量与5日均量比值 |

## LLM 分析维度

1. **趋势判断** — 结合均线排列、MACD、区间涨跌幅，给出偏多/偏空/震荡 + 置信度
2. **波动率分析** — ATR、布林带宽、振幅数据，判断波动水平和收敛/发散趋势
3. **量价配合** — 涨跌天数分布、放量/缩量与价格方向的配合关系
4. **关键价位** — 均线、布林轨、近期高低点构成的支撑/压力位
5. **风险提示** — 2-3 条基于数据的短期风险

## 异地使用 / 远程部署

### 方案一：Docker 部署到云服务器（推荐）

适用于阿里云/腾讯云/VPS，一次部署永久可用：

```bash
# 上传项目到服务器后
docker compose up -d
# 访问 http://你的服务器IP:8501
```

### 方案二：ngrok 内网穿透（最快）

本地电脑变公网服务，适合临时分享/演示：

```bash
# 1. 下载 ngrok: https://ngrok.com/download
# 2. 注册获取 authtoken: https://dashboard.ngrok.com
ngrok config add-authtoken 你的token
# 3. 启动隧道
ngrok http 8501
# 4. 会生成一个固定公网URL，如 https://xxx.ngrok-free.app
```

### 方案三：路由器端口映射

在路由器设置中将 8501 端口映射到本机，通过公网 IP 直接访问。

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_BASE_URL` | API 地址 | `https://api.openai.com/v1` |
| `LLM_API_KEY` | API 密钥 | (必填) |
| `LLM_MODEL` | 模型名称 | `gpt-4o` |

## 依赖

- **akshare** — A 股免费行情数据
- **pandas / numpy** — 数据处理和指标计算
- **pydantic** — 数据校验和模型定义
- **openai** — LLM 调用 (兼容所有 OpenAI 协议接口)
- **python-dotenv** — 环境变量加载
