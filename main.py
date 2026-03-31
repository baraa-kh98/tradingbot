"""
ICT Trading Bot — البوت الرئيسي

يستخدم:
- Twelve Data: لجلب البيانات
- MetaTrader 5: لتنفيذ الصفقات
- استراتيجية ICT: Market Structure, OB, FVG, Liquidity
- Claude AI: تحليل ماكرو (اختياري)
- Telegram: إرسال التقارير والإشعارات
"""

from data.data_feed import DataFeed
from data.macro_analyzer import MacroAnalyzer
from strategy.signal_generator import ICTSignalGenerator
from strategy.kill_zones import get_current_session
from risk.risk_manager import RiskManager
from risk.trade_monitor import TradeMonitor
from risk.trade_journal import TradeJournal
from strategy.self_optimizer import SelfOptimizer
from execution.executor import Executor
from notifier import Notifier
from telegram_dashboard import TelegramDashboard
from data.market_intelligence import MarketIntelligence
from config import (
    CLAUDE_API_KEY,
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    BALANCE,
    RISK_PERCENT,
    MIN_RR_RATIO,
    USE_MACRO_FILTER,
    MACRO_MIN_SCORE,
    ACTIVE_PAIRS,
)


def run_bot():
    """تشغيل البوت — فحص جميع الأزواج واختيار الأفضل"""

    notifier = Notifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    notifier.send(f"🤖 البوت شغّال — فحص {len(ACTIVE_PAIRS)} أزواج...")

    # ═══════════════════════════════════════════════════════════
    # 1. الاتصال بـ MT5
    # ═══════════════════════════════════════════════════════════

    executor = Executor()
    if not executor.connect():
        notifier.send("❌ فشل الاتصال بـ MT5!")
        return

    account = executor.get_account_info()
    if account:
        notifier.send(
            f"💰 الحساب: {account['login']}\n"
            f"الرصيد: ${account['balance']:.2f}\n"
            f"{'🟢 Demo' if account['is_demo'] else '🔴 Real'}"
        )

    # ═══════════════════════════════════════════════════════════
    # 2. ذكاء السوق (أخبار + سنتيمنت)
    # ═══════════════════════════════════════════════════════════

    macro_result = None
    intel = MarketIntelligence()
    try:
        can_trade, blockers, intel_data = intel.should_trade()
        notifier.send(intel.get_report())

        if not can_trade:
            notifier.send(f"🚫 ظروف غير مناسبة:\n" + "\n".join(blockers))
            executor.disconnect()
            return

        intel_bias, intel_score, _ = intel.get_usdjpy_bias()
        macro_result = {"bias": intel_bias, "score": intel_score}
    except Exception as e:
        print(f"⚠️ خطأ في ذكاء السوق (مكمّلين): {e}")

    # ═══════════════════════════════════════════════════════════
    # 3. فحص جميع الأزواج (Multi-Pair Scanner)
    # ═══════════════════════════════════════════════════════════

    from strategy.multi_pair import MultiPairScanner

    scanner = MultiPairScanner()
    scanner.scan_all()

    # إرسال تقرير الفحص
    notifier.send(scanner.get_report())

    # الصفقات المفتوحة حالياً
    open_positions = executor.get_open_positions()
    open_pairs = set()
    for pos in open_positions:
        for pname, pcfg in TRADING_PAIRS.items():
            if pcfg["mt5"] in str(getattr(pos, "symbol", "")):
                open_pairs.add(pname)

    # اختيار أفضل فرصة مع فلتر الارتباط
    best = scanner.get_best_opportunity(open_pairs=open_pairs)

    if best is None:
        notifier.send("⏳ لا توجد فرص بالتقاء كافي — ننتظر...")
        executor.disconnect()
        return

    # ═══════════════════════════════════════════════════════════
    # 4. تنفيذ أفضل فرصة
    # ═══════════════════════════════════════════════════════════

    pair_name = best["pair"]
    pair_config = best["config"]
    signal = best
    levels = best["levels"]
    final_action = best["action"]

    notifier.send(
        f"🏆 أفضل فرصة: {pair_name}\n"
        f"📍 {final_action} | التقاء: {best['score']}/140"
    )

    if levels is None:
        notifier.send(f"⚠️ لم يتم تحديد مستويات لـ {pair_name}")
        executor.disconnect()
        return

    # فلتر الماكرو
    if macro_result:
        if macro_result["bias"] == "BULLISH" and final_action == "SELL":
            if abs(macro_result["score"]) > 50:
                notifier.send("⚠️ ICT=SELL لكن ذكاء السوق BULLISH قوي — ينتظر...")
                executor.disconnect()
                return
        elif macro_result["bias"] == "BEARISH" and final_action == "BUY":
            if abs(macro_result["score"]) > 50:
                notifier.send("⚠️ ICT=BUY لكن ذكاء السوق BEARISH قوي — ينتظر...")
                executor.disconnect()
                return

    # ═══════════════════════════════════════════════════════════
    # 6. إدارة المخاطر المتقدمة
    # ═══════════════════════════════════════════════════════════

    # استخدام رصيد الحساب الحقيقي إذا متصل
    balance = account["balance"] if account else BALANCE

    rm = RiskManager(balance=balance, risk_percent=RISK_PERCENT)

    # فحص الحدود اليومية
    open_positions = executor.get_open_positions()
    can_trade, trade_reason = rm.can_trade(len(open_positions))
    if not can_trade:
        notifier.send(f"{trade_reason}")
        executor.disconnect()
        return

    trade_info = rm.get_trade_info(
        levels["entry"],
        levels["stop_loss"],
        levels["take_profit"]
    )

    if not trade_info["trade_valid"]:
        notifier.send(
            f"⚠️ نسبة الربح/الخسارة ضعيفة ({trade_info['rr_ratio']}) "
            f"— الحد الأدنى: {MIN_RR_RATIO}"
        )
        executor.disconnect()
        return

    # ═══════════════════════════════════════════════════════════
    # 7. تنفيذ الصفقة على MT5
    # ═══════════════════════════════════════════════════════════

    lots = trade_info["lots"]

    # TP متعدد
    tp_info = ""
    tp_levels = trade_info.get("tp_levels")
    if tp_levels:
        tp_info = (
            f"\n🎯 TP1: {tp_levels['tp1']} ({tp_levels['tp1_rr']}R) — أغلق {int(tp_levels['tp1_close_ratio']*100)}%"
            f"\n🎯 TP2: {tp_levels['tp2']} ({tp_levels['tp2_rr']}R) — الباقي"
            f"\n🔒 Break-Even عند 1R"
            f"\n📈 Trailing Stop بعد 1.5R"
        )

    notifier.send(
        f"🚀 تنفيذ صفقة ICT على MT5:\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🌍 الزوج: {pair_name}\n"
        f"📍 الاتجاه: {final_action}\n"
        f"💰 الدخول: {levels['entry']}\n"
        f"🛑 وقف الخسارة: {levels['stop_loss']}\n"
        f"🎯 هدف الربح: {levels['take_profit']}\n"
        f"📐 RR: 1:{levels['rr_ratio']}\n"
        f"📦 الحجم: {lots} lots\n"
        f"💵 المخاطرة: ${trade_info['risk_amount']}\n"
        f"🔑 نوع الدخول: {levels['entry_type']}\n"
        f"📊 الالتقاء: {best['score']}/140"
        f"{tp_info}"
    )

    try:
        result = executor.place_order(
            signal=final_action,
            lots=lots,
            stop_loss=levels["stop_loss"],
            take_profit=levels["take_profit"],
            entry_price=levels["entry"],
            symbol=pair_config["mt5"],
        )

        if result:
            order_type = result.get("order_type", "MARKET")
            order_icon = "🔄" if order_type == "MARKET" else "⏳"
            notifier.send(
                f"✅ تم تنفيذ الصفقة!\n"
                f"{order_icon} النوع: {order_type}\n"
                f"Ticket: #{result['ticket']}\n"
                f"السعر: {result['price']}"
            )

            # تسجيل الصفقة في اليوميات
            try:
                journal = TradeJournal()
                journal.log_trade_open(
                    ticket=result['ticket'],
                    direction=final_action,
                    entry=result['price'],
                    sl=levels['stop_loss'],
                    tp=levels['take_profit'],
                    lots=lots,
                    confluence_score=signal['confluence_score'],
                    entry_type=levels['entry_type'],
                    reasons=signal.get('details', []),
                    session=signal.get('session', ''),
                    bias=signal.get('bias', ''),
                )
            except Exception as je:
                print(f"⚠️ فشل تسجيل الصفقة: {je}")
        else:
            sym = executor.get_symbol_info()
            current = f"Bid:{sym['bid']} Ask:{sym['ask']}" if sym else "?"
            notifier.send(
                f"❌ فشل تنفيذ الصفقة على MT5\n"
                f"📍 السعر الحالي: {current}\n"
                f"📦 اللوت: {lots}\n"
                f"تحقق من: AutoTrading مفعّل + الرصيد كافي"
            )
    except Exception as e:
        notifier.send(f"❌ خطأ في التنفيذ: {e}")

    executor.disconnect()


# ═══════════════════════════════════════════════════════════════
# التشغيل المستمر
# ═══════════════════════════════════════════════════════════════

SCAN_INTERVAL_MINUTES = 15  # كل 15 دقيقة يحلل السوق


def is_market_open():
    """تحقق إذا سوق الفوركس مفتوح (مغلق السبت والأحد)"""
    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone("US/Eastern"))
    # الفوركس مغلق: الجمعة 17:00 EST → الأحد 17:00 EST
    if now.weekday() == 5:  # السبت
        return False
    if now.weekday() == 6 and now.hour < 17:  # الأحد قبل 5 مساءً
        return False
    if now.weekday() == 4 and now.hour >= 17:  # الجمعة بعد 5 مساءً
        return False
    return True


if __name__ == "__main__":
    import time
    import sys

    # وضع الدورة الواحدة
    if "--once" in sys.argv:
        print("🔄 وضع الدورة الواحدة...")
        run_bot()
        sys.exit(0)

    # حالة البوت المشتركة
    bot_state = {
        "paused": False,
        "cycle": 0,
        "last_scan": "",
        "open_trades": 0,
        "active_pairs": ACTIVE_PAIRS,
    }

    # Telegram Dashboard
    dashboard = TelegramDashboard(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, bot_state)

    # تسجيل أوامر إضافية
    def cmd_report(args=None):
        try:
            return journal.get_telegram_report()
        except Exception as e:
            return f"❌ {e}"

    def cmd_analyze(args=None):
        try:
            f = DataFeed()
            htf = f.get_htf_data()
            ltf = f.get_ltf_data()
            if htf is not None:
                gen = ICTSignalGenerator(htf, ltf)
                return gen.get_full_report()
            return "❌ فشل جلب البيانات"
        except Exception as e:
            return f"❌ {e}"

    def cmd_lessons(args=None):
        try:
            return journal.get_lessons_summary() + "\n\n" + journal.get_recommendations()
        except Exception as e:
            return f"❌ {e}"

    def cmd_pairs(args=None):
        from config import TRADING_PAIRS
        lines = ["═══ 🌍 الأزواج ═══"]
        for name, cfg in TRADING_PAIRS.items():
            icon = "✅" if cfg["enabled"] else "❌"
            lines.append(f"{icon} {name} — spread: {cfg['spread_pips']}p")
        lines.append("\nلتفعيل/تعطيل: عدّل config.py")
        return "\n".join(lines)

    def cmd_news(args=None):
        try:
            intel = MarketIntelligence()
            return intel.get_report()
        except Exception as e:
            return f"❌ {e}"

    def cmd_scan(args=None):
        try:
            from strategy.multi_pair import MultiPairScanner
            dash_scanner = MultiPairScanner()
            dash_scanner.scan_all()
            return dash_scanner.get_report()
        except Exception as e:
            return f"❌ خطأ في فحص الأزواج: {e}"

    dashboard.register_handler("report", cmd_report)
    dashboard.register_handler("analyze", cmd_analyze)
    dashboard.register_handler("lessons", cmd_lessons)
    dashboard.register_handler("pairs", cmd_pairs)
    dashboard.register_handler("news", cmd_news)
    dashboard.register_handler("scan", cmd_scan)

    dashboard.start_polling()

    dashboard.send(
        f"🤖 البوت بدأ التشغيل المستمر!\n"
        f"⏱️ فحص كل {SCAN_INTERVAL_MINUTES} دقيقة\n"
        f"📊 الزوج: USDJPY\n"
        f"🛡️ إدارة مخاطر: Partial TP + Trailing SL\n"
        f"📲 لوحة التحكم: /help\n"
        f"💡 لإيقاف البوت: Ctrl+C"
    )

    # إعداد مراقب الصفقات
    feed = DataFeed()
    executor = Executor()
    rm = RiskManager(balance=BALANCE, risk_percent=RISK_PERCENT)
    monitor = TradeMonitor(executor, rm, feed, dashboard)
    journal = TradeJournal()
    optimizer_self = SelfOptimizer(journal)
    notifier = dashboard  # للتوافق مع الكود القديم

    cycle = 0
    last_day = None
    last_report_day = None

    while True:
        cycle += 1

        try:
            # إعادة تعيين الحدود اليومية عند بداية يوم جديد
            from datetime import datetime
            today = datetime.now().date()
            if last_day != today:
                rm.reset_daily()
                last_day = today
                if cycle > 1:
                    # تقرير يومي
                    try:
                        report = journal.get_telegram_report()
                        notifier.send(f"📅 يوم جديد\n{report}")
                    except Exception:
                        notifier.send("📅 يوم جديد — إعادة تعيين الحدود اليومية")

                    # تقرير أسبوعي (كل أحد)
                    if today.weekday() == 6 and last_report_day != today:
                        last_report_day = today
                        try:
                            opt_report = optimizer_self.get_report()
                            dashboard.send(opt_report)
                        except Exception:
                            pass

            if not is_market_open():
                print(f"\n⏸️ [{time.strftime('%H:%M')}] السوق مغلق (عطلة نهاية الأسبوع)")
                print(f"   ⏰ الفحص التالي بعد 60 دقيقة...")
                time.sleep(60 * 60)
                continue

            print(f"\n{'═' * 50}")
            print(f"   🔄 الدورة #{cycle} — {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'═' * 50}")

            # مراقبة الصفقات المفتوحة (كل دورة)
            if executor.connected or executor.connect():
                mods = monitor.check_and_manage()
                if mods > 0:
                    print(f"   📊 تم تعديل {mods} صفقة")

                status = monitor.get_status()
                print(f"   {status}")

            # تحقق من الإيقاف المؤقت
            if bot_state.get("paused"):
                print(f"   ⏸️ البوت متوقف مؤقتاً (اكتب /resume)")
                time.sleep(30)
                continue

            # تحديث حالة البوت
            bot_state["cycle"] = cycle
            bot_state["last_scan"] = time.strftime("%H:%M:%S")

            # تحليل فرص جديدة
            run_bot()

            print(f"\n⏰ الفحص التالي بعد {SCAN_INTERVAL_MINUTES} دقيقة...")
            time.sleep(SCAN_INTERVAL_MINUTES * 60)

        except KeyboardInterrupt:
            print("\n\n🛑 تم إيقاف البوت يدوياً")
            dashboard.send("🛑 تم إيقاف البوت يدوياً")
            dashboard.stop_polling()
            if executor.connected:
                executor.disconnect()
            break

        except Exception as e:
            print(f"\n❌ خطأ غير متوقع: {e}")
            notifier.send(f"❌ خطأ غير متوقع: {e}\n🔄 إعادة المحاولة بعد دقيقة...")
            time.sleep(60)
