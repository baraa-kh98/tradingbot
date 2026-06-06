"""
GBPUSDSignalGenerator — NY Open Breakout
==========================================
استراتيجية مثبتة بالباكتست (2 سنة H1):
  Sharpe=1.224 | Return=+19.1% | Max DD=-7.1% | PF=1.74 | 41 صفقة

نفس منطق EURUSD لكن مع:
  - min_range_pips=60 بدل 25 (GBP أكثر تقلباً)
  - min_rr=3.0 بدل 3.5

المنطق:
  1. بناء Range من 07:00–13:00 UTC (جلسة لندن)
  2. الدخول عند كسر الـ Range خلال 13:00–15:00 UTC (فتح نيويورك)
  3. الـ Range لازم >= 60 pips (تصفية الأيام الهادئة)
  4. SL = 1.8 × ATR(14)
  5. TP = 3.0 × risk
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, Any

from strategy.base_strategy import BaseStrategy


class GBPUSDSignalGenerator(BaseStrategy):
    """
    GBPUSD NY Open Breakout — يرث من BaseStrategy
    يعمل مع StrategyRouter تلقائياً
    """

    # ── باراميترات مثبتة بالباكتست ───────────────────────────────
    RANGE_START_H  = 7     # بداية بناء الـ Range (UTC)
    RANGE_END_H    = 13    # نهاية الـ Range = بداية NY
    SESSION_END_H  = 15    # نهاية نافذة التداول
    MIN_RANGE_PIPS = 60    # أدنى حجم range (GBP أكثر تقلباً من EUR)
    ATR_SL         = 1.8   # SL = 1.8 × ATR
    MIN_RR         = 4.0   # TP = 4.0 × risk (finetune 2026-06-06: 3.0→4.0, Sharpe 1.224→1.270)
    ATR_PERIOD     = 14
    PIP            = 0.0001

    def __init__(self, pair: str, h1_df: pd.DataFrame,
                 h4_df: Optional[pd.DataFrame] = None):
        super().__init__(pair, h1_df, h4_df)
        self._in_trade  = False
        self._trade_dir = None
        self._entry     = 0.0
        self._sl        = 0.0
        self._tp        = 0.0

    # ── Helpers ──────────────────────────────────────────────────

    def _atr(self) -> float:
        try:
            n = min(len(self.h1) - 1, self.ATR_PERIOD * 3)
            h = self.h1["High"].values[-n:].astype(float)
            l = self.h1["Low"].values[-n:].astype(float)
            c = self.h1["Close"].values[-n:].astype(float)
            tr = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                  for i in range(1, len(h))]
            return float(np.mean(tr[-self.ATR_PERIOD:])) if len(tr) >= self.ATR_PERIOD else float(np.mean(tr))
        except Exception:
            return 0.001  # fallback ~10 pips

    def _build_range(self) -> tuple:
        """
        يحسب High/Low لجلسة لندن (07:00–13:00 UTC) لليوم الحالي.
        يرجع (range_high, range_low, range_pips) أو (None, None, 0)
        الـ datetime هو index الـ DataFrame (مش column)
        """
        try:
            idx = pd.DatetimeIndex(self.h1.index)
            last_dt = idx[-1]
            if last_dt.tzinfo is None:
                last_dt = last_dt.tz_localize("UTC")

            day   = last_dt.normalize()
            start = day + pd.Timedelta(hours=self.RANGE_START_H)
            end   = day + pd.Timedelta(hours=self.RANGE_END_H)

            mask  = (idx >= start) & (idx < end)
            pre   = self.h1[mask]
            if len(pre) < 2:
                return None, None, 0
            r_high = float(pre["High"].max())
            r_low  = float(pre["Low"].min())
            r_pips = (r_high - r_low) / self.PIP
            return r_high, r_low, round(r_pips, 1)
        except Exception:
            return None, None, 0

    def _current_hour(self) -> int:
        """ساعة آخر شمعة (UTC) من الـ index"""
        try:
            idx = pd.DatetimeIndex(self.h1.index)
            last = idx[-1]
            if last.tzinfo is None:
                last = last.tz_localize("UTC")
            return last.hour
        except Exception:
            return -1

    # ── Signal Generation ────────────────────────────────────────

    def get_signal(self) -> Optional[Dict[str, Any]]:
        if self._in_trade:
            return None

        if len(self.h1) < 50:
            return None

        hour = self._current_hour()
        if not (self.RANGE_END_H <= hour < self.SESSION_END_H):
            return None

        r_high, r_low, r_pips = self._build_range()
        if r_high is None or r_pips < self.MIN_RANGE_PIPS:
            return None

        atr = self._atr()
        if atr <= 0:
            return None

        price  = float(self.h1["Close"].values[-1])
        prev_c = float(self.h1["Close"].values[-2])
        sl_dist = self.ATR_SL * atr

        # ── BUY: كسر فوق لندن High ──────────────────────────────
        if prev_c <= r_high and price > r_high:
            sl = price - sl_dist
            tp = price + sl_dist * self.MIN_RR
            return {
                "pair":      self.pair,
                "direction": "BUY",
                "entry":     round(price, 5),
                "sl":        round(sl, 5),
                "tp":        round(tp, 5),
                "risk_pips": round(sl_dist / self.PIP, 1),
                "rr":        self.MIN_RR,
                "h4_bias":   "BULLISH",
                "reason":    (
                    f"GBPUSD NY Breakout BUY | London range={r_pips:.0f}pips "
                    f"[{r_low:.5f}–{r_high:.5f}] broken UP | ATR={atr*10000:.1f}pips"
                ),
            }

        # ── SELL: كسر تحت لندن Low ──────────────────────────────
        if prev_c >= r_low and price < r_low:
            sl = price + sl_dist
            tp = price - sl_dist * self.MIN_RR
            return {
                "pair":      self.pair,
                "direction": "SELL",
                "entry":     round(price, 5),
                "sl":        round(sl, 5),
                "tp":        round(tp, 5),
                "risk_pips": round(sl_dist / self.PIP, 1),
                "rr":        self.MIN_RR,
                "h4_bias":   "BEARISH",
                "reason":    (
                    f"GBPUSD NY Breakout SELL | London range={r_pips:.0f}pips "
                    f"[{r_low:.5f}–{r_high:.5f}] broken DOWN | ATR={atr*10000:.1f}pips"
                ),
            }

        return None

    def mark_trade_open(self, direction: str, entry: float,
                        sl: float, tp: float) -> None:
        self._in_trade  = True
        self._trade_dir = direction
        self._entry     = entry
        self._sl        = sl
        self._tp        = tp

    def mark_trade_closed(self) -> None:
        self._in_trade  = False
        self._trade_dir = None
        self._entry     = 0.0
        self._sl        = 0.0
        self._tp        = 0.0

    def get_session_report(self) -> str:
        atr = self._atr()
        r_high, r_low, r_pips = self._build_range()
        hour = self._current_hour()

        if self._in_trade:
            return (
                f"📊 {self.pair} [NY Breakout] — في صفقة {self._trade_dir} "
                f"| Entry={self._entry:.5f} SL={self._sl:.5f} TP={self._tp:.5f}"
            )

        if not (self.RANGE_END_H <= hour < self.SESSION_END_H):
            return (
                f"📊 {self.pair} [NY Breakout] — ⏸️ خارج نافذة التداول (UTC {hour}:00) "
                f"| نافذة: 13–15 UTC"
            )

        range_info = f"Range={r_pips:.0f}pips [{r_low:.5f}–{r_high:.5f}]" if r_high else "Range: N/A"
        status = (
            "🔍 يبحث عن كسر" if r_pips >= self.MIN_RANGE_PIPS
            else f"⏸️ Range صغير ({r_pips:.0f}pips < {self.MIN_RANGE_PIPS})"
        )
        return (
            f"📊 {self.pair} [NY Breakout] — {status} "
            f"| {range_info} | ATR={atr*10000:.1f}pips"
        )
