"""
London Breakout Signal Generator
==================================
الاستراتيجية الفائزة من الباكتست:
  - +17.81% / سنتين | Sharpe 0.97 | Max DD -5.68% | PF 1.66

المنطق:
  1. احسب Range آسيا (00:00 - 06:59 UTC)
  2. عند London Open (07:00 - 09:59 UTC):
       - Break فوق Asia High + buffer → BUY
       - Break تحت Asia Low  - buffer → SELL
  3. فلتر H4: لا تعاكس اتجاه H4 (EMA20 vs EMA50)
  4. SL = طرف الـ Range الآخر
  5. TP = price + risk × 3.0 (RR = 3:1)
  6. Trailing Stop: عند 1:1 → SL = Breakeven، عند 2:1 → SL = +1×risk

الباراميترات المثلى (من Grid Search):
  buffer_pips    = 3   pip
  min_rr         = 3.0
  min_range_pips = 40  pip
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

from config import (
    PIP_VALUE,
    TRADING_PAIRS,
    KILL_ZONES,
)


class LondonSignalGenerator:
    """
    مولّد إشارات London Breakout

    الاستخدام:
        gen = LondonSignalGenerator("USDJPY", h1_df, h4_df)
        signal = gen.get_signal()
        # signal: None | {"direction": "BUY"/"SELL", "entry": ..., "sl": ..., "tp": ...}
    """

    # ── الباراميترات المثلى ──────────────────────────────────────
    BUFFER_PIPS    = 3      # عازل فوق/تحت الـ Range
    MIN_RR         = 3.0    # Risk : Reward
    MIN_RANGE_PIPS = 40     # الحد الأدنى لحجم Range آسيا
    MAX_RANGE_PIPS = 200    # الحد الأعلى (تجنب أيام الأخبار المتطرفة)

    # نافذة لندن (ساعات UTC)
    LONDON_OPEN  = 7
    LONDON_CLOSE = 10

    def __init__(self, pair: str, h1_df: pd.DataFrame, h4_df: Optional[pd.DataFrame] = None):
        """
        pair  : "USDJPY" | "EURUSD" | ...
        h1_df : DataFrame بـ OHLCV على H1، index = DatetimeIndex (UTC)
        h4_df : DataFrame بـ OHLCV على H4 للـ Bias (اختياري)
        """
        self.pair  = pair
        self.h1    = h1_df.copy() if h1_df is not None else pd.DataFrame()
        self.h4    = h4_df.copy() if h4_df is not None else None

        cfg = TRADING_PAIRS.get(pair, {})
        self.pip = cfg.get("pip", PIP_VALUE)

        self._state: Dict[str, Any] = {
            "in_trade":   False,
            "direction":  None,
            "entry":      0.0,
            "sl":         0.0,
            "tp":         0.0,
            "risk":       0.0,
            "trade_date": None,   # منع التداول المتعدد في نفس اليوم
        }

    # ═══════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════

    def get_signal(self) -> Optional[Dict[str, Any]]:
        """
        يرجع إشارة التداول أو None.

        المخرجات (إذا وُجدت الإشارة):
        {
            "pair":      "USDJPY",
            "direction": "BUY" | "SELL",
            "entry":     float,
            "sl":        float,
            "tp":        float,
            "risk_pips": float,
            "rr":        float,
            "asia_high": float,
            "asia_low":  float,
            "h4_bias":   "BULLISH" | "BEARISH" | "NEUTRAL",
            "reason":    str,
        }
        """
        if self.h1.empty or len(self.h1) < 20:
            return None

        now  = self._now_bar()
        hour = now.hour if now else -1

        # فقط في نافذة لندن
        if not (self.LONDON_OPEN <= hour < self.LONDON_CLOSE):
            return None

        # لا نتداول مرتين في نفس اليوم
        today = now.date() if now else None
        if self._state["trade_date"] == today and self._state["in_trade"]:
            return None

        # احسب Range آسيا
        asia_high, asia_low = self._calc_asia_range()
        if asia_high is None:
            return None

        rng = asia_high - asia_low
        pip = self.pip
        if rng < self.MIN_RANGE_PIPS * pip:
            return None
        if rng > self.MAX_RANGE_PIPS * pip:
            return None

        # السعر الحالي
        price = float(self.h1["Close"].iloc[-1])
        buf   = self.BUFFER_PIPS * pip
        bias  = self._h4_bias()

        # BUY: كسر فوق Asia High
        if price > asia_high + buf and bias != "BEARISH":
            sl   = asia_low
            risk = price - sl
            if risk <= 0:
                return None
            tp = price + risk * self.MIN_RR
            return self._build_signal("BUY", price, sl, tp, risk, asia_high, asia_low, bias)

        # SELL: كسر تحت Asia Low
        elif price < asia_low - buf and bias != "BULLISH":
            sl   = asia_high
            risk = sl - price
            if risk <= 0:
                return None
            tp = price - risk * self.MIN_RR
            return self._build_signal("SELL", price, sl, tp, risk, asia_high, asia_low, bias)

        return None

    def update_trailing_stop(self, current_price: float) -> Optional[float]:
        """
        Trailing Stop Manager — يُستدعى عند كل تحديث سعر.

        يرجع SL الجديد إذا تغيّر، أو None إذا لم يتغير.
        """
        st = self._state
        if not st["in_trade"] or st["risk"] <= 0:
            return None

        entry = st["entry"]
        sl    = st["sl"]
        risk  = st["risk"]
        long  = st["direction"] == "BUY"

        profit = (current_price - entry) if long else (entry - current_price)
        new_sl = sl

        if profit >= risk:                       # 1×risk → Breakeven
            candidate = entry
            new_sl = max(sl, candidate) if long else min(sl, candidate)
        if profit >= 2 * risk:                   # 2×risk → lock 1:1
            candidate = entry + risk if long else entry - risk
            new_sl = max(sl, candidate) if long else min(sl, candidate)

        if new_sl != sl:
            st["sl"] = new_sl
            return round(new_sl, 5)
        return None

    def mark_trade_open(self, direction: str, entry: float, sl: float, tp: float):
        """سجّل الصفقة المفتوحة لتتبع الـ trailing"""
        risk = abs(entry - sl)
        self._state.update({
            "in_trade":   True,
            "direction":  direction,
            "entry":      entry,
            "sl":         sl,
            "tp":         tp,
            "risk":       risk,
            "trade_date": datetime.now(timezone.utc).date(),
        })

    def mark_trade_closed(self):
        """سجّل إغلاق الصفقة"""
        self._state["in_trade"] = False
        self._state["direction"] = None

    def get_session_report(self) -> str:
        """تقرير مختصر لـ Telegram"""
        asia_high, asia_low = self._calc_asia_range()
        if asia_high is None:
            return f"📊 {self.pair} — لم يتم حساب Range آسيا بعد"

        rng = asia_high - asia_low
        pip = self.pip
        bias = self._h4_bias()

        lines = [
            f"📊 {self.pair} — London Breakout",
            f"  Asia Range: {rng/pip:.0f} pip "
            f"({asia_low:.3f} - {asia_high:.3f})",
            f"  H4 Bias: {bias}",
            f"  BUY فوق:  {asia_high + self.BUFFER_PIPS * pip:.3f}",
            f"  SELL تحت: {asia_low  - self.BUFFER_PIPS * pip:.3f}",
        ]
        if rng < self.MIN_RANGE_PIPS * pip:
            lines.append(f"  ⚠️ Range صغير جداً ({rng/pip:.0f} < {self.MIN_RANGE_PIPS} pip) — لا تداول")
        elif rng > self.MAX_RANGE_PIPS * pip:
            lines.append(f"  ⚠️ Range كبير جداً ({rng/pip:.0f} > {self.MAX_RANGE_PIPS} pip) — لا تداول")
        else:
            lines.append(f"  ✅ Range صالح للتداول")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ═══════════════════════════════════════════════════════════

    def _now_bar(self):
        """آخر شمعة"""
        try:
            ts = self.h1.index[-1]
            if hasattr(ts, "hour"):
                return ts
            return pd.Timestamp(ts, tz="UTC")
        except Exception:
            return None

    def _calc_asia_range(self) -> Tuple[Optional[float], Optional[float]]:
        """حساب High/Low من شموع 00:00-06:59 UTC لآخر يوم"""
        try:
            last = self.h1.index[-1]
            today = pd.Timestamp(last).date()

            mask = (
                (self.h1.index.date == today) &           # نفس اليوم
                (self.h1.index.hour >= 0) &
                (self.h1.index.hour < 7)                  # 00:00-06:59
            )
            asia = self.h1[mask]
            if len(asia) < 3:
                return None, None

            return float(asia["High"].max()), float(asia["Low"].min())
        except Exception:
            return None, None

    def _h4_bias(self) -> str:
        """H4 EMA20 vs EMA50 للـ Bias"""
        if self.h4 is None or len(self.h4) < 55:
            return "NEUTRAL"
        try:
            c   = self.h4["Close"].values.astype(float)
            e20 = float(pd.Series(c).ewm(span=20, adjust=False).mean().iloc[-1])
            e50 = float(pd.Series(c).ewm(span=50, adjust=False).mean().iloc[-1])
            if e20 > e50 * 1.0003:
                return "BULLISH"
            if e20 < e50 * 0.9997:
                return "BEARISH"
            return "NEUTRAL"
        except Exception:
            return "NEUTRAL"

    def _build_signal(
        self, direction, entry, sl, tp, risk,
        asia_high, asia_low, bias
    ) -> Dict[str, Any]:
        """بناء dict الإشارة"""
        pip = self.pip
        return {
            "pair":       self.pair,
            "direction":  direction,
            "entry":      round(entry, 5),
            "sl":         round(sl,    5),
            "tp":         round(tp,    5),
            "risk_pips":  round(risk / pip, 1),
            "rr":         self.MIN_RR,
            "asia_high":  round(asia_high, 5),
            "asia_low":   round(asia_low,  5),
            "h4_bias":    bias,
            "reason":     (
                f"London Breakout {direction} | "
                f"Asia Range {(asia_high-asia_low)/pip:.0f}pip | "
                f"H4={bias} | RR={self.MIN_RR}"
            ),
        }
