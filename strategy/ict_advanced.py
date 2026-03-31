"""
ICT Advanced — مفاهيم ICT المتقدمة

يحتوي على:
1. Breaker Blocks — OB مخترق يصبح دعم/مقاومة عكسي
2. Silver Bullet — نوافذ دخول ICT الزمنية
3. AMD (Accumulation, Manipulation, Distribution) — دورة السوق
4. Mitigation Blocks — OB تم لمسه ولكن لم يُخترق بالكامل
5. Inducement — فخ سيولة صغير
"""

import pandas as pd
import numpy as np
from config import (
    PIP_VALUE,
    OB_DISPLACEMENT_MULTIPLIER,
    OB_MAX_AGE,
)
from strategy.ict_core import _calculate_atr


# ═══════════════════════════════════════════════════════════════
# 1. BREAKER BLOCKS — كتل كاسرة
# ═══════════════════════════════════════════════════════════════

def detect_breaker_blocks(data, max_age=None):
    """
    Breaker Block = Order Block مخترق (mitigated)
    يتحول من دعم لمقاومة أو العكس

    Bullish Breaker (للشراء):
    - Bearish OB سابق تم اختراقه لأعلى
    - يصبح منطقة دعم (السعر يرتد منه لأعلى)

    Bearish Breaker (للبيع):
    - Bullish OB سابق تم اختراقه لأسفل
    - يصبح منطقة مقاومة (السعر يرتد منه لأسفل)
    """
    if max_age is None:
        max_age = OB_MAX_AGE

    open_p = data["Open"].values if isinstance(data["Open"], pd.Series) else data["Open"].squeeze().values
    high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
    low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
    close = data["Close"].values if isinstance(data["Close"], pd.Series) else data["Close"].squeeze().values
    atr = _calculate_atr(data)
    n = len(data)

    bullish_breakers = []
    bearish_breakers = []

    for i in range(2, n - 1):
        if np.isnan(atr[i]):
            continue

        body_size = abs(close[i] - open_p[i])
        displacement = atr[i] * OB_DISPLACEMENT_MULTIPLIER

        # البحث عن Bearish OB مخترق (يصبح Bullish Breaker)
        if close[i] > open_p[i] and body_size > displacement:
            for j in range(i - 1, max(i - 5, 0), -1):
                if close[j] > open_p[j]:  # شمعة صعودية سابقة (كانت Bearish OB)
                    ob_top = float(close[j])
                    ob_bottom = float(open_p[j])
                    # تأكد أن السعر اخترقها فعلاً ( كانت OB ثم انكسرت)
                    was_broken = False
                    for k in range(j + 1, i):
                        if low[k] < ob_bottom:
                            was_broken = True
                            break
                    if was_broken:
                        # تأكد ما رجع واخترقها مرة ثانية
                        still_valid = True
                        for k in range(i + 1, n):
                            if low[k] < ob_bottom:
                                still_valid = False
                                break
                        if still_valid and (n - 1 - j) <= max_age:
                            bullish_breakers.append({
                                "type": "BULLISH_BREAKER",
                                "index": j,
                                "top": ob_top,
                                "bottom": ob_bottom,
                                "break_index": i,
                            })
                    break

        # البحث عن Bullish OB مخترق (يصبح Bearish Breaker)
        if close[i] < open_p[i] and body_size > displacement:
            for j in range(i - 1, max(i - 5, 0), -1):
                if close[j] < open_p[j]:  # شمعة هبوطية سابقة (كانت Bullish OB)
                    ob_top = float(open_p[j])
                    ob_bottom = float(close[j])
                    was_broken = False
                    for k in range(j + 1, i):
                        if high[k] > ob_top:
                            was_broken = True
                            break
                    if was_broken:
                        still_valid = True
                        for k in range(i + 1, n):
                            if high[k] > ob_top:
                                still_valid = False
                                break
                        if still_valid and (n - 1 - j) <= max_age:
                            bearish_breakers.append({
                                "type": "BEARISH_BREAKER",
                                "index": j,
                                "top": ob_top,
                                "bottom": ob_bottom,
                                "break_index": i,
                            })
                    break

    return {"bullish": bullish_breakers, "bearish": bearish_breakers}


# ═══════════════════════════════════════════════════════════════
# 2. SILVER BULLET — نوافذ ICT الزمنية
# ═══════════════════════════════════════════════════════════════

def detect_silver_bullet(data):
    """
    Silver Bullet — نوافذ دخول ICT الزمنية

    3 نوافذ يومية (بتوقيت EST):
    1. London Open: 03:00 - 04:00 EST
    2. NY AM:       10:00 - 11:00 EST
    3. NY PM:       14:00 - 15:00 EST

    الفكرة: FVG تتشكل خلال هذه النوافذ = فرصة عالية الاحتمال
    """
    if not isinstance(data.index, pd.DatetimeIndex):
        return {"active": False, "window": None, "fvgs_in_window": []}

    high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
    low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
    n = len(data)

    # تحويل لـ EST
    try:
        import pytz
        est = pytz.timezone("US/Eastern")
        last_time = data.index[-1]
        if last_time.tzinfo is None:
            last_time = last_time.tz_localize("UTC").tz_convert(est)
        else:
            last_time = last_time.tz_convert(est)
        current_hour = last_time.hour
        current_minute = last_time.minute
    except Exception:
        return {"active": False, "window": None, "fvgs_in_window": []}

    # تحديد النافذة الحالية
    windows = {
        "LONDON_SB": (3, 0, 4, 0),     # 03:00 - 04:00 EST
        "NY_AM_SB":  (10, 0, 11, 0),    # 10:00 - 11:00 EST
        "NY_PM_SB":  (14, 0, 15, 0),    # 14:00 - 15:00 EST
    }

    active_window = None
    for name, (sh, sm, eh, em) in windows.items():
        start_mins = sh * 60 + sm
        end_mins = eh * 60 + em
        current_mins = current_hour * 60 + current_minute
        if start_mins <= current_mins <= end_mins:
            active_window = name
            break

    if not active_window:
        return {"active": False, "window": None, "fvgs_in_window": []}

    # البحث عن FVGs تشكلت خلال النافذة
    min_size = 3 * PIP_VALUE  # FVG أصغر مقبول للـ Silver Bullet
    fvgs_in_window = []

    for i in range(max(2, n - 12), n):  # آخر 12 شمعة (ساعة تقريباً على 5min)
        # Bullish FVG
        gap_top = float(low[i])
        gap_bottom = float(high[i - 2])
        if gap_top > gap_bottom and (gap_top - gap_bottom) >= min_size:
            fvgs_in_window.append({
                "direction": "BULLISH",
                "top": gap_top,
                "bottom": gap_bottom,
                "index": i,
            })

        # Bearish FVG
        gap_top_b = float(low[i - 2])
        gap_bottom_b = float(high[i])
        if gap_top_b > gap_bottom_b and (gap_top_b - gap_bottom_b) >= min_size:
            fvgs_in_window.append({
                "direction": "BEARISH",
                "top": gap_top_b,
                "bottom": gap_bottom_b,
                "index": i,
            })

    return {
        "active": True,
        "window": active_window,
        "fvgs_in_window": fvgs_in_window,
    }


# ═══════════════════════════════════════════════════════════════
# 3. AMD — Accumulation, Manipulation, Distribution
# ═══════════════════════════════════════════════════════════════

def detect_amd_pattern(data, session_candles=24):
    """
    AMD (Accumulation, Manipulation, Distribution)

    المراحل:
    1. Accumulation: تداول ضيق (low volatility range)
    2. Manipulation: كسر وهمي (fake breakout) — اكتساح سيولة
    3. Distribution: الحركة الحقيقية بالاتجاه المعاكس

    يبحث في آخر جلسة (24 شمعة ساعية = يوم)
    """
    high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
    low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
    close = data["Close"].values if isinstance(data["Close"], pd.Series) else data["Close"].squeeze().values
    open_p = data["Open"].values if isinstance(data["Open"], pd.Series) else data["Open"].squeeze().values
    atr = _calculate_atr(data)
    n = len(data)

    if n < session_candles + 10:
        return {"detected": False, "phase": None}

    # ─── 1. Accumulation: تداول ضيق ───
    # أول 8 شموع من الجلسة
    acc_start = n - session_candles
    acc_end = acc_start + 8
    if acc_end >= n:
        return {"detected": False, "phase": None}

    acc_range = max(high[acc_start:acc_end]) - min(low[acc_start:acc_end])
    avg_atr = np.nanmean(atr[acc_start:acc_end])

    if avg_atr == 0 or np.isnan(avg_atr):
        return {"detected": False, "phase": None}

    acc_ratio = acc_range / (avg_atr * 8)

    # نطاق ضيق = accumulation
    if acc_ratio > 0.7:
        return {"detected": False, "phase": None, "reason": "لا يوجد accumulation واضح"}

    acc_high = max(high[acc_start:acc_end])
    acc_low = min(low[acc_start:acc_end])

    # ─── 2. Manipulation: كسر وهمي ───
    manip_start = acc_end
    manip_end = min(manip_start + 6, n)

    manipulation = None
    for i in range(manip_start, manip_end):
        # كسر فوق accumulation ثم رجوع
        if high[i] > acc_high and close[i] < acc_high:
            manipulation = {
                "type": "BEARISH_MANIP",
                "index": i,
                "sweep_price": float(high[i]),
                "close": float(close[i]),
            }
            break
        # كسر تحت accumulation ثم رجوع
        if low[i] < acc_low and close[i] > acc_low:
            manipulation = {
                "type": "BULLISH_MANIP",
                "index": i,
                "sweep_price": float(low[i]),
                "close": float(close[i]),
            }
            break

    if not manipulation:
        return {
            "detected": False,
            "phase": "ACCUMULATION",
            "accumulation_range": (float(acc_low), float(acc_high)),
        }

    # ─── 3. Distribution: الحركة الحقيقية ───
    dist_start = manipulation["index"] + 1

    if dist_start >= n:
        return {
            "detected": True,
            "phase": "MANIPULATION",
            "manipulation": manipulation,
            "accumulation_range": (float(acc_low), float(acc_high)),
            "bias": "BUY" if manipulation["type"] == "BULLISH_MANIP" else "SELL",
        }

    # تأكد إن في حركة بعد الـ manipulation
    dist_close = close[-1]
    if manipulation["type"] == "BULLISH_MANIP":
        dist_move = dist_close - manipulation["close"]
        if dist_move > avg_atr * 2:
            phase = "DISTRIBUTION"
            bias = "BUY"
        else:
            phase = "EARLY_DISTRIBUTION"
            bias = "BUY"
    else:
        dist_move = manipulation["close"] - dist_close
        if dist_move > avg_atr * 2:
            phase = "DISTRIBUTION"
            bias = "SELL"
        else:
            phase = "EARLY_DISTRIBUTION"
            bias = "SELL"

    return {
        "detected": True,
        "phase": phase,
        "manipulation": manipulation,
        "accumulation_range": (float(acc_low), float(acc_high)),
        "distribution_move": round(float(dist_move / PIP_VALUE), 1),
        "bias": bias,
    }


# ═══════════════════════════════════════════════════════════════
# 4. INDUCEMENT — فخ سيولة صغير
# ═══════════════════════════════════════════════════════════════

def detect_inducement(data, swing_lows, swing_highs):
    """
    Inducement — Minor liquidity sweep بين swing points

    يحصل عندما السعر يكسر minor swing point لجذب المتداولين
    ثم يعكس الاتجاه

    مفيد لتأكيد أن Smart Money بدأت التجميع
    """
    high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
    low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
    close = data["Close"].values if isinstance(data["Close"], pd.Series) else data["Close"].squeeze().values
    n = len(data)

    inducements = []

    # Bullish Inducement: كسر minor low ثم إغلاق فوقه
    for i in range(n - 10, n):
        if i < 1:
            continue
        for sl in swing_lows[-5:]:
            sl_price = sl["price"] if isinstance(sl, dict) else sl
            sl_idx = sl["index"] if isinstance(sl, dict) else 0
            if sl_idx >= i:
                continue
            if low[i] < sl_price and close[i] > sl_price:
                inducements.append({
                    "type": "BULLISH_INDUCEMENT",
                    "index": i,
                    "level": sl_price,
                    "wick": float(low[i]),
                })
                break

    # Bearish Inducement: كسر minor high ثم إغلاق تحته
    for i in range(n - 10, n):
        if i < 1:
            continue
        for sh in swing_highs[-5:]:
            sh_price = sh["price"] if isinstance(sh, dict) else sh
            sh_idx = sh["index"] if isinstance(sh, dict) else 0
            if sh_idx >= i:
                continue
            if high[i] > sh_price and close[i] < sh_price:
                inducements.append({
                    "type": "BEARISH_INDUCEMENT",
                    "index": i,
                    "level": sh_price,
                    "wick": float(high[i]),
                })
                break

    return inducements


# ═══════════════════════════════════════════════════════════════
# 5. FULL ADVANCED ANALYSIS
# ═══════════════════════════════════════════════════════════════

def run_advanced_ict_analysis(data, basic_analysis=None):
    """
    تشغيل التحليل المتقدم — يُضاف فوق التحليل الأساسي

    basic_analysis: نتيجة run_full_ict_analysis()
    """
    breakers = detect_breaker_blocks(data)
    silver_bullet = detect_silver_bullet(data)
    amd = detect_amd_pattern(data)

    # Inducement يحتاج swing points
    swing_highs = []
    swing_lows = []
    if basic_analysis:
        struct = basic_analysis.get("structure", {})
        swing_highs = struct.get("swing_highs", [])
        swing_lows = struct.get("swing_lows", [])

    inducements = detect_inducement(data, swing_lows, swing_highs)

    return {
        "breaker_blocks": breakers,
        "silver_bullet": silver_bullet,
        "amd": amd,
        "inducements": inducements,
    }


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("═══ اختبار ICT Advanced ═══\n")

    from data.data_feed import DataFeed
    from strategy.ict_core import run_full_ict_analysis

    feed = DataFeed()
    data = feed.get_htf_data()

    if data is not None:
        # تحليل أساسي
        basic = run_full_ict_analysis(data)
        print(f"الاتجاه: {basic['structure']['trend']}")

        # تحليل متقدم
        advanced = run_advanced_ict_analysis(data, basic)

        bb = advanced["breaker_blocks"]
        print(f"\n📦 Breaker Blocks: {len(bb['bullish'])} bullish | {len(bb['bearish'])} bearish")

        sb = advanced["silver_bullet"]
        print(f"🔫 Silver Bullet: {'✅ ' + sb['window'] if sb['active'] else '❌ مش بنافذة'}")
        if sb["active"]:
            print(f"   FVGs بالنافذة: {len(sb['fvgs_in_window'])}")

        amd = advanced["amd"]
        print(f"📊 AMD: {'✅ ' + amd['phase'] if amd['detected'] else '❌'}", end="")
        if amd.get("bias"):
            print(f" → {amd['bias']}")
        else:
            print()

        ind = advanced["inducements"]
        print(f"🪤 Inducements: {len(ind)}")

        print("\n✅ تحليل متقدم شغّال!")
