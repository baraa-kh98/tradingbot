"""
Order Flow Analyzer — تحليل تدفق الأوامر

يحلل:
1. Volume Profile — توزيع الحجم على مستويات السعر
2. Delta Estimation — تقدير ضغط الشراء vs البيع
3. Absorption Detection — كشف مناطق الامتصاص
4. POC (Point of Control) — مستوى الحجم الأعلى
5. Value Area — منطقة القيمة (70% من الحجم)
"""

import pandas as pd
import numpy as np
from config import PIP_VALUE


class OrderFlowAnalyzer:
    """تحليل تدفق الأوامر — يكشف نوايا Smart Money"""

    def __init__(self, data):
        self.data = data
        self.high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
        self.low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
        self.close = data["Close"].values if isinstance(data["Close"], pd.Series) else data["Close"].squeeze().values
        self.open = data["Open"].values if isinstance(data["Open"], pd.Series) else data["Open"].squeeze().values

        # Volume — إذا مش متوفر نقدّره من حجم الشمعة
        if "Volume" in data.columns:
            vol = data["Volume"]
            self.volume = vol.values if isinstance(vol, pd.Series) else vol.squeeze().values
            self.has_real_volume = True
        else:
            self.volume = np.abs(self.close - self.open) * 1000
            self.has_real_volume = False

        self.n = len(data)

    # ═══════════════════════════════════════════════════════════
    # 1. Volume Profile — توزيع الحجم
    # ═══════════════════════════════════════════════════════════

    def get_volume_profile(self, lookback=100, num_levels=50):
        """
        بناء Volume Profile — توزيع الحجم على مستويات الأسعار

        returns: dict مع POC, VAH, VAL
        """
        start = max(0, self.n - lookback)
        h = self.high[start:]
        l = self.low[start:]
        vol = self.volume[start:]

        price_min = float(np.min(l))
        price_max = float(np.max(h))
        price_range = price_max - price_min

        if price_range <= 0:
            return {"poc": 0, "vah": 0, "val": 0}

        step = price_range / num_levels
        levels = np.arange(price_min, price_max, step)
        profile = np.zeros(len(levels))

        # توزيع الحجم على المستويات
        for i in range(len(h)):
            candle_low = l[i]
            candle_high = h[i]
            candle_vol = vol[i] if vol[i] > 0 else 1

            for j, level in enumerate(levels):
                if candle_low <= level <= candle_high:
                    profile[j] += candle_vol

        # POC — نقطة التحكم (أعلى حجم)
        poc_idx = np.argmax(profile)
        poc = float(levels[poc_idx])

        # Value Area — 70% من الحجم حول POC
        total_vol = np.sum(profile)
        if total_vol == 0:
            return {"poc": round(poc, 3), "vah": round(price_max, 3), "val": round(price_min, 3)}

        target_vol = total_vol * 0.7
        accumulated = profile[poc_idx]
        upper_idx = poc_idx
        lower_idx = poc_idx

        while accumulated < target_vol:
            expand_up = profile[upper_idx + 1] if upper_idx + 1 < len(profile) else 0
            expand_down = profile[lower_idx - 1] if lower_idx - 1 >= 0 else 0

            if expand_up >= expand_down and upper_idx + 1 < len(profile):
                upper_idx += 1
                accumulated += expand_up
            elif lower_idx - 1 >= 0:
                lower_idx -= 1
                accumulated += expand_down
            else:
                break

        vah = float(levels[min(upper_idx, len(levels) - 1)])  # Value Area High
        val = float(levels[max(lower_idx, 0)])                  # Value Area Low

        return {
            "poc": round(poc, 3),
            "vah": round(vah, 3),
            "val": round(val, 3),
            "profile": [(round(float(levels[i]), 3), round(float(profile[i]), 0))
                       for i in range(len(levels)) if profile[i] > 0],
        }

    # ═══════════════════════════════════════════════════════════
    # 2. Delta Estimation — ضغط الشراء vs البيع
    # ═══════════════════════════════════════════════════════════

    def estimate_delta(self, lookback=20):
        """
        تقدير Delta (ضغط الشراء - البيع)

        الطريقة: نسبة إغلاق الشمعة ضمن مداها
        - إغلاق قرب الأعلى = ضغط شراء
        - إغلاق قرب الأدنى = ضغط بيع
        """
        start = max(0, self.n - lookback)
        deltas = []
        cumulative_delta = 0

        for i in range(start, self.n):
            candle_range = self.high[i] - self.low[i]
            if candle_range == 0:
                deltas.append(0)
                continue

            # نسبة الإغلاق (0=أدنى, 1=أعلى)
            close_ratio = (self.close[i] - self.low[i]) / candle_range
            vol = self.volume[i] if self.volume[i] > 0 else 1

            # Delta = ضغط الشراء - ضغط البيع
            buy_vol = vol * close_ratio
            sell_vol = vol * (1 - close_ratio)
            delta = buy_vol - sell_vol

            cumulative_delta += delta
            deltas.append(delta)

        # آخر 5 شموع
        recent_delta = sum(deltas[-5:])
        bias = "BULLISH" if recent_delta > 0 else "BEARISH" if recent_delta < 0 else "NEUTRAL"

        # Divergence — السعر يطلع والـ delta ينزل أو العكس
        price_change = self.close[-1] - self.close[start]
        divergence = False
        if price_change > 0 and cumulative_delta < 0:
            divergence = True  # Bearish divergence
        elif price_change < 0 and cumulative_delta > 0:
            divergence = True  # Bullish divergence

        return {
            "cumulative_delta": round(float(cumulative_delta), 0),
            "recent_delta": round(float(recent_delta), 0),
            "bias": bias,
            "divergence": divergence,
            "divergence_type": (
                "BEARISH_DIV" if price_change > 0 and cumulative_delta < 0 else
                "BULLISH_DIV" if price_change < 0 and cumulative_delta > 0 else
                None
            ),
        }

    # ═══════════════════════════════════════════════════════════
    # 3. Absorption — كشف الامتصاص
    # ═══════════════════════════════════════════════════════════

    def detect_absorption(self, lookback=10):
        """
        كشف الامتصاص — حجم عالي مع حركة سعر صغيرة

        يدل على أن Smart Money تمتص أوامر الجانب المقابل
        - Bullish Absorption: حجم عالي عند Low مع إغلاق قرب الأعلى
        - Bearish Absorption: حجم عالي عند High مع إغلاق قرب الأدنى
        """
        start = max(0, self.n - lookback)
        avg_vol = np.mean(self.volume[max(0, self.n - 50):self.n])
        if avg_vol == 0:
            avg_vol = 1

        absorptions = []

        for i in range(start, self.n):
            candle_range = self.high[i] - self.low[i]
            if candle_range == 0:
                continue

            vol_ratio = self.volume[i] / avg_vol
            close_ratio = (self.close[i] - self.low[i]) / candle_range
            body_ratio = abs(self.close[i] - self.open[i]) / candle_range

            # حجم عالي + جسم صغير = امتصاص
            if vol_ratio > 1.5 and body_ratio < 0.4:
                if close_ratio > 0.6:
                    absorptions.append({
                        "type": "BULLISH_ABSORPTION",
                        "index": i,
                        "price": float(self.low[i]),
                        "volume_ratio": round(vol_ratio, 1),
                    })
                elif close_ratio < 0.4:
                    absorptions.append({
                        "type": "BEARISH_ABSORPTION",
                        "index": i,
                        "price": float(self.high[i]),
                        "volume_ratio": round(vol_ratio, 1),
                    })

        return absorptions

    # ═══════════════════════════════════════════════════════════
    # 4. Volume Climax — ذروة الحجم
    # ═══════════════════════════════════════════════════════════

    def detect_volume_climax(self, lookback=20, threshold=2.5):
        """
        كشف ذروة الحجم — حجم أعلى بكثير من المتوسط

        غالباً يدل على نهاية حركة (exhaustion) أو بداية حركة جديدة
        """
        start = max(0, self.n - lookback)
        avg_vol = np.mean(self.volume[max(0, self.n - 50):self.n])
        if avg_vol == 0:
            return []

        climaxes = []
        for i in range(start, self.n):
            if self.volume[i] > avg_vol * threshold:
                body = self.close[i] - self.open[i]
                climax_type = "BUYING_CLIMAX" if body > 0 else "SELLING_CLIMAX"

                climaxes.append({
                    "type": climax_type,
                    "index": i,
                    "volume_ratio": round(self.volume[i] / avg_vol, 1),
                    "price": float(self.close[i]),
                })

        return climaxes

    # ═══════════════════════════════════════════════════════════
    # 5. التحليل الشامل
    # ═══════════════════════════════════════════════════════════

    def get_full_analysis(self):
        """تحليل شامل — كل المؤشرات"""
        vp = self.get_volume_profile()
        delta = self.estimate_delta()
        absorptions = self.detect_absorption()
        climaxes = self.detect_volume_climax()

        current_price = float(self.close[-1])

        # هل السعر فوق أو تحت POC؟
        poc_position = "ABOVE" if current_price > vp["poc"] else "BELOW"

        # هل السعر ضمن Value Area؟
        in_value_area = vp["val"] <= current_price <= vp["vah"]

        return {
            "volume_profile": vp,
            "delta": delta,
            "absorptions": absorptions,
            "climaxes": climaxes,
            "poc_position": poc_position,
            "in_value_area": in_value_area,
            "has_real_volume": self.has_real_volume,
        }

    def get_bias(self):
        """
        تحديد الاتجاه من Order Flow

        returns: (str bias, int score, list reasons)
        """
        analysis = self.get_full_analysis()
        score = 0
        reasons = []

        # Delta bias
        delta = analysis["delta"]
        if delta["bias"] == "BULLISH":
            score += 5
            reasons.append("📊 Delta إيجابي (ضغط شراء)")
        elif delta["bias"] == "BEARISH":
            score -= 5
            reasons.append("📊 Delta سلبي (ضغط بيع)")

        # Divergence
        if delta["divergence"]:
            if delta["divergence_type"] == "BULLISH_DIV":
                score += 10
                reasons.append("🔄 Divergence صعودي — السعر نازل والـ Delta إيجابي")
            elif delta["divergence_type"] == "BEARISH_DIV":
                score -= 10
                reasons.append("🔄 Divergence هبوطي — السعر طالع والـ Delta سلبي")

        # POC position
        vp = analysis["volume_profile"]
        current = float(self.close[-1])
        if current > vp["poc"]:
            score += 3
            reasons.append(f"📍 السعر فوق POC ({vp['poc']})")
        else:
            score -= 3
            reasons.append(f"📍 السعر تحت POC ({vp['poc']})")

        # Absorption
        for abs_event in analysis["absorptions"][-3:]:
            if abs_event["type"] == "BULLISH_ABSORPTION":
                score += 5
                reasons.append(f"🟢 امتصاص شرائي عند {abs_event['price']}")
            elif abs_event["type"] == "BEARISH_ABSORPTION":
                score -= 5
                reasons.append(f"🔴 امتصاص بيعي عند {abs_event['price']}")

        bias = "BULLISH" if score > 5 else "BEARISH" if score < -5 else "NEUTRAL"
        return bias, score, reasons

    def get_report(self):
        """تقرير Order Flow لـ Telegram"""
        analysis = self.get_full_analysis()
        bias, score, reasons = self.get_bias()

        vp = analysis["volume_profile"]
        delta = analysis["delta"]

        lines = [
            "── تحليل Order Flow ──",
            f"📍 POC: {vp['poc']} | VAH: {vp['vah']} | VAL: {vp['val']}",
            f"{'📦 داخل' if analysis['in_value_area'] else '🔓 خارج'} Value Area",
            f"📊 Delta: {delta['cumulative_delta']:+.0f} ({delta['bias']})",
        ]

        if delta["divergence"]:
            lines.append(f"🔄 Divergence: {delta['divergence_type']}")

        if analysis["absorptions"]:
            last = analysis["absorptions"][-1]
            lines.append(f"🧱 امتصاص: {last['type']} ({last['volume_ratio']}x vol)")

        if analysis["climaxes"]:
            last = analysis["climaxes"][-1]
            lines.append(f"💥 ذروة حجم: {last['type']} ({last['volume_ratio']}x)")

        if not self.has_real_volume:
            lines.append("⚠️ حجم مقدّر (لا يوجد Volume حقيقي)")

        bias_icon = "📈" if bias == "BULLISH" else "📉" if bias == "BEARISH" else "➡️"
        lines.append(f"{bias_icon} الميل: {bias} (درجة: {score:+d})")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from data.data_feed import DataFeed
    feed = DataFeed()
    data = feed.get_htf_data()

    if data is not None:
        of = OrderFlowAnalyzer(data)
        print("═══ تحليل Order Flow ═══\n")
        print(of.get_report())
