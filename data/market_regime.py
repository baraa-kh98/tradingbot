"""
Market Regime Classifier — مصنّف نظام السوق

يحلل البيانات الاقتصادية ويصنّف السوق في أحد 6 أنظمة:
- RATE_HIKE_CYCLE   : الفيد يرفع الفائدة، USD قوي
- RATE_CUT_CYCLE    : الفيد يخفض، USD ضعيف
- RISK_ON_GROWTH    : VIX منخفض، أسهم ترتفع، شهية المخاطرة
- RISK_OFF_FLIGHT   : VIX مرتفع، هروب للملاذات الآمنة
- STAGFLATION       : تضخم + نمو بطيء
- NEUTRAL           : لا إشارة واضحة

لكل نظام bias محدد لكل زوج تداول (-1.0 إلى +1.0).
"""

from typing import Dict, Any, List
from dataclasses import dataclass


# ═══════════════════════════════════════════════════════════════
# Regime Definitions
# ═══════════════════════════════════════════════════════════════

# bias لكل زوج في كل نظام (+1 = BUY، -1 = SELL، 0 = محايد)
REGIME_PAIR_BIASES: Dict[str, Dict[str, float]] = {
    "RATE_HIKE_CYCLE": {
        "USDJPY": +0.80,   # الفائدة الأمريكية > اليابانية = carry trade
        "EURUSD": -0.40,   # USD قوي يضغط EUR
        "GBPUSD": -0.40,   # نفس تأثير USD
        "XAUUSD": -0.30,   # الذهب يتراجع مع ارتفاع الفائدة
    },
    "RATE_CUT_CYCLE": {
        "USDJPY": -0.70,   # USD يضعف، JPY يقوى
        "EURUSD": +0.40,   # EUR يستفيد من ضعف USD
        "GBPUSD": +0.40,
        "XAUUSD": +0.60,   # الذهب يرتفع مع خفض الفائدة
    },
    "RISK_ON_GROWTH": {
        "USDJPY": +0.50,   # risk-on = بيع JPY (ملاذ آمن)
        "EURUSD": +0.20,
        "GBPUSD": +0.30,
        "XAUUSD": -0.20,   # risk-on = بيع الذهب
    },
    "RISK_OFF_FLIGHT": {
        "USDJPY": -0.60,   # هروب لـ JPY
        "EURUSD": -0.10,
        "GBPUSD": -0.20,
        "XAUUSD": +0.70,   # الذهب ملاذ آمن
    },
    "STAGFLATION": {
        "USDJPY": +0.30,   # USD يستفيد أحياناً
        "EURUSD": -0.20,
        "GBPUSD": -0.30,
        "XAUUSD": +0.80,   # الذهب الأفضل في ستاغفليشن
    },
    "NEUTRAL": {
        "USDJPY": 0.0,
        "EURUSD": 0.0,
        "GBPUSD": 0.0,
        "XAUUSD": 0.0,
    },
}

REGIME_DESCRIPTIONS = {
    "RATE_HIKE_CYCLE":  "دورة رفع الفائدة — USD قوي، carry trades مربحة",
    "RATE_CUT_CYCLE":   "دورة خفض الفائدة — USD ضعيف، JPY وذهب يرتفعان",
    "RISK_ON_GROWTH":   "نمو ومخاطرة — أسهم ترتفع، JPY يضعف",
    "RISK_OFF_FLIGHT":  "هروب للملاذات — VIX مرتفع، JPY وذهب يصعدان",
    "STAGFLATION":      "ركود تضخمي — تضخم مع نمو بطيء",
    "NEUTRAL":          "نظام محايد — لا إشارة اتجاهية واضحة",
}


@dataclass
class RegimeResult:
    regime_name: str
    confidence: float           # 0-100
    pair_biases: Dict[str, float]
    regime_drivers: List[str]
    description: str


# ═══════════════════════════════════════════════════════════════
# MarketRegimeClassifier
# ═══════════════════════════════════════════════════════════════

class MarketRegimeClassifier:
    """
    يصنّف وضع السوق الكلي في أحد 6 أنظمة بناءً على snapshot الاقتصادي.
    يُستدعى من MarketViewBuilder مرة واحدة لكل دورة.
    """

    def __init__(self, tracker=None):
        self.tracker = tracker

    def classify(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        المدخل: snapshot من EconomicTracker.get_full_snapshot()
        المخرج: dict يحتوي على:
          - regime_name, confidence, pair_biases, regime_drivers, description
        """
        scores: Dict[str, float] = {r: 0.0 for r in REGIME_PAIR_BIASES}
        drivers: List[str] = []

        fed_rate     = snapshot.get("fed_rate", 4.5)
        boj_rate     = snapshot.get("boj_rate", 0.25)
        fed_direction = snapshot.get("fed_direction", "HOLDING")
        cpi          = snapshot.get("cpi", {})
        cpi_yoy      = cpi.get("cpi_yoy", 2.5)
        core_cpi     = cpi.get("core_cpi_yoy", 2.8)
        gdp          = snapshot.get("gdp", {})
        gdp_growth   = gdp.get("gdp_growth_qoq", 2.0)
        vix          = snapshot.get("vix", 20.0)
        sp500_5d     = snapshot.get("sp500_5d_change", 0.0)
        yield_curve  = snapshot.get("yield_curve", {})
        curve_shape  = yield_curve.get("curve_shape", "FLAT")
        spread_2_10  = yield_curve.get("spread_2_10", 0.0)
        rate_diff    = snapshot.get("rate_differential_usd_jpy", 4.0)

        # ── شروط RATE_HIKE_CYCLE ──────────────────────────────
        if fed_direction == "HIKING" or fed_rate >= 4.5:
            scores["RATE_HIKE_CYCLE"] += 35
            drivers.append(f"Fed {fed_direction} (rate={fed_rate}%)")
        if cpi_yoy > 3.0:
            scores["RATE_HIKE_CYCLE"] += 20
            drivers.append(f"CPI مرتفع ({cpi_yoy}%)")
        if rate_diff > 3.5:
            scores["RATE_HIKE_CYCLE"] += 20
            drivers.append(f"فارق فائدة USD/JPY كبير ({rate_diff}%)")
        if curve_shape == "FLAT":
            scores["RATE_HIKE_CYCLE"] += 10

        # ── شروط RATE_CUT_CYCLE ───────────────────────────────
        if fed_direction == "CUTTING" or fed_rate < 3.5:
            scores["RATE_CUT_CYCLE"] += 40
            drivers.append(f"Fed {fed_direction} (rate={fed_rate}%)")
        if cpi_yoy < 2.5:
            scores["RATE_CUT_CYCLE"] += 20
            drivers.append(f"تضخم منخفض ({cpi_yoy}%)")
        if rate_diff < 2.0:
            scores["RATE_CUT_CYCLE"] += 15

        # ── شروط RISK_ON_GROWTH ───────────────────────────────
        if vix < 18:
            scores["RISK_ON_GROWTH"] += 30
            drivers.append(f"VIX منخفض ({vix:.1f})")
        if sp500_5d > 1.5:
            scores["RISK_ON_GROWTH"] += 25
            drivers.append(f"أسهم ترتفع (SP500 +{sp500_5d:.1f}% أسبوعياً)")
        if gdp_growth > 2.5:
            scores["RISK_ON_GROWTH"] += 20
            drivers.append(f"نمو قوي GDP={gdp_growth}%")
        if curve_shape == "NORMAL":
            scores["RISK_ON_GROWTH"] += 15

        # ── شروط RISK_OFF_FLIGHT ──────────────────────────────
        if vix > 25:
            scores["RISK_OFF_FLIGHT"] += 40
            drivers.append(f"VIX مرتفع ({vix:.1f}) — خوف في الأسواق")
        if sp500_5d < -2.0:
            scores["RISK_OFF_FLIGHT"] += 30
            drivers.append(f"أسهم تتراجع (SP500 {sp500_5d:.1f}% أسبوعياً)")
        if curve_shape == "INVERTED":
            scores["RISK_OFF_FLIGHT"] += 20
            drivers.append(f"منحنى عائد مقلوب (spread={spread_2_10})")

        # ── شروط STAGFLATION ─────────────────────────────────
        if cpi_yoy > 3.5 and gdp_growth < 1.5:
            scores["STAGFLATION"] += 50
            drivers.append(f"ركود تضخمي: CPI={cpi_yoy}%, GDP={gdp_growth}%")
        elif cpi_yoy > 3.0 and gdp_growth < 2.0:
            scores["STAGFLATION"] += 25

        # ── اختيار النظام الفائز ────────────────────────────
        best_regime = max(scores, key=lambda r: scores[r])
        best_score = scores[best_regime]

        # احسب confidence: النسبة من المجموع الكلي
        total_score = sum(scores.values())
        if total_score > 0:
            confidence = round((best_score / total_score) * 100, 1)
        else:
            confidence = 0.0

        # إذا الفرق بسيط جداً → NEUTRAL
        scores_sorted = sorted(scores.values(), reverse=True)
        if len(scores_sorted) >= 2 and scores_sorted[0] - scores_sorted[1] < 15:
            best_regime = "NEUTRAL"
            confidence = max(20.0, confidence * 0.6)

        # إزالة drivers المكررة
        seen = set()
        unique_drivers: List[str] = []
        for d in drivers:
            key = d[:30]
            if key not in seen:
                seen.add(key)
                unique_drivers.append(d)

        result = RegimeResult(
            regime_name=best_regime,
            confidence=confidence,
            pair_biases=REGIME_PAIR_BIASES[best_regime].copy(),
            regime_drivers=unique_drivers[:5],
            description=REGIME_DESCRIPTIONS[best_regime],
        )

        return {
            "regime_name":   result.regime_name,
            "confidence":    result.confidence,
            "pair_biases":   result.pair_biases,
            "regime_drivers": result.regime_drivers,
            "description":   result.description,
            "all_scores":    {k: round(v, 1) for k, v in scores.items()},
        }

    def get_telegram_report(self, regime_result: Dict) -> str:
        """تقرير مختصر للـ Telegram"""
        regime = regime_result["regime_name"]
        conf = regime_result["confidence"]
        desc = regime_result["description"]
        biases = regime_result["pair_biases"]
        drivers = regime_result["regime_drivers"]

        lines = [
            f"🌐 نظام السوق: {regime} ({conf:.0f}%)",
            f"📝 {desc}",
            "",
            "📊 الاتجاهات:",
        ]
        for pair, bias in biases.items():
            if bias > 0.3:
                icon = "🟢 BUY"
            elif bias < -0.3:
                icon = "🔴 SELL"
            else:
                icon = "⚪ محايد"
            lines.append(f"  {pair}: {icon} ({bias:+.1f})")

        if drivers:
            lines.append("\n⚡ المحركات:")
            for d in drivers[:3]:
                lines.append(f"  • {d}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from data.economic_tracker import EconomicTracker

    print("═══ اختبار MarketRegimeClassifier ═══\n")
    tracker = EconomicTracker()
    snap = tracker.get_full_snapshot()

    clf = MarketRegimeClassifier(tracker)
    result = clf.classify(snap)

    print(f"النظام: {result['regime_name']}")
    print(f"الثقة: {result['confidence']}%")
    print(f"الوصف: {result['description']}")
    print(f"\nالاتجاهات:")
    for pair, bias in result['pair_biases'].items():
        print(f"  {pair}: {bias:+.2f}")
    print(f"\nالمحركات:")
    for d in result['regime_drivers']:
        print(f"  • {d}")
    print(f"\nدرجات كل الأنظمة:")
    for r, s in result['all_scores'].items():
        print(f"  {r}: {s}")
