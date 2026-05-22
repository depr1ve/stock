"""
配置管理：LLM 连接、模型参数、默认值。
通过环境变量或 .env 文件加载，避免硬编码密钥。
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    """LLM 连接配置，兼容 OpenAI 协议（DeepSeek / Qwen / GPT / Claude 均可）"""
    base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"))
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o"))
    temperature: float = 0.3
    max_tokens: int = 2048
    timeout: int = 60


@dataclass
class WebSearchConfig:
    """Tavily 网页搜索配置"""
    api_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))
    max_results: int = 5
    search_depth: str = "advanced"  # basic / advanced
    include_domains: list = field(default_factory=lambda: ["eastmoney.com", "sina.com.cn", "10jqka.com.cn", "cninfo.com.cn", "cls.cn"])


@dataclass
class SentimentConfig:
    """FinBERT 情绪分析配置"""
    model_name: str = "ProsusAI/finbert"
    enabled: bool = True
    device: str = "cpu"  # cpu / cuda
    source_weights: dict = field(default_factory=lambda: {
        "exchange_announcement": 0.40,
        "financial_report": 0.30,
        "authoritative_media": 0.20,
        "general_news": 0.10,
    })
    fetch_full_content: bool = True   # Tavily snippet 太短时自动拉取完整页面
    fetch_timeout: int = 10           # 拉取页面超时秒数
    min_content_length: int = 100     # snippet 低于此长度时尝试拉取正文


@dataclass
class AnalysisConfig:
    """分析参数默认值"""
    default_days: int = 60
    min_days: int = 5
    max_days: int = 365
    ma_periods: tuple = (5, 10, 20, 60)
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    boll_period: int = 20
    boll_std: float = 2.0
    atr_period: int = 14


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)


default_config = Config()
