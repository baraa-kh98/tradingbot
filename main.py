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
from config import (
    CLAUDE_API_KEY,
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    BALANCE,
    RISK_PERCENT,
    MIN_RR_RATIO,
    USE_MACRO_FILTER,
    MACRO_MIN_SCORE,
)


def run_bot():
    """تشغيل البوت — دورة واحدة"""

    notifier = Notifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    notifier.send("🤖 البوت شغّال — تحليل ICT...")

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
    # 2. جلب البيانات (Multi-Timeframe)
    # ═══════════════════════════════════════════════════════════

    feed = DataFeed()

    try:
        htf_data = feed.get_htf_data()
        ltf_data = feed.get_ltf_data()
        current_price = feed.get_latest_price()

        if htf_data is None or ltf_data is None:
            notifier.send("❌ فشل جلب البيانات!")
            executor.disconnect()
            return

        notifier.send(f"📊 السعر الحالي: {current_price}")
    except Exception as e:
        notifier.send(f"❌ خطأ في جلب البيانات: {e}")
        executor.disconnect()
        return

    # ═══════════════════════════════════════════════════════════
    # 3. تحليل الماكرو (اختياري)
    # ═══════════════════════════════════════════════════════════

    macro_result = None
    if USE_MACRO_FILTER and CLAUDE_API_KEY:
        try:
            macro = MacroAnalyzer(CLAUDE_API_KEY)
            macro_result = macro.analyze()
            notifier.send(
                f"🌐 تحليل الماكرو:\n"
                f"Score: {macro_result['score']}\n"
                f"Bias: {macro_result['bias']}\n"
                f"السبب: {macro_result['reason']}"
            )

            if abs(macro_result["score"]) < MACRO_MIN_SCORE:
                notifier.send("⚠️ الماكرو محايد — يُؤخذ بعين الاعتبار")
        except Exception as e:
            notifier.send(f"⚠️ خطأ في تحليل الماكرو (مكمّلين): {e}")

    # ═══════════════════════════════════════════════════════════
    # 4. تحليل ICT وتوليد الإشارة
    # ═══════════════════════════════════════════════════════════

    try:
        signal_gen = ICTSignalGenerator(htf_data, ltf_data)
        signal = signal_gen.get_signal()
        levels = signal_gen.get_levels()

        # إرسال التقرير الكامل
        full_report = signal_gen.get_full_report()
        notifier.send(full_report)
    except Exception as e:
        notifier.send(f"❌ خطأ في تحليل ICT: {e}")
        executor.disconnect()
        return

    # ═══════════════════════════════════════════════════════════
    # 5. اتخاذ القرار
    # ═══════════════════════════════════════════════════════════

    if signal["action"] == "WAIT":
        notifier.send("⏳ لا توجد فرصة حالياً — البوت ينتظر...")
        executor.disconnect()
        return

    if levels is None:
        notifier.send("⚠️ لم يتم تحديد مستويات واضحة — البوت ينتظر...")
        executor.disconnect()
        return

    final_action = signal["action"]

    # فلتر الماكرو (اختياري)
    if USE_MACRO_FILTER and macro_result:
        if macro_result["bias"] == "BULLISH" and final_action == "SELL":
            if abs(macro_result["score"]) > 50:
                notifier.send("⚠️ ICT=SELL لكن الماكرو BULLISH قوي — ينتظر...")
                executor.disconnect()
                return
        elif macro_result["bias"] == "BEARISH" and final_action == "BUY":
            if abs(macro_result["score"]) > 50:
                notifier.send("⚠️ ICT=BUY لكن الماكرو BEARISH قوي — ينتظر...")
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
        f"📍 الاتجاه: {final_action}\n"
        f"💰 الدخول: {levels['entry']}\n"
        f"🛑 وقف الخسارة: {levels['stop_loss']}\n"
        f"🎯 هدف الربح: {levels['take_profit']}\n"
        f"📐 RR: 1:{levels['rr_ratio']}\n"
        f"📦 الحجم: {lots} lots\n"
        f"💵 المخاطرة: ${trade_info['risk_amount']}\n"
        f"🔑 نوع الدخول: {levels['entry_type']}\n"
        f"📊 الالتقاء: {signal['confluence_score']}/100"
        f"{tp_info}"
    )

    try:
        result = executor.place_order(
            signal=final_action,
            lots=lots,
            stop_loss=levels["stop_loss"],
            take_profit=levels["take_profit"],
        )

        if result:
            notifier.send(
                f"✅ تم تنفيذ الصفقة!\n"
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
            notifier.send("❌ فشل تنفيذ الصفقة على MT5")
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

    # الوضع المستمر 24/7
    notifier = Notifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    notifier.send(
        f"🤖 البوت بدأ التشغيل المستمر!\n"
        f"⏱️ فحص كل {SCAN_INTERVAL_MINUTES} دقيقة\n"
        f"📊 الزوج: USDJPY\n"
        f"🛡️ إدارة مخاطر: Partial TP + Trailing SL\n"
        f"💡 لإيقاف البوت: Ctrl+C"
    )

    # إعداد مراقب الصفقات
    feed = DataFeed()
    executor = Executor()
    rm = RiskManager(balance=BALANCE, risk_percent=RISK_PERCENT)
    monitor = TradeMonitor(executor, rm, feed, notifier)
    journal = TradeJournal()
    optimizer = SelfOptimizer(journal)

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
                            opt_report = optimizer.get_report()
                            notifier.send(opt_report)
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

            # تحليل فرص جديدة
            run_bot()

            print(f"\n⏰ الفحص التالي بعد {SCAN_INTERVAL_MINUTES} دقيقة...")
            time.sleep(SCAN_INTERVAL_MINUTES * 60)

        except KeyboardInterrupt:
            print("\n\n🛑 تم إيقاف البوت يدوياً")
            notifier.send("🛑 تم إيقاف البوت يدوياً")
            if executor.connected:
                executor.disconnect()
            break

        except Exception as e:
            print(f"\n❌ خطأ غير متوقع: {e}")
            notifier.send(f"❌ خطأ غير متوقع: {e}\n🔄 إعادة المحاولة بعد دقيقة...")
            time.sleep(60)
