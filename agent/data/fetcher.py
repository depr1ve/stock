"""
akshare 行情数据获取层。
优先使用新浪源 (stock_zh_a_daily)，失败时回退到东方财富源。
"""

import asyncio
import logging
from datetime import date, timedelta

import pandas as pd

from agent.models.schemas import StockRequest, MarketData, MarketRow

logger = logging.getLogger(__name__)


class FetchError(Exception):
    """数据拉取异常"""
    pass


class DataFetcher:
    """akshare 行情数据获取器，双源容灾"""

    def __init__(self, retries: int = 3, retry_delay: float = 1.0):
        self.retries = retries
        self.retry_delay = retry_delay

    async def fetch(self, request: StockRequest) -> MarketData:
        """
        拉取 A 股历史日线数据，优先新浪源，回退东方财富源。
        """
        start = (date.today() - timedelta(days=request.days * 2)).strftime("%Y%m%d")
        end = date.today().strftime("%Y%m%d")

        for attempt in range(1, self.retries + 1):
            try:
                # 优先新浪源
                df = await asyncio.to_thread(
                    self._fetch_sina, request.pure_code, start, end, request.market
                )
                if df.empty:
                    logger.warning("新浪源返回空数据，尝试东方财富源...")
                    df = await asyncio.to_thread(
                        self._fetch_eastmoney, request.pure_code, start, end, request.market
                    )

                if df.empty:
                    raise FetchError(f"akshare 两个数据源均返回空数据: {request.raw_code}")

                rows = self._parse_dataframe(df)
                if len(rows) < request.days:
                    logger.warning(
                        "请求 %d 天，实际获取 %d 天数据", request.days, len(rows)
                    )

                stock_name = self._get_stock_name(request.raw_code)
                return MarketData(
                    stock_code=request.raw_code,
                    stock_name=stock_name,
                    rows=rows[-request.days:],
                )

            except FetchError:
                raise
            except Exception as e:
                logger.warning("第 %d 次拉取失败: %s", attempt, e)
                if attempt < self.retries:
                    await asyncio.sleep(self.retry_delay * attempt)
                else:
                    raise FetchError(
                        f"拉取 {request.raw_code} 失败，已重试 {self.retries} 次"
                    ) from e

        raise FetchError("unreachable")

    @staticmethod
    def _fetch_sina(code: str, start: str, end: str, market: str) -> pd.DataFrame:
        """新浪数据源 (stock_zh_a_daily)，返回标准列名"""
        import akshare as ak
        symbol = f"{market}{code}"
        df = ak.stock_zh_a_daily(symbol=symbol, start_date=start, end_date=end, adjust="qfq")
        if df is None or df.empty:
            return pd.DataFrame()
        # 列名: date, open, high, low, close, volume, amount
        return df

    @staticmethod
    def _fetch_eastmoney(code: str, start: str, end: str, market: str) -> pd.DataFrame:
        """东方财富数据源 (stock_zh_a_hist)，中文列名"""
        import akshare as ak
        symbol = f"{market}{code}"
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start, end_date=end, adjust="qfq")
        if df is None or df.empty:
            return pd.DataFrame()
        # 中文列名映射
        em_map = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "amount", "振幅": "amplitude_pct", "涨跌幅": "change_pct",
        }
        df = df.rename(columns=em_map)
        # 只保留标准列
        keep = [v for k, v in em_map.items() if v in df.columns]
        return df[keep]

    @staticmethod
    def _parse_dataframe(df: pd.DataFrame) -> list[MarketRow]:
        """列名统一 + 类型转换 + 自算振幅/涨跌幅"""
        df = df.copy()

        # 日期
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date

        # 数值列填充
        for col in ["open", "close", "high", "low"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in ["volume", "amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # 如果数据源未提供振幅/涨跌幅，自行计算
        if "amplitude_pct" not in df.columns:
            prev_close = df["close"].shift(1)
            df["amplitude_pct"] = (df["high"] - df["low"]) / prev_close * 100
        if "change_pct" not in df.columns:
            df["change_pct"] = df["close"].pct_change() * 100

        # 移除缺失 OHLC 的行
        df = df.dropna(subset=["open", "close", "high", "low"])

        rows: list[MarketRow] = []
        for _, s in df.iterrows():
            try:
                amp = float(s.get("amplitude_pct", 0))
                chg = float(s.get("change_pct", 0))
                if pd.isna(amp):
                    amp = 0.0
                if pd.isna(chg):
                    chg = 0.0
                rows.append(MarketRow(
                    date=s["date"],
                    open=float(s["open"]),
                    close=float(s["close"]),
                    high=float(s["high"]),
                    low=float(s["low"]),
                    volume=int(s.get("volume", 0) or 0),
                    amount=float(s.get("amount", 0) or 0),
                    amplitude_pct=round(amp, 2),
                    change_pct=round(chg, 2),
                ))
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("跳过异常行 %s: %s", s.get("date"), e)
                continue

        return rows

    @staticmethod
    def _get_stock_name(raw_code: str) -> str:
        """尝试获取股票名称"""
        try:
            import akshare as ak
            info = ak.stock_individual_info_em(symbol=raw_code.split(".")[1])
            if info is not None and not info.empty:
                name_row = info[info["item"] == "股票简称"]
                if not name_row.empty:
                    return str(name_row["value"].values[0])
        except Exception:
            pass
        return ""
