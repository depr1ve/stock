"""
技术指标计算器。
纯 pandas/numpy 实现，全部为确定性计算，不依赖 LLM。
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from config.settings import default_config
from models.schemas import (
    IndicatorResult,
    IndicatorSnapshot,
    PeriodStats,
    MarketData,
    MarketRow,
)

logger = logging.getLogger(__name__)

cfg = default_config.analysis


class IndicatorCalculator:
    """技术指标计算器"""

    def compute(self, data: MarketData) -> IndicatorResult:
        """从行情数据计算全部指标，返回结构化结果"""
        df = data.df
        if df.empty:
            raise ValueError("行情数据为空，无法计算指标")

        close: np.ndarray = df["close"].values
        high: np.ndarray = df["high"].values
        low: np.ndarray = df["low"].values
        volume: np.ndarray = df["volume"].values
        dates = df["date"].values

        n = len(close)

        # ── 均线 ──────────────────────────────────────
        mas = {}
        for p in cfg.ma_periods:
            mas[p] = self._sma(close, p)

        # ── MACD ──────────────────────────────────────
        dif, dea, hist = self._macd(close, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)

        # ── RSI ───────────────────────────────────────
        rsi = self._rsi(close, cfg.rsi_period)

        # ── 布林带 ────────────────────────────────────
        boll_upper, boll_mid, boll_lower, boll_width = self._bollinger(
            close, cfg.boll_period, cfg.boll_std
        )

        # ── ATR ───────────────────────────────────────
        atr = self._atr(high, low, close, cfg.atr_period)

        # ── 量比（与5日均量比）─────────────────────────
        vol_ma5 = self._sma(volume.astype(float), 5)
        vol_ratio = np.full(n, np.nan)
        vol_ratio[4:] = volume[4:] / np.maximum(vol_ma5[4:], 1)

        # ── 期间统计 ──────────────────────────────────
        period_stats = self._calc_period_stats(dates, close, high, low, volume, data.rows)

        # ── 最新快照 ──────────────────────────────────
        snapshot = IndicatorSnapshot(
            date=dates[-1],
            close=float(close[-1]),
            ma5=self._last(mas[5]),
            ma10=self._last(mas[10]),
            ma20=self._last(mas[20]),
            ma60=self._last(mas[60]),
            rsi=self._last(rsi),
            macd_dif=self._last(dif),
            macd_dea=self._last(dea),
            macd_hist=self._last(hist),
            boll_upper=self._last(boll_upper),
            boll_mid=self._last(boll_mid),
            boll_lower=self._last(boll_lower),
            boll_width=self._last(boll_width),
            atr=self._last(atr),
            volume_ratio=self._last(vol_ratio),
        )

        # ── 定性描述 ──────────────────────────────────
        ma_arr = self._describe_ma_arrangement(mas, close, n)
        ma_cross = self._describe_recent_cross(dif, dea, dates)
        rsi_zone = self._describe_rsi_zone(snapshot.rsi)
        boll_pos = self._describe_boll_position(close[-1], boll_upper[-1], boll_mid[-1], boll_lower[-1])

        return IndicatorResult(
            stock_code=data.stock_code,
            stock_name=data.stock_name,
            period_stats=period_stats,
            latest_snapshot=snapshot,
            ma_arrangement=ma_arr,
            ma_cross=ma_cross,
            rsi_zone=rsi_zone,
            boll_position=boll_pos,
        )

    # ── 指标计算函数 ──────────────────────────────────

    @staticmethod
    def _sma(series: np.ndarray, period: int) -> np.ndarray:
        """简单移动平均"""
        if len(series) < period:
            return np.full_like(series, np.nan, dtype=float)
        result = np.full_like(series, np.nan, dtype=float)
        cumsum = np.cumsum(np.insert(series.astype(float), 0, 0))
        result[period - 1:] = (cumsum[period:] - cumsum[:-period]) / period
        return result

    @staticmethod
    def _ema(series: np.ndarray, period: int) -> np.ndarray:
        """指数移动平均"""
        result = np.full_like(series, np.nan, dtype=float)
        if len(series) < period:
            return result
        result[period - 1] = np.mean(series[:period])
        alpha = 2 / (period + 1)
        for i in range(period, len(series)):
            result[i] = alpha * series[i] + (1 - alpha) * result[i - 1]
        return result

    @classmethod
    def _macd(cls, close: np.ndarray, fast: int, slow: int, signal: int) -> tuple:
        """MACD: 返回 (DIF, DEA, 柱)"""
        ema_fast = cls._ema(close, fast)
        ema_slow = cls._ema(close, slow)
        dif = ema_fast - ema_slow
        dea = cls._ema(dif, signal)
        hist = 2 * (dif - dea)
        return dif, dea, hist

    @classmethod
    def _rsi(cls, close: np.ndarray, period: int = 14) -> np.ndarray:
        """RSI 相对强弱指标"""
        if len(close) < period + 1:
            return np.full_like(close, np.nan, dtype=float)
        delta = np.diff(close)
        gain = np.where(delta > 0, delta, 0.0)
        loss = np.where(delta < 0, -delta, 0.0)
        avg_gain = np.full(len(close), np.nan)
        avg_loss = np.full(len(close), np.nan)
        avg_gain[period] = np.mean(gain[:period])
        avg_loss[period] = np.mean(loss[:period])
        for i in range(period + 1, len(close)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i - 1]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i - 1]) / period
        rs = avg_gain / np.maximum(avg_loss, 1e-10)
        return 100 - 100 / (1 + rs)

    @classmethod
    def _bollinger(cls, close: np.ndarray, period: int, std_mult: float) -> tuple:
        """布林带: (upper, mid, lower, width)"""
        mid = cls._sma(close, period)
        std = np.full_like(close, np.nan)
        for i in range(period - 1, len(close)):
            std[i] = np.std(close[i - period + 1 : i + 1], ddof=1)
        upper = mid + std_mult * std
        lower = mid - std_mult * std
        width = (upper - lower) / np.maximum(mid, 1e-10)
        return upper, mid, lower, width

    @staticmethod
    def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
        """ATR 平均真实波幅"""
        n = len(close)
        tr = np.zeros(n)
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )
        atr = np.full(n, np.nan)
        if n > period:
            atr[period] = np.mean(tr[1:period + 1])
            for i in range(period + 1, n):
                atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        return atr

    # ── 统计与描述 ────────────────────────────────────

    @staticmethod
    def _calc_period_stats(
        dates: np.ndarray,
        close: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        volume: np.ndarray,
        rows: list[MarketRow],
    ) -> PeriodStats:
        """计算期间涨跌幅/振幅/涨跌天数等"""
        changes = np.array([r.change_pct for r in rows])
        amplitudes = np.array([r.amplitude_pct for r in rows])

        # 如果 akshare 已经提供了涨跌幅和振幅就直接用，否则自己算
        if np.all(changes == 0):
            changes = np.diff(close, prepend=close[0]) / close * 100
            changes[0] = 0
        if np.all(amplitudes == 0):
            prev_close = np.roll(close, 1)
            prev_close[0] = close[0]
            amplitudes = (high - low) / prev_close * 100

        total_change = (close[-1] / close[0] - 1) * 100 if close[0] > 0 else 0
        up_days = int(np.sum(changes > 0))
        down_days = int(np.sum(changes < 0))

        return PeriodStats(
            start_date=dates[0],
            end_date=dates[-1],
            total_change_pct=round(total_change, 2),
            max_amplitude_pct=round(float(np.max(amplitudes)), 2),
            avg_amplitude_pct=round(float(np.mean(amplitudes)), 2),
            up_days=up_days,
            down_days=down_days,
            max_up_pct=round(float(np.max(changes)), 2),
            max_down_pct=round(float(np.min(changes)), 2),
            avg_volume=round(float(np.mean(volume)), 0),
        )

    @staticmethod
    def _describe_ma_arrangement(mas: dict, close: np.ndarray, n: int) -> str:
        """判断均线排列状态"""
        periods = sorted(mas.keys())
        last_vals = [mas[p][-1] for p in periods]
        if all(not np.isnan(v) for v in last_vals):
            if last_vals == sorted(last_vals, reverse=True):
                return "多头排列（短周期均线在上）"
            if last_vals == sorted(last_vals):
                return "空头排列（短周期均线在下）"
            return "交叉震荡，均线方向不一致"
        return "数据不足，无法判断均线排列"

    @staticmethod
    def _describe_recent_cross(dif: np.ndarray, dea: np.ndarray, dates) -> str:
        """查找最近一次 MACD 金叉/死叉"""
        valid = ~(np.isnan(dif) | np.isnan(dea))
        if valid.sum() < 2:
            return "MACD 数据不足"
        d = dif[valid]
        e = dea[valid]
        dt = dates[valid]
        cross = d - e
        for i in range(len(cross) - 1, 0, -1):
            if cross[i - 1] < 0 and cross[i] >= 0:
                return f"最近金叉: {dt[i]}"
            if cross[i - 1] > 0 and cross[i] <= 0:
                return f"最近死叉: {dt[i]}"
        return "近期无金叉/死叉信号"

    @staticmethod
    def _describe_rsi_zone(rsi_val: Optional[float]) -> str:
        if rsi_val is None or np.isnan(rsi_val):
            return "RSI 数据不足"
        if rsi_val > 80:
            return "超买区 (RSI>80)"
        if rsi_val > 70:
            return "偏强区 (70<RSI≤80)"
        if rsi_val < 20:
            return "超卖区 (RSI<20)"
        if rsi_val < 30:
            return "偏弱区 (20≤RSI<30)"
        return "中性区 (30≤RSI≤70)"

    @staticmethod
    def _describe_boll_position(
        price: float, upper: float, mid: float, lower: float
    ) -> str:
        if any(np.isnan([price, upper, mid, lower])):
            return "布林带数据不足"
        if price > upper:
            return "价格突破布林上轨，短期偏强"
        if price < lower:
            return "价格跌破布林下轨，短期偏弱"
        pos = (price - mid) / max(upper - mid, 1e-10)
        if pos > 0.6:
            return "价格运行于布林带上半区，接近上轨压力"
        if pos < -0.6:
            return "价格运行于布林带下半区，接近下轨支撑"
        return "价格运行于布林带中轨附近"

    # ── 辅助 ──────────────────────────────────────────

    @staticmethod
    def _last(arr: np.ndarray) -> Optional[float]:
        """取数组最后一个有效值"""
        if len(arr) == 0:
            return None
        val = arr[-1]
        if isinstance(val, (np.floating, np.integer)):
            val = float(val)
        return None if val is None or (isinstance(val, float) and np.isnan(val)) else val
