"""
London Breakout Trading Bot — البوت الرئيسي
=============================================
الاستراتيجية: London Breakout (مثبتة بالباكتست)
  +17.81% / سنتين | Sharpe 0.97 | Max DD -5.68%

المنطق:
  1. احسب Asia Range (00:00-06:59 UTC)
  2. عند London Open (07:00-09:59 UTC):
       Break فوق High → BUY | Break تحت Low → SELL
  3. فلتر H4 Bias + فلتر MarketView (Quant)
  4. SL = Asia Range الآخر | TP = 3.0 × Risk
  5. Trailing Stop: Breakeven عند 1:1 + Lock عند 2:1
"""

from data.data_feed import DataFeed
from data.macro_analyzer import MacroAnalyzer
from strategy.london_signal import LondonSignalGenerator
from strategy.market_view_builder import MarketViewBuilder
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
    ACTIVE_PAIRS,
    TRADING_PAIRS,
    REQUIRE_VIEW_ALIGNMENT,
)

# ── London generators لكل زوج (تُحدَّث في كل دورة) ──
_london_generators: dict = {}


def run_bot():
    """
    تشغيل البوت — London Breakout Strategy
    يفحص جميع الأزواج المفعّلة ويدخل عند كسر Range آسيا
    """
    global _london_generators

    notifier = Notifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)

    # ═══════════════════════════════════════════════════════════
    # 1. الاتصال بـ MT5
    # ═══════════════════════════════════════════════════════════

    executor = Executor()
    if not executor.connect():
        notifier.send("❌ فشل الاتصال بـ MT5!")
        return

    account = executor.get_account_info()
    balance = account["balance"] if account else BALANCE

    # ═══════════════════════════════════════════════════════════
    # 2. فحص الظروف العامة (اختياري — لا يوقف البوت)
    # ═══════════════════════════════════════════════════════════

    intel = MarketIntelligence()
    try:
        can_trade, blockers, _ = intel.should_trade()
        if not can_trade:
            notifier.send(f"🚫 ظروف غير مناسبة للتداول اليوم:\n" + "\n".join(blockers))
            executor.disconnect()
            return
    except Exception as e:
        print(f"⚠️ MarketIntelligence: {e} — مكمّلين بدونها")

    # ═══════════════════════════════════════════════════════════
    # 3. فحص ساعة لندن
    # ═══════════════════════════════════════════════════════════

    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    hour    = now_utc.hour

    if not (7 <= hour < 10):
        print(f"⏰ ليس وقت لندن (07-10 UTC) — الساعة الحالية: {hour}:00 UTC")
        executor.disconnect()
        return

    # ═══════════════════════════════════════════════════════════
    # 4. جلب البيانات + توليد الإشارات لكل زوج
    # ═══════════════════════════════════════════════════════════

    feed = DataFeed()
    signals_found = []

    for pair in ACTIVE_PAIRS:
        try:
            cfg   = TRADING_PAIRS[pair]
            td_sym = cfg["td"]

            # H1: آخر 200 شمعة (كافية لحساب Asia Range + ATR)
            h1_feed = DataFeed(td_sym)
            h1 = h1_feed.get_historical_range(days=8, interval="1h")

            # H4: آخر 120 شمعة (كافية لـ EMA20/50)
            h4 = h1_feed.get_historical_range(days=30, interval="4h")

            if h1 is None or len(h1) < 20:
                print(f"  ⚠️ {pair}: بيانات H1 غير كافية")
                continue

            # أنشئ أو حدّث Generator
            gen = _london_generators.get(pair)
            if gen is None:
                gen = LondonSignalGenerator(pair, h1, h4)
                _london_generators[pair] = gen
            else:
                gen.h1 = h1
                if h4 is not None:
                    gen.h4 = h4

            signal = gen.get_signal()

            if signal:
                signals_found.append((pair, cfg, gen, signal))
                print(f"  🎯 {pair}: إشارة {signal['direction']} مكتشفة!")
            else:
                # أرسل تقرير المراقبة (لكل زوج كل ساعة)
                print(f"  ⏳ {pair}: {gen.get_session_report()}")

        except Exception as e:
            print(f"  ❌ {pair}: خطأ — {e}")

    if not signals_found:
        print("⏳ لا توجد إشارات London Breakout حالياً")
        executor.disconnect()
        return

    # ═══════════════════════════════════════════════════════════
    # 5. النظرة السوقية الكوانتية (MarketViewBuilder)
    # ═══════════════════════════════════════════════════════════

    market_views = {}
    try:
        view_builder = MarketViewBuilder()
        ict_signals_for_view = {
            pair: {"bias": sig["direction"], "score": 80}
            for pair, cfg, gen, sig in signals_found
        }
        market_views = view_builder.build_all_views(ict_signals_for_view)
        notifier.send(view_builder.get_telegram_report(market_views))
    except Exception as e:
        print(f"⚠️ MarketViewBuilder: {e}")

    # ═══════════════════════════════════════════════════════════
    # 6. تنفيذ الإشارات
    # ═══════════════════════════════════════════════════════════

    rm = RiskManager(balance=balance, risk_percent=RISK_PERCENT)
    open_positions = executor.get_open_positions()
    open_pairs = set()
    for pos in open_positions:
        for pname, pcfg in TRADING_PAIRS.items():
            if pcfg["mt5"] in str(getattr(pos, "symbol", "")):
                open_pairs.add(pname)

    for pair, cfg, gen, signal in signals_found:

        # لا تفتح على زوج مفتوح مسبقاً
        if pair in open_pairs:
            notifier.send(f"⏩ {pair}: صفقة مفتوحة مسبقاً — يتجاوز")
            continue

        direction = signal["direction"]

        # ── فلتر MarketView ────────────────────────────────────
        view = market_views.get(pair)
        if view and REQUIRE_VIEW_ALIGNMENT:
            if not getattr(view, "should_trade", True):
                notifier.send(
                    f"⛔ {pair}: محظور بواسطة Market View ({getattr(view, 'no_trade_reason', '')})"
                )
                continue

        # ── فحص حدود المخاطرة ─────────────────────────────────
        can_trade, trade_reason = rm.can_trade(len(open_positions))
        if not can_trade:
            notifier.send(trade_reason)
            break

        # ── حجم اللوت ────────────────────────────────────────
        trade_info = rm.get_trade_info(
            signal["entry"], signal["sl"], signal["tp"]
        )
        if not trade_info["trade_valid"]:
            notifier.send(
                f"⚠️ {pair}: RR = {trade_info.get('rr_ratio', '?')} < {MIN_RR_RATIO} — يتجاوز"
            )
            continue

        lots = trade_info["lots"]
        if view and hasattr(view, "position_size_multiplier"):
            lots = max(0.01, round(lots * view.position_size_multiplier, 2))

        # ── إرسال إشعار التنفيذ ──────────────────────────────
        view_line = ""
        if view:
            view_line = f"\n📊 MarketView: {getattr(view,'recommended_bias','?')} [{getattr(view,'conviction','?')}]"

        notifier.send(
            f"🇬🇧 London Breakout — {pair}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 الاتجاه : {direction}\n"
            f"💰 الدخول  : {signal['entry']}\n"
            f"🛑 وقف الخسارة: {signal['sl']}\n"
            f"🎯 هدف الربح : {signal['tp']}\n"
            f"📐 RR     : 1:{signal['rr']}\n"
            f"📏 Risk   : {signal['risk_pips']} pip\n"
            f"📦 الحجم  : {lots} lots\n"
            f"🕛 Asia High: {signal['asia_high']} | Low: {signal['asia_low']}\n"
            f"📊 H4 Bias: {signal['h4_bias']}"
            f"{view_line}"
        )

        # ── تنفيذ على MT5 ─────────────────────────────────────
        try:
            result = executor.place_order(
                signal=direction,
                lots=lots,
                stop_loss=signal["sl"],
                take_profit=signal["tp"],
                entry_price=signal["entry"],
                symbol=cfg["mt5"],
            )

            if result:
                notifier.send(
                    f"✅ تم تنفيذ {pair} {direction}!\n"
                    f"🎫 Ticket: #{result['ticket']}\n"
                    f"💹 السعر: {result['price']}\n"
                    f"🔒 Trailing Stop: يُفعَّل عند 1:1"
                )

                # تسجيل في اليوميات
                try:
                    journal = TradeJournal()
                    journal.log_trade_open(
                        ticket=result['ticket'],
                        direction=direction,
                        entry=result['price'],
                        sl=signal['sl'],
                        tp=signal['tp'],
                        lots=lots,
                        confluence_score=80,
                        entry_type="London_Breakout",
                        reasons=[signal['reason']],
                        session="london",
                        bias=signal['h4_bias'],
                    )
                except Exception as je:
                    print(f"⚠️ فشل تسجيل الصفقة: {je}")

                # سجّل في Generator للـ trailing
                gen.mark_trade_open(direction, result['price'], signal['sl'], signal['tp'])
                open_pairs.add(pair)

            else:
                notifier.send(
                    f"❌ فشل تنفيذ {pair}\n"
                    f"تحقق: AutoTrading مفعّل + رصيد كافي"
                )
        except Exception as e:
            notifier.send(f"❌ خطأ في تنفيذ {pair}: {e}")

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
        """تقرير London Breakout لجميع الأزواج"""
        try:
            lines = ["🇬🇧 London Breakout — حالة الأزواج\n"]
            for pair in ACTIVE_PAIRS:
                cfg  = TRADING_PAIRS[pair]
                feed = DataFeed(cfg["td"])
                h1   = feed.get_historical_range(days=8,  interval="1h")
                h4   = feed.get_historical_range(days=30, interval="4h")
                if h1 is None or len(h1) < 10:
                    lines.append(f"❌ {pair}: فشل جلب البيانات")
                    continue
                gen = LondonSignalGenerator(pair, h1, h4)
                lines.append(gen.get_session_report())
            return "\n\n".join(lines)
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
    def cmd_optimize(args=None):
        try:
            return getattr(optimizer_self, "get_report")()
        except Exception as e:
            return f"❌ خطأ في التحسين: {e}"

    dashboard.register_handler("report", cmd_report)
    dashboard.register_handler("analyze", cmd_analyze)
    dashboard.register_handler("lessons", cmd_lessons)
    dashboard.register_handler("pairs", cmd_pairs)
    dashboard.register_handler("news", cmd_news)
    dashboard.register_handler("scan", cmd_scan)
    dashboard.register_handler("optimize", cmd_optimize)

    dashboard.start_polling()

    dashboard.send(
        f"🤖 London Breakout Bot — شغّال!\n"
        f"🇬🇧 الاستراتيجية: London Breakout (07-10 UTC)\n"
        f"📊 الأزواج: {', '.join(ACTIVE_PAIRS)}\n"
        f"⏱️ فحص كل {SCAN_INTERVAL_MINUTES} دقيقة\n"
        f"🛡️ RR = 3:1 | Trailing SL بعد 1:1\n"
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
    last_vision_day = None

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

            # تقرير الرؤية الصباحية عبر الإيميل
            from config import VISION_REPORT_HOUR
            if datetime.now().hour == VISION_REPORT_HOUR and last_vision_day != today:
                last_vision_day = today
                try:
                    from strategy.ai_vision import AIVisionGenerator
                    vision_gen = AIVisionGenerator()
                    sent = vision_gen.execute_daily_vision()
                    if sent:
                        notifier.send("📧 تم إعداد وتوليد الرؤية الاقتصادية الصباحية بنجاح وإرسالها لإيميلك!")
                except Exception as vi_err:
                    print(f"⚠️ خطأ في توليد رؤية الإيميل: {vi_err}")

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
