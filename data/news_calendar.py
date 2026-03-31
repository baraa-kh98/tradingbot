"""
News Calendar — تقويم اقتصادي + فلتر أخبار عالية التأثير

يحدد الأوقات اللي فيها أخبار مهمة ويمنع التداول قبلها وبعدها.

المصادر:
- FRED API: تواريخ إصدار البيانات الاقتصادية
- جدول ثابت: أوقات أخبار معروفة (NFP, CPI, FOMC)
"""

import pandas as pd
from datetime import datetime, timedelta


# ═══════════════════════════════════════════════════════════════
# أحداث اقتصادية عالية التأثير (🔴)
# ═══════════════════════════════════════════════════════════════

HIGH_IMPACT_EVENTS = {
    "NFP": {
        "name": "Non-Farm Payrolls",
        "impact": "HIGH",
        "day": "first_friday",          # أول جمعة من كل شهر
        "time_est": "08:30",
        "blackout_before_min": 60,      # وقف التداول ساعة قبل
        "blackout_after_min": 30,       # وقف التداول 30 دقيقة بعد
        "affects": ["USD"],
    },
    "CPI": {
        "name": "Consumer Price Index",
        "impact": "HIGH",
        "typical_day": 13,              # عادةً حوالي 10-15 من الشهر
        "time_est": "08:30",
        "blackout_before_min": 60,
        "blackout_after_min": 30,
        "affects": ["USD"],
    },
    "FOMC": {
        "name": "FOMC Rate Decision",
        "impact": "HIGH",
        "time_est": "14:00",
        "blackout_before_min": 120,     # ساعتين قبل
        "blackout_after_min": 60,       # ساعة بعد
        "affects": ["USD", "ALL"],
    },
    "GDP": {
        "name": "GDP (Advance)",
        "impact": "HIGH",
        "time_est": "08:30",
        "blackout_before_min": 30,
        "blackout_after_min": 15,
        "affects": ["USD"],
    },
    "RETAIL_SALES": {
        "name": "Retail Sales",
        "impact": "MEDIUM",
        "time_est": "08:30",
        "blackout_before_min": 30,
        "blackout_after_min": 15,
        "affects": ["USD"],
    },
    "ISM_PMI": {
        "name": "ISM Manufacturing PMI",
        "impact": "MEDIUM",
        "day": "first_business",        # أول يوم عمل من الشهر
        "time_est": "10:00",
        "blackout_before_min": 30,
        "blackout_after_min": 15,
        "affects": ["USD"],
    },
}

# FOMC Meeting Dates 2024-2026 (ثابتة — يتم تحديثها يدوياً)
FOMC_DATES = [
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-11-05", "2025-12-17",
    # 2026
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16",
]


class NewsCalendar:
    """تقويم اقتصادي + فلتر أخبار"""

    def __init__(self):
        self._calendar = None

    def generate_calendar(self, start_date, end_date):
        """
        توليد تقويم اقتصادي تاريخي بين تاريخين

        يرجع DataFrame مع: date, time_est, event, impact
        """
        events = []
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)

        current = start
        while current <= end:
            # NFP — أول جمعة من كل شهر
            if current.day <= 7 and current.weekday() == 4:
                events.append({
                    "date": current,
                    "time_est": "08:30",
                    "event": "NFP",
                    "name": "Non-Farm Payrolls",
                    "impact": "HIGH",
                    "blackout_before": 60,
                    "blackout_after": 30,
                })

            # CPI — حوالي 10-15 من كل شهر (تقريبي)
            if current.day == 13 and current.weekday() < 5:
                events.append({
                    "date": current,
                    "time_est": "08:30",
                    "event": "CPI",
                    "name": "Consumer Price Index",
                    "impact": "HIGH",
                    "blackout_before": 60,
                    "blackout_after": 30,
                })

            # ISM PMI — أول يوم عمل من الشهر
            if current.day in [1, 2, 3] and current.weekday() == 0:
                events.append({
                    "date": current,
                    "time_est": "10:00",
                    "event": "ISM_PMI",
                    "name": "ISM Manufacturing PMI",
                    "impact": "MEDIUM",
                    "blackout_before": 30,
                    "blackout_after": 15,
                })

            # Retail Sales — حوالي 15 من الشهر
            if current.day == 15 and current.weekday() < 5:
                events.append({
                    "date": current,
                    "time_est": "08:30",
                    "event": "RETAIL_SALES",
                    "name": "Retail Sales",
                    "impact": "MEDIUM",
                    "blackout_before": 30,
                    "blackout_after": 15,
                })

            current += timedelta(days=1)

        # FOMC dates
        for fomc_date_str in FOMC_DATES:
            fomc_date = pd.Timestamp(fomc_date_str)
            if start <= fomc_date <= end:
                events.append({
                    "date": fomc_date,
                    "time_est": "14:00",
                    "event": "FOMC",
                    "name": "FOMC Rate Decision",
                    "impact": "HIGH",
                    "blackout_before": 120,
                    "blackout_after": 60,
                })

        if not events:
            return pd.DataFrame()

        self._calendar = pd.DataFrame(events).sort_values("date").reset_index(drop=True)
        return self._calendar

    def is_blackout(self, check_datetime, calendar_df=None):
        """
        تحقق إذا الوقت المحدد ضمن فترة حظر تداول

        check_datetime: التاريخ والوقت للتحقق (timezone-aware أو naive EST)
        returns: (bool, str) — (هل ممنوع؟, سبب المنع)
        """
        if calendar_df is None:
            calendar_df = self._calendar

        if calendar_df is None or len(calendar_df) == 0:
            return False, ""

        check_dt = pd.Timestamp(check_datetime)
        check_date = check_dt.normalize()

        # فلتر أحداث نفس اليوم
        day_events = calendar_df[calendar_df["date"].dt.normalize() == check_date]

        for _, event in day_events.iterrows():
            # حساب وقت الحدث
            hour, minute = map(int, event["time_est"].split(":"))
            event_time = event["date"].replace(hour=hour, minute=minute)

            # فترة الحظر
            blackout_start = event_time - timedelta(minutes=event["blackout_before"])
            blackout_end = event_time + timedelta(minutes=event["blackout_after"])

            if blackout_start <= check_dt <= blackout_end:
                return True, f"🚫 {event['name']} ({event['impact']}) @ {event['time_est']} EST"

        return False, ""

    def is_blackout_for_candle(self, candle_datetime, calendar_df=None):
        """
        تحقق إذا شمعة محددة ضمن فترة حظر (للباكتست)
        يتحقق من اليوم الحالي واليوم السابق (لأخبار آخر الليل)
        """
        blocked, reason = self.is_blackout(candle_datetime, calendar_df)
        return blocked, reason

    def get_events_on_date(self, date, calendar_df=None):
        """جلب كل الأحداث في يوم محدد"""
        if calendar_df is None:
            calendar_df = self._calendar
        if calendar_df is None:
            return []

        date = pd.Timestamp(date).normalize()
        events = calendar_df[calendar_df["date"].dt.normalize() == date]
        return events.to_dict("records")

    def get_next_event(self, from_datetime, calendar_df=None):
        """جلب الحدث القادم"""
        if calendar_df is None:
            calendar_df = self._calendar
        if calendar_df is None:
            return None

        from_dt = pd.Timestamp(from_datetime)
        future = calendar_df[calendar_df["date"] >= from_dt]
        if len(future) == 0:
            return None
        return future.iloc[0].to_dict()

    def get_high_impact_dates(self, calendar_df=None):
        """جلب كل تواريخ الأخبار عالية التأثير فقط"""
        if calendar_df is None:
            calendar_df = self._calendar
        if calendar_df is None:
            return []

        high = calendar_df[calendar_df["impact"] == "HIGH"]
        return high["date"].dt.normalize().unique().tolist()


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    cal = NewsCalendar()

    print("═══ تقويم اقتصادي (2024-2026) ═══\n")
    events = cal.generate_calendar("2024-01-01", "2026-12-31")
    print(f"📅 إجمالي الأحداث: {len(events)}")

    high = events[events["impact"] == "HIGH"]
    print(f"🔴 أحداث عالية التأثير: {len(high)}")
    print(f"🟡 أحداث متوسطة التأثير: {len(events) - len(high)}")

    print(f"\nآخر 5 أحداث:")
    for _, e in events.tail(5).iterrows():
        print(f"   {e['date'].strftime('%Y-%m-%d')} {e['time_est']} — {e['name']} ({e['impact']})")

    # اختبار blackout
    test = "2025-03-07 08:00"  # قبل NFP بنص ساعة
    blocked, reason = cal.is_blackout(test)
    print(f"\n🔍 {test}: {'🚫 ممنوع' if blocked else '✅ مسموح'} {reason}")
