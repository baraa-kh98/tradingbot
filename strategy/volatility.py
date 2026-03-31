"""
Volatility Analyzer — تحليل التقلبات

يحلل:
1. ATR Regime — هل السوق متقلب أم هادئ؟
2. نمط التقلب اليومي — أفضل أوقات التداول
3. Bollinger Squeeze — ضغط يسبق انفجار
4. فلتر التقلبات — لا تتداول بتقلبات منخفضة جداً
"""

import pandas as pd
import numpy as np
from config import PIP_VALUE


class VolatilityAnalyzer:
    """تحليل التقلبات — يساعد بتحديد حجم الصفقة وتوقيت الدخول"""

    def __init__(self, data):
        self.data = data
        self.high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
        self.low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
        self.close = data["Close"].values if isinstance(data["Close"], pd.Series) else data["Close"].squeeze().values
        self.open = data["Open"].values if isinstance(data["Open"], pd.Series) else data["Open"].squeeze().values
        self.n = len(data)

        # حساب مؤشرات التقلب
        self.atr_14 = self._calc_atr(14)
        self.atr_50 = self._calc_atr(50)

    def _calc_atr(self, period):
        """حساب ATR"""
        tr = np.zeros(self.n)
        for i in range(1, self.n):
            tr[i] = max(
                self.high[i] - self.low[i],
                abs(self.high[i] - self.close[i-1]),
                abs(self.low[i] - self.close[i-1])
            )
        return pd.Series(tr).rolling(window=period).mean().values

    # ═══════════════════════════════════════════════════════════
    # 1. ATR Regime — نظام التقلبات
    # ═══════════════════════════════════════════════════════════

    def get_volatility_regime(self):
        """
        تحديد نظام التقلبات الحالي

        - HIGH: ATR14 > ATR50 * 1.3 — سوق متقلب (حذر)
        - NORMAL: ATR14 بين 0.7-1.3 * ATR50
        - LOW: ATR14 < ATR50 * 0.7 — سوق هادئ (احتمال انفجار)
        - EXPANDING: ATR14 يزداد — التقلب يرتفع
        - CONTRACTING: ATR14 ينخفض — التقلب ينخفض
        """
        if np.isnan(self.atr_14[-1]) or np.isnan(self.atr_50[-1]) or self.atr_50[-1] == 0:
            return {"regime": "UNKNOWN", "ratio": 0}

        current_atr = self.atr_14[-1]
        avg_atr = self.atr_50[-1]
        ratio = current_atr / avg_atr

        # اتجاه التقلب
        if len(self.atr_14) >= 5:
            atr_recent = np.nanmean(self.atr_14[-3:])
            atr_prev = np.nanmean(self.atr_14[-8:-3]) if len(self.atr_14) >= 8 else atr_recent
            if atr_prev > 0:
                direction = "EXPANDING" if atr_recent > atr_prev * 1.1 else \
                           ("CONTRACTING" if atr_recent < atr_prev * 0.9 else "STABLE")
            else:
                direction = "STABLE"
        else:
            direction = "STABLE"

        # النظام
        if ratio > 1.3:
            regime = "HIGH"
        elif ratio < 0.7:
            regime = "LOW"
        else:
            regime = "NORMAL"

        return {
            "regime": regime,
            "ratio": round(ratio, 2),
            "current_atr": round(current_atr, 4),
            "avg_atr": round(avg_atr, 4),
            "current_atr_pips": round(current_atr / PIP_VALUE, 1),
            "direction": direction,
        }

    # ═══════════════════════════════════════════════════════════
    # 2. Bollinger Squeeze — كشف الانضغاط
    # ═══════════════════════════════════════════════════════════

    def detect_squeeze(self, bb_period=20, bb_std=2.0, kc_period=20, kc_mult=1.5):
        """
        Bollinger Squeeze — عندما Bollinger Bands داخل Keltner Channels

        يدل على تقلبات منخفضة جداً = انفجار قادم
        """
        if self.n < bb_period + 5:
            return {"squeeze": False}

        close_series = pd.Series(self.close)

        # Bollinger Bands
        bb_mid = close_series.rolling(bb_period).mean()
        bb_std_val = close_series.rolling(bb_period).std()
        bb_upper = bb_mid + bb_std * bb_std_val
        bb_lower = bb_mid - bb_std * bb_std_val

        # Keltner Channels
        atr_series = pd.Series(self.atr_14)
        kc_mid = close_series.rolling(kc_period).mean()
        kc_upper = kc_mid + kc_mult * atr_series
        kc_lower = kc_mid - kc_mult * atr_series

        # Squeeze: BB داخل KC
        bb_width = (bb_upper - bb_lower).values
        kc_width = (kc_upper - kc_lower).values

        is_squeeze = bool(bb_width[-1] < kc_width[-1]) if not np.isnan(bb_width[-1]) else False

        # عدد شموع الـ squeeze المتتالية
        squeeze_count = 0
        for i in range(self.n - 1, max(0, self.n - 30), -1):
            if not np.isnan(bb_width[i]) and not np.isnan(kc_width[i]):
                if bb_width[i] < kc_width[i]:
                    squeeze_count += 1
                else:
                    break

        # اتجاه الـ Momentum (للتنبؤ باتجاه الانفجار)
        momentum = self.close[-1] - bb_mid.values[-1] if not np.isnan(bb_mid.values[-1]) else 0
        bias = "BULLISH" if momentum > 0 else "BEARISH"

        return {
            "squeeze": is_squeeze,
            "squeeze_bars": squeeze_count,
            "momentum_bias": bias,
            "bb_width_pips": round(float(bb_width[-1]) / PIP_VALUE, 1) if not np.isnan(bb_width[-1]) else 0,
        }

    # ═══════════════════════════════════════════════════════════
    # 3. Session Volatility — تقلب الجلسات
    # ═══════════════════════════════════════════════════════════

    def get_session_volatility(self):
        """
        تحليل تقلبات كل جلسة تداول

        يحسب متوسط المدى (High-Low) حسب الساعة
        """
        if not isinstance(self.data.index, pd.DatetimeIndex):
            return {}

        df = self.data.copy()
        df["range_pips"] = (df["High"] - df["Low"]) / PIP_VALUE
        df["hour"] = df.index.hour

        hourly_vol = df.groupby("hour")["range_pips"].mean()

        # تحديد أفضل ساعات
        best_hours = hourly_vol.nlargest(5).index.tolist()
        worst_hours = hourly_vol.nsmallest(5).index.tolist()

        return {
            "hourly_avg": {int(h): round(float(v), 1) for h, v in hourly_vol.items()},
            "best_hours_utc": best_hours,
            "worst_hours_utc": worst_hours,
            "current_hour_vol": round(float(hourly_vol.get(self.data.index[-1].hour, 0)), 1),
        }

    # ═══════════════════════════════════════════════════════════
    # 4. فلتر التداول بالتقلبات
    # ═══════════════════════════════════════════════════════════

    def should_trade(self):
        """
        هل الظروف مناسبة للتداول من ناحية التقلبات؟

        returns: (bool, str reason, dict adjustments)
        """
        regime = self.get_volatility_regime()
        squeeze = self.detect_squeeze()

        adjustments = {
            "sl_multiplier": 1.0,
            "tp_multiplier": 1.0,
            "lot_multiplier": 1.0,
        }

        # تقلبات عالية جداً = خطر
        if regime["regime"] == "HIGH" and regime["ratio"] > 1.8:
            return False, f"🔴 تقلبات عالية جداً (ATR {regime['ratio']}x)", adjustments

        # تقلبات عالية = وسّع SL, صغّر حجم
        if regime["regime"] == "HIGH":
            adjustments["sl_multiplier"] = 1.3
            adjustments["tp_multiplier"] = 1.5
            adjustments["lot_multiplier"] = 0.7
            return True, f"⚠️ تقلبات عالية — SL أوسع, حجم أصغر", adjustments

        # تقلبات منخفضة + squeeze = احتمال انفجار
        if regime["regime"] == "LOW" and squeeze["squeeze"]:
            if squeeze["squeeze_bars"] >= 5:
                adjustments["tp_multiplier"] = 1.5
                return True, f"🔋 Squeeze ({squeeze['squeeze_bars']} bars) — انفجار قادم → {squeeze['momentum_bias']}", adjustments

        # تقلبات منخفضة جداً = لا تتداول
        if regime["regime"] == "LOW" and regime["ratio"] < 0.5:
            return False, f"⏸️ تقلبات منخفضة جداً (ATR {regime['ratio']}x) — انتظر", adjustments

        return True, f"✅ تقلبات طبيعية (ATR {regime['ratio']}x)", adjustments

    # ═══════════════════════════════════════════════════════════
    # 5. التقرير الشامل
    # ═══════════════════════════════════════════════════════════

    def get_report(self):
        """تقرير التقلبات لـ Telegram"""
        regime = self.get_volatility_regime()
        squeeze = self.detect_squeeze()
        can_trade, trade_reason, adjustments = self.should_trade()

        regime_icons = {"HIGH": "🔴", "NORMAL": "🟢", "LOW": "🟡", "UNKNOWN": "⚪"}
        dir_icons = {"EXPANDING": "📈", "CONTRACTING": "📉", "STABLE": "➡️"}

        lines = [
            "── تحليل التقلبات ──",
            f"{regime_icons.get(regime['regime'], '⚪')} النظام: {regime['regime']} ({regime['ratio']}x)",
            f"📊 ATR: {regime.get('current_atr_pips', 0)} pips",
            f"{dir_icons.get(regime['direction'], '➡️')} الاتجاه: {regime['direction']}",
        ]

        if squeeze["squeeze"]:
            lines.append(f"🔋 SQUEEZE! ({squeeze['squeeze_bars']} bars) → {squeeze['momentum_bias']}")

        lines.append(f"{'✅' if can_trade else '❌'} {trade_reason}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from data.data_feed import DataFeed
    feed = DataFeed()
    data = feed.get_htf_data()

    if data is not None:
        va = VolatilityAnalyzer(data)

        print("═══ تحليل التقلبات ═══\n")
        print(va.get_report())

        sess = va.get_session_volatility()
        if sess.get("best_hours_utc"):
            print(f"\n⏰ أفضل ساعات (UTC): {sess['best_hours_utc']}")
            print(f"😴 أسوأ ساعات (UTC): {sess['worst_hours_utc']}")
