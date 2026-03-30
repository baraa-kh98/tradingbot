"""
ICT Trading Bot — البوت الرئيسي

يستخدم استراتيجية ICT (Inner Circle Trader):
1. تحليل Market Structure على HTF
2. كشف Order Blocks, FVG, Liquidity على LTF
3. حساب نقاط الالتقاء (Confluence)
4. تنفيذ الصفقة على OANDA
5. إرسال تقرير على Telegram
"""

from data.data_feed import DataFeed
from data.macro_analyzer import MacroAnalyzer
from strategy.signal_generator import ICTSignalGenerator
from strategy.kill_zones import get_current_session
from risk.risk_manager import RiskManager
from execution.executor import Executor
from notifier import Notifier
from config import (
    CLAUDE_API_KEY,
    OANDA_API_KEY,
    ACCOUNT_ID,
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    BALANCE,
    RISK_PERCENT,
    MIN_RR_RATIO,
    USE_MACRO_FILTER,
    MACRO_MIN_SCORE,
    OANDA_DEMO,
)


def run_bot():
    """تشغيل البوت — دورة واحدة"""

    notifier = Notifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    notifier.send("🤖 البوت شغّال — تحليل ICT...")

    # ═══════════════════════════════════════════════════════
    # 1. جلب البيانات (Multi-Timeframe)
    # ═══════════════════════════════════════════════════════

    feed = DataFeed()

    try:
        htf_data = feed.get_htf_data()
        ltf_data = feed.get_ltf_data()
        current_price = feed.get_latest_price()
        notifier.send(f"📊 السعر الحالي: {current_price}")
    except Exception as e:
        notifier.send(f"❌ خطأ في جلب البيانات: {e}")
        return

    # ═══════════════════════════════════════════════════════
    # 2. تحليل الماكرو (اختياري)
    # ═══════════════════════════════════════════════════════

    macro_result = None
    if USE_MACRO_FILTER:
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

    # ═══════════════════════════════════════════════════════
    # 3. تحليل ICT وتوليد الإشارة
    # ═══════════════════════════════════════════════════════

    try:
        signal_gen = ICTSignalGenerator(htf_data, ltf_data)
        signal = signal_gen.get_signal()
        levels = signal_gen.get_levels()

        # إرسال التقرير الكامل
        full_report = signal_gen.get_full_report()
        notifier.send(full_report)
    except Exception as e:
        notifier.send(f"❌ خطأ في تحليل ICT: {e}")
        return

    # ═══════════════════════════════════════════════════════
    # 4. اتخاذ القرار
    # ═══════════════════════════════════════════════════════

    if signal["action"] == "WAIT":
        notifier.send("⏳ لا توجد فرصة حالياً — البوت ينتظر...")
        return

    if levels is None:
        notifier.send("⚠️ لم يتم تحديد مستويات واضحة — البوت ينتظر...")
        return

    final_action = signal["action"]

    # فلتر الماكرو (اختياري)
    if USE_MACRO_FILTER and macro_result:
        if macro_result["bias"] == "BULLISH" and final_action == "SELL":
            if abs(macro_result["score"]) > 50:
                notifier.send("⚠️ ICT يقول SELL لكن الماكرو BULLISH قوي — البوت ينتظر...")
                return
        elif macro_result["bias"] == "BEARISH" and final_action == "BUY":
            if abs(macro_result["score"]) > 50:
                notifier.send("⚠️ ICT يقول BUY لكن الماكرو BEARISH قوي — البوت ينتظر...")
                return

    # ═══════════════════════════════════════════════════════
    # 5. إدارة المخاطر
    # ═══════════════════════════════════════════════════════

    rm = RiskManager(balance=BALANCE, risk_percent=RISK_PERCENT)
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
        return

    # ═══════════════════════════════════════════════════════
    # 6. تنفيذ الصفقة
    # ═══════════════════════════════════════════════════════

    notifier.send(
        f"🚀 تنفيذ صفقة ICT:\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📍 الاتجاه: {final_action}\n"
        f"💰 الدخول: {levels['entry']}\n"
        f"🛑 وقف الخسارة: {levels['stop_loss']}\n"
        f"🎯 هدف الربح: {levels['take_profit']}\n"
        f"📐 RR: 1:{levels['rr_ratio']}\n"
        f"📦 الحجم: {trade_info['position_size']}\n"
        f"💵 المخاطرة: ${trade_info['risk_amount']}\n"
        f"🔑 نوع الدخول: {levels['entry_type']}\n"
        f"📊 الالتقاء: {signal['confluence_score']}/100"
    )

    try:
        executor = Executor(OANDA_API_KEY, ACCOUNT_ID, demo=OANDA_DEMO)
        executor.place_order(
            final_action,
            int(trade_info["position_size"]),
            levels["stop_loss"],
            levels["take_profit"]
        )
        notifier.send("✅ تم تنفيذ الصفقة على OANDA بنجاح!")
    except Exception as e:
        notifier.send(f"❌ خطأ في تنفيذ الصفقة: {e}")


if __name__ == "__main__":
    run_bot()
