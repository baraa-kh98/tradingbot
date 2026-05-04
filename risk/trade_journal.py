"""
Trade Journal — سجل الصفقات + تحليل الأداء

يسجل كل صفقة مع:
- تفاصيل الدخول (سبب، confluence، مستويات)
- النتيجة (ربح/خسارة، pips، وقت)
- تحليل ما بعد الصفقة (ما اشتغل وما ما اشتغل)

يُستخدم لـ:
1. تتبع الأداء بالوقت الحقيقي
2. اكتشاف أنماط الخسارة
3. تحسين الاستراتيجية تلقائياً
"""

import json
import os
import csv
from datetime import datetime
from config import PIP_VALUE


JOURNAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "journal")
TRADES_FILE = os.path.join(JOURNAL_DIR, "trades.json")
STATS_FILE = os.path.join(JOURNAL_DIR, "stats.json")
CSV_FILE = os.path.join(JOURNAL_DIR, "trades.csv")


class TradeJournal:
    """سجل الصفقات وتحليل الأداء"""

    def __init__(self):
        os.makedirs(JOURNAL_DIR, exist_ok=True)
        self.trades = self._load_trades()

    def _load_trades(self):
        """تحميل الصفقات المحفوظة"""
        if os.path.exists(TRADES_FILE):
            try:
                with open(TRADES_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ فشل تحميل سجل الصفقات ({TRADES_FILE}): {e}")
                return []
        return []

    def _save_trades(self):
        """حفظ الصفقات"""
        with open(TRADES_FILE, "w") as f:
            json.dump(self.trades, f, indent=2, default=str)

    # ═══════════════════════════════════════════════════════════
    # تسجيل الصفقات
    # ═══════════════════════════════════════════════════════════

    def log_trade_open(self, ticket, direction, entry, sl, tp, lots,
                       confluence_score, entry_type, reasons, session, bias):
        """تسجيل فتح صفقة"""
        trade = {
            "ticket": ticket,
            "status": "OPEN",
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "lots": lots,
            "open_time": datetime.now().isoformat(),
            "close_time": None,
            "close_price": None,
            "pnl": None,
            "pips": None,
            "rr_achieved": None,
            "confluence_score": confluence_score,
            "entry_type": entry_type,
            "reasons": reasons,
            "session": session,
            "htf_bias": bias,
            "modifications": [],
            "partial_closes": [],
            "lessons": [],
        }
        self.trades.append(trade)
        self._save_trades()
        return trade

    def log_trade_close(self, ticket, close_price, pnl, close_reason=""):
        """تسجيل إغلاق صفقة"""
        for trade in self.trades:
            if trade["ticket"] == ticket and trade["status"] == "OPEN":
                trade["status"] = "CLOSED"
                trade["close_time"] = datetime.now().isoformat()
                trade["close_price"] = close_price
                trade["pnl"] = round(pnl, 2)

                # حساب النقاط
                if trade["direction"] == "BUY":
                    trade["pips"] = round((close_price - trade["entry"]) / PIP_VALUE, 1)
                else:
                    trade["pips"] = round((trade["entry"] - close_price) / PIP_VALUE, 1)

                # RR المحقق
                risk = abs(trade["entry"] - trade["sl"])
                if risk > 0:
                    trade["rr_achieved"] = round(abs(close_price - trade["entry"]) / risk, 2)
                    if trade["pips"] < 0:
                        trade["rr_achieved"] = -trade["rr_achieved"]

                trade["close_reason"] = close_reason

                # تحليل تلقائي
                trade["lessons"] = self._analyze_trade(trade)

                self._save_trades()
                self._export_csv()
                return trade
        return None

    def log_modification(self, ticket, mod_type, old_value, new_value):
        """تسجيل تعديل على صفقة"""
        for trade in self.trades:
            if trade["ticket"] == ticket and trade["status"] == "OPEN":
                trade["modifications"].append({
                    "time": datetime.now().isoformat(),
                    "type": mod_type,
                    "old": old_value,
                    "new": new_value,
                })
                self._save_trades()
                return True
        return False

    def log_partial_close(self, ticket, lots_closed, price, pnl):
        """تسجيل إغلاق جزئي"""
        for trade in self.trades:
            if trade["ticket"] == ticket and trade["status"] == "OPEN":
                trade["partial_closes"].append({
                    "time": datetime.now().isoformat(),
                    "lots": lots_closed,
                    "price": price,
                    "pnl": round(pnl, 2),
                })
                self._save_trades()
                return True
        return False

    # ═══════════════════════════════════════════════════════════
    # تحليل تلقائي للصفقات
    # ═══════════════════════════════════════════════════════════

    def _analyze_trade(self, trade):
        """تحليل صفقة مغلقة واستخلاص الدروس"""
        lessons = []

        # ─── فوز أو خسارة ───
        if trade["pips"] and trade["pips"] > 0:
            if trade["rr_achieved"] and trade["rr_achieved"] >= 2:
                lessons.append("✅ صفقة ممتازة — حققت 2R+")
            else:
                lessons.append("✅ صفقة رابحة")

            if trade["confluence_score"] >= 80:
                lessons.append("📊 الالتقاء العالي أعطى نتيجة جيدة")
        else:
            # تحليل أسباب الخسارة
            if trade["confluence_score"] < 65:
                lessons.append("⚠️ الالتقاء كان ضعيف — ارفع الحد الأدنى؟")

            if trade["entry_type"] == "MARKET":
                lessons.append("⚠️ دخول سوق (بدون OB/FVG) — نتائج ضعيفة عادةً")

            # هل SL كان ضيق جداً؟
            risk_pips = abs(trade["entry"] - trade["sl"]) / PIP_VALUE
            if risk_pips < 15:
                lessons.append("⚠️ SL ضيق جداً — زيد مسافة OB Buffer؟")

            # هل كان عكس HTF bias؟
            if trade.get("htf_bias"):
                bias_dir = trade["htf_bias"]
                if isinstance(bias_dir, dict):
                    bias_dir = bias_dir.get("direction", "")
                if trade["direction"] == "BUY" and bias_dir == "BEARISH":
                    lessons.append("🔴 الدخول كان عكس HTF Bias!")
                elif trade["direction"] == "SELL" and bias_dir == "BULLISH":
                    lessons.append("🔴 الدخول كان عكس HTF Bias!")

            # هل الجلسة كانت kill zone؟
            session = trade.get("session", "")
            if isinstance(session, dict):
                if not session.get("is_kill_zone"):
                    lessons.append("⚠️ دخول خارج Kill Zone")

        return lessons

    # ═══════════════════════════════════════════════════════════
    # تحليل الأداء
    # ═══════════════════════════════════════════════════════════

    def get_stats(self):
        """إحصائيات الأداء الشاملة"""
        closed = [t for t in self.trades if t["status"] == "CLOSED"]
        if not closed:
            return {"total": 0, "message": "لا توجد صفقات مغلقة بعد"}

        wins = [t for t in closed if t.get("pips", 0) > 0]
        losses = [t for t in closed if t.get("pips", 0) <= 0]

        total_pips = sum(t.get("pips", 0) for t in closed)
        total_pnl = sum(t.get("pnl", 0) for t in closed)

        avg_win_pips = sum(t.get("pips", 0) for t in wins) / len(wins) if wins else 0
        avg_loss_pips = sum(t.get("pips", 0) for t in losses) / len(losses) if losses else 0

        # أفضل وأسوأ صفقة
        best = max(closed, key=lambda t: t.get("pips", 0))
        worst = min(closed, key=lambda t: t.get("pips", 0))

        # تحليل حسب نوع الدخول
        by_entry_type = {}
        for t in closed:
            et = t.get("entry_type", "UNKNOWN")
            if et not in by_entry_type:
                by_entry_type[et] = {"wins": 0, "losses": 0, "pips": 0}
            if t.get("pips", 0) > 0:
                by_entry_type[et]["wins"] += 1
            else:
                by_entry_type[et]["losses"] += 1
            by_entry_type[et]["pips"] += t.get("pips", 0)

        # تحليل حسب الجلسة
        by_session = {}
        for t in closed:
            sess = t.get("session", {})
            s_name = sess.get("session", "UNKNOWN") if isinstance(sess, dict) else str(sess)
            if s_name not in by_session:
                by_session[s_name] = {"wins": 0, "losses": 0, "pips": 0}
            if t.get("pips", 0) > 0:
                by_session[s_name]["wins"] += 1
            else:
                by_session[s_name]["losses"] += 1
            by_session[s_name]["pips"] += t.get("pips", 0)

        # تحليل حسب الاتجاه
        buy_trades = [t for t in closed if t["direction"] == "BUY"]
        sell_trades = [t for t in closed if t["direction"] == "SELL"]

        # Profit Factor
        gross_profit = sum(t.get("pips", 0) for t in wins)
        gross_loss = abs(sum(t.get("pips", 0) for t in losses))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

        # تحليل الالتقاء
        high_conf = [t for t in closed if t.get("confluence_score", 0) >= 80]
        low_conf = [t for t in closed if t.get("confluence_score", 0) < 70]

        stats = {
            "total": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed) * 100, 1),
            "total_pips": round(total_pips, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_win_pips": round(avg_win_pips, 1),
            "avg_loss_pips": round(avg_loss_pips, 1),
            "profit_factor": profit_factor,
            "best_trade": {"pips": best.get("pips", 0), "ticket": best["ticket"]},
            "worst_trade": {"pips": worst.get("pips", 0), "ticket": worst["ticket"]},
            "by_entry_type": by_entry_type,
            "by_session": by_session,
            "buy_stats": {
                "total": len(buy_trades),
                "wins": len([t for t in buy_trades if t.get("pips", 0) > 0]),
                "pips": round(sum(t.get("pips", 0) for t in buy_trades), 1),
            },
            "sell_stats": {
                "total": len(sell_trades),
                "wins": len([t for t in sell_trades if t.get("pips", 0) > 0]),
                "pips": round(sum(t.get("pips", 0) for t in sell_trades), 1),
            },
            "high_confluence": {
                "total": len(high_conf),
                "wins": len([t for t in high_conf if t.get("pips", 0) > 0]),
                "win_rate": round(len([t for t in high_conf if t.get("pips", 0) > 0]) / len(high_conf) * 100, 1) if high_conf else 0,
            },
            "low_confluence": {
                "total": len(low_conf),
                "wins": len([t for t in low_conf if t.get("pips", 0) > 0]),
                "win_rate": round(len([t for t in low_conf if t.get("pips", 0) > 0]) / len(low_conf) * 100, 1) if low_conf else 0,
            },
        }

        # حفظ الإحصائيات
        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=2, default=str)

        return stats

    def get_lessons_summary(self, last_n=20):
        """ملخص الدروس من آخر N صفقة"""
        closed = [t for t in self.trades if t["status"] == "CLOSED"][-last_n:]
        if not closed:
            return "لا توجد صفقات بعد"

        all_lessons = []
        for t in closed:
            for lesson in t.get("lessons", []):
                all_lessons.append(lesson)

        # حساب تكرار كل درس
        lesson_counts = {}
        for lesson in all_lessons:
            lesson_counts[lesson] = lesson_counts.get(lesson, 0) + 1

        # ترتيب حسب التكرار
        sorted_lessons = sorted(lesson_counts.items(), key=lambda x: x[1], reverse=True)

        lines = [f"📚 دروس من آخر {len(closed)} صفقة:"]
        for lesson, count in sorted_lessons[:10]:
            lines.append(f"  ({count}x) {lesson}")

        return "\n".join(lines)

    def get_recommendations(self):
        """توصيات تلقائية لتحسين الأداء"""
        stats = self.get_stats()
        if stats.get("total", 0) < 5:
            return "📊 تحتاج 5+ صفقات لتوليد توصيات"

        recs = ["═══ توصيات التحسين ═══"]

        # 1. Win Rate
        if stats["win_rate"] < 40:
            recs.append("🔴 نسبة الفوز ضعيفة — ارفع MIN_CONFLUENCE_SCORE")
        elif stats["win_rate"] > 65:
            recs.append("✅ نسبة الفوز ممتازة!")

        # 2. Entry Type analysis
        for et, data in stats["by_entry_type"].items():
            total = data["wins"] + data["losses"]
            if total >= 3:
                wr = round(data["wins"] / total * 100, 1)
                if wr < 30:
                    recs.append(f"⚠️ دخول {et} ضعيف ({wr}% فوز) — قلّل استخدامه")
                elif wr > 70:
                    recs.append(f"✅ دخول {et} ممتاز ({wr}% فوز) — زيد استخدامه")

        # 3. Session analysis
        for sess, data in stats["by_session"].items():
            total = data["wins"] + data["losses"]
            if total >= 3 and data["pips"] < -20:
                recs.append(f"⚠️ جلسة {sess} خاسرة ({data['pips']}p) — تجنبها")

        # 4. Higher confluence = better?
        if stats["high_confluence"]["total"] >= 3 and stats["low_confluence"]["total"] >= 3:
            if stats["high_confluence"]["win_rate"] > stats["low_confluence"]["win_rate"] + 10:
                recs.append(f"📊 التقاء عالي أفضل بكثير ({stats['high_confluence']['win_rate']}% vs {stats['low_confluence']['win_rate']}%)")

        # 5. Direction bias
        if stats["buy_stats"]["total"] >= 3 and stats["sell_stats"]["total"] >= 3:
            buy_wr = round(stats["buy_stats"]["wins"] / stats["buy_stats"]["total"] * 100, 1)
            sell_wr = round(stats["sell_stats"]["wins"] / stats["sell_stats"]["total"] * 100, 1)
            if abs(buy_wr - sell_wr) > 20:
                better = "BUY" if buy_wr > sell_wr else "SELL"
                recs.append(f"📈 {better} أقوى ({buy_wr}% vs {sell_wr}%) — ركّز عليه")

        if len(recs) == 1:
            recs.append("✅ الأداء جيد — استمر بنفس الطريقة")

        return "\n".join(recs)

    def get_telegram_report(self):
        """تقرير أسبوعي لـ Telegram"""
        stats = self.get_stats()
        if stats.get("total", 0) == 0:
            return "📊 لا توجد صفقات بعد"

        report = [
            "═══ 📊 تقرير الأداء ═══",
            f"📈 صفقات: {stats['total']} ({stats['wins']}W / {stats['losses']}L)",
            f"🎯 نسبة الفوز: {stats['win_rate']}%",
            f"💰 إجمالي: {stats['total_pips']}p (${stats['total_pnl']})",
            f"📊 متوسط الربح: +{stats['avg_win_pips']}p | خسارة: {stats['avg_loss_pips']}p",
            f"⚖️ Profit Factor: {stats['profit_factor']}",
            f"🏆 أفضل: +{stats['best_trade']['pips']}p",
            f"💀 أسوأ: {stats['worst_trade']['pips']}p",
        ]

        # BUY vs SELL
        bs = stats["buy_stats"]
        ss = stats["sell_stats"]
        if bs["total"] > 0:
            report.append(f"\n📈 BUY: {bs['wins']}/{bs['total']} ({bs['pips']}p)")
        if ss["total"] > 0:
            report.append(f"📉 SELL: {ss['wins']}/{ss['total']} ({ss['pips']}p)")

        # أفضل نوع دخول
        report.append("\n── حسب نوع الدخول ──")
        for et, data in stats["by_entry_type"].items():
            total = data["wins"] + data["losses"]
            wr = round(data["wins"] / total * 100, 1) if total > 0 else 0
            report.append(f"  {et}: {wr}% ({data['pips']}p)")

        return "\n".join(report)

    # ═══════════════════════════════════════════════════════════
    # تصدير CSV
    # ═══════════════════════════════════════════════════════════

    def _export_csv(self):
        """تصدير الصفقات لملف CSV"""
        closed = [t for t in self.trades if t["status"] == "CLOSED"]
        if not closed:
            return

        fields = ["ticket", "direction", "open_time", "close_time", "entry",
                  "sl", "tp", "close_price", "lots", "pips", "pnl",
                  "rr_achieved", "confluence_score", "entry_type", "close_reason"]

        with open(CSV_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for t in closed:
                row = {k: t.get(k, "") for k in fields}
                writer.writerow(row)


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    journal = TradeJournal()

    print("═══ Trade Journal Test ═══\n")

    # محاكاة صفقات
    journal.log_trade_open(
        ticket=12345, direction="BUY", entry=144.500, sl=144.200,
        tp=145.400, lots=0.03, confluence_score=78, entry_type="OB",
        reasons=["BOS_BULLISH", "Bullish OB", "Discount Zone"],
        session={"session": "LONDON", "is_kill_zone": True},
        bias={"direction": "BULLISH"}
    )
    journal.log_trade_close(12345, close_price=145.100, pnl=18.0, close_reason="TP1")

    journal.log_trade_open(
        ticket=12346, direction="SELL", entry=145.200, sl=145.500,
        tp=144.500, lots=0.03, confluence_score=62, entry_type="FVG",
        reasons=["BOS_BEARISH", "Bearish FVG"],
        session={"session": "NY_AM", "is_kill_zone": True},
        bias={"direction": "BEARISH"}
    )
    journal.log_trade_close(12346, close_price=145.450, pnl=-7.5, close_reason="SL")

    journal.log_trade_open(
        ticket=12347, direction="BUY", entry=144.800, sl=144.600,
        tp=145.200, lots=0.03, confluence_score=85, entry_type="OB",
        reasons=["CHoCH_BULLISH", "Bullish OB", "Silver Bullet", "Discount"],
        session={"session": "LONDON", "is_kill_zone": True},
        bias={"direction": "BULLISH"}
    )
    journal.log_trade_close(12347, close_price=145.150, pnl=10.5, close_reason="TP")

    # عرض النتائج
    stats = journal.get_stats()
    print(f"📊 صفقات: {stats['total']} | فوز: {stats['win_rate']}%")
    print(f"💰 إجمالي: {stats['total_pips']}p | ${stats['total_pnl']}")

    print(f"\n{journal.get_lessons_summary()}")
    print(f"\n{journal.get_recommendations()}")
    print(f"\n{journal.get_telegram_report()}")
