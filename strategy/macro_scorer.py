"""
Macro Scorer — تقييم حالة الماكرو بدون AI

يعطي score من -100 (bearish USD) إلى +100 (bullish USD)
بناءً على: VIX, DXY, Fed Rate, US 10Y

يُستخدم في الباكتست بدل Claude AI (لأن Claude ما بيعرف الماضي)
ويُستخدم كفلتر إضافي في التداول الحي
"""

import pandas as pd
import numpy as np


class MacroScorer:
    """تقييم الماكرو — يعطي bias و score"""

    def __init__(self, macro_df=None):
        """
        macro_df: DataFrame من MacroData.get_all_macro()
                  الأعمدة: VIX, DXY, FED_RATE, US10Y
        """
        self.macro_df = macro_df

    def score_at_date(self, date):
        """
        حساب سكور الماكرو في تاريخ محدد

        returns: dict مع:
            score: -100 إلى +100 (إيجابي = bullish USD)
            bias: "BULLISH" / "BEARISH" / "NEUTRAL"
            components: تفاصيل كل مكوّن
            risk_level: "LOW" / "MEDIUM" / "HIGH"
        """
        if self.macro_df is None or len(self.macro_df) == 0:
            return {"score": 0, "bias": "NEUTRAL", "components": {}, "risk_level": "MEDIUM"}

        date = pd.Timestamp(date)
        mask = self.macro_df.index <= date
        if mask.sum() == 0:
            return {"score": 0, "bias": "NEUTRAL", "components": {}, "risk_level": "MEDIUM"}

        current = self.macro_df.loc[mask].iloc[-1]
        components = {}
        total_score = 0

        # ─── 1. VIX Analysis (30 نقطة) ───
        if "VIX" in current and pd.notna(current["VIX"]):
            vix = current["VIX"]
            if vix < 15:
                vix_score = 25       # سوق هادئ — ممتاز
                vix_note = "سوق هادئ جداً"
            elif vix < 20:
                vix_score = 10       # طبيعي
                vix_note = "تقلبات طبيعية"
            elif vix < 25:
                vix_score = 0        # مرتفع قليلاً
                vix_note = "تقلبات مرتفعة"
            elif vix < 30:
                vix_score = -15      # عالي
                vix_note = "⚠️ تقلبات عالية"
            else:
                vix_score = -30      # خطر
                vix_note = "🔴 خوف شديد بالسوق"

            components["VIX"] = {"value": round(vix, 1), "score": vix_score, "note": vix_note}
            total_score += vix_score

        # ─── 2. DXY Trend (30 نقطة) ───
        if "DXY" in current and pd.notna(current["DXY"]):
            dxy = current["DXY"]

            # حساب اتجاه DXY (مقارنة بمتوسط 20 يوم)
            dxy_series = self.macro_df.loc[mask, "DXY"].dropna()
            if len(dxy_series) >= 20:
                dxy_ma20 = dxy_series.iloc[-20:].mean()
                dxy_change = ((dxy - dxy_ma20) / dxy_ma20) * 100

                if dxy_change > 1:
                    # DXY صاعد = دولار قوي = USDJPY صاعد
                    dxy_score = 25
                    dxy_note = "الدولار قوي ↑"
                elif dxy_change > 0.3:
                    dxy_score = 10
                    dxy_note = "الدولار يتحسّن"
                elif dxy_change > -0.3:
                    dxy_score = 0
                    dxy_note = "الدولار مستقر"
                elif dxy_change > -1:
                    dxy_score = -10
                    dxy_note = "الدولار يضعف"
                else:
                    dxy_score = -25
                    dxy_note = "الدولار ضعيف ↓"

                components["DXY"] = {
                    "value": round(dxy, 2),
                    "ma20": round(dxy_ma20, 2),
                    "change_pct": round(dxy_change, 2),
                    "score": dxy_score,
                    "note": dxy_note,
                }
                total_score += dxy_score

        # ─── 3. Fed Rate Direction (20 نقطة) ───
        if "FED_RATE" in current and pd.notna(current["FED_RATE"]):
            rate = current["FED_RATE"]

            # اتجاه الفائدة
            rate_series = self.macro_df.loc[mask, "FED_RATE"].dropna()
            if len(rate_series) >= 2:
                prev_rate = rate_series.iloc[-2]
                if rate > prev_rate:
                    rate_score = 20   # رفع فائدة = bullish USD
                    rate_note = "رفع فائدة ↑ — bullish USD"
                elif rate < prev_rate:
                    rate_score = -20  # خفض فائدة = bearish USD
                    rate_note = "خفض فائدة ↓ — bearish USD"
                else:
                    rate_score = 5    # ثبات
                    rate_note = "فائدة ثابتة"

                components["FED_RATE"] = {
                    "value": round(rate, 2),
                    "prev": round(prev_rate, 2),
                    "score": rate_score,
                    "note": rate_note,
                }
                total_score += rate_score

        # ─── 4. Yield Curve: US10Y - US2Y (20 نقطة) ───
        if "US10Y" in current and pd.notna(current["US10Y"]):
            us10y = current["US10Y"]

            us10y_series = self.macro_df.loc[mask, "US10Y"].dropna()
            if len(us10y_series) >= 20:
                us10y_ma20 = us10y_series.iloc[-20:].mean()
                yield_change = us10y - us10y_ma20

                if yield_change > 0.2:
                    yield_score = 15
                    yield_note = "عوائد صاعدة — bullish USD"
                elif yield_change > 0:
                    yield_score = 5
                    yield_note = "عوائد ثابتة"
                elif yield_change > -0.2:
                    yield_score = -5
                    yield_note = "عوائد تتراجع"
                else:
                    yield_score = -15
                    yield_note = "عوائد هابطة — bearish USD"

                components["US10Y"] = {
                    "value": round(us10y, 2),
                    "ma20": round(us10y_ma20, 2),
                    "score": yield_score,
                    "note": yield_note,
                }
                total_score += yield_score

        # ─── النتيجة النهائية ───
        total_score = max(-100, min(100, total_score))

        if total_score > 25:
            bias = "BULLISH"
        elif total_score < -25:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        # مستوى المخاطرة
        vix_val = components.get("VIX", {}).get("value", 20)
        if vix_val > 30:
            risk = "HIGH"
        elif vix_val > 22:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return {
            "score": total_score,
            "bias": bias,
            "risk_level": risk,
            "components": components,
        }

    def should_trade(self, date, min_score=None):
        """
        هل الظروف الماكرو مناسبة للتداول؟

        returns: (bool, str reason)
        """
        result = self.score_at_date(date)

        if result["risk_level"] == "HIGH":
            return False, f"🔴 مخاطر عالية (VIX مرتفع) — Score: {result['score']}"

        return True, f"✅ ماكرو: {result['bias']} (Score: {result['score']}, Risk: {result['risk_level']})"

    def get_usdjpy_bias(self, date):
        """
        bias محدد لـ USDJPY

        USDJPY يرتفع عندما:
        - الدولار قوي (DXY ↑)
        - الفائدة الأمريكية أعلى (عادةً → rate hikes)
        - عوائد السندات ترتفع (US10Y ↑)

        returns: "BUY" / "SELL" / "NEUTRAL"
        """
        result = self.score_at_date(date)

        if result["score"] > 30:
            return "BUY"    # دولار قوي = USDJPY صاعد
        elif result["score"] < -30:
            return "SELL"   # دولار ضعيف = USDJPY هابط
        else:
            return "NEUTRAL"


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # اختبار مع بيانات من yfinance
    print("═══ اختبار Macro Scorer ═══\n")

    from data.macro_data import MacroData
    macro_data = MacroData()

    print("جاري جلب البيانات...")
    all_data = macro_data.get_all_macro("2024-01-01")

    if all_data is not None:
        scorer = MacroScorer(all_data)

        test_dates = ["2024-06-01", "2024-09-15", "2025-01-10", "2025-06-01"]
        for d in test_dates:
            result = scorer.score_at_date(d)
            usdjpy = scorer.get_usdjpy_bias(d)
            print(f"\n📅 {d}:")
            print(f"   Score: {result['score']} | Bias: {result['bias']} | Risk: {result['risk_level']}")
            print(f"   USDJPY: {usdjpy}")
            for name, comp in result["components"].items():
                print(f"   {name}: {comp['value']} → {comp['note']} ({comp['score']:+d})")
