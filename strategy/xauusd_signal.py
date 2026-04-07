"""
XAUUSDSignalGenerator — Gold ATR Channel Breakout
===================================================
استراتيجية مثبتة بالباكتست (2 سنة H1):
  Sharpe=1.201 | Return=+35.97% | Max DD=-7.33% | PF=1.373 | 305 صفقة

المنطق:
  1. ADX > 25 → السوق في ترند حقيقي (مش range)
  2. سعر يكسر N-bar High/Low مع momentum
  3. SL = 1.5 × ATR من نقطة الدخول
  4. TP = 2.5 × risk

الباراميترات المثلى (أعلى Sharpe):
  nbar=35, adx_min=25, atr_sl=1.5, min_rr=2.5
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, Any

from strategy.base_strategy import BaseStrategy


class XAUUSDSignalGenerator(BaseStrategy):
    """
    Gold ATR Breakout — يرث من BaseStrategy
    يعمل مع StrategyRouter تلقائياً
    """

    # ── باراميترات مثبتة بالباكتست (أعلى Sharpe) ─────────────
    NBAR     = 35     # عدد الشموع للـ channel (N-bar high/low)
    ADX_MIN  = 25     # ADX لازم فوق هذا للدخول
    ATR_SL   = 1.5    # SL = 1.5 × ATR
    MIN_RR   = 2.5    # TP = 2.5 × risk
    ATR_PERIOD = 14

    def __init__(self, pair: str, h1_df: pd.DataFrame,
                 h4_df: Optional[pd.DataFrame] = None):
        super().__init__(pair, h1_df, h4_df)
        self._in_trade   = False
        self._trade_dir  = None
        self._entry      = 0.0
        self._sl         = 0.0
        self._tp         = 0.0

    # ── Helpers ───────────────────────────────────────────────

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
            return 5.0

    def _adx(self) -> float:
        try:
            period = self.ATR_PERIOD
            n  = min(len(self.h1) - 1, period * 4)
            h  = self.h1["High"].values[-n:].astype(float)
            l  = self.h1["Low"].values[-n:].astype(float)
            c  = self.h1["Close"].values[-n:].astype(float)
            if len(h) < period + 2:
                return 0.0
            dh = np.diff(h); dl = -np.diff(l)
            dmp = np.where((dh > dl) & (dh > 0), dh, 0.0)
            dmm = np.where((dl > dh) & (dl > 0), dl, 0.0)
            tr  = np.array([max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                            for i in range(1, len(h))])
            def smma(arr, p):
                out = np.zeros(len(arr))
                out[p-1] = arr[:p].mean()
                for i in range(p, len(arr)):
                    out[i] = (out[i-1] * (p-1) + arr[i]) / p
                return out
            atr_s = smma(tr, period)
            dip   = smma(dmp, period) / (atr_s + 1e-9) * 100
            dim   = smma(dmm, period) / (atr_s + 1e-9) * 100
            dx    = np.abs(dip - dim) / (dip + dim + 1e-9) * 100
            return float(np.mean(dx[-period:]))
        except Exception:
            return 0.0

    def _h4_bias(self) -> str:
        """H4 EMA20/50 bias — اختياري كتأكيد إضافي"""
        if self.h4 is None or len(self.h4) < 55:
            return "NEUTRAL"
        try:
            c   = self.h4["Close"].values.astype(float)
            e20 = float(pd.Series(c).ewm(span=20, adjust=False).mean().iloc[-1])
            e50 = float(pd.Series(c).ewm(span=50, adjust=False).mean().iloc[-1])
            if e20 > e50 * 1.0005: return "BULLISH"
            if e20 < e50 * 0.9995: return "BEARISH"
            return "NEUTRAL"
        except Exception:
            return "NEUTRAL"

    def _channel(self):
        """أعلى وأدنى آخر NBAR شمعة (عدا الأخيرة)"""
        try:
            highs = self.h1["High"].values[-(self.NBAR + 1):-1].astype(float)
            lows  = self.h1["Low"].values[-(self.NBAR + 1):-1].astype(float)
            return float(np.max(highs)), float(np.min(lows))
        except Exception:
            return None, None

    # ── Signal Generation ─────────────────────────────────────

    def get_signal(self) -> Optional[Dict[str, Any]]:
        """
        يرجع signal dict أو None.
        يُستدعى في كل دورة من main.py.
        """
        if self._in_trade:
            return None

        if len(self.h1) < self.NBAR + 20:
            return None

        atr = self._atr()
        adx = self._adx()

        # شرط الـ ADX — لا ندخل في السوق الجانبي
        if adx < self.ADX_MIN or atr <= 0:
            return None

        price    = float(self.h1["Close"].values[-1])
        prev_c   = float(self.h1["Close"].values[-2])
        ch_high, ch_low = self._channel()

        if ch_high is None:
            return None

        sl_dist  = self.ATR_SL * atr
        bias     = self._h4_bias()

        # ── BUY: كسر فوق N-bar High ──────────────────────────
        if prev_c <= ch_high and price > ch_high and bias != "BEARISH":
            sl   = price - sl_dist
            risk = sl_dist
            tp   = price + risk * self.MIN_RR
            return {
                "pair":      self.pair,
                "direction": "BUY",
                "entry":     round(price, 2),
                "sl":        round(sl, 2),
                "tp":        round(tp, 2),
                "risk_pips": round(risk / 0.01, 1),
                "rr":        self.MIN_RR,
                "h4_bias":   bias,
                "reason":    f"Gold ATR Breakout BUY | {self.NBAR}-bar high={ch_high:.2f} broken | ADX={adx:.1f} | ATR=${atr:.2f}",
            }

        # ── SELL: كسر تحت N-bar Low ──────────────────────────
        if prev_c >= ch_low and price < ch_low and bias != "BULLISH":
            sl   = price + sl_dist
            risk = sl_dist
            tp   = price - risk * self.MIN_RR
            return {
                "pair":      self.pair,
                "direction": "SELL",
                "entry":     round(price, 2),
                "sl":        round(sl, 2),
                "tp":        round(tp, 2),
                "risk_pips": round(risk / 0.01, 1),
                "rr":        self.MIN_RR,
                "h4_bias":   bias,
                "reason":    f"Gold ATR Breakout SELL | {self.NBAR}-bar low={ch_low:.2f} broken | ADX={adx:.1f} | ATR=${atr:.2f}",
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
        adx = self._adx()
        ch_high, ch_low = self._channel()
        if self._in_trade:
            return (
                f"📊 {self.pair} [Gold ATR] — في صفقة {self._trade_dir} "
                f"| Entry={self._entry:.2f} SL={self._sl:.2f} TP={self._tp:.2f}"
            )
        status = "🔍 يبحث عن إشارة"
        if adx < self.ADX_MIN:
            status = f"⏸️ ADX={adx:.0f} < {self.ADX_MIN} (سوق جانبي)"
        return (
            f"📊 {self.pair} [Gold ATR Breakout] — {status} "
            f"| Channel: {ch_low:.0f}–{ch_high:.0f} | ADX={adx:.0f} | ATR=${atr:.1f}"
        )
