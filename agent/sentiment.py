"""
FinBERT 情绪分析器：对网络情报进行量化情绪分析，按来源权威性加权汇总。
纯代码逻辑 + FinBERT 模型推理，可选组件，不可用时静默降级。
"""

import logging
from typing import Optional

from config.settings import SentimentConfig
from models.schemas import (
    WebIntel, SearchItem, AggregatedSentiment, SourceSentiment, SentimentScore,
)

logger = logging.getLogger(__name__)

# 来源标签映射
SOURCE_LABEL_MAP = {
    "exchange_announcement": "交易所公告",
    "financial_report": "公司财报",
    "authoritative_media": "权威媒体",
    "general_news": "普通新闻",
}


class SentimentAnalyzer:
    """FinBERT 情绪分析器 — 懒加载模型，可选降级"""

    def __init__(self, config: SentimentConfig):
        self.model_name = config.model_name
        self.enabled = config.enabled
        self.device = config.device
        self.source_weights = config.source_weights
        self.fetch_full_content = config.fetch_full_content
        self.fetch_timeout = config.fetch_timeout
        self.min_content_length = config.min_content_length
        self._model = None
        self._available = None  # None = 尚未检测, True/False = 已检测

    @property
    def available(self) -> bool:
        if self._available is None:
            if not self.enabled:
                self._available = False
                return False
            self._load_model()
        return self._available

    def _load_model(self):
        """懒加载 FinBERT pipeline，失败则标记不可用"""
        try:
            from transformers import pipeline
            logger.info("正在加载 FinBERT 模型: %s ...", self.model_name)
            self._model = pipeline(
                "text-classification",
                model=self.model_name,
                top_k=None,
                device=self.device if self.device != "cpu" else -1,
            )
            self._available = True
            logger.info("FinBERT 模型加载完成")
        except ImportError:
            logger.warning("transformers 未安装，FinBERT 情绪分析不可用。安装: pip install transformers torch")
            self._available = False
        except Exception as e:
            logger.warning("FinBERT 模型加载失败: %s", e)
            self._available = False

    def _analyze_text(self, text: str, url: str = "") -> SentimentScore:
        """对单段文本进行 FinBERT 情绪分析，snippet 太短时可拉取完整正文"""
        if not text or not text.strip():
            return SentimentScore(positive=0.34, neutral=0.33, negative=0.33)

        clean = text.strip()
        # 如果 snippet 太短且有 URL，尝试拉取完整页面正文
        if (
            self.fetch_full_content
            and url
            and len(clean) < self.min_content_length
        ):
            try:
                from utils.http_utils import fetch_text, summarize_text
                full = fetch_text(url, timeout=self.fetch_timeout)
                if full and len(full) > len(clean):
                    summary = summarize_text(full)
                    logger.debug("拉取正文 %d 字符，摘要 %d 字符", len(full), len(summary))
                    clean = summary
            except Exception as e:
                logger.debug("拉取完整正文失败 %s: %s", url, e)

        try:
            # FinBERT 限制 512 token，取前 400 字符
            clean = clean[:400]
            result = self._model(clean)[0]  # list of {label, score} dicts
            scores = {r["label"].lower(): r["score"] for r in result}
            return SentimentScore(
                positive=scores.get("positive", 0.0),
                neutral=scores.get("neutral", 0.0),
                negative=scores.get("negative", 0.0),
            )
        except Exception as e:
            logger.warning("FinBERT 推理失败: %s", e)
            return SentimentScore(positive=0.34, neutral=0.33, negative=0.33)

    def analyze(self, web_intel: WebIntel) -> Optional[AggregatedSentiment]:
        """
        对 WebIntel 中的所有搜索结果进行情绪分析，按来源加权汇总。

        返回 AggregatedSentiment，如果 FinBERT 不可用或结果为空则返回 None。
        """
        if not self.available:
            return AggregatedSentiment(available=False, error="FinBERT 不可用")

        if not web_intel or not web_intel.results:
            return AggregatedSentiment(available=True, error="无搜索内容")

        items: list[SourceSentiment] = []
        total_weight = 0.0
        weighted_positive = 0.0
        weighted_neutral = 0.0
        weighted_negative = 0.0

        for item in web_intel.results:
            source_type = item.source_type or "general_news"
            source_label = item.source_label or SOURCE_LABEL_MAP.get(source_type, "普通新闻")
            weight = self.source_weights.get(source_type, 0.10)

            sentiment = self._analyze_text(item.content or item.title, item.url)

            items.append(SourceSentiment(
                title=item.title,
                url=item.url,
                source_type=source_type,
                source_label=source_label,
                weight=weight,
                sentiment=sentiment,
            ))

            total_weight += weight
            weighted_positive += sentiment.positive * weight
            weighted_neutral += sentiment.neutral * weight
            weighted_negative += sentiment.negative * weight

        if total_weight == 0:
            return AggregatedSentiment(available=True, items=items, error="权重总和为 0")

        overall = SentimentScore(
            positive=round(weighted_positive / total_weight, 4),
            neutral=round(weighted_neutral / total_weight, 4),
            negative=round(weighted_negative / total_weight, 4),
        )

        logger.info(
            "FinBERT 情绪汇总 (来自 %d 条消息): 正面=%.1f%% 中性=%.1f%% 负面=%.1f%%",
            len(items),
            overall.positive * 100,
            overall.neutral * 100,
            overall.negative * 100,
        )

        return AggregatedSentiment(items=items, overall=overall, available=True)

    @staticmethod
    def format_for_prompt(agg: Optional[AggregatedSentiment]) -> str:
        """将 FinBERT 情绪分析结果格式化为 LLM prompt 可用的文本"""
        if not agg or not agg.available or not agg.items:
            return "（FinBERT 情绪分析不可用）"

        lines = [
            "## FinBERT 量化情绪分析（机器学习模型输出，仅供参考）",
            "",
            f"**整体情绪**: 正面 {agg.overall.positive:.1%} | 中性 {agg.overall.neutral:.1%} | 负面 {agg.overall.negative:.1%}",
            "",
            "### 各来源明细",
            "",
        ]

        # 按权重从高到低排列
        sorted_items = sorted(agg.items, key=lambda x: x.weight, reverse=True)
        for i, item in enumerate(sorted_items, 1):
            s = item.sentiment
            lines.append(
                f"**{i}. [{item.source_label}]** {item.title} "
                f"(正面:{s.positive:.1%} 中性:{s.neutral:.1%} 负面:{s.negative:.1%})"
            )

        return "\n".join(lines)
