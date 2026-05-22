"""
Pydantic 数据模型：请求/行情/指标/报告。
所有模块之间的数据交换都通过这里定义的结构体，保证类型安全。
"""

from datetime import date
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator
import re


class SourceType(str, Enum):
    """消息来源类型，按权威性从高到低排列"""
    EXCHANGE_ANNOUNCEMENT = "exchange_announcement"    # 交易所公告
    FINANCIAL_REPORT = "financial_report"              # 公司财报
    AUTHORITATIVE_MEDIA = "authoritative_media"        # 权威媒体
    GENERAL_NEWS = "general_news"                      # 普通新闻


# ── 输入 ──────────────────────────────────────────────

class StockRequest(BaseModel):
    """用户输入：股票代码 + 统计天数"""
    raw_code: str = Field(..., description="原始输入，如 'sh.600000' 或 '600000'")
    days: int = Field(60, ge=5, le=365, description="统计天数，5~365")

    @model_validator(mode="after")
    def normalize_code(self) -> "StockRequest":
        code = self.raw_code.strip().lower()
        # 已经是 sh.xxx / sz.xxx / bj.xxx 格式
        if re.match(r"^(sh|sz|bj)\.\d{6}$", code):
            self.raw_code = code
            return self
        # 纯 6 位数字，自动推断前缀
        if re.match(r"^\d{6}$", code):
            if code.startswith("6") or code.startswith("9"):
                self.raw_code = f"sh.{code}"
            elif code.startswith("0") or code.startswith("3"):
                self.raw_code = f"sz.{code}"
            elif code.startswith("4") or code.startswith("8"):
                self.raw_code = f"bj.{code}"
            else:
                raise ValueError(f"无法推断代码前缀: {code}")
            return self
        raise ValueError(f"无效的股票代码格式: {self.raw_code}")

    @property
    def pure_code(self) -> str:
        """返回纯数字代码，如 '600000'"""
        return self.raw_code.split(".")[1]

    @property
    def market(self) -> str:
        """返回市场标识: sh / sz / bj"""
        return self.raw_code.split(".")[0]


# ── 行情数据 ──────────────────────────────────────────

class MarketRow(BaseModel):
    """单日行情"""
    date: date
    open: float
    close: float
    high: float
    low: float
    volume: int = 0          # 成交量（手）
    amount: float = 0.0       # 成交额（元）
    amplitude_pct: float = 0  # 振幅 %
    change_pct: float = 0     # 涨跌幅 %

    class Config:
        frozen = True


class MarketData(BaseModel):
    """完整行情数据"""
    stock_code: str
    stock_name: str = ""
    rows: list[MarketRow] = []

    @property
    def df(self):
        """转为 pandas DataFrame 供指标计算使用"""
        import pandas as pd
        return pd.DataFrame([r.model_dump() for r in self.rows])

    @property
    def latest(self) -> Optional[MarketRow]:
        return self.rows[-1] if self.rows else None

    @property
    def count(self) -> int:
        return len(self.rows)


# ── 指标摘要（序列化为 JSON 注入 LLM prompt）───────────

class IndicatorSnapshot(BaseModel):
    """最新一日的指标快照"""
    date: date
    close: float
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    rsi: Optional[float] = None
    macd_dif: Optional[float] = None
    macd_dea: Optional[float] = None
    macd_hist: Optional[float] = None
    boll_upper: Optional[float] = None
    boll_mid: Optional[float] = None
    boll_lower: Optional[float] = None
    boll_width: Optional[float] = None   # 带宽 = (upper-lower)/mid
    atr: Optional[float] = None
    volume_ratio: Optional[float] = None  # 量比（与5日均量比）


class PeriodStats(BaseModel):
    """期间统计"""
    start_date: date
    end_date: date
    total_change_pct: float      # 区间涨跌幅
    max_amplitude_pct: float     # 最大单日振幅
    avg_amplitude_pct: float     # 平均单日振幅
    up_days: int                 # 上涨天数
    down_days: int               # 下跌天数
    max_up_pct: float            # 最大单日涨幅
    max_down_pct: float          # 最大单日跌幅
    avg_volume: float            # 平均成交量


class IndicatorResult(BaseModel):
    """完整指标计算结果"""
    stock_code: str
    stock_name: str
    period_stats: PeriodStats
    latest_snapshot: IndicatorSnapshot
    ma_arrangement: str = ""     # "多头排列" / "空头排列" / "交叉震荡"
    ma_cross: str = ""           # 最近一次金叉/死叉描述
    rsi_zone: str = ""           # "超买区" / "超卖区" / "中性区"
    boll_position: str = ""      # 价格在布林带中的位置描述


# ── 网络情报 ──────────────────────────────────────────

class SearchItem(BaseModel):
    """单条搜索结果"""
    title: str
    url: str
    content: str = ""
    score: float = 0.0
    published_date: str = ""
    source_type: Optional[str] = None   # SourceType 枚举值
    source_label: Optional[str] = None  # 中文标签，如"交易所公告"


class WebIntel(BaseModel):
    """聚合网络情报"""
    stock_code: str
    stock_name: str
    query: str = ""
    results: list[SearchItem] = []
    summary: str = ""  # LLM 对搜索结果的摘要
    sentiment: str = ""  # positive / negative / neutral
    error: str = ""
    sentiment_analysis: Optional["AggregatedSentiment"] = None  # FinBERT 情绪分析结果


# ── FinBERT 情绪分析 ──────────────────────────────────

class SentimentScore(BaseModel):
    """FinBERT 情绪概率分布"""
    positive: float = 0.0
    neutral: float = 0.0
    negative: float = 0.0


class SourceSentiment(BaseModel):
    """单条消息的 FinBERT 情绪分析结果"""
    title: str
    url: str
    source_type: str = ""          # SourceType 枚举值
    source_label: str = ""         # 中文标签
    weight: float = 0.0            # 来源权重
    sentiment: SentimentScore = Field(default_factory=SentimentScore)


class AggregatedSentiment(BaseModel):
    """加权汇总后的情绪分析结果"""
    items: list[SourceSentiment] = []
    overall: SentimentScore = Field(default_factory=SentimentScore)
    available: bool = False        # FinBERT 是否可用
    error: Optional[str] = None


# ── LLM 分析结果 ──────────────────────────────────────

class AnalysisReport(BaseModel):
    """LLM 输出的分析报告"""
    stock_code: str
    stock_name: str
    days: int
    trend: str                   # 趋势判断
    volatility: str              # 波动分析
    volume_price: str            # 量价分析
    key_levels: str              # 关键价位
    risk: str                    # 风险提示
    news_sentiment: str = ""     # 消息面与情绪分析
    raw_text: str = ""           # LLM 原始输出（兜底用）
