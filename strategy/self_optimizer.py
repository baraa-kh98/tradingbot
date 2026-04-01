"""
Self Optimizer — تحسين ذاتي للاستراتيجية

يحلل أداء البوت ويقترح/يطبق تعديلات تلقائية:
1. رفع/خفض MIN_CONFLUENCE_SCORE حسب Win Rate
2. تعديل OB_BUFFER_PIPS حسب SL hits
3. تفضيل أنواع دخول ناجحة
4. تحسين Kill Zone filter
5. تقرير أسبوعي مع إحصائيات
"""

import json
import os
import config
from datetime import datetime


OPTIMIZER_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "journal", "optimizer_state.json"
)


class SelfOptimizer:
    """تحسين ذاتي — يتعلم من الصفقات السابقة"""

    def __init__(self, journal):
        """
        journal: TradeJournal instance
        """
        self.journal = journal
        self.state = self._load_state()

    def _load_state(self):
        """تحميل حالة المحسّن"""
        if os.path.exists(OPTIMIZER_FILE):
            try:
                with open(OPTIMIZER_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "adjustments": [],
            "last_review": None,
            "review_count": 0,
            "current_params": {},
        }

    def _save_state(self):
        """حفظ الحالة"""
        os.makedirs(os.path.dirname(OPTIMIZER_FILE), exist_ok=True)
        with open(OPTIMIZER_FILE, "w") as f:
            json.dump(self.state, f, indent=2, default=str)

    def analyze_and_suggest(self, min_trades=10):
        """
        تحليل الأداء واقتراح تعديلات

        returns: list of suggestions
        """
        stats = self.journal.get_stats()
        if stats.get("total", 0) < min_trades:
            return [f"📊 تحتاج {min_trades}+ صفقة ({stats.get('total', 0)} حالياً)"]

        suggestions = []
        adjustments = []

        # ─── 1. تعديل Confluence Score ───
        wr = stats["win_rate"]
        if wr < 35:
            suggestions.append({
                "param": "MIN_CONFLUENCE_SCORE",
                "action": "INCREASE",
                "reason": f"نسبة الفوز ضعيفة ({wr}%) — ارفع الحد الأدنى للالتقاء",
                "current": 60,
                "suggested": 70,
                "priority": "HIGH",
            })
        elif wr < 45:
            suggestions.append({
                "param": "MIN_CONFLUENCE_SCORE",
                "action": "SLIGHT_INCREASE",
                "reason": f"نسبة الفوز أقل من المطلوب ({wr}%)",
                "current": 60,
                "suggested": 65,
                "priority": "MEDIUM",
            })
        elif wr > 65 and stats["total"] > 20:
            suggestions.append({
                "param": "MIN_CONFLUENCE_SCORE",
                "action": "DECREASE",
                "reason": f"نسبة الفوز ممتازة ({wr}%) — يمكن تقليل الحد للحصول على المزيد من الصفقات",
                "current": 60,
                "suggested": 55,
                "priority": "LOW",
            })

        # ─── 2. تحليل SL Buffer ───
        closed = [t for t in self.journal.trades if t.get("status") == "CLOSED"]
        sl_hits = [t for t in closed if t.get("close_reason") == "SL"]
        if len(sl_hits) > 0:
            tight_sl = [t for t in sl_hits
                        if abs(t.get("entry", 0) - t.get("sl", 0)) / 0.01 < 20]  # أقل من 20 pips
            if len(tight_sl) > len(sl_hits) * 0.6:
                suggestions.append({
                    "param": "OB_BUFFER_PIPS",
                    "action": "INCREASE",
                    "reason": f"{len(tight_sl)}/{len(sl_hits)} SL hits بسبب SL ضيق",
                    "current": getattr(config, 'OB_BUFFER_PIPS', 5),
                    "suggested": getattr(config, 'OB_BUFFER_PIPS', 5) + 3,
                    "priority": "HIGH",
                })

        # ─── 3. تحليل أنواع الدخول ───
        for et, data in stats.get("by_entry_type", {}).items():
            total = data["wins"] + data["losses"]
            if total >= 5:
                wr = round(data["wins"] / total * 100, 1)
                if wr < 25:
                    suggestions.append({
                        "param": f"ENTRY_{et}",
                        "action": "AVOID",
                        "reason": f"دخول {et} فاشل ({wr}% فوز من {total} صفقة)",
                        "priority": "HIGH",
                    })
                elif wr > 75:
                    suggestions.append({
                        "param": f"ENTRY_{et}",
                        "action": "PREFER",
                        "reason": f"دخول {et} ممتاز ({wr}% فوز)",
                        "priority": "LOW",
                    })

        # ─── 4. تحليل الجلسات ───
        for sess, data in stats.get("by_session", {}).items():
            total = data["wins"] + data["losses"]
            if total >= 5 and data["pips"] < -30:
                suggestions.append({
                    "param": f"SESSION_{sess}",
                    "action": "AVOID",
                    "reason": f"جلسة {sess} خسارة ({data['pips']} pips من {total} صفقة)",
                    "priority": "MEDIUM",
                })

        # ─── 5. تحليل الاتجاه ───
        buy_s = stats.get("buy_stats", {})
        sell_s = stats.get("sell_stats", {})
        if buy_s.get("total", 0) >= 5 and sell_s.get("total", 0) >= 5:
            buy_wr = round(buy_s["wins"] / buy_s["total"] * 100, 1)
            sell_wr = round(sell_s["wins"] / sell_s["total"] * 100, 1)
            if buy_wr < 25:
                suggestions.append({
                    "param": "DIRECTION_FILTER",
                    "action": "AVOID_BUY",
                    "reason": f"BUY ضعيف جداً ({buy_wr}%) — فكّر بتقييده",
                    "priority": "MEDIUM",
                })
            if sell_wr < 25:
                suggestions.append({
                    "param": "DIRECTION_FILTER",
                    "action": "AVOID_SELL",
                    "reason": f"SELL ضعيف جداً ({sell_wr}%) — فكّر بتقييده",
                    "priority": "MEDIUM",
                })

        # ─── 6. Profit Factor ───
        pf = stats.get("profit_factor", 0)
        if pf < 1.0 and stats["total"] > 15:
            suggestions.append({
                "param": "OVERALL",
                "action": "REVIEW",
                "reason": f"Profit Factor أقل من 1 ({pf}) — الاستراتيجية خاسرة",
                "priority": "CRITICAL",
            })

        # حفظ
        self.state["adjustments"].extend(suggestions)
        self.state["last_review"] = datetime.now().isoformat()
        self.state["review_count"] += 1
        self._save_state()

        return suggestions

    def get_report(self):
        """تقرير التحسين لـ Telegram"""
        suggestions = self.analyze_and_suggest(min_trades=5)

        if not suggestions:
            return "✅ لا توجد توصيات حالياً — الأداء جيد"

        if isinstance(suggestions[0], str):
            return suggestions[0]

        lines = ["═══ 🧠 تقرير التحسين الذاتي ═══"]
        lines.append(f"📅 المراجعة #{self.state['review_count']}")

        priority_icons = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}

        for s in suggestions:
            icon = priority_icons.get(s.get("priority", "LOW"), "⚪")
            lines.append(f"\n{icon} {s['reason']}")
            if "suggested" in s:
                lines.append(f"   اقتراح: {s['param']} → {s['suggested']}")

        stats = self.journal.get_stats()
        lines.extend([
            f"\n── الأداء الحالي ──",
            f"📊 فوز: {stats.get('win_rate', 0)}% | PF: {stats.get('profit_factor', 0)}",
            f"💰 إجمالي: {stats.get('total_pips', 0)} pips",
        ])

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from risk.trade_journal import TradeJournal

    journal = TradeJournal()
    optimizer = SelfOptimizer(journal)

    print(optimizer.get_report())
