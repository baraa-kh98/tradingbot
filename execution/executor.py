"""
MT5 Executor — تنفيذ الصفقات عبر MetaTrader 5

يدعم:
- أوامر السوق (Market Orders)
- وقف الخسارة وجني الأرباح
- إغلاق الصفقات
- معلومات الحساب

⚠️ يتطلب: Windows + MT5 مثبّت ومفتوح + pip install MetaTrader5
"""

import time as time_module
from config import (
    MT5_LOGIN,
    MT5_PASSWORD,
    MT5_SERVER,
    SYMBOL_MT5,
    MT5_MAGIC_NUMBER,
    MT5_DEVIATION,
    MT5_LOT_MIN,
)


class Executor:
    """منفّذ الصفقات عبر MetaTrader 5"""

    def __init__(self, login=None, password=None, server=None):
        self.login = login or MT5_LOGIN
        self.password = password or MT5_PASSWORD
        self.server = server or MT5_SERVER
        self.connected = False
        self.mt5 = None

    def connect(self):
        """الاتصال بـ MT5"""
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
        except ImportError:
            print("❌ MetaTrader5 مش مثبّت. استخدم: pip install MetaTrader5")
            print("   ⚠️ يعمل فقط على Windows مع MT5 مفتوح")
            return False

        # تهيئة MT5 — محاولة بدون مسار أولاً
        if not self.mt5.initialize():
            print(f"⚠️ فشل تهيئة MT5 بدون مسار: {self.mt5.last_error()}")
            print("🔍 جاري البحث عن MT5...")

            # البحث التلقائي عن terminal64.exe
            import os
            mt5_found = False
            search_dirs = []
            for drive in ["C:", "D:"]:
                for pf in ["Program Files", "Program Files (x86)"]:
                    d = f"{drive}\\{pf}"
                    if os.path.exists(d):
                        search_dirs.append(d)

            for search_dir in search_dirs:
                try:
                    for folder in os.listdir(search_dir):
                        path = os.path.join(search_dir, folder, "terminal64.exe")
                        if os.path.exists(path):
                            print(f"   📍 وجدت MT5: {path}")
                            if self.mt5.initialize(path=path):
                                mt5_found = True
                                print(f"   ✅ تم الاتصال!")
                                break
                            else:
                                print(f"   ❌ فشل: {self.mt5.last_error()}")
                except PermissionError:
                    continue
                if mt5_found:
                    break

            if not mt5_found:
                print("❌ فشل تهيئة MT5! تأكد إن:")
                print("   1. برنامج MT5 مفتوح ومسجّل دخول")
                print("   2. شغّل CMD كـ Administrator")
                print("   3. MT5 و Python بنفس الصلاحيات")
                return False

        # تسجيل الدخول — فقط إذا مش مسجّل أصلاً
        if self.login and self.password and self.server:
            # تحقق إذا الحساب الصحيح أصلاً مفتوح
            account = self.mt5.account_info()
            if account and account.login == self.login:
                print(f"ℹ️ الحساب {self.login} أصلاً مسجّل دخول — تخطّي login()")
            else:
                print(f"🔑 جاري تسجيل الدخول: {self.login}@{self.server}")
                authorized = self.mt5.login(
                    login=self.login,
                    password=self.password,
                    server=self.server
                )
                if not authorized:
                    print(f"❌ فشل تسجيل الدخول: {self.mt5.last_error()}")
                    # لسا ممكن نكمل بالحساب الحالي
                    account = self.mt5.account_info()
                    if account:
                        print(f"ℹ️ مكمّلين بالحساب الحالي: {account.login}")
                    else:
                        self.mt5.shutdown()
                        return False

        self.connected = True
        account = self.mt5.account_info()
        print(f"✅ متصل بـ MT5: {account.server}")
        print(f"   الحساب: {account.login}")
        print(f"   الرصيد: ${account.balance:.2f}")
        print(f"   النوع: {'Demo' if account.trade_mode == 0 else 'Real'}")
        return True

    def disconnect(self):
        """قطع الاتصال"""
        if self.mt5:
            self.mt5.shutdown()
            self.connected = False
            print("🔌 تم قطع الاتصال بـ MT5")

    def _ensure_connected(self):
        """التأكد من الاتصال"""
        if not self.connected:
            return self.connect()
        return True

    def get_account_info(self):
        """معلومات الحساب"""
        if not self._ensure_connected():
            return None

        account = self.mt5.account_info()
        return {
            "login": account.login,
            "balance": account.balance,
            "equity": account.equity,
            "margin": account.margin,
            "free_margin": account.margin_free,
            "profit": account.profit,
            "server": account.server,
            "is_demo": account.trade_mode == 0,
        }

    def get_symbol_info(self, symbol=None):
        """معلومات الزوج"""
        if not self._ensure_connected():
            return None

        symbol = symbol or SYMBOL_MT5
        info = self.mt5.symbol_info(symbol)

        if info is None:
            print(f"❌ الرمز {symbol} مش موجود. تأكد من اسم الرمز على MT5")
            return None

        # تفعيل الرمز إذا مش مفعّل
        if not info.visible:
            self.mt5.symbol_select(symbol, True)

        return {
            "symbol": info.name,
            "bid": info.bid,
            "ask": info.ask,
            "spread": info.spread,
            "lot_min": info.volume_min,
            "lot_max": info.volume_max,
            "lot_step": info.volume_step,
            "point": info.point,
            "digits": info.digits,
        }

    def place_order(self, signal, lots, stop_loss, take_profit, entry_price=None, symbol=None):
        """
        فتح صفقة جديدة — Market أو Pending Limit تلقائياً

        signal: "BUY" أو "SELL"
        lots: حجم اللوت
        stop_loss: سعر وقف الخسارة
        take_profit: سعر جني الأرباح
        entry_price: سعر الدخول المطلوب (إذا None = market order)
        """
        if not self._ensure_connected():
            return None

        symbol = symbol or SYMBOL_MT5
        sym_info = self.get_symbol_info(symbol)
        if sym_info is None:
            return None

        # السعر الحالي
        if signal == "BUY":
            market_price = sym_info["ask"]
        elif signal == "SELL":
            market_price = sym_info["bid"]
        else:
            print(f"❌ إشارة غير صالحة: {signal}")
            return None

        digits = sym_info["digits"]
        point = sym_info["point"]
        pip = point * 10  # عادةً 10 نقاط = 1 pip

        # التأكد من حجم اللوت
        lots = max(lots, sym_info["lot_min"])
        lots = min(lots, sym_info.get("lot_max", 100))
        lots = round(lots / sym_info["lot_step"]) * sym_info["lot_step"]
        lots = round(lots, 2)

        # تقريب المستويات
        stop_loss = round(stop_loss, digits)
        take_profit = round(take_profit, digits)

        # ═══ تحديد نوع الأمر: Market أو Pending ═══
        threshold = pip * 5  # 5 pips تحمّل

        if entry_price is not None:
            entry_price = round(entry_price, digits)
            distance = abs(market_price - entry_price)
        else:
            entry_price = market_price
            distance = 0

        if distance <= threshold:
            # ═══ MARKET ORDER — السعر عند الدخول ═══
            return self._execute_market_order(
                signal, symbol, lots, market_price,
                stop_loss, take_profit, sym_info
            )
        else:
            # ═══ PENDING LIMIT — السعر لسا ما وصل ═══
            return self._execute_limit_order(
                signal, symbol, lots, entry_price,
                stop_loss, take_profit, sym_info
            )

    def _execute_market_order(self, signal, symbol, lots, price, sl, tp, sym_info):
        """تنفيذ Market Order فوري"""
        # تحقق من المستويات
        if signal == "BUY":
            if sl >= price:
                print(f"⚠️ SL ({sl}) >= سعر الشراء ({price}) — مستويات غلط!")
                return None
            if tp <= price:
                print(f"⚠️ TP ({tp}) <= سعر الشراء ({price}) — الفرصة فاتت!")
                return None
            order_type = self.mt5.ORDER_TYPE_BUY
        else:
            if sl <= price:
                print(f"⚠️ SL ({sl}) <= سعر البيع ({price}) — مستويات غلط!")
                return None
            if tp >= price:
                print(f"⚠️ TP ({tp}) >= سعر البيع ({price}) — الفرصة فاتت!")
                return None
            order_type = self.mt5.ORDER_TYPE_SELL

        print(f"   🔄 Market Order: {signal} {lots} lots @ {price}")

        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lots,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": MT5_DEVIATION,
            "magic": MT5_MAGIC_NUMBER,
            "comment": "ICT Bot",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }

        result = self.mt5.order_send(request)
        return self._handle_result(result, signal, lots, sl, tp, "MARKET")

    def _execute_limit_order(self, signal, symbol, lots, entry, sl, tp, sym_info):
        """وضع أمر معلّق Limit"""
        price = sym_info["bid"] if signal == "SELL" else sym_info["ask"]

        if signal == "BUY":
            if entry >= price:
                # السعر تحت الدخول → Buy Limit (ننتظر السعر ينزل للدخول)
                # لكن هذا يعني السعر لسا ما وصل فوق... غريب
                # عادةً Buy Limit = ندخل عند سعر أقل
                order_type = self.mt5.ORDER_TYPE_BUY_LIMIT
                # لو الدخول فوق السعر الحالي = ننتظر السعر يرتفع = Buy Stop
                order_type = self.mt5.ORDER_TYPE_BUY_STOP
            else:
                # الدخول تحت السعر → Buy Limit (ننتظر السعر ينزل)
                order_type = self.mt5.ORDER_TYPE_BUY_LIMIT
        else:  # SELL
            if entry <= price:
                # الدخول تحت السعر → Sell Stop
                order_type = self.mt5.ORDER_TYPE_SELL_STOP
            else:
                # الدخول فوق السعر → Sell Limit (ننتظر السعر يرتفع)
                order_type = self.mt5.ORDER_TYPE_SELL_LIMIT

        order_name = {
            self.mt5.ORDER_TYPE_BUY_LIMIT: "BUY LIMIT",
            self.mt5.ORDER_TYPE_BUY_STOP: "BUY STOP",
            self.mt5.ORDER_TYPE_SELL_LIMIT: "SELL LIMIT",
            self.mt5.ORDER_TYPE_SELL_STOP: "SELL STOP",
        }.get(order_type, "PENDING")

        print(f"   ⏳ {order_name}: {lots} lots @ {entry}")
        print(f"   📍 السعر الحالي: {price} | ننتظر الوصول لـ {entry}")

        # التحقق من المستويات
        if signal == "BUY":
            if sl >= entry:
                print(f"⚠️ SL ({sl}) >= Entry ({entry}) — مستويات غلط!")
                return None
            if tp <= entry:
                print(f"⚠️ TP ({tp}) <= Entry ({entry}) — مستويات غلط!")
                return None
        else:
            if sl <= entry:
                print(f"⚠️ SL ({sl}) <= Entry ({entry}) — مستويات غلط!")
                return None
            if tp >= entry:
                print(f"⚠️ TP ({tp}) >= Entry ({entry}) — مستويات غلط!")
                return None

        request = {
            "action": self.mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": lots,
            "type": order_type,
            "price": entry,
            "sl": sl,
            "tp": tp,
            "magic": MT5_MAGIC_NUMBER,
            "comment": "ICT Bot Limit",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_RETURN,
        }

        result = self.mt5.order_send(request)
        return self._handle_result(result, signal, lots, sl, tp, order_name, entry)

    def _handle_result(self, result, signal, lots, sl, tp, order_type, entry=None):
        """معالجة نتيجة الأمر"""
        if result is None:
            print(f"❌ order_send فشل: {self.mt5.last_error()}")
            return None

        if result.retcode != self.mt5.TRADE_RETCODE_DONE:
            print(f"❌ فشل تنفيذ الصفقة: {result.retcode} — {result.comment}")
            return None

        exec_price = entry if entry else result.price
        print(f"✅ تم: {order_type} {signal} {lots} lots @ {exec_price}")
        print(f"   SL: {sl} | TP: {tp}")
        print(f"   Ticket: {result.order}")

        return {
            "ticket": result.order,
            "price": exec_price,
            "lots": lots,
            "signal": signal,
            "sl": sl,
            "tp": tp,
            "order_type": order_type,
        }

    def close_position(self, ticket=None, symbol=None):
        """
        إغلاق صفقة معينة أو كل الصفقات

        ticket: رقم الصفقة (إذا None يغلق كل صفقات البوت)
        """
        if not self._ensure_connected():
            return None

        symbol = symbol or SYMBOL_MT5

        if ticket:
            # إغلاق صفقة محددة
            positions = self.mt5.positions_get(ticket=ticket)
        else:
            # إغلاق كل صفقات هذا الرمز من البوت
            positions = self.mt5.positions_get(symbol=symbol)

        if positions is None or len(positions) == 0:
            print("ℹ️ لا توجد صفقات مفتوحة")
            return []

        results = []
        for pos in positions:
            # فلتر: فقط صفقات البوت
            if ticket is None and pos.magic != MT5_MAGIC_NUMBER:
                continue

            # تحديد نوع الإغلاق (عكس الصفقة)
            if pos.type == self.mt5.ORDER_TYPE_BUY:
                close_type = self.mt5.ORDER_TYPE_SELL
                close_price = self.mt5.symbol_info_tick(pos.symbol).bid
            else:
                close_type = self.mt5.ORDER_TYPE_BUY
                close_price = self.mt5.symbol_info_tick(pos.symbol).ask

            request = {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": close_price,
                "deviation": MT5_DEVIATION,
                "magic": MT5_MAGIC_NUMBER,
                "comment": "ICT Bot Close",
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self.mt5.ORDER_FILLING_IOC,
            }

            result = self.mt5.order_send(request)

            if result and result.retcode == self.mt5.TRADE_RETCODE_DONE:
                print(f"✅ تم إغلاق صفقة #{pos.ticket} | ربح: {pos.profit}")
                results.append({
                    "ticket": pos.ticket,
                    "profit": pos.profit,
                    "close_price": close_price,
                })
            else:
                error = result.comment if result else "unknown"
                print(f"❌ فشل إغلاق #{pos.ticket}: {error}")

        return results

    def close_all(self, symbol=None):
        """إغلاق كل صفقات البوت"""
        return self.close_position(ticket=None, symbol=symbol)

    def get_open_positions(self, symbol=None):
        """جلب الصفقات المفتوحة"""
        if not self._ensure_connected():
            return []

        symbol = symbol or SYMBOL_MT5
        positions = self.mt5.positions_get(symbol=symbol)

        if positions is None:
            return []

        result = []
        for pos in positions:
            if pos.magic == MT5_MAGIC_NUMBER:
                result.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": "BUY" if pos.type == 0 else "SELL",
                    "volume": pos.volume,
                    "open_price": pos.price_open,
                    "current_price": pos.price_current,
                    "sl": pos.sl,
                    "tp": pos.tp,
                    "profit": pos.profit,
                    "time": pos.time,
                })

        return result

    def modify_position(self, ticket, sl=None, tp=None):
        """تعديل SL/TP لصفقة مفتوحة"""
        if not self._ensure_connected():
            return False

        positions = self.mt5.positions_get(ticket=ticket)
        if not positions:
            print(f"❌ الصفقة #{ticket} مش موجودة")
            return False

        pos = positions[0]
        new_sl = sl if sl is not None else pos.sl
        new_tp = tp if tp is not None else pos.tp

        sym_info = self.get_symbol_info(pos.symbol)
        digits = sym_info["digits"] if sym_info else 3
        new_sl = round(new_sl, digits)
        new_tp = round(new_tp, digits)

        request = {
            "action": self.mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": new_tp,
        }

        result = self.mt5.order_send(request)

        if result and result.retcode == self.mt5.TRADE_RETCODE_DONE:
            print(f"✅ تم تعديل #{ticket}: SL={new_sl} TP={new_tp}")
            return True
        else:
            error = result.comment if result else "unknown"
            print(f"❌ فشل تعديل #{ticket}: {error}")
            return False


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    executor = Executor()

    if executor.connect():
        # معلومات الحساب
        info = executor.get_account_info()
        print(f"\n💰 الرصيد: ${info['balance']}")
        print(f"📊 الإيكويتي: ${info['equity']}")
        print(f"🏷️ Demo: {info['is_demo']}")

        # معلومات الرمز
        sym = executor.get_symbol_info()
        if sym:
            print(f"\n📊 {sym['symbol']}: Bid={sym['bid']} Ask={sym['ask']}")
            print(f"   Spread: {sym['spread']} | Min Lot: {sym['lot_min']}")

        # عرض الصفقات المفتوحة
        positions = executor.get_open_positions()
        print(f"\n📋 صفقات مفتوحة: {len(positions)}")
        for p in positions:
            print(f"   #{p['ticket']} {p['type']} {p['volume']}lots P/L: {p['profit']}")

        executor.disconnect()