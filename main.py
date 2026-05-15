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

import os

from utils.logger import get_logger, get_trade_logger

log         = get_logger("main")
trade_log   = get_trade_logger()

from data.data_feed import DataFeed
from data.macro_analyzer import MacroAnalyzer
from strategy.strategy_router import get_strategy
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

# ── Strategy generators لكل زوج (تُحدَّث في كل دورة) ──
_strategy_generators: dict = {}


# ═══════════════════════════════════════════════════════════════
# Daily Report — يُحفظ في reports/ ويُرفع لـ GitHub تلقائياً
# ═══════════════════════════════════════════════════════════════

def save_daily_report(journal, balance: float = 0):
    """
    يكتب ملخص يومي في reports/daily_YYYY-MM-DD.md
    ثم يعمل git commit + push تلقائياً لـ GitHub.
    """
    import subprocess, os
    from datetime import datetime, timezone

    today     = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = os.path.join("reports", f"daily_{today}.md")
    log_dir   = "logs"
    error_log = os.path.join(log_dir, f"errors_{today}.log")
    trade_log = os.path.join(log_dir, f"trades_{today}.log")

    # ── اقرأ أخطاء اليوم ──────────────────────────────────────
    errors_content = ""
    if os.path.exists(error_log):
        with open(error_log, "r", encoding="utf-8") as f:
            lines = f.readlines()[-50:]          # آخر 50 سطر
        errors_content = "".join(lines).strip()
    else:
        errors_content = "لا أخطاء اليوم ✅"

    # ── اقرأ صفقات اليوم ──────────────────────────────────────
    trades_content = ""
    if os.path.exists(trade_log):
        with open(trade_log, "r", encoding="utf-8") as f:
            trades_content = f.read().strip()
    else:
        trades_content = "لا صفقات اليوم"

    # ── إحصائيات من الـ Journal ───────────────────────────────
    stats_section = ""
    try:
        stats_section = journal.get_telegram_report()
    except Exception:
        stats_section = "تعذّر جلب الإحصائيات"

    # ── اكتب الملف ────────────────────────────────────────────
    content = f"""# Daily Bot Report — {today}

> **الإصدار:** {open('PRD.md').readline().strip() if os.path.exists('PRD.md') else 'N/A'}
> **الرصيد:** ${balance:,.2f}
> **التوقيت:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

---

## 📊 إحصائيات اليوم
```
{stats_section}
```

---

## 💹 الصفقات المنفّذة
```
{trades_content if trades_content else 'لا صفقات اليوم'}
```

---

## ❌ الأخطاء (آخر 50 سطر)
```
{errors_content}
```

---

## 🗂️ ملاحظات للمراجعة
- راجع الأخطاء المتكررة وحدّد الأنماط
- تحقق من نسبة Win Rate اليومية
- قارن الإشارات مع نتائج الـ backtest
"""

    os.makedirs("reports", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)
    log.info(f"📄 تم حفظ التقرير اليومي: {report_path}")

    # ── ارفع لـ GitHub ─────────────────────────────────────────
    try:
        subprocess.run(["git", "add", report_path], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"report: daily summary {today}"],
            check=True, capture_output=True
        )
        subprocess.run(["git", "push", "origin", "main"], check=True, capture_output=True)
        log.info(f"✅ تم رفع التقرير اليومي لـ GitHub")
    except subprocess.CalledProcessError as e:
        log.warning(f"تعذّر رفع التقرير لـ GitHub: {e}")


def push_logs_to_github():
    """
    يرفع ملفات الـ log الحالية لـ GitHub كل 6 ساعات
    حتى يقدر الروتين اليومي يقرأها ويحلّلها.

    يرفع:
      logs/bot_YYYY-MM-DD.log     ← كل الأحداث
      logs/errors_YYYY-MM-DD.log  ← الأخطاء فقط
      logs/trades_YYYY-MM-DD.log  ← الصفقات
    """
    import subprocess, os
    from datetime import datetime, timezone

    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_dir = "logs"

    if not os.path.exists(log_dir):
        return

    # اجمع ملفات اليوم الموجودة
    files_to_push = []
    for prefix in ("bot_", "errors_", "trades_"):
        path = os.path.join(log_dir, f"{prefix}{today}.log")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            files_to_push.append(path)

    if not files_to_push:
        log.info("push_logs: لا ملفات لرفعها")
        return

    try:
        subprocess.run(["git", "add"] + files_to_push,
                       check=True, capture_output=True)

        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True
        )
        if result.returncode == 0:
            log.info("push_logs: لا تغييرات جديدة في الـ logs")
            return

        ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
        subprocess.run(
            ["git", "commit", "-m", f"logs: auto-push {today} @ {ts}"],
            check=True, capture_output=True
        )
        subprocess.run(["git", "push", "origin", "main"],
                       check=True, capture_output=True)
        log.info(f"✅ تم رفع {len(files_to_push)} ملف log لـ GitHub")

    except subprocess.CalledProcessError as e:
        log.warning(f"push_logs: فشل الرفع — {e}")


def run_bot():
    """
    تشغيل البوت — London Breakout Strategy
    يفحص جميع الأزواج المفعّلة ويدخل عند كسر Range آسيا
    """
    global _strategy_generators

    notifier = Notifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)

    # ═══════════════════════════════════════════════════════════
    # 1. الاتصال بـ MT5
    # ═══════════════════════════════════════════════════════════

    executor = Executor()
    if not executor.connect():
        log.error("فشل الاتصال بـ MT5!")
        notifier.send("❌ فشل الاتصال بـ MT5!")
        return

    account = executor.get_account_info()
    balance = account["balance"] if account else BALANCE
    log.info(f"MT5 متصل | الرصيد: ${balance:,.2f}")

    # ═══════════════════════════════════════════════════════════
    # 2. فحص الظروف العامة (اختياري — لا يوقف البوت)
    # ═══════════════════════════════════════════════════════════

    intel = MarketIntelligence()
    try:
        can_trade, blockers, _ = intel.should_trade()
        if not can_trade:
            log.warning(f"ظروف غير مناسبة: {blockers}")
            notifier.send(f"🚫 ظروف غير مناسبة للتداول اليوم:\n" + "\n".join(blockers))
            executor.disconnect()
            return
    except Exception as e:
        log.warning(f"MarketIntelligence: {e} — مكمّلين بدونها")

    # ═══════════════════════════════════════════════════════════
    # 3. فحص نوافذ التداول (لندن + نيويورك)
    # ═══════════════════════════════════════════════════════════

    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    hour    = now_utc.hour
    minute  = now_utc.minute

    london    = 7 <= hour < 10                                          # 07:00–10:00 UTC
    ny_am     = (hour == 13 and minute >= 30) or (14 <= hour < 16)     # 13:30–16:00 UTC
    ny_pm     = 19 <= hour < 21                                         # 19:00–21:00 UTC

    if not (london or ny_am or ny_pm):
        log.info(
            f"خارج جميع نوافذ التداول — {hour:02d}:{minute:02d} UTC | "
            f"لندن 07-10 | NY 13:30-16 | NY-PM 19-21"
        )
        executor.disconnect()
        return

    active_session = "london" if london else ("ny_pm" if ny_pm else "ny_am")
    log.info(f"النافذة النشطة: {active_session} | {hour:02d}:{minute:02d} UTC")

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
            h1 = h1_feed.get_candles(interval="1h", period_days=8)

            # H4: آخر 120 شمعة (كافية لـ EMA20/50)
            h4 = h1_feed.get_candles(interval="4h", period_days=30)

            if h1 is None or len(h1) < 20:
                log.warning(f"{pair}: بيانات H1 غير كافية")
                continue

            # أنشئ أو حدّث Generator
            gen = _strategy_generators.get(pair)
            if gen is None:
                gen = get_strategy(pair, h1, h4)
                _strategy_generators[pair] = gen
            else:
                gen.h1 = h1
                if h4 is not None:
                    gen.h4 = h4

            signal = gen.get_signal()

            if signal:
                signals_found.append((pair, cfg, gen, signal))
                log.info(f"🎯 {pair}: إشارة {signal['direction']} | entry={signal['entry']} sl={signal['sl']} tp={signal['tp']}")
            else:
                log.info(f"{pair}: {gen.get_session_report()}")

        except Exception as e:
            log.error(f"{pair}: خطأ في توليد الإشارة — {e}", exc_info=True)

    if not signals_found:
        log.info("لا توجد إشارات London Breakout حالياً")
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
        log.warning(f"MarketViewBuilder: {e}")

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

        _strategy_label = signal.get("strategy", "Breakout")
        _asia_line = ""
        if signal.get("asia_high") is not None:
            _asia_line = f"\n🕛 Asia High: {signal['asia_high']} | Low: {signal['asia_low']}"
        notifier.send(
            f"📡 {_strategy_label} — {pair}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 الاتجاه : {direction}\n"
            f"💰 الدخول  : {signal['entry']}\n"
            f"🛑 وقف الخسارة: {signal['sl']}\n"
            f"🎯 هدف الربح : {signal['tp']}\n"
            f"📐 RR     : 1:{signal['rr']}\n"
            f"📏 Risk   : {signal['risk_pips']} pip\n"
            f"📦 الحجم  : {lots} lots"
            f"{_asia_line}\n"
            f"📊 H4 Bias: {signal['h4_bias']}"
            f"{view_line}"
        )

        # ── تنفيذ على MT5 ─────────────────────────────────────
        try:
            log.info(f"{pair}: إرسال أمر {direction} | lots={lots} entry={signal['entry']} sl={signal['sl']} tp={signal['tp']}")
            result = executor.place_order(
                signal=direction,
                lots=lots,
                stop_loss=signal["sl"],
                take_profit=signal["tp"],
                entry_price=signal["entry"],
                symbol=cfg["mt5"],
            )

            if result:
                log.info(f"✅ {pair}: تم تنفيذ #{result['ticket']} @ {result['price']}")
                trade_log.info(
                    f"OPEN | {pair} | {direction} | ticket={result['ticket']} | "
                    f"entry={result['price']} | sl={signal['sl']} | tp={signal['tp']} | lots={lots}"
                )
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
                    log.warning(f"فشل تسجيل الصفقة في Journal: {je}")

                # سجّل في Generator للـ trailing
                gen.mark_trade_open(direction, result['price'], signal['sl'], signal['tp'])
                open_pairs.add(pair)

            else:
                log.error(f"{pair}: فشل تنفيذ الأمر — تحقق من AutoTrading والرصيد")
                notifier.send(
                    f"❌ فشل تنفيذ {pair}\n"
                    f"تحقق: AutoTrading مفعّل + رصيد كافي"
                )
        except Exception as e:
            log.error(f"{pair}: خطأ في تنفيذ الأمر — {e}", exc_info=True)
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
                h1   = feed.get_candles(interval="1h", period_days=8)
                h4   = feed.get_candles(interval="4h", period_days=30)
                if h1 is None or len(h1) < 10:
                    lines.append(f"❌ {pair}: فشل جلب البيانات")
                    continue
                gen = get_strategy(pair, h1, h4)
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

    def cmd_reload(args=None):
        """إعادة تحميل الاستراتيجيات من config.py بدون restart"""
        _strategy_generators.clear()
        from config import PAIR_STRATEGIES
        lines = "\n".join([f"  {p}: {s}" for p, s in PAIR_STRATEGIES.items()])
        return f"✅ تم إعادة تحميل الاستراتيجيات:\n{lines}"

    dashboard.register_handler("report", cmd_report)
    dashboard.register_handler("analyze", cmd_analyze)
    dashboard.register_handler("lessons", cmd_lessons)
    dashboard.register_handler("pairs", cmd_pairs)
    dashboard.register_handler("news", cmd_news)
    dashboard.register_handler("scan", cmd_scan)
    dashboard.register_handler("optimize", cmd_optimize)
    dashboard.register_handler("reload", cmd_reload)

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
    last_heartbeat_hour = -1   # لمنع إرسال heartbeat مرتين في نفس الساعة
    last_log_push_hour = -1    # لمنع رفع الـ logs مرتين في نفس الساعة
    last_fix_plan_day  = None  # لمنع إرسال خطة الإصلاح مرتين في نفس اليوم

    while True:
        cycle += 1

        try:
            # إعادة تعيين الحدود اليومية عند بداية يوم جديد
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).date()
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

                    # حفظ ورفع التقرير اليومي لـ GitHub
                    try:
                        acct = executor.get_account_info()
                        bal  = acct["balance"] if acct else BALANCE
                        save_daily_report(journal, bal)
                    except Exception as e:
                        log.warning(f"تعذّر حفظ التقرير اليومي: {e}")

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
            if datetime.now(timezone.utc).hour == VISION_REPORT_HOUR and last_vision_day != today:
                last_vision_day = today
                try:
                    from strategy.ai_vision import AIVisionGenerator
                    vision_gen = AIVisionGenerator()
                    sent = vision_gen.execute_daily_vision()
                    if sent:
                        notifier.send("📧 تم إعداد وتوليد الرؤية الاقتصادية الصباحية بنجاح وإرسالها لإيميلك!")
                except Exception as vi_err:
                    print(f"⚠️ خطأ في توليد رؤية الإيميل: {vi_err}")

            # ساعة الوقت الحالي UTC — تُستخدم في log push + heartbeat
            _now_h = datetime.now(timezone.utc).hour

            # ═══ رفع الـ logs لـ GitHub كل 6 ساعات ═══
            _log_push_hours = {0, 6, 12, 18}
            if _now_h in _log_push_hours and _now_h != last_log_push_hour:
                last_log_push_hour = _now_h
                try:
                    push_logs_to_github()
                except Exception as _e:
                    log.warning(f"push_logs خطأ: {_e}")

            # ═══ خطة الإصلاح — إرسال تلقائي الساعة 07:00 UTC ═══
            from datetime import timezone as _tz_fix
            _utc_now   = datetime.now(_tz_fix.utc)
            _utc_h_fix = _utc_now.hour
            _today_fix = _utc_now.date()

            if _utc_h_fix == 7 and last_fix_plan_day != _today_fix:
                last_fix_plan_day = _today_fix
                try:
                    import subprocess as _sp
                    # سحب آخر تحديثات (قد تشمل fix_plan من الروتين)
                    _pull = _sp.run(
                        ["git", "pull", "origin", "main"],
                        capture_output=True, text=True, timeout=30
                    )
                    if _pull.returncode == 0 and "Already up to date" not in _pull.stdout:
                        log.info("✅ git pull نجح — يبحث عن خطة إصلاح جديدة")

                    # ابحث عن fix_plan اليوم
                    _plan_path = os.path.join(
                        "reports", f"fix_plan_{_today_fix.strftime('%Y-%m-%d')}.md"
                    )
                    # إذا ما وجد اليوم، خذ أحدث خطة
                    if not os.path.exists(_plan_path):
                        _all_plans = sorted([
                            f for f in os.listdir("reports")
                            if f.startswith("fix_plan_") and f.endswith(".md")
                        ], reverse=True) if os.path.exists("reports") else []
                        if _all_plans:
                            _plan_path = os.path.join("reports", _all_plans[0])
                        else:
                            _plan_path = None

                    if _plan_path and os.path.exists(_plan_path):
                        with open(_plan_path, "r", encoding="utf-8") as _pf:
                            _plan_content = _pf.read()
                        log.info(f"📋 إرسال خطة الإصلاح: {_plan_path}")
                        dashboard.activate_fix_plan(_plan_content)
                    else:
                        log.info("📋 لا توجد خطة إصلاح لإرسالها اليوم")

                except Exception as _fe:
                    log.warning(f"خطأ في إرسال خطة الإصلاح: {_fe}")

            # ═══ Heartbeat — إشعار "البوت حي" كل 4 ساعات ═══
            _heartbeat_hours = {0, 4, 8, 12, 16, 20}   # كل 4 ساعات
            if _now_h in _heartbeat_hours and _now_h != last_heartbeat_hour:
                last_heartbeat_hour = _now_h
                from datetime import timezone as _tz
                _utc_h = datetime.now(_tz.utc).hour
                _in_window = (
                    7 <= _utc_h < 10 or
                    (_utc_h == 13) or (14 <= _utc_h < 16) or
                    (19 <= _utc_h < 21)
                )
                _window_str = "🟢 في نافذة تداول" if _in_window else "🔵 Dead Zone — ينتظر"
                try:
                    acct_hb = executor.get_account_info()
                    bal_hb  = f"${acct_hb['balance']:,.2f}" if acct_hb else "N/A"
                except Exception:
                    bal_hb  = "N/A"
                notifier.send(
                    f"💓 البوت شغال\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🕐 {time.strftime('%H:%M')} VPS | UTC {_utc_h:02d}:xx\n"
                    f"💰 الرصيد: {bal_hb}\n"
                    f"📊 الدورة: #{cycle}\n"
                    f"{_window_str}"
                )

            if not is_market_open():
                print(f"\n⏸️ [{time.strftime('%H:%M')}] السوق مغلق (عطلة نهاية الأسبوع)")
                print(f"   ⏰ الفحص التالي بعد 60 دقيقة...")
                time.sleep(60 * 60)
                continue

            log.info(f"{'═'*40}")
            log.info(f"الدورة #{cycle} — {time.strftime('%Y-%m-%d %H:%M:%S')}")
            log.info(f"{'═'*40}")

            # مراقبة الصفقات المفتوحة (كل دورة)
            if executor.connected or executor.connect():
                mods = monitor.check_and_manage()
                if mods > 0:
                    log.info(f"TradeMonitor: تم تعديل {mods} صفقة")

                status = monitor.get_status()
                log.info(f"TradeMonitor: {status}")

            # تحقق من الإيقاف المؤقت
            if bot_state.get("paused"):
                log.info("البوت متوقف مؤقتاً — /resume للاستئناف")
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
            log.info("تم إيقاف البوت يدوياً")
            dashboard.send("🛑 تم إيقاف البوت يدوياً")
            dashboard.stop_polling()
            if executor.connected:
                executor.disconnect()
            break

        except Exception as e:
            log.error(f"خطأ غير متوقع في الدورة #{cycle}: {e}", exc_info=True)
            notifier.send(
                f"🚨 خطأ غير متوقع في البوت!\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"❌ الخطأ: {e}\n"
                f"🔄 إعادة المحاولة بعد دقيقة...\n"
                f"📋 راجع: logs/errors_{time.strftime('%Y-%m-%d')}.log"
            )
            time.sleep(60)
