"""
Trade Monitor — مراقبة الصفقات المفتوحة على MT5

يعمل بالخلفية ويتحقق كل بضع ثواني من:
1. هل يجب نقل SL لنقطة التعادل؟
2. هل يجب تحريك Trailing Stop؟
3. هل يجب إغلاق جزئي (Partial TP)؟

يرسل إشعارات Telegram لكل تعديل
"""

import time
from config import (
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    PIP_VALUE,
)
from utils.logger import get_logger

_log = get_logger("trade_monitor")


class TradeMonitor:
    """مراقب الصفقات المفتوحة"""

    def __init__(self, executor, risk_manager, data_feed, notifier=None):
        """
        executor: Executor (MT5)
        risk_manager: RiskManager
        data_feed: DataFeed (لجلب ATR)
        notifier: Notifier (Telegram)
        """
        self.executor = executor
        self.rm = risk_manager
        self.feed = data_feed
        self.notifier = notifier

        # تتبع حالة كل صفقة
        self.tracked_positions = {}
        # {ticket: {"partial_closed": False, "breakeven_done": False, "original_sl": ..., "original_tp": ...}}

    def notify(self, msg):
        """إرسال إشعار"""
        _log.info(msg)
        if self.notifier:
            try:
                self.notifier.send(msg)
            except Exception as e:
                _log.error(f"فشل إرسال إشعار Telegram: {e}")

    # قيم ATR الافتراضية لكل زوج عند فشل جلب البيانات
    _ATR_DEFAULTS = {
        "USDJPY": 0.15,
        "EURUSD": 0.0008,
        "GBPUSD": 0.0010,
        "XAUUSD": 3.0,
    }

    def get_current_atr(self, symbol=None):
        """جلب ATR الحالي"""
        fallback = self._ATR_DEFAULTS.get(symbol, 0.001) if symbol else 0.001
        try:
            ltf = self.feed.get_candles(interval="15min", period_days=7)
            if ltf is not None and "ATR" in ltf.columns:
                atr = ltf["ATR"].iloc[-1]
                if atr and atr > 0:
                    return atr
        except Exception as e:
            _log.error(f"خطأ جلب ATR لـ {symbol}: {e}")
        return fallback

    def check_and_manage(self):
        """
        فحص وإدارة كل الصفقات المفتوحة — يُستدعى كل دورة

        returns: عدد التعديلات
        """
        positions = self.executor.get_open_positions()
        if not positions:
            return 0

        modifications = 0

        for pos in positions:
            ticket = pos["ticket"]
            symbol = pos.get("symbol")
            atr = self.get_current_atr(symbol)
            direction = pos["type"]
            entry = pos["open_price"]
            current_price = pos["current_price"]
            current_sl = pos["sl"]
            current_tp = pos["tp"]
            lots = pos["volume"]
            profit = pos["profit"]

            # تهيئة التتبع لصفقة جديدة
            if ticket not in self.tracked_positions:
                self.tracked_positions[ticket] = {
                    "partial_closed": False,
                    "breakeven_done": False,
                    "original_sl": current_sl,
                    "original_tp": current_tp,
                    "original_entry": entry,
                    "original_lots": lots,
                }
                self.notify(
                    f"👁️ مراقبة صفقة جديدة #{ticket}\n"
                    f"   {direction} {lots} lots @ {entry}\n"
                    f"   SL: {current_sl} | TP: {current_tp}"
                )

            tracked = self.tracked_positions[ticket]

            # بناء كائن position لـ RiskManager
            pos_info = {
                "entry": entry,
                "sl": current_sl,
                "tp": current_tp,
                "direction": direction,
                "lots": lots,
                "partial_closed": tracked["partial_closed"],
            }

            # ─── فحص الإدارة ───
            actions = self.rm.manage_open_position(pos_info, current_price, atr)

            # ─── 1. Partial TP — إغلاق جزئي ───
            if actions["close_partial"] and not tracked["partial_closed"]:
                partial_lots = actions["partial_lots"]

                self.notify(
                    f"✂️ إغلاق جزئي #{ticket}\n"
                    f"   {partial_lots}/{lots} lots عند {actions['profit_rr']}R\n"
                    f"   ربح حتى الآن: {actions['profit_pips']} pips"
                )

                success = self._close_partial(ticket, partial_lots)
                if success:
                    tracked["partial_closed"] = True
                    modifications += 1

            # ─── 2. تحديث SL (Break-Even أو Trailing) ───
            if actions["update_sl"] and actions["new_sl"] != current_sl:
                new_sl = actions["new_sl"]

                # تأكد ما ننقل SL بالاتجاه الخطأ
                if direction == "BUY" and new_sl < current_sl:
                    continue
                if direction == "SELL" and new_sl > current_sl:
                    continue

                self.notify(
                    f"📊 تعديل SL #{ticket}\n"
                    f"   {actions['reason']}\n"
                    f"   SL: {current_sl} → {new_sl}\n"
                    f"   الربح: {actions['profit_pips']} pips ({actions['profit_rr']}R)"
                )

                success = self.executor.modify_position(ticket, sl=new_sl)
                if success:
                    if not tracked["breakeven_done"]:
                        _be_off = self.rm.breakeven_offset_pips * PIP_VALUE
                        if new_sl in (round(entry + _be_off, 3), round(entry - _be_off, 3)):
                            tracked["breakeven_done"] = True
                    modifications += 1

        # تنظيف الصفقات المغلقة
        open_tickets = {p["ticket"] for p in positions}
        closed = [t for t in self.tracked_positions if t not in open_tickets]
        for t in closed:
            self.notify(f"📋 صفقة #{t} أُغلقت")
            del self.tracked_positions[t]

        return modifications

    def _close_partial(self, ticket, lots):
        """إغلاق جزئي لصفقة — يفتح أمر عكسي بحجم جزئي"""
        try:
            positions = self.executor.mt5.positions_get(ticket=ticket)
            if not positions:
                return False

            pos = positions[0]
            mt5 = self.executor.mt5

            # أمر عكسي بحجم جزئي
            if pos.type == 0:  # BUY → SELL partial
                close_type = mt5.ORDER_TYPE_SELL
                close_price = mt5.symbol_info_tick(pos.symbol).bid
            else:  # SELL → BUY partial
                close_type = mt5.ORDER_TYPE_BUY
                close_price = mt5.symbol_info_tick(pos.symbol).ask

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": lots,
                "type": close_type,
                "position": ticket,
                "price": close_price,
                "deviation": 20,
                "magic": pos.magic,
                "comment": "ICT Partial TP",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                self.notify(f"✅ تم إغلاق جزئي {lots} lots من #{ticket}")
                return True
            else:
                error = result.comment if result else "unknown"
                self.notify(f"❌ فشل الإغلاق الجزئي: {error}")
                return False

        except Exception as e:
            self.notify(f"❌ خطأ إغلاق جزئي: {e}")
            return False

    def get_status(self):
        """حالة المراقبة"""
        positions = self.executor.get_open_positions()
        if not positions:
            return "📊 لا توجد صفقات مفتوحة"

        lines = [f"📊 صفقات مفتوحة: {len(positions)}"]
        for pos in positions:
            ticket = pos["ticket"]
            tracked = self.tracked_positions.get(ticket, {})
            pips = round((pos["current_price"] - pos["open_price"]) / PIP_VALUE, 1) \
                   if pos["type"] == "BUY" else \
                   round((pos["open_price"] - pos["current_price"]) / PIP_VALUE, 1)

            status = "🟢" if pos["profit"] > 0 else "🔴"
            be = "✅" if tracked.get("breakeven_done") else "❌"
            pt = "✅" if tracked.get("partial_closed") else "❌"

            lines.append(
                f"  {status} #{ticket} {pos['type']} {pos['volume']}lots\n"
                f"     ربح: {pips} pips (${pos['profit']:.2f})\n"
                f"     SL: {pos['sl']} | TP: {pos['tp']}\n"
                f"     Break-Even: {be} | Partial: {pt}"
            )
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("═══ Trade Monitor ═══")
    print("هذا الموديول يحتاج MT5 للاختبار.")
    print("سيعمل تلقائياً مع main.py")

    # محاكاة
    from risk.risk_manager import RiskManager
    rm = RiskManager(balance=3000)

    pos = {"entry": 144.500, "sl": 144.200, "tp": 145.400, "direction": "BUY", "lots": 0.03}

    print("\n📊 محاكاة حركة السعر:")
    for price in [144.600, 144.800, 145.000, 145.200, 145.500]:
        actions = rm.manage_open_position(pos, price, atr_value=0.15)
        print(f"\n  💰 السعر: {price} | ربح: {actions['profit_pips']}p ({actions['profit_rr']}R)")
        if actions["update_sl"]:
            print(f"    📊 {actions['reason']}")
            pos["sl"] = actions["new_sl"]
        if actions["close_partial"]:
            print(f"    ✂️ {actions['reason']}")
            pos["partial_closed"] = True
