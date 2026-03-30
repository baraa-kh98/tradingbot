"""
ICT Core Engine — محرك استراتيجية ICT الأساسي

يحتوي على كل حسابات:
- Market Structure (BOS / CHoCH)
- Order Blocks (OB)
- Fair Value Gaps (FVG)
- Liquidity Sweeps
- Premium/Discount Zones & OTE
"""

import pandas as pd
import numpy as np
from config import (
    SWING_LOOKBACK,
    OB_DISPLACEMENT_MULTIPLIER,
    OB_MAX_AGE,
    FVG_MIN_SIZE_PIPS,
    FVG_MAX_AGE,
    PIP_VALUE,
    LIQ_EQUAL_THRESHOLD,
    LIQ_SWEEP_PIPS,
    OTE_FIB_LOW,
    OTE_FIB_HIGH,
)


# ═══════════════════════════════════════════════════════════════
# 1. SWING POINTS — نقاط التأرجح
# ═══════════════════════════════════════════════════════════════

def detect_swing_points(data, lookback=None):
    """
    تحديد Swing Highs و Swing Lows

    Swing High = شمعة أعلاها أعلى من كل الشموع المحيطة (lookback يمين ويسار)
    Swing Low = شمعة أدناها أدنى من كل الشموع المحيطة
    """
    if lookback is None:
        lookback = SWING_LOOKBACK

    highs = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
    lows = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
    n = len(data)

    swing_highs = []  # [(index, price), ...]
    swing_lows = []

    for i in range(lookback, n - lookback):
        # Swing High: أعلى من كل الشموع المحيطة
        is_swing_high = True
        for j in range(1, lookback + 1):
            if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                is_swing_high = False
                break
        if is_swing_high:
            swing_highs.append({"index": i, "price": float(highs[i])})

        # Swing Low: أدنى من كل الشموع المحيطة
        is_swing_low = True
        for j in range(1, lookback + 1):
            if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                is_swing_low = False
                break
        if is_swing_low:
            swing_lows.append({"index": i, "price": float(lows[i])})

    return swing_highs, swing_lows


# ═══════════════════════════════════════════════════════════════
# 2. MARKET STRUCTURE — هيكل السوق (BOS / CHoCH)
# ═══════════════════════════════════════════════════════════════

def detect_market_structure(data, lookback=None):
    """
    كشف كسر الهيكل (BOS) وتغيير الطابع (CHoCH)

    BOS (Break of Structure):
        - صاعد: السعر يكسر فوق آخر Swing High في ترند صاعد
        - هابط: السعر يكسر تحت آخر Swing Low في ترند هابط

    CHoCH (Change of Character):
        - من هابط لصاعد: السعر يكسر فوق Swing High في ترند هابط
        - من صاعد لهابط: السعر يكسر تحت Swing Low في ترند صاعد
    """
    swing_highs, swing_lows = detect_swing_points(data, lookback)

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return {"trend": "NEUTRAL", "events": [], "last_event": None}

    close = data["Close"].values if isinstance(data["Close"], pd.Series) else data["Close"].squeeze().values
    high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
    low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values

    # تحديد الاتجاه الأولي من أول نقطتين
    events = []
    trend = "NEUTRAL"

    # نبني قائمة مرتبة من كل الـ swings
    all_swings = []
    for sh in swing_highs:
        all_swings.append({"type": "high", "index": sh["index"], "price": sh["price"]})
    for sl in swing_lows:
        all_swings.append({"type": "low", "index": sl["index"], "price": sl["price"]})
    all_swings.sort(key=lambda x: x["index"])

    # تحديد الاتجاه الأولي
    if len(all_swings) >= 4:
        recent_highs = [s for s in all_swings if s["type"] == "high"][-2:]
        recent_lows = [s for s in all_swings if s["type"] == "low"][-2:]

        if len(recent_highs) >= 2 and len(recent_lows) >= 2:
            if (recent_highs[-1]["price"] > recent_highs[-2]["price"] and
                    recent_lows[-1]["price"] > recent_lows[-2]["price"]):
                trend = "BULLISH"
            elif (recent_highs[-1]["price"] < recent_highs[-2]["price"] and
                  recent_lows[-1]["price"] < recent_lows[-2]["price"]):
                trend = "BEARISH"

    # كشف BOS و CHoCH
    last_sh = swing_highs[-2] if len(swing_highs) >= 2 else swing_highs[-1]
    last_sl = swing_lows[-2] if len(swing_lows) >= 2 else swing_lows[-1]

    # البحث في الشموع الأخيرة عن كسر
    search_start = max(last_sh["index"], last_sl["index"])
    n = len(data)

    for i in range(search_start, n):
        # كسر Swing High
        if high[i] > last_sh["price"]:
            if trend == "BULLISH":
                event_type = "BOS_BULLISH"
            else:
                event_type = "CHoCH_BULLISH"
                trend = "BULLISH"
            events.append({
                "type": event_type,
                "index": i,
                "price": last_sh["price"],
                "break_price": float(high[i])
            })
            # تحديث آخر swing high مكسور
            for sh in swing_highs:
                if sh["index"] > last_sh["index"]:
                    last_sh = sh
                    break

        # كسر Swing Low
        if low[i] < last_sl["price"]:
            if trend == "BEARISH":
                event_type = "BOS_BEARISH"
            else:
                event_type = "CHoCH_BEARISH"
                trend = "BEARISH"
            events.append({
                "type": event_type,
                "index": i,
                "price": last_sl["price"],
                "break_price": float(low[i])
            })
            # تحديث آخر swing low مكسور
            for sl in swing_lows:
                if sl["index"] > last_sl["index"]:
                    last_sl = sl
                    break

    last_event = events[-1] if events else None

    return {
        "trend": trend,
        "events": events,
        "last_event": last_event,
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
    }


# ═══════════════════════════════════════════════════════════════
# 3. ORDER BLOCKS — كتل الأوامر
# ═══════════════════════════════════════════════════════════════

def _calculate_atr(data, period=14):
    """حساب ATR (Average True Range)"""
    high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
    low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
    close = data["Close"].values if isinstance(data["Close"], pd.Series) else data["Close"].squeeze().values

    tr = np.zeros(len(data))
    for i in range(1, len(data)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )

    atr = pd.Series(tr).rolling(window=period).mean().values
    return atr


def detect_order_blocks(data, max_age=None):
    """
    كشف Order Blocks

    Bullish OB:
        - آخر شمعة هبوطية (Close < Open) قبل حركة صعودية قوية (displacement)
        - Displacement = شمعة صعودية بجسم أكبر من 1.5x ATR

    Bearish OB:
        - آخر شمعة صعودية (Close > Open) قبل حركة هبوطية قوية
        - Displacement = شمعة هبوطية بجسم أكبر من 1.5x ATR

    يرجع فقط OBs التي لم يتم اختراقها (mitigated)
    """
    if max_age is None:
        max_age = OB_MAX_AGE

    open_p = data["Open"].values if isinstance(data["Open"], pd.Series) else data["Open"].squeeze().values
    high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
    low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
    close = data["Close"].values if isinstance(data["Close"], pd.Series) else data["Close"].squeeze().values
    atr = _calculate_atr(data)

    n = len(data)
    bullish_obs = []
    bearish_obs = []

    for i in range(2, n):
        if np.isnan(atr[i]):
            continue

        body_size = abs(close[i] - open_p[i])
        displacement_threshold = atr[i] * OB_DISPLACEMENT_MULTIPLIER

        # Bullish Displacement: شمعة صعودية قوية
        if close[i] > open_p[i] and body_size > displacement_threshold:
            # البحث عن آخر شمعة هبوطية قبلها
            for j in range(i - 1, max(i - 4, 0), -1):
                if close[j] < open_p[j]:  # شمعة هبوطية
                    ob = {
                        "type": "BULLISH",
                        "index": j,
                        "top": float(open_p[j]),     # أعلى OB = Open (لأن هبوطية)
                        "bottom": float(close[j]),   # أدنى OB = Close
                        "low": float(low[j]),        # أدنى الشمعة الكامل
                        "displacement_index": i,
                        "mitigated": False,
                    }
                    bullish_obs.append(ob)
                    break

        # Bearish Displacement: شمعة هبوطية قوية
        elif close[i] < open_p[i] and body_size > displacement_threshold:
            # البحث عن آخر شمعة صعودية قبلها
            for j in range(i - 1, max(i - 4, 0), -1):
                if close[j] > open_p[j]:  # شمعة صعودية
                    ob = {
                        "type": "BEARISH",
                        "index": j,
                        "top": float(close[j]),      # أعلى OB = Close (لأن صعودية)
                        "bottom": float(open_p[j]),   # أدنى OB = Open
                        "high": float(high[j]),       # أعلى الشمعة الكامل
                        "displacement_index": i,
                        "mitigated": False,
                    }
                    bearish_obs.append(ob)
                    break

    # تحقق من OBs المخترقة (mitigated)
    active_bullish = []
    for ob in bullish_obs:
        mitigated = False
        for k in range(ob["displacement_index"] + 1, n):
            if low[k] < ob["bottom"]:  # السعر اخترق أدنى OB
                mitigated = True
                break
        if not mitigated and (n - 1 - ob["index"]) <= max_age:
            ob["mitigated"] = False
            active_bullish.append(ob)

    active_bearish = []
    for ob in bearish_obs:
        mitigated = False
        for k in range(ob["displacement_index"] + 1, n):
            if high[k] > ob["top"]:  # السعر اخترق أعلى OB
                mitigated = True
                break
        if not mitigated and (n - 1 - ob["index"]) <= max_age:
            ob["mitigated"] = False
            active_bearish.append(ob)

    return {
        "bullish": active_bullish,
        "bearish": active_bearish,
    }


# ═══════════════════════════════════════════════════════════════
# 4. FAIR VALUE GAPS — فجوات القيمة العادلة
# ═══════════════════════════════════════════════════════════════

def detect_fvg(data, max_age=None):
    """
    كشف Fair Value Gaps (FVG)

    Bullish FVG (فجوة صعودية):
        - Low[i] > High[i-2]
        - يعني هناك فجوة بين الشمعة 3 والشمعة 1

    Bearish FVG (فجوة هبوطية):
        - High[i] < Low[i-2]

    يرجع فقط FVGs التي لم يتم ملؤها بالكامل
    """
    if max_age is None:
        max_age = FVG_MAX_AGE

    high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
    low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
    min_size = FVG_MIN_SIZE_PIPS * PIP_VALUE
    n = len(data)

    bullish_fvgs = []
    bearish_fvgs = []

    for i in range(2, n):
        # Bullish FVG
        gap_bottom = float(high[i - 2])
        gap_top = float(low[i])
        if gap_top > gap_bottom and (gap_top - gap_bottom) >= min_size:
            bullish_fvgs.append({
                "type": "BULLISH",
                "index": i - 1,  # الشمعة الوسطى
                "top": gap_top,
                "bottom": gap_bottom,
                "midpoint": round((gap_top + gap_bottom) / 2, 5),
                "filled": False,
            })

        # Bearish FVG
        gap_top_b = float(low[i - 2])
        gap_bottom_b = float(high[i])
        if gap_top_b > gap_bottom_b and (gap_top_b - gap_bottom_b) >= min_size:
            bearish_fvgs.append({
                "type": "BEARISH",
                "index": i - 1,
                "top": gap_top_b,
                "bottom": gap_bottom_b,
                "midpoint": round((gap_top_b + gap_bottom_b) / 2, 5),
                "filled": False,
            })

    # تحقق من FVGs المملوءة
    active_bullish = []
    for fvg in bullish_fvgs:
        filled = False
        for k in range(fvg["index"] + 2, n):
            if low[k] <= fvg["bottom"]:  # السعر ملأ الفجوة
                filled = True
                break
        if not filled and (n - 1 - fvg["index"]) <= max_age:
            active_bullish.append(fvg)

    active_bearish = []
    for fvg in bearish_fvgs:
        filled = False
        for k in range(fvg["index"] + 2, n):
            if high[k] >= fvg["top"]:  # السعر ملأ الفجوة
                filled = True
                break
        if not filled and (n - 1 - fvg["index"]) <= max_age:
            active_bearish.append(fvg)

    return {
        "bullish": active_bullish,
        "bearish": active_bearish,
    }


# ═══════════════════════════════════════════════════════════════
# 5. LIQUIDITY — مستويات السيولة واكتساحها
# ═══════════════════════════════════════════════════════════════

def detect_liquidity_levels(data, lookback=None):
    """
    تحديد مستويات السيولة:
    - Equal Highs: قمم بأسعار متقاربة (سيولة فوقها)
    - Equal Lows: قيعان بأسعار متقاربة (سيولة تحتها)
    - Previous session highs/lows
    """
    swing_highs, swing_lows = detect_swing_points(data, lookback)
    threshold = LIQ_EQUAL_THRESHOLD

    # Equal Highs
    equal_highs = []
    for i in range(len(swing_highs)):
        for j in range(i + 1, len(swing_highs)):
            if abs(swing_highs[i]["price"] - swing_highs[j]["price"]) <= threshold:
                level = round((swing_highs[i]["price"] + swing_highs[j]["price"]) / 2, 5)
                if not any(abs(eh["price"] - level) < threshold for eh in equal_highs):
                    equal_highs.append({
                        "type": "EQUAL_HIGH",
                        "price": level,
                        "indices": [swing_highs[i]["index"], swing_highs[j]["index"]],
                    })

    # Equal Lows
    equal_lows = []
    for i in range(len(swing_lows)):
        for j in range(i + 1, len(swing_lows)):
            if abs(swing_lows[i]["price"] - swing_lows[j]["price"]) <= threshold:
                level = round((swing_lows[i]["price"] + swing_lows[j]["price"]) / 2, 5)
                if not any(abs(el["price"] - level) < threshold for el in equal_lows):
                    equal_lows.append({
                        "type": "EQUAL_LOW",
                        "price": level,
                        "indices": [swing_lows[i]["index"], swing_lows[j]["index"]],
                    })

    # أعلى وأدنى الشموع الأخيرة (Previous Day/Session)
    high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
    low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
    n = len(data)

    # آخر 24 شمعة (لتقريب PDH/PDL على إطار الساعة)
    session_len = min(24, n - 1)
    pdh = float(max(high[n - session_len - 1:n - 1]))
    pdl = float(min(low[n - session_len - 1:n - 1]))

    return {
        "equal_highs": equal_highs,
        "equal_lows": equal_lows,
        "pdh": pdh,
        "pdl": pdl,
        "swing_highs": [sh["price"] for sh in swing_highs[-5:]],
        "swing_lows": [sl["price"] for sl in swing_lows[-5:]],
    }


def detect_liquidity_sweep(data, liquidity_levels):
    """
    كشف اكتساح السيولة (Liquidity Sweep / Grab)

    يحصل عندما السعر يخترق مستوى سيولة (equal high/low, PDH/PDL)
    ثم يرجع بقوة بنفس الشمعة أو الشمعة التالية

    هذا يدل على أن Smart Money جمعت السيولة وتغير الاتجاه
    """
    high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
    low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
    close = data["Close"].values if isinstance(data["Close"], pd.Series) else data["Close"].squeeze().values
    open_p = data["Open"].values if isinstance(data["Open"], pd.Series) else data["Open"].squeeze().values
    n = len(data)

    sweep_buffer = LIQ_SWEEP_PIPS * PIP_VALUE
    sweeps = []

    # تجميع كل مستويات السيولة
    buy_side_levels = []  # سيولة فوق (Sell-side targeting buy-side)
    sell_side_levels = []  # سيولة تحت

    for eh in liquidity_levels.get("equal_highs", []):
        buy_side_levels.append(eh["price"])
    buy_side_levels.append(liquidity_levels.get("pdh", 0))
    for sh in liquidity_levels.get("swing_highs", []):
        buy_side_levels.append(sh)

    for el in liquidity_levels.get("equal_lows", []):
        sell_side_levels.append(el["price"])
    sell_side_levels.append(liquidity_levels.get("pdl", float("inf")))
    for sl in liquidity_levels.get("swing_lows", []):
        sell_side_levels.append(sl)

    # كشف Sweeps في آخر 10 شموع
    search_range = min(10, n - 1)
    for i in range(n - search_range, n):
        # Sweep فوق (Bearish Sweep — السعر اكتسح سيولة الشراء ثم نزل)
        for level in buy_side_levels:
            if level > 0 and high[i] > level + sweep_buffer and close[i] < level:
                sweeps.append({
                    "type": "BEARISH_SWEEP",
                    "index": i,
                    "level": level,
                    "wick_high": float(high[i]),
                    "close": float(close[i]),
                })

        # Sweep تحت (Bullish Sweep — السعر اكتسح سيولة البيع ثم طلع)
        for level in sell_side_levels:
            if level < float("inf") and low[i] < level - sweep_buffer and close[i] > level:
                sweeps.append({
                    "type": "BULLISH_SWEEP",
                    "index": i,
                    "level": level,
                    "wick_low": float(low[i]),
                    "close": float(close[i]),
                })

    return sweeps


# ═══════════════════════════════════════════════════════════════
# 6. PREMIUM / DISCOUNT & OTE — مناطق الأسعار المثالية
# ═══════════════════════════════════════════════════════════════

def get_premium_discount_zones(data, lookback=None):
    """
    حساب مناطق Premium / Discount بناءً على آخر Swing High و Swing Low

    - Premium Zone: فوق 50% — منطقة بيع مثالية
    - Discount Zone: تحت 50% — منطقة شراء مثالية
    - OTE (Optimal Trade Entry): 62% - 79% فيبوناتشي
    - Equilibrium: 50% — نقطة التوازن

    في ترند صاعد: نشتري من Discount (ارتدادات)
    في ترند هابط: نبيع من Premium (ارتدادات)
    """
    swing_highs, swing_lows = detect_swing_points(data, lookback)

    if not swing_highs or not swing_lows:
        return None

    # آخر swing high و low
    last_high = max(swing_highs[-3:], key=lambda x: x["price"]) if len(swing_highs) >= 3 else swing_highs[-1]
    last_low = min(swing_lows[-3:], key=lambda x: x["price"]) if len(swing_lows) >= 3 else swing_lows[-1]

    swing_range = last_high["price"] - last_low["price"]
    if swing_range <= 0:
        return None

    equilibrium = last_low["price"] + swing_range * 0.5

    close = data["Close"].values if isinstance(data["Close"], pd.Series) else data["Close"].squeeze().values
    current_price = float(close[-1])

    # حساب مناطق OTE
    # في ترند صاعد: OTE = ارتداد لأسفل (من الأعلى)
    ote_buy_high = last_high["price"] - swing_range * OTE_FIB_LOW    # 62%
    ote_buy_low = last_high["price"] - swing_range * OTE_FIB_HIGH    # 79%

    # في ترند هابط: OTE = ارتداد لأعلى (من الأسفل)
    ote_sell_low = last_low["price"] + swing_range * OTE_FIB_LOW
    ote_sell_high = last_low["price"] + swing_range * OTE_FIB_HIGH

    # تحديد المنطقة الحالية
    if current_price > equilibrium:
        zone = "PREMIUM"
    elif current_price < equilibrium:
        zone = "DISCOUNT"
    else:
        zone = "EQUILIBRIUM"

    # هل السعر في OTE؟
    in_buy_ote = ote_buy_low <= current_price <= ote_buy_high
    in_sell_ote = ote_sell_low <= current_price <= ote_sell_high

    return {
        "swing_high": last_high["price"],
        "swing_low": last_low["price"],
        "equilibrium": round(equilibrium, 5),
        "zone": zone,
        "current_price": current_price,
        "premium_start": round(equilibrium, 5),
        "discount_end": round(equilibrium, 5),
        "ote_buy": {"high": round(ote_buy_high, 5), "low": round(ote_buy_low, 5)},
        "ote_sell": {"high": round(ote_sell_high, 5), "low": round(ote_sell_low, 5)},
        "in_buy_ote": in_buy_ote,
        "in_sell_ote": in_sell_ote,
    }


# ═══════════════════════════════════════════════════════════════
# 7. FULL ICT ANALYSIS — التحليل الشامل
# ═══════════════════════════════════════════════════════════════

def run_full_ict_analysis(data, lookback=None):
    """
    تشغيل كل تحليلات ICT ورجع النتائج مجمّعة

    هذه الدالة الرئيسية — تستدعيها من signal_generator
    """
    structure = detect_market_structure(data, lookback)
    order_blocks = detect_order_blocks(data)
    fvgs = detect_fvg(data)
    liquidity = detect_liquidity_levels(data, lookback)
    sweeps = detect_liquidity_sweep(data, liquidity)
    pd_zones = get_premium_discount_zones(data, lookback)

    return {
        "structure": structure,
        "order_blocks": order_blocks,
        "fvgs": fvgs,
        "liquidity": liquidity,
        "sweeps": sweeps,
        "pd_zones": pd_zones,
    }
