"""
Quant Signal Models — النماذج الكمية الأربعة

كل نموذج يرجع ModelSignal مع:
- direction: -1.0 إلى +1.0 (سالب = بيع، موجب = شراء)
- confidence: 0-100
- reasoning: شرح مختصر

النماذج:
1. CarryModel       — فارق أسعار الفائدة
2. MomentumModel    — زخم السعر متعدد الفترات
3. MeanReversionModel — الارتداد من المتوسط
4. MacroFactorModel — العوامل الاقتصادية المباشرة
"""

import numpy as np
import yfinance as yf
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Optional, Any


# رموز yfinance لكل زوج
PAIR_SYMBOLS = {
    "USDJPY": "USDJPY=X",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "XAUUSD": "GC=F",
}


@dataclass
class ModelSignal:
    direction: float    # -1.0 إلى +1.0
    confidence: float   # 0-100
    reasoning: str
    raw_value: float    # القيمة الخام قبل التطبيع


# ═══════════════════════════════════════════════════════════════
# 1. CarryModel — نموذج الكاري
# ═══════════════════════════════════════════════════════════════

class CarryModel:
    """
    يحسب فارق أسعار الفائدة بين عملتي الزوج.
    فارق كبير موجب = BUY الزوج (بيع العملة الأضعف فائدة)

    USDJPY: carry = fed_rate - boj_rate
    EURUSD: carry = ecb_rate - fed_rate (سالب يعني USD أفضل)
    XAUUSD: carry ≈ -fed_rate (الذهب يتأثر عكسياً بالفائدة)
    """

    # نطاق تاريخي لكل زوج لتطبيع الـ carry (min, max تقريبية)
    CARRY_RANGES = {
        "USDJPY": (-2.0, 8.0),   # تاريخياً: من سالب أثناء ZIRP إلى 8% في التشديد
        "EURUSD": (-5.0, 3.0),
        "GBPUSD": (-5.0, 3.0),
        "XAUUSD": (-8.0, 0.5),   # الذهب دائماً سالب الـ carry
    }

    def calculate(self, pair: str, snapshot: Dict[str, Any]) -> ModelSignal:
        fed = snapshot.get("fed_rate", 4.5)
        boj = snapshot.get("boj_rate", 0.25)
        ecb = snapshot.get("ecb_rate", 2.5)

        if pair == "USDJPY":
            carry = fed - boj
            desc = f"USD/JPY carry: Fed({fed}%) - BOJ({boj}%) = {carry:+.2f}%"
        elif pair == "EURUSD":
            carry = ecb - fed
            desc = f"EUR/USD carry: ECB({ecb}%) - Fed({fed}%) = {carry:+.2f}%"
        elif pair == "GBPUSD":
            # BoE fallback: تقدير من Fed spread
            boe = fed * 0.85  # تقريب
            carry = boe - fed
            desc = f"GBP/USD carry ≈ {carry:+.2f}% (BoE تقديري)"
        elif pair == "XAUUSD":
            carry = -fed  # الذهب يتعاكس مع الفائدة
            desc = f"Gold carry: -{fed}% (عكسي مع الفائدة)"
        else:
            return ModelSignal(0.0, 0.0, "زوج غير معروف", 0.0)

        # طبّع على النطاق التاريخي → -1 إلى +1
        lo, hi = self.CARRY_RANGES.get(pair, (-5.0, 5.0))
        direction = float(np.clip((carry - lo) / (hi - lo) * 2 - 1, -1.0, 1.0))
        confidence = min(100.0, abs(direction) * 100)

        return ModelSignal(
            direction=round(direction, 3),
            confidence=round(confidence, 1),
            reasoning=desc,
            raw_value=carry,
        )


# ═══════════════════════════════════════════════════════════════
# 2. MomentumModel — نموذج الزخم
# ═══════════════════════════════════════════════════════════════

class MomentumModel:
    """
    يحسب زخم السعر على 4 فترات: 1M, 3M, 6M, 12M
    يوزّن كل فترة ويطبّع على z-score.
    z-score موجب = momentum صاعد = BUY
    """

    PERIOD_WEIGHTS = [0.40, 0.30, 0.20, 0.10]   # 1M, 3M, 6M, 12M
    PERIODS_DAYS   = [21,   63,   126,  252]

    def calculate(self, pair: str, snapshot: Optional[Dict] = None) -> ModelSignal:
        symbol = PAIR_SYMBOLS.get(pair)
        if not symbol:
            return ModelSignal(0.0, 0.0, "رمز غير معروف", 0.0)

        try:
            df = yf.download(symbol, period="400d", progress=False, auto_adjust=True)
            if df.empty or len(df) < 252:
                return ModelSignal(0.0, 30.0, "بيانات غير كافية للزخم", 0.0)

            close = df["Close"].squeeze().dropna()
            current = float(close.iloc[-1])

            rocs = []
            for days in self.PERIODS_DAYS:
                if len(close) > days:
                    past = float(close.iloc[-days - 1])
                    roc = (current / past - 1) * 100 if past != 0 else 0.0
                else:
                    roc = 0.0
                rocs.append(roc)

            weighted_roc = sum(r * w for r, w in zip(rocs, self.PERIOD_WEIGHTS))

            # احسب z-score من تاريخ أطول
            rolling_rocs = []
            for i in range(252, len(close)):
                past_21 = float(close.iloc[i - 21]) if i >= 21 else float(close.iloc[0])
                rolling_rocs.append((float(close.iloc[i]) / past_21 - 1) * 100)

            if len(rolling_rocs) >= 30:
                mu = np.mean(rolling_rocs)
                sigma = np.std(rolling_rocs)
                z = (weighted_roc - mu) / sigma if sigma > 0 else 0.0
            else:
                z = weighted_roc / 3.0  # تبسيط

            direction = float(np.clip(z / 2.0, -1.0, 1.0))
            confidence = min(100.0, abs(z) * 35)

            desc = (f"Momentum: 1M={rocs[0]:+.1f}% 3M={rocs[1]:+.1f}% "
                    f"6M={rocs[2]:+.1f}% z={z:+.2f}")

            return ModelSignal(
                direction=round(direction, 3),
                confidence=round(confidence, 1),
                reasoning=desc,
                raw_value=round(weighted_roc, 3),
            )

        except Exception as e:
            return ModelSignal(0.0, 0.0, f"خطأ في حساب الزخم: {e}", 0.0)


# ═══════════════════════════════════════════════════════════════
# 3. MeanReversionModel — نموذج الارتداد
# ═══════════════════════════════════════════════════════════════

class MeanReversionModel:
    """
    يحسب z-score السعر من المتوسط المتحرك (60 يوم).
    z > +2.0 → بعيد للأعلى → SELL (توقع ارتداد)
    z < -2.0 → بعيد للأسفل → BUY (توقع ارتداد)
    يُكبح إذا كان الـ Momentum قوياً جداً.
    """

    LOOKBACK_DAYS = 60

    def calculate(self, pair: str, snapshot: Optional[Dict] = None) -> ModelSignal:
        symbol = PAIR_SYMBOLS.get(pair)
        if not symbol:
            return ModelSignal(0.0, 0.0, "رمز غير معروف", 0.0)

        try:
            df = yf.download(symbol, period="90d", progress=False, auto_adjust=True)
            if df.empty or len(df) < self.LOOKBACK_DAYS + 5:
                return ModelSignal(0.0, 0.0, "بيانات غير كافية للارتداد", 0.0)

            close = df["Close"].squeeze().dropna()
            window = close.iloc[-self.LOOKBACK_DAYS:]
            current = float(close.iloc[-1])
            mu = float(window.mean())
            sigma = float(window.std())

            if sigma == 0:
                return ModelSignal(0.0, 0.0, "تقلب صفري", 0.0)

            z = (current - mu) / sigma

            # الارتداد = عكس الاتجاه الحالي
            direction = float(np.clip(-z / 2.0, -1.0, 1.0))
            confidence = min(100.0, abs(z) * 25)  # وزن أقل من الزخم

            desc = f"Mean Reversion: z={z:+.2f} (price={current:.4f}, mean={mu:.4f}, σ={sigma:.4f})"

            return ModelSignal(
                direction=round(direction, 3),
                confidence=round(confidence, 1),
                reasoning=desc,
                raw_value=round(z, 3),
            )

        except Exception as e:
            return ModelSignal(0.0, 0.0, f"خطأ في الارتداد: {e}", 0.0)


# ═══════════════════════════════════════════════════════════════
# 4. MacroFactorModel — نموذج العوامل الاقتصادية
# ═══════════════════════════════════════════════════════════════

class MacroFactorModel:
    """
    يربط المؤشرات الاقتصادية بالاتجاه المتوقع لكل زوج.
    يستخدم coefficients تاريخية مبنية على الفهم الاقتصادي.

    USDJPY:
      + Fed hawkish / CPI مرتفع → UP
      + GDP قوي → UP
      - VIX مرتفع → DOWN (risk-off = JPY يقوى)
      - BOJ hawkish → DOWN
    """

    # معاملات التأثير لكل زوج (علامة = اتجاه، قيمة = قوة)
    FACTOR_COEFFICIENTS: Dict[str, Dict[str, float]] = {
        "USDJPY": {
            "cpi_yoy_vs_2":     +0.25,   # CPI أعلى من 2% = تشديد فيد = UP
            "fed_rate_vs_boj":  +0.30,   # فارق الفائدة
            "gdp_vs_2":         +0.20,   # نمو قوي = USD قوي
            "vix_inv":          -0.25,   # VIX مرتفع = جين يقوى
        },
        "EURUSD": {
            "ecb_vs_fed":       +0.30,   # ECB أعلى من Fed = EUR يرتفع
            "cpi_yoy_vs_2":     -0.20,   # تضخم أمريكي = USD قوي = EURUSD ينخفض
            "vix_inv":          -0.10,
            "sp500_positive":   -0.15,   # risk-on = USD يقوى أحياناً
        },
        "GBPUSD": {
            "cpi_yoy_vs_2":     -0.25,
            "fed_rate_vs_3":    -0.20,
            "vix_inv":          -0.15,
            "gdp_vs_2":         +0.15,
        },
        "XAUUSD": {
            "cpi_yoy_vs_2":     +0.30,   # تضخم = ذهب يرتفع
            "fed_rate_inv":     -0.25,   # فائدة مرتفعة = ذهب ينخفض
            "vix_positive":     +0.25,   # خوف = ذهب يرتفع
            "gdp_vs_2":         -0.10,
        },
    }

    def calculate(self, pair: str, snapshot: Dict[str, Any]) -> ModelSignal:
        coefficients = self.FACTOR_COEFFICIENTS.get(pair)
        if not coefficients:
            return ModelSignal(0.0, 0.0, "لا يوجد نموذج لهذا الزوج", 0.0)

        cpi     = snapshot.get("cpi", {}).get("cpi_yoy", 2.5)
        fed     = snapshot.get("fed_rate", 4.5)
        boj     = snapshot.get("boj_rate", 0.25)
        ecb     = snapshot.get("ecb_rate", 2.5)
        gdp     = snapshot.get("gdp", {}).get("gdp_growth_qoq", 2.0)
        vix     = snapshot.get("vix", 20.0)
        sp500   = snapshot.get("sp500_5d_change", 0.0)

        # تطبيع كل عامل إلى -1 / +1
        factors = {
            "cpi_yoy_vs_2":    np.clip((cpi - 2.0) / 3.0, -1.0, 1.0),
            "fed_rate_vs_boj": np.clip((fed - boj) / 6.0, -1.0, 1.0),
            "ecb_vs_fed":      np.clip((ecb - fed) / 4.0, -1.0, 1.0),
            "fed_rate_vs_3":   np.clip((fed - 3.0) / 4.0, -1.0, 1.0),
            "gdp_vs_2":        np.clip((gdp - 2.0) / 3.0, -1.0, 1.0),
            "vix_inv":         np.clip(-(vix - 20.0) / 15.0, -1.0, 1.0),
            "vix_positive":    np.clip((vix - 20.0) / 15.0, -1.0, 1.0),
            "fed_rate_inv":    np.clip(-(fed - 3.0) / 4.0, -1.0, 1.0),
            "sp500_positive":  np.clip(sp500 / 5.0, -1.0, 1.0),
        }

        # المجموع الموزون
        total = sum(
            coeff * factors.get(factor, 0.0)
            for factor, coeff in coefficients.items()
        )
        direction = float(np.clip(total, -1.0, 1.0))
        confidence = min(100.0, abs(direction) * 100)

        # أبرز العوامل الرئيسية
        contributions = {
            f: round(coeff * float(factors.get(f, 0.0)), 3)
            for f, coeff in coefficients.items()
        }
        top = sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:2]
        desc = f"Macro factors: {', '.join(f'{k}={v:+.2f}' for k, v in top)} → total={direction:+.2f}"

        return ModelSignal(
            direction=round(direction, 3),
            confidence=round(confidence, 1),
            reasoning=desc,
            raw_value=round(total, 3),
        )


# ═══════════════════════════════════════════════════════════════
# QuantSignalAggregator — يجمع كل النماذج
# ═══════════════════════════════════════════════════════════════

class QuantSignalAggregator:
    """يشغّل الأربعة نماذج على زوج واحد ويرجع dict بالنتائج"""

    def __init__(self, tracker=None):
        self.tracker = tracker
        self.carry_model = CarryModel()
        self.momentum_model = MomentumModel()
        self.reversion_model = MeanReversionModel()
        self.macro_model = MacroFactorModel()

    def run_all(
        self,
        pair: str,
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, ModelSignal]:
        """
        يشغّل كل النماذج ويرجع dict:
        {
          "carry":          ModelSignal,
          "momentum":       ModelSignal,
          "mean_reversion": ModelSignal,
          "macro_factor":   ModelSignal,
        }
        """
        if snapshot is None and self.tracker is not None:
            snapshot = self.tracker.get_full_snapshot()
        if snapshot is None:
            snapshot = {}

        return {
            "carry":          self.carry_model.calculate(pair, snapshot),
            "momentum":       self.momentum_model.calculate(pair, snapshot),
            "mean_reversion": self.reversion_model.calculate(pair, snapshot),
            "macro_factor":   self.macro_model.calculate(pair, snapshot),
        }

    def get_summary(self, pair: str, snapshot: Optional[Dict] = None) -> str:
        """ملخص نصي لكل النماذج"""
        signals = self.run_all(pair, snapshot)
        lines = [f"═══ نماذج كوانت: {pair} ═══"]
        for name, sig in signals.items():
            arrow = "↑" if sig.direction > 0.1 else ("↓" if sig.direction < -0.1 else "→")
            lines.append(
                f"  {name:16s}: {arrow} {sig.direction:+.2f} "
                f"(conf={sig.confidence:.0f}%) — {sig.reasoning}"
            )
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from data.economic_tracker import EconomicTracker

    print("═══ اختبار النماذج الكمية ═══\n")
    tracker = EconomicTracker()
    snap = tracker.get_full_snapshot()

    agg = QuantSignalAggregator(tracker)

    for pair in ["USDJPY", "EURUSD", "XAUUSD"]:
        print(agg.get_summary(pair, snap))
        print()
