"""
Kill Zones — فلتر أوقات التداول حسب ICT

ICT يؤكد أن أقوى الحركات تحصل في أوقات محددة (Kill Zones):
- Asian Session: تجميع السيولة والمدى السعري
- London Open: أول حركة اتجاهية قوية
- New York Open: الحركة الأقوى — ICT Power of 3
"""

from datetime import datetime, time
import pytz
from config import KILL_ZONES


# توقيت نيويورك (EST/EDT)
NY_TZ = pytz.timezone("America/New_York")


def _parse_time(t_str):
    """تحويل 'HH:MM' لـ time object"""
    parts = t_str.split(":")
    return time(int(parts[0]), int(parts[1]))


def get_ny_time(timestamp=None):
    """
    تحويل التوقيت لتوقيت نيويورك

    إذا ما أعطيته وقت، يستخدم الوقت الحالي
    """
    if timestamp is None:
        return datetime.now(NY_TZ)

    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            # إذا بدون timezone، نفترض UTC
            timestamp = pytz.utc.localize(timestamp)
        return timestamp.astimezone(NY_TZ)

    return datetime.now(NY_TZ)


def is_kill_zone(timestamp=None):
    """
    هل الوقت الحالي ضمن Kill Zone؟

    يرجع True/False مع اسم الـ Kill Zone
    """
    ny_time = get_ny_time(timestamp)
    current = ny_time.time()

    for zone_name, times in KILL_ZONES.items():
        start = _parse_time(times["start"])
        end = _parse_time(times["end"])

        # معالجة الحالة عندما يتخطى نصف الليل (مثل 20:00 - 00:00)
        if start > end:
            if current >= start or current <= end:
                return True, zone_name
        else:
            if start <= current <= end:
                return True, zone_name

    return False, None


def get_current_session(timestamp=None):
    """
    تحديد الجلسة الحالية بالتفصيل

    يرجع معلومات الجلسة الحالية:
    - اسم الجلسة
    - هل هي Kill Zone
    - الوقت المتبقي
    """
    ny_time = get_ny_time(timestamp)
    current = ny_time.time()

    in_kz, kz_name = is_kill_zone(timestamp)

    # تحديد الجلسة العامة
    if time(20, 0) <= current or current <= time(4, 0):
        session = "ASIAN"
    elif time(2, 0) <= current <= time(8, 0):
        session = "LONDON"
    elif time(7, 0) <= current <= time(16, 0):
        session = "NEW_YORK"
    else:
        session = "OFF_HOURS"

    return {
        "session": session,
        "is_kill_zone": in_kz,
        "kill_zone_name": kz_name,
        "ny_time": ny_time.strftime("%H:%M EST"),
    }


def get_asian_range(data):
    """
    حساب مدى الجلسة الأسيوية (Asian Range)

    في ICT: الحركة في الجلسة الأسيوية تحدد مناطق السيولة
    التي ستُكتسح في London أو New York

    يرجع: أعلى سعر وأدنى سعر في الجلسة الأسيوية
    """
    if not hasattr(data.index, 'tz') or data.index.tz is None:
        # إذا ما فيه timezone بالبيانات، نرجع آخر 8 شموع كتقريب
        last_8 = data.tail(8)
        high = last_8["High"].values if isinstance(last_8["High"], pd.Series) else last_8["High"].squeeze().values
        low = last_8["Low"].values if isinstance(last_8["Low"], pd.Series) else last_8["Low"].squeeze().values
        return {
            "high": float(max(high)),
            "low": float(min(low)),
            "range": float(max(high) - min(low)),
        }

    # فلترة شموع الجلسة الأسيوية
    import pandas as pd
    data_ny = data.copy()
    if data_ny.index.tz != NY_TZ:
        data_ny.index = data_ny.index.tz_convert(NY_TZ)

    asian_mask = (data_ny.index.time >= time(20, 0)) | (data_ny.index.time <= time(0, 0))
    asian_data = data_ny[asian_mask]

    if len(asian_data) == 0:
        return None

    high = asian_data["High"].values if isinstance(asian_data["High"], pd.Series) else asian_data["High"].squeeze().values
    low = asian_data["Low"].values if isinstance(asian_data["Low"], pd.Series) else asian_data["Low"].squeeze().values

    return {
        "high": float(max(high)),
        "low": float(min(low)),
        "range": float(max(high) - min(low)),
    }
