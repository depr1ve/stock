"""
报告生成器：将 LLM 分析结果 + 指标数据整合为最终 Markdown 报告。
"""

from typing import Optional
from models.schemas import IndicatorResult, AnalysisReport, AggregatedSentiment


class ReportGenerator:
    """Markdown 报告渲染器"""

    def render(
        self, indicators: IndicatorResult, analysis: AnalysisReport,
        sentiment: Optional[AggregatedSentiment] = None,
    ) -> str:
        s = indicators.latest_snapshot
        ps = indicators.period_stats

        lines = [
            f"# {indicators.stock_name or indicators.stock_code} 技术分析报告",
            "",
            f"**股票代码**: `{indicators.stock_code}`  "
            f"**统计周期**: {ps.start_date} ~ {ps.end_date} （{analysis.days} 个交易日）",
            "",
            "---",
            "",
            "## 核心指标速览",
            "",
            f"| 项目 | 数值 |",
            f"|------|------|",
            f"| 最新收盘价 | {s.close:.2f} 元 |",
            f"| 区间涨跌幅 | {ps.total_change_pct:+.2f}% |",
            f"| 区间振幅(均值) | {ps.avg_amplitude_pct:.2f}% |",
            f"| 上涨/下跌天数 | {ps.up_days} / {ps.down_days} |",
            f"| RSI(14) | {self._na(s.rsi, 1)} |",
            f"| ATR(14) | {self._na(s.atr)} |",
            f"| 均线排列 | {indicators.ma_arrangement} |",
            f"| MACD 信号 | {indicators.ma_cross} |",
            f"| 布林带位置 | {indicators.boll_position} |",
            "",
            "---",
            "",
        ]

        # FinBERT 情绪量化分析
        if sentiment and sentiment.available and sentiment.items:
            lines.extend(self._render_sentiment(sentiment))

        # LLM 分析正文
        if analysis.trend:
            lines.extend([
                "## 趋势判断",
                "",
                analysis.trend,
                "",
            ])
        if analysis.volatility:
            lines.extend([
                "## 波动率分析",
                "",
                analysis.volatility,
                "",
            ])
        if analysis.volume_price:
            lines.extend([
                "## 量价配合分析",
                "",
                analysis.volume_price,
                "",
            ])
        if analysis.key_levels:
            lines.extend([
                "## 关键价位",
                "",
                analysis.key_levels,
                "",
            ])
        if analysis.news_sentiment:
            lines.extend([
                "## 消息面与情绪分析",
                "",
                analysis.news_sentiment,
                "",
            ])
        if analysis.risk:
            lines.extend([
                "## 风险提示",
                "",
                analysis.risk,
                "",
            ])

        # 若 LLM 没有结构化输出，兜底输出 raw
        if not any([analysis.trend, analysis.volatility, analysis.volume_price, analysis.news_sentiment]):
            lines.extend([
                "---",
                "",
                analysis.raw_text or "（分析结果为空，请检查 LLM 配置）",
                "",
            ])

        lines.extend([
            "---",
            "",
            "*报告由 AI 自动生成 | " + str(ps.end_date) + "*",
            "",
        ])

        return "\n".join(lines)

    @staticmethod
    def _render_sentiment(sentiment: AggregatedSentiment) -> list[str]:
        """渲染 FinBERT 情绪分析 section"""
        lines = [
            "## 消息面情绪量化分析 (FinBERT)",
            "",
            "| 情绪类别 | 概率 |",
            "|----------|------|",
            f"| :green[正面] | {sentiment.overall.positive:.1%} |",
            f"| :gray[中性] | {sentiment.overall.neutral:.1%} |",
            f"| :red[负面] | {sentiment.overall.negative:.1%} |",
            "",
            "### 各来源明细",
            "",
            "| 来源类型 | 标题 | 正面 | 中性 | 负面 |",
            "|----------|------|------|------|------|",
        ]
        for item in sorted(sentiment.items, key=lambda x: x.weight, reverse=True):
            title_short = item.title[:40] + "..." if len(item.title) > 40 else item.title
            s = item.sentiment
            lines.append(
                f"| {item.source_label} | {title_short} | "
                f"{s.positive:.1%} | {s.neutral:.1%} | {s.negative:.1%} |"
            )
        lines.extend(["", "---", ""])
        return lines

    @staticmethod
    def _na(value, precision: int = 2) -> str:
        if value is None:
            return "N/A"
        try:
            if isinstance(value, float):
                import math
                if math.isnan(value):
                    return "N/A"
        except Exception:
            pass
        return f"{value:.{precision}f}"
