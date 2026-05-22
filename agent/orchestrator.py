"""
Pipeline 编排器：串联 输入校验 → 数据拉取 → 指标计算 → LLM 分析 → 报告输出。
这是整个系统的核心入口，对外暴露唯一的 run() 方法。
"""

import logging

from config.settings import Config, default_config
from models.schemas import StockRequest, AnalysisReport
from data.fetcher import DataFetcher, FetchError
from indicators.calculator import IndicatorCalculator
from agent.analyzer import LLMAnalyzer
from agent.searcher import WebSearcher
from agent.sentiment import SentimentAnalyzer
from report.generator import ReportGenerator

logger = logging.getLogger(__name__)


class StockAnalysisOrchestrator:
    """股票分析流水线编排器"""

    def __init__(self, config: Config = None):
        cfg = config or default_config
        self.fetcher = DataFetcher()
        self.calculator = IndicatorCalculator()
        self.searcher = WebSearcher(cfg.web_search)
        self.sentiment_analyzer = SentimentAnalyzer(cfg.sentiment)
        self.analyzer = LLMAnalyzer(cfg.llm)
        self.reporter = ReportGenerator()

    async def run(self, stock_code: str, days: int = 60) -> str:
        """
        执行完整分析流水线，返回 Markdown 格式分析报告。

        Args:
            stock_code: A 股代码，如 '600000' 或 'sh.600000'
            days: 统计天数，5~365

        Returns:
            Markdown 格式的完整分析报告
        """
        # 1. 输入校验
        request = StockRequest(raw_code=stock_code, days=days)
        logger.info("分析目标: %s, 统计 %d 天", request.raw_code, request.days)

        # 2. 拉取行情数据
        logger.info("正在拉取行情数据...")
        market_data = await self.fetcher.fetch(request)
        logger.info("获取 %d 条行情记录", market_data.count)

        # 3. 计算技术指标
        logger.info("正在计算技术指标...")
        indicators = self.calculator.compute(market_data)

        # 4. 网络情报搜索
        web_intel = None
        if self.searcher.available:
            logger.info("正在搜索网络情报...")
            web_intel = await self.searcher.search(
                market_data.stock_code, market_data.stock_name
            )
        else:
            logger.info("Tavily API Key 未配置，跳过网络搜索")

        # 4.5 FinBERT 情绪分析
        sentiment = None
        if web_intel and web_intel.results and self.sentiment_analyzer.available:
            logger.info("正在进行 FinBERT 情绪分析...")
            try:
                sentiment = self.sentiment_analyzer.analyze(web_intel)
                if sentiment:
                    web_intel.sentiment_analysis = sentiment
            except Exception as e:
                logger.warning("FinBERT 情绪分析失败: %s", e)
        else:
            logger.info("跳过 FinBERT 情绪分析（搜索无结果或模型不可用）")

        # 5. LLM 分析
        logger.info("正在调用 LLM 进行分析...")
        analysis = await self.analyzer.analyze(market_data, indicators, web_intel, sentiment)

        # 6. 生成报告
        logger.info("正在生成报告...")
        report = self.reporter.render(indicators, analysis, sentiment)

        return report

    def run_sync(self, stock_code: str, days: int = 60) -> str:
        """同步包装器，方便在非 async 环境中调用"""
        import asyncio
        return asyncio.run(self.run(stock_code, days))
