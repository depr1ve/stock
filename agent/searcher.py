"""
网络情报搜索器：通过 Tavily API 搜索标的相关新闻、公告和市场情绪。
纯代码逻辑，不依赖 LLM。
"""

import logging
from typing import Optional

from agent.config.settings import WebSearchConfig
from agent.models.schemas import WebIntel, SearchItem

logger = logging.getLogger(__name__)


class WebSearcher:
    """Tavily 网页搜索，获取标的最新情报"""

    def __init__(self, config: WebSearchConfig):
        self.api_key = config.api_key
        self.max_results = config.max_results
        self.search_depth = config.search_depth
        self.include_domains = config.include_domains
        self._available = bool(self.api_key)

    @property
    def available(self) -> bool:
        return self._available

    async def search(self, stock_code: str, stock_name: str = "") -> WebIntel:
        """
        搜索标的相关的最新新闻和公告。

        Args:
            stock_code: 股票代码，如 'sh.600000'
            stock_name: 股票名称，如 '浦发银行'

        Returns:
            WebIntel 聚合结果
        """
        if not self._available:
            return WebIntel(
                stock_code=stock_code,
                stock_name=stock_name,
                error="Tavily API Key 未配置，跳过网页搜索",
            )

        pure_code = stock_code.split(".")[-1]
        query = self._build_query(pure_code, stock_name)

        try:
            results = await self._call_tavily(query)
            logger.info("网页搜索返回 %d 条结果: %s", len(results), query)
            return WebIntel(
                stock_code=stock_code,
                stock_name=stock_name,
                query=query,
                results=results,
            )
        except Exception as e:
            logger.error("Tavily 搜索失败: %s", e)
            return WebIntel(
                stock_code=stock_code,
                stock_name=stock_name,
                query=query,
                error=str(e),
            )

    def _build_query(self, pure_code: str, stock_name: str) -> str:
        """构造搜索查询词"""
        parts = []
        if stock_name:
            parts.append(f"{stock_name}")
        parts.append(f"股票{pure_code}")
        parts.append("最新消息 OR 公告 OR 新闻 OR 研报")
        return " ".join(parts)

    async def _call_tavily(self, query: str) -> list[SearchItem]:
        """调用 Tavily Search API"""
        from tavily import TavilyClient

        client = TavilyClient(api_key=self.api_key)
        response = client.search(
            query=query,
            search_depth=self.search_depth,
            max_results=self.max_results,
            include_domains=self.include_domains,
        )

        items = []
        for r in response.get("results", []):
            url = r.get("url", "")
            title = r.get("title", "")
            source_type, source_label = self._classify_source(url, title)
            items.append(SearchItem(
                title=title,
                url=url,
                content=r.get("content", "")[:500],
                score=r.get("score", 0.0),
                published_date=r.get("published_date", ""),
                source_type=source_type,
                source_label=source_label,
            ))
        return items

    @staticmethod
    def _classify_source(url: str, title: str) -> tuple:
        """根据域名和标题关键词分类消息来源"""
        from agent.models.schemas import SourceType

        # 公告/财报关键词（用于 cninfo.com.cn 细分）
        announcement_keywords = ["公告", "披露", "停牌", "复牌", "重组", "增持", "减持", "质押"]
        report_keywords = ["年度报告", "季度报告", "年报", "季报", "财报", "业绩", "营收", "净利润", "利润", "分红", "半年报", "三季报", "一季报"]

        if "cninfo.com.cn" in url:
            combined = title + url
            for kw in report_keywords:
                if kw in combined:
                    return (SourceType.FINANCIAL_REPORT.value, "公司财报")
            for kw in announcement_keywords:
                if kw in combined:
                    return (SourceType.EXCHANGE_ANNOUNCEMENT.value, "交易所公告")
            return (SourceType.EXCHANGE_ANNOUNCEMENT.value, "交易所公告")

        if any(d in url for d in ["eastmoney.com", "10jqka.com.cn", "cls.cn"]):
            return (SourceType.AUTHORITATIVE_MEDIA.value, "权威媒体")

        if "sina.com.cn" in url:
            return (SourceType.GENERAL_NEWS.value, "普通新闻")

        return (SourceType.GENERAL_NEWS.value, "普通新闻")

    @staticmethod
    def format_for_prompt(intel: WebIntel) -> str:
        """将网络情报格式化为 LLM prompt 可用的文本"""
        if intel.error and not intel.results:
            return f"（网络情报获取失败：{intel.error}）"

        if not intel.results:
            return "（未搜索到相关网络情报）"

        lines = [f"以下是通过网络搜索获取的关于 {intel.stock_name or intel.stock_code} 的最新情报：", ""]
        for i, item in enumerate(intel.results, 1):
            date_str = f" ({item.published_date})" if item.published_date else ""
            source_tag = f" [{item.source_label}]" if item.source_label else ""
            lines.append(f"**{i}. {item.title}**{date_str}{source_tag}")
            if item.content:
                lines.append(f"   {item.content[:300]}")
            lines.append(f"   来源: {item.url}")
            lines.append("")
        return "\n".join(lines)
