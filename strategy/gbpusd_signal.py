"""
GBPUSDSignalGenerator — NY Open Breakout
==========================================
استراتيجية محسّنة (2026-07-05: H4 RSI Filter):
  Sharpe=1.664 | Return=+31.62% | Max DD=-6.14% | PF=2.22 | 32 صفقة

BASELINE (قبل H4 RSI Filter — 2026-06-06):
  Sharpe=1.270 | Return=+19.1% | Max DD=-7.1% | PF=1.74 | 41 صفقة
  (فاينتيون 2026-06-06: MIN_RR 3.0→4.0، Sharpe 1.224→1.270)

نفس منطق EURUSD لكن مع:
  - min_range_pips=60 بدل 25 (GBP أكثر تقلباً)
  - min_rr=4.0 بدل 3.5

المنطق:
  1. بناء Range من 07:00–13:00 UTC (جلسة لندن)
  2. الدخول عند كسر الـ Range خلال 13:00–15:00 UTC (فتح نيويورك)
  3. الـ Range لازم >= 60 pips (تصفية الأيام الهادئة)
  4. SL = 1.8 × ATR(14)
  5. TP = 4.0 × risk
  6. H4 RSI(14) Filter (2026-07-05): لا BUY عند RSI > 75، لا SELL عند RSI < 25
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, Any

from strategy.base_strategy import BaseStrategy
from utils.logger import get_logger

_log = get_logger("gbpusd_signal")


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

    # ── H4 RSI Filter (2026-07-05) ────────────────────────────────
    # Backtest: Sharpe 1.27→1.664 | WR 34.2%→40.6% | DD -7.14%→-6.14%
    # لا BUY عند RSI H4 > 75 (overbought — انعكاس محتمل)
    # لا SELL عند RSI H4 < 25 (oversold — انعكاس محتمل)
    RSI_HI     = 75    # BUY محظور فوق هذا (overbought على H4)
    RSI_LO     = 25    # SELL محظور تحت هذا (oversold على H4)
    RSI_PERIOD = 14

    def __init__(self, pair: str, h1_df: pd.DataFrame,
                 h4_df: Optional[pd.DataFrame] = None):
        super().__init__(pair, h1_df, h4_df)
        self._in_trade  = False
        self._trade_dir = None
        self._entry     = 0.0
        self._sl        = 0.0
        self._tp        = 0.0

    # ── Helpers ──────────────────────────────────────────────────

    def _h4_rsi(self) -> Optional[float]:
        """
        RSI(14) على H4 — يُستخدم لفلتر الـ overbought/oversold.
        يستخدم h4_df إن أُعطي، وإلا يُعيد sampling من H1.
        يرجع None عند عدم كفاية البيانات.
        """
        try:
            if self.h4 is not None and len(self.h4) >= self.RSI_PERIOD + 5:
                source = self.h4["Close"]
            elif len(self.h1) >= (self.RSI_PERIOD + 5) * 4:
                # resample H1 → H4 locally
                h4 = self.h1["Close"].resample("4h").last().dropna()
                if len(h4) < self.RSI_PERIOD + 5:
                    return None
                source = h4
            else:
                return None

            delta = source.diff()
            gain = delta.clip(lower=0).rolling(self.RSI_PERIOD).mean()
            loss = (-delta.clip(upper=0)).rolling(self.RSI_PERIOD).mean()
            rs = gain / (loss + 1e-9)
            rsi = 100 - (100 / (1 + rs))
            val = float(rsi.iloc[-1])
            return val if not pd.isna(val) else None
        except Exception as e:
            _log.debug(f"_h4_rsi error: {e}")
            return None

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

        h4_rsi = self._h4_rsi()

        # ── BUY: كسر فوق لندن High ──────────────────────────────
        if prev_c <= r_high and price > r_high:
            # H4 RSI Filter: لا BUY عند overbought (RSI > 75)
            if h4_rsi is not None and h4_rsi > self.RSI_HI:
                _log.debug(f"GBPUSD BUY blocked: H4 RSI={h4_rsi:.1f} > {self.RSI_HI} (overbought)")
                return None
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
                    + (f" | H4 RSI={h4_rsi:.0f}" if h4_rsi is not None else "")
                ),
            }

        # ── SELL: كسر تحت لندن Low ──────────────────────────────
        if prev_c >= r_low and price < r_low:
            # H4 RSI Filter: لا SELL عند oversold (RSI < 25)
            if h4_rsi is not None and h4_rsi < self.RSI_LO:
                _log.debug(f"GBPUSD SELL blocked: H4 RSI={h4_rsi:.1f} < {self.RSI_LO} (oversold)")
                return None
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
                    + (f" | H4 RSI={h4_rsi:.0f}" if h4_rsi is not None else "")
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
