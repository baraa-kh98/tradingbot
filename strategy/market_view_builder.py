"""
Market View Builder — محرك النظرة السوقية الكوانتية

يجمع كل المدخلات في MarketView موحد لكل زوج:
  - Market Regime    (25%)
  - Carry Model      (20%)
  - Momentum Model   (20%)
  - Mean Reversion   (10%)
  - Macro Factor     (15%)
  - ICT Technical    (10%)

المخرج: MarketView مع view_score (-100 إلى +100)،
         conviction، recommended_bias، وسرد بالعربية.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

from data.economic_tracker import EconomicTracker
from data.market_regime import MarketRegimeClassifier
from strategy.quant_signals import QuantSignalAggregator
from config import MARKET_VIEW_WEIGHTS, ACTIVE_PAIRS, MIN_CONVICTION_TO_TRADE


# ═══════════════════════════════════════════════════════════════
# Enums / Constants
# ═══════════════════════════════════════════════════════════════

CONVICTION_LEVELS = ["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]
CONVICTION_ORDER  = {c: i for i, c in enumerate(CONVICTION_LEVELS)}

RECOMMENDED_BIASES = ["STRONG_SELL", "SELL", "NEUTRAL", "BUY", "STRONG_BUY"]

ARABIC_REGIME_NAMES = {
    "RATE_HIKE_CYCLE":  "دورة رفع الفائدة",
    "RATE_CUT_CYCLE":   "دورة خفض الفائدة",
    "RISK_ON_GROWTH":   "نمو وشهية مخاطرة",
    "RISK_OFF_FLIGHT":  "هروب للملاذات الآمنة",
    "STAGFLATION":      "ركود تضخمي",
    "NEUTRAL":          "نظام محايد",
}

ARABIC_DRIVERS = {
    "carry":          "فارق أسعار الفائدة",
    "momentum":       "زخم السعر",
    "mean_reversion": "الارتداد من المتوسط",
    "macro_factor":   "العوامل الاقتصادية",
    "regime":         "نظام السوق الكلي",
    "ict_technical":  "التحليل التقني ICT",
}


# ═══════════════════════════════════════════════════════════════
# MarketView dataclass
# ═══════════════════════════════════════════════════════════════

@dataclass
class MarketView:
    pair:                     str
    view_score:               float          # -100 إلى +100
    conviction:               str            # LOW / MEDIUM / HIGH / VERY_HIGH
    recommended_bias:         str            # STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL
    position_size_multiplier: float          # 0.5 إلى 1.5
    primary_driver:           str
    key_risks:                List[str]
    regime:                   str
    component_scores:         Dict[str, float]
    narrative_ar:             str
    timestamp:                str
    should_trade:             bool = True
    no_trade_reason:          str = ""


# ═══════════════════════════════════════════════════════════════
# MarketViewBuilder
# ═══════════════════════════════════════════════════════════════

class MarketViewBuilder:
    """
    المحرك الرئيسي — يبني نظرة سوقية كاملة لكل زوج في كل دورة.

    الاستخدام:
        builder = MarketViewBuilder()
        views = builder.build_all_views(ict_signals)
        # ict_signals: Dict[pair_name → {"bias": "BUY"|"SELL"|"WAIT", "score": int}]
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        tracker: Optional[EconomicTracker] = None,
    ):
        self.weights = weights or MARKET_VIEW_WEIGHTS
        self.tracker = tracker or EconomicTracker()
        self.regime_clf = MarketRegimeClassifier(self.tracker)
        self.quant_agg = QuantSignalAggregator(self.tracker)

        self._snapshot: Optional[Dict] = None
        self._regime:   Optional[Dict] = None

    # ──────────────────────────────────────────
    # Macro Refresh (مرة واحدة لكل دورة)
    # ──────────────────────────────────────────

    def refresh_macro(self) -> None:
        """يجدد snapshot الاقتصادي ونظام السوق — استدعِه مرة واحدة لكل دورة 15 دق"""
        self._snapshot = self.tracker.get_full_snapshot()
        self._regime   = self.regime_clf.classify(self._snapshot)

    # ──────────────────────────────────────────
    # Build Single Pair View
    # ──────────────────────────────────────────

    def build_view(
        self,
        pair: str,
        ict_bias: Optional[str] = None,
        ict_confluence_score: Optional[int] = None,
    ) -> MarketView:
        """
        يبني MarketView لزوج واحد.

        pair:                  اسم الزوج (USDJPY, EURUSD ...)
        ict_bias:              "BUY" | "SELL" | "WAIT" | None
        ict_confluence_score:  0-140
        """
        if self._snapshot is None:
            self.refresh_macro()

        snapshot = self._snapshot
        regime   = self._regime
        timestamp = snapshot.get("timestamp", "")

        # 1. Regime component
        regime_bias = regime["pair_biases"].get(pair, 0.0)

        # 2. Quant signals
        quant = self.quant_agg.run_all(pair, snapshot)

        # 3. ICT component
        ict_component = self._normalize_ict(ict_bias, ict_confluence_score)

        # 4. Weighted combination
        raw_components = {
            "regime":          float(regime_bias),
            "carry":           float(quant["carry"].direction),
            "momentum":        float(quant["momentum"].direction),
            "mean_reversion":  float(quant["mean_reversion"].direction),
            "macro_factor":    float(quant["macro_factor"].direction),
            "ict_technical":   float(ict_component),
        }

        view_score_norm = self._weighted_combine(raw_components)   # -1 إلى +1
        view_score = round(view_score_norm * 100, 1)               # -100 إلى +100

        # 5. Conviction
        conviction = self._score_to_conviction(view_score, quant)

        # 6. Recommended bias
        recommended_bias = self._score_to_bias(view_score)

        # 7. Size multiplier
        size_mult = self._conviction_to_size_mult(conviction)

        # 8. Primary driver & risks
        primary_driver = self._primary_driver(raw_components)
        key_risks = self._key_risks(pair, snapshot, regime)

        # 9. Arabic narrative
        narrative = self._arabic_narrative(pair, view_score, regime, quant, conviction)

        # 10. Should trade?
        can_trade, reason = self._gate_check(conviction, view_score, ict_bias, view_score_norm)

        return MarketView(
            pair=pair,
            view_score=view_score,
            conviction=conviction,
            recommended_bias=recommended_bias,
            position_size_multiplier=size_mult,
            primary_driver=primary_driver,
            key_risks=key_risks,
            regime=regime["regime_name"],
            component_scores={k: round(v * 100, 1) for k, v in raw_components.items()},
            narrative_ar=narrative,
            timestamp=timestamp,
            should_trade=can_trade,
            no_trade_reason=reason,
        )

    # ──────────────────────────────────────────
    # Build All Pairs
    # ──────────────────────────────────────────

    def build_all_views(
        self,
        ict_signals: Optional[Dict[str, Dict]] = None,
    ) -> Dict[str, MarketView]:
        """
        يبني MarketView لكل ACTIVE_PAIRS في دورة واحدة.
        يستدعي refresh_macro() مرة واحدة فقط.

        ict_signals مثال:
        {
          "USDJPY": {"bias": "BUY",  "score": 95},
          "EURUSD": {"bias": "WAIT", "score": 60},
        }
        """
        self.refresh_macro()

        views: Dict[str, MarketView] = {}
        for pair in ACTIVE_PAIRS:
            ict = (ict_signals or {}).get(pair, {})
            views[pair] = self.build_view(
                pair=pair,
                ict_bias=ict.get("bias") or ict.get("action"),
                ict_confluence_score=ict.get("score") or ict.get("confluence_score"),
            )
        return views

    # ──────────────────────────────────────────
    # Private Helpers
    # ──────────────────────────────────────────

    def _normalize_ict(
        self,
        ict_bias: Optional[str],
        ict_score: Optional[int],
    ) -> float:
        """يحوّل ICT bias + score إلى -1/+1"""
        if not ict_bias or ict_bias in ("WAIT", "NEUTRAL"):
            return 0.0
        normalized = (ict_score or 70) / 140.0
        direction = +1.0 if ict_bias == "BUY" else -1.0
        return direction * normalized

    def _weighted_combine(self, components: Dict[str, float]) -> float:
        total = sum(self.weights.get(k, 0.0) * v for k, v in components.items())
        return float(np.clip(total, -1.0, 1.0))

    def _score_to_conviction(self, view_score: float, quant: Dict) -> str:
        abs_score = abs(view_score)
        sign = 1 if view_score > 0 else -1
        directions = [
            quant["carry"].direction,
            quant["momentum"].direction,
            quant["mean_reversion"].direction,
            quant["macro_factor"].direction,
        ]
        agreement = sum(1 for d in directions if d * sign > 0.05) / 4

        if abs_score >= 60 and agreement >= 0.75:
            return "VERY_HIGH"
        elif abs_score >= 40 and agreement >= 0.50:
            return "HIGH"
        elif abs_score >= 20:
            return "MEDIUM"
        else:
            return "LOW"

    def _score_to_bias(self, view_score: float) -> str:
        if   view_score >=  60: return "STRONG_BUY"
        elif view_score >=  20: return "BUY"
        elif view_score <= -60: return "STRONG_SELL"
        elif view_score <= -20: return "SELL"
        else:                   return "NEUTRAL"

    def _conviction_to_size_mult(self, conviction: str) -> float:
        return {"VERY_HIGH": 1.5, "HIGH": 1.2, "MEDIUM": 1.0, "LOW": 0.5}.get(conviction, 1.0)

    def _primary_driver(self, components: Dict[str, float]) -> str:
        contributions = {k: abs(v) * self.weights.get(k, 0.0) for k, v in components.items()}
        best_key = max(contributions, key=lambda k: contributions[k])
        return ARABIC_DRIVERS.get(best_key, best_key)

    def _key_risks(
        self,
        pair: str,
        snapshot: Dict,
        regime: Dict,
    ) -> List[str]:
        risks = []
        vix = snapshot.get("vix", 20.0)
        cpi = snapshot.get("cpi", {}).get("cpi_yoy", 2.5)
        curve = snapshot.get("yield_curve", {}).get("curve_shape", "FLAT")
        regime_name = regime.get("regime_name", "NEUTRAL")

        if vix > 25:
            risks.append(f"VIX مرتفع ({vix:.1f}) — تقلبات عالية")
        if curve == "INVERTED":
            risks.append("منحنى عائد مقلوب — خطر ركود")
        if cpi > 4.0:
            risks.append(f"تضخم مرتفع ({cpi}%) — قد يغير مسار الفيد")
        if regime_name == "NEUTRAL":
            risks.append("نظام سوق غير واضح — ثقة منخفضة")
        if pair == "XAUUSD" and regime_name == "RATE_HIKE_CYCLE":
            risks.append("رفع الفائدة يضغط على الذهب")

        return risks[:4] if risks else ["لا مخاطر كلية رئيسية حالياً"]

    def _gate_check(
        self,
        conviction: str,
        view_score: float,
        ict_bias: Optional[str],
        view_norm: float,
    ) -> Tuple[bool, str]:
        """يقرر هل يجب التداول أم لا"""
        conviction_idx = CONVICTION_ORDER.get(conviction, 0)
        min_idx = CONVICTION_ORDER.get(MIN_CONVICTION_TO_TRADE, 1)

        if conviction_idx < min_idx:
            return False, f"Conviction {conviction} أقل من الحد الأدنى {MIN_CONVICTION_TO_TRADE}"

        # إذا ICT يعاكس Market View بشكل قوي → تحذير
        if ict_bias == "BUY" and view_norm < -0.3:
            return False, f"ICT=BUY لكن Market View سلبي ({view_score:.1f}) — تعارض قوي"
        if ict_bias == "SELL" and view_norm > 0.3:
            return False, f"ICT=SELL لكن Market View إيجابي ({view_score:.1f}) — تعارض قوي"

        return True, ""

    def _arabic_narrative(
        self,
        pair: str,
        view_score: float,
        regime: Dict,
        quant: Dict,
        conviction: str,
    ) -> str:
        """يبني سرداً عربياً للنظرة السوقية"""
        regime_ar = ARABIC_REGIME_NAMES.get(regime["regime_name"], regime["regime_name"])
        direction_ar = (
            "صاعد" if view_score > 20 else
            "هابط" if view_score < -20 else
            "محايد"
        )
        conviction_ar = {
            "VERY_HIGH": "عالية جداً",
            "HIGH": "عالية",
            "MEDIUM": "متوسطة",
            "LOW": "منخفضة",
        }.get(conviction, conviction)

        carry_dir = "إيجابي" if quant["carry"].direction > 0 else "سلبي"
        mom_dir   = "صاعد" if quant["momentum"].direction > 0 else "هابط"

        narrative = (
            f"النظرة على {pair}: {direction_ar} بدرجة ثقة {conviction_ar} "
            f"(درجة: {view_score:+.0f}/100). "
            f"النظام الكلي: {regime_ar}. "
            f"الكاري [Carry] {carry_dir}، "
            f"والزخم [Momentum] {mom_dir}. "
        )

        drivers = regime.get("regime_drivers", [])
        if drivers:
            narrative += f"المحركات الرئيسية: {'; '.join(drivers[:2])}."

        return narrative

    # ──────────────────────────────────────────
    # Reports
    # ──────────────────────────────────────────

    def get_telegram_report(self, views: Dict[str, "MarketView"]) -> str:
        """تقرير مختصر لكل الأزواج للـ Telegram"""
        regime_name = self._regime["regime_name"] if self._regime else "UNKNOWN"
        regime_conf = self._regime["confidence"] if self._regime else 0.0

        lines = [
            f"🌐 نظام السوق: {regime_name} ({regime_conf:.0f}%)",
            "━━━━━━━━━━━━━━━━━━━━━",
        ]

        for pair, view in views.items():
            icon = {
                "STRONG_BUY":  "🟢🟢",
                "BUY":         "🟢",
                "NEUTRAL":     "⚪",
                "SELL":        "🔴",
                "STRONG_SELL": "🔴🔴",
            }.get(view.recommended_bias, "⚪")

            status = "" if view.should_trade else " ⛔"
            lines.append(
                f"{icon} {pair}: {view.recommended_bias} "
                f"({view.view_score:+.0f}) [{view.conviction}]{status}"
            )
            if not view.should_trade:
                lines.append(f"   ↳ {view.no_trade_reason}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("═══ اختبار MarketViewBuilder ═══\n")
    builder = MarketViewBuilder()
    views = builder.build_all_views()

    for pair, v in views.items():
        print(f"\n{pair}:")
        print(f"  Score:     {v.view_score:+.1f}/100")
        print(f"  Bias:      {v.recommended_bias}")
        print(f"  Conviction:{v.conviction}")
        print(f"  Regime:    {v.regime}")
        print(f"  Driver:    {v.primary_driver}")
        print(f"  Trade:     {'✅' if v.should_trade else '❌ ' + v.no_trade_reason}")
        print(f"  Size×:     {v.position_size_multiplier}")
        print(f"  Narrative: {v.narrative_ar}")

    print("\n" + builder.get_telegram_report(views))
