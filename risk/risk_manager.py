"""
Risk Manager — إدارة مخاطر متقدمة

ميزات:
1. حساب حجم الصفقة الديناميكي
2. Partial Take Profit (جني أرباح جزئي)
3. Break-Even (نقل SL للدخول عند 1R)
4. Trailing Stop Loss (وقف خسارة متحرك)
5. حدود يومية/أسبوعية
"""

from config import (
    BALANCE,
    RISK_PERCENT,
    MIN_RR_RATIO,
    PIP_VALUE,
)


class RiskManager:
    """إدارة مخاطر متقدمة"""

    def __init__(self, balance=None, risk_percent=None):
        self.balance = balance or BALANCE
        self.risk_percent = risk_percent or RISK_PERCENT

        # ═══ إعدادات الإدارة المتقدمة ═══

        # Partial TP — جني أرباح جزئي
        self.partial_tp_enabled = True
        self.partial_tp_ratio = 0.5          # أغلق 50% عند TP1
        self.partial_tp1_rr = 1.5            # TP1 عند 1.5R
        self.partial_tp2_rr = 3.0            # TP2 (النهائي) عند 3R

        # Break-Even — نقل SL للدخول
        self.breakeven_enabled = True
        self.breakeven_trigger_rr = 1.0      # نقل SL عند 1R ربح
        self.breakeven_offset_pips = 2       # SL فوق/تحت الدخول بنقطتين (لحماية من الأخبار)

        # Trailing Stop — وقف متحرك
        self.trailing_enabled = True
        self.trailing_trigger_rr = 1.5       # يبدأ Trailing بعد 1.5R
        self.trailing_distance_atr = 1.5     # المسافة = 1.5 × ATR

        # حدود يومية
        self.max_daily_trades = 3            # أقصى عدد صفقات يومياً
        self.max_daily_loss_percent = 3.0    # أقصى خسارة يومية %
        self.max_open_positions = 1          # أقصى صفقات مفتوحة (زوج واحد)

        # تتبع
        self.daily_trades = 0
        self.daily_pnl = 0.0

    # ═══════════════════════════════════════════════════════════
    # حساب حجم الصفقة
    # ═══════════════════════════════════════════════════════════

    def calculate_position_size(self, entry, stop_loss):
        """حساب حجم الصفقة بناءً على المخاطرة"""
        risk_amount = self.balance * (self.risk_percent / 100)
        pips_at_risk = abs(entry - stop_loss)
        if pips_at_risk == 0:
            return 0
        position_size = round(risk_amount / pips_at_risk, 2)
        return position_size

    def calculate_lots(self, entry, stop_loss):
        """حساب حجم اللوت (لـ MT5)"""
        position_size = self.calculate_position_size(entry, stop_loss)
        lots = round(position_size / 100000, 2)
        return max(lots, 0.01)  # minimum 0.01 lot

    def calculate_rr(self, entry, stop_loss, take_profit):
        """حساب نسبة الربح/الخسارة"""
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        if risk == 0:
            return 0
        return round(reward / risk, 2)

    def is_trade_valid(self, entry, stop_loss, take_profit, min_rr=None):
        """هل الصفقة مقبولة؟"""
        rr = self.calculate_rr(entry, stop_loss, take_profit)
        min_ratio = min_rr or MIN_RR_RATIO
        return rr >= min_ratio

    # ═══════════════════════════════════════════════════════════
    # مستويات TP المتعددة
    # ═══════════════════════════════════════════════════════════

    def get_tp_levels(self, entry, stop_loss, direction):
        """
        حساب مستويات TP المتعددة

        returns: dict مع tp1, tp2, والنسب
        """
        risk = abs(entry - stop_loss)

        if direction == "BUY":
            tp1 = round(entry + risk * self.partial_tp1_rr, 3)
            tp2 = round(entry + risk * self.partial_tp2_rr, 3)
        else:  # SELL
            tp1 = round(entry - risk * self.partial_tp1_rr, 3)
            tp2 = round(entry - risk * self.partial_tp2_rr, 3)

        return {
            "tp1": tp1,
            "tp1_rr": self.partial_tp1_rr,
            "tp1_close_ratio": self.partial_tp_ratio,  # أغلق 50% عند TP1
            "tp2": tp2,
            "tp2_rr": self.partial_tp2_rr,
        }

    # ═══════════════════════════════════════════════════════════
    # Break-Even
    # ═══════════════════════════════════════════════════════════

    def should_move_to_breakeven(self, entry, current_price, stop_loss, direction):
        """
        هل يجب نقل SL لنقطة التعادل؟

        returns: (bool, new_sl)
        """
        if not self.breakeven_enabled:
            return False, stop_loss

        risk = abs(entry - stop_loss)
        offset = self.breakeven_offset_pips * PIP_VALUE

        if direction == "BUY":
            current_profit = current_price - entry
            trigger = risk * self.breakeven_trigger_rr
            if current_profit >= trigger and stop_loss < entry:
                new_sl = round(entry + offset, 3)
                return True, new_sl

        else:  # SELL
            current_profit = entry - current_price
            trigger = risk * self.breakeven_trigger_rr
            if current_profit >= trigger and stop_loss > entry:
                new_sl = round(entry - offset, 3)
                return True, new_sl

        return False, stop_loss

    # ═══════════════════════════════════════════════════════════
    # Trailing Stop
    # ═══════════════════════════════════════════════════════════

    def calculate_trailing_sl(self, entry, current_price, current_sl, direction, atr_value):
        """
        حساب Trailing Stop Loss

        returns: (bool should_update, float new_sl)
        """
        if not self.trailing_enabled or atr_value is None or atr_value == 0:
            return False, current_sl

        risk = abs(entry - current_sl) if current_sl else atr_value * 2
        trailing_distance = atr_value * self.trailing_distance_atr

        if direction == "BUY":
            current_profit = current_price - entry
            trigger = risk * self.trailing_trigger_rr

            if current_profit >= trigger:
                new_sl = round(current_price - trailing_distance, 3)
                if new_sl > current_sl:
                    return True, new_sl

        else:  # SELL
            current_profit = entry - current_price
            trigger = risk * self.trailing_trigger_rr

            if current_profit >= trigger:
                new_sl = round(current_price + trailing_distance, 3)
                if new_sl < current_sl:
                    return True, new_sl

        return False, current_sl

    # ═══════════════════════════════════════════════════════════
    # إدارة الصفقة الشاملة
    # ═══════════════════════════════════════════════════════════

    def manage_open_position(self, position, current_price, atr_value=None):
        """
        إدارة صفقة مفتوحة — يتحقق من كل القواعد

        position: dict مع {entry, sl, tp, direction, lots, partial_closed}
        current_price: السعر الحالي
        atr_value: قيمة ATR الحالية

        returns: dict مع الإجراءات المطلوبة
        """
        entry = position["entry"]
        sl = position["sl"]
        tp = position["tp"]
        direction = position["direction"]
        lots = position["lots"]
        partial_closed = position.get("partial_closed", False)

        actions = {
            "update_sl": False,
            "new_sl": sl,
            "close_partial": False,
            "partial_lots": 0,
            "reason": "",
        }

        risk = abs(entry - sl)
        if risk == 0:
            return actions

        # حساب الربح الحالي بالنقاط
        if direction == "BUY":
            profit_pips = (current_price - entry) / PIP_VALUE
            profit_rr = (current_price - entry) / risk
        else:
            profit_pips = (entry - current_price) / PIP_VALUE
            profit_rr = (entry - current_price) / risk

        # ─── 1. Partial TP ───
        if self.partial_tp_enabled and not partial_closed:
            if profit_rr >= self.partial_tp1_rr:
                actions["close_partial"] = True
                actions["partial_lots"] = round(lots * self.partial_tp_ratio, 2)
                actions["partial_lots"] = max(actions["partial_lots"], 0.01)
                actions["reason"] += f"✂️ إغلاق جزئي {actions['partial_lots']} lots عند {self.partial_tp1_rr}R | "

        # ─── 2. Break-Even ───
        should_be, new_sl = self.should_move_to_breakeven(entry, current_price, sl, direction)
        if should_be:
            actions["update_sl"] = True
            actions["new_sl"] = new_sl
            actions["reason"] += f"🔒 نقل SL لنقطة التعادل ({new_sl}) | "

        # ─── 3. Trailing Stop ───
        if atr_value:
            should_trail, trail_sl = self.calculate_trailing_sl(
                entry, current_price, sl, direction, atr_value
            )
            if should_trail:
                # اختار الأفضل (الأعلى لـ BUY, الأقل لـ SELL)
                if direction == "BUY" and trail_sl > actions["new_sl"]:
                    actions["update_sl"] = True
                    actions["new_sl"] = trail_sl
                    actions["reason"] += f"📈 Trailing SL → {trail_sl} | "
                elif direction == "SELL" and trail_sl < actions["new_sl"]:
                    actions["update_sl"] = True
                    actions["new_sl"] = trail_sl
                    actions["reason"] += f"📉 Trailing SL → {trail_sl} | "

        # إضافة معلومات
        actions["profit_pips"] = round(profit_pips, 1)
        actions["profit_rr"] = round(profit_rr, 2)

        return actions

    # ═══════════════════════════════════════════════════════════
    # حدود يومية
    # ═══════════════════════════════════════════════════════════

    def can_trade(self, open_positions_count=0):
        """
        هل مسموح نفتح صفقة جديدة؟

        returns: (bool, str reason)
        """
        if open_positions_count >= self.max_open_positions:
            return False, f"⚠️ فيه صفقة مفتوحة أصلاً ({open_positions_count})"

        if self.daily_trades >= self.max_daily_trades:
            return False, f"⚠️ وصلت الحد اليومي ({self.max_daily_trades} صفقات)"

        daily_loss_limit = self.balance * (self.max_daily_loss_percent / 100)
        if self.daily_pnl <= -daily_loss_limit:
            return False, f"🛑 وصلت الحد اليومي للخسارة (${daily_loss_limit})"

        return True, "✅ مسموح بالتداول"

    def record_trade(self, pnl):
        """تسجيل صفقة منتهية"""
        self.daily_trades += 1
        self.daily_pnl += pnl

    def reset_daily(self):
        """إعادة تعيين الحدود اليومية (يُستدعى بداية كل يوم)"""
        self.daily_trades = 0
        self.daily_pnl = 0.0

    # ═══════════════════════════════════════════════════════════
    # معلومات الصفقة الكاملة
    # ═══════════════════════════════════════════════════════════

    def get_trade_info(self, entry, stop_loss, take_profit):
        """معلومات الصفقة الكاملة"""
        size = self.calculate_position_size(entry, stop_loss)
        lots = self.calculate_lots(entry, stop_loss)
        rr = self.calculate_rr(entry, stop_loss, take_profit)
        valid = self.is_trade_valid(entry, stop_loss, take_profit)

        direction = "BUY" if take_profit > entry else "SELL"
        tp_levels = self.get_tp_levels(entry, stop_loss, direction) if self.partial_tp_enabled else None

        return {
            "position_size": size,
            "lots": lots,
            "rr_ratio": rr,
            "trade_valid": valid,
            "risk_amount": round(self.balance * self.risk_percent / 100, 2),
            "direction": direction,
            "tp_levels": tp_levels,
        }


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    rm = RiskManager(balance=3000, risk_percent=1.0)

    entry = 144.500
    sl = 144.200
    tp = 145.400

    print("═══ معلومات الصفقة ═══")
    info = rm.get_trade_info(entry, sl, tp)
    print(f"  حجم الصفقة: {info['position_size']} وحدة")
    print(f"  اللوت: {info['lots']}")
    print(f"  RR: 1:{info['rr_ratio']}")
    print(f"  المخاطرة: ${info['risk_amount']}")

    if info["tp_levels"]:
        tp = info["tp_levels"]
        print(f"\n═══ TP المتعددة ═══")
        print(f"  TP1: {tp['tp1']} ({tp['tp1_rr']}R) — أغلق {int(tp['tp1_close_ratio']*100)}%")
        print(f"  TP2: {tp['tp2']} ({tp['tp2_rr']}R) — الباقي")

    print(f"\n═══ محاكاة إدارة الصفقة ═══")
    position = {"entry": entry, "sl": sl, "tp": tp, "direction": "BUY", "lots": 0.03, "partial_closed": False}

    # محاكاة حركة السعر
    test_prices = [144.600, 144.800, 145.000, 145.200, 145.500]
    for price in test_prices:
        result = rm.manage_open_position(position, price, atr_value=0.15)
        print(f"\n  السعر: {price} | ربح: {result['profit_pips']} pips ({result['profit_rr']}R)")
        if result["update_sl"]:
            print(f"    → {result['reason']}")
            position["sl"] = result["new_sl"]
        if result["close_partial"]:
            print(f"    → {result['reason']}")
            position["partial_closed"] = True
