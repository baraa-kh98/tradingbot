"""
Macro Data — جلب بيانات ماكرو تاريخية من FRED API

FRED (Federal Reserve Economic Data) يوفر مجاناً:
- NFP (Non-Farm Payrolls) — سوق العمل
- CPI (Consumer Price Index) — التضخم
- Fed Funds Rate — سعر الفائدة
- GDP — الناتج المحلي
- VIX — مؤشر الخوف
- DXY — مؤشر الدولار
- US 10Y Treasury — عوائد السندات

API Key مجاني: https://fred.stlouisfed.org/docs/api/api_key.html
"""

import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from config import FRED_API_KEY


# ═══════════════════════════════════════════════════════════════
# FRED Series IDs
# ═══════════════════════════════════════════════════════════════

FRED_SERIES = {
    # سوق العمل
    "NFP": "PAYEMS",               # Non-Farm Payrolls (شهري)
    "UNEMPLOYMENT": "UNRATE",       # معدل البطالة (شهري)
    "JOBLESS_CLAIMS": "ICSA",       # طلبات إعانة البطالة (أسبوعي)

    # التضخم
    "CPI": "CPIAUCSL",             # مؤشر أسعار المستهلك (شهري)
    "CPI_YOY": "CPALTT01USM657N",  # CPI سنوي %
    "PCE": "PCEPI",                # PCE Price Index (المفضل لدى الفيد)

    # أسعار الفائدة
    "FED_RATE": "FEDFUNDS",        # سعر الفائدة الفيدرالي
    "US10Y": "DGS10",              # عائد السندات 10 سنوات
    "US2Y": "DGS2",                # عائد السندات 2 سنة

    # الناتج المحلي
    "GDP": "GDP",                   # الناتج المحلي (ربع سنوي)
    "GDP_GROWTH": "A191RL1Q225SBEA", # نمو GDP %

    # أسواق المال
    "VIX": "VIXCLS",               # مؤشر التقلبات VIX (يومي)
    "DXY": "DTWEXBGS",             # مؤشر الدولار (يومي)
    "SP500": "SP500",              # S&P 500 (يومي)
}


class MacroData:
    """جلب وتحليل بيانات ماكرو تاريخية من FRED"""

    def __init__(self, api_key=None):
        self.api_key = api_key or FRED_API_KEY
        self.base_url = "https://api.stlouisfed.org/fred"
        self._cache = {}

    def get_series(self, series_id, start_date=None, end_date=None):
        """
        جلب بيانات سلسلة من FRED

        series_id: رمز السلسلة (مثل "VIXCLS")
        start_date: تاريخ البداية (مثل "2022-01-01")
        end_date: تاريخ النهاية
        """
        cache_key = f"{series_id}_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self.api_key or self.api_key == "your_fred_api_key_here":
            print(f"⚠️ FRED API Key مش محطوط — يستخدم yfinance fallback")
            return self._fallback_yfinance(series_id, start_date, end_date)

        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        url = f"{self.base_url}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start_date,
            "observation_end": end_date,
            "sort_order": "asc",
        }

        try:
            r = requests.get(url, params=params, timeout=15)
            data = r.json()

            if "observations" not in data:
                print(f"⚠️ FRED: خطأ في {series_id}: {data.get('error_message', 'unknown')}")
                return None

            observations = data["observations"]
            df = pd.DataFrame(observations)
            df["date"] = pd.to_datetime(df["date"])
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df = df[["date", "value"]].dropna()
            df = df.set_index("date")
            df.columns = [series_id]

            self._cache[cache_key] = df
            return df

        except Exception as e:
            print(f"⚠️ FRED: خطأ في جلب {series_id}: {e}")
            return self._fallback_yfinance(series_id, start_date, end_date)

    def _fallback_yfinance(self, series_id, start_date, end_date):
        """Fallback لـ yfinance للبيانات اليومية"""
        yf_map = {
            "VIXCLS": "^VIX",
            "DTWEXBGS": "DX-Y.NYB",
            "DGS10": "^TNX",
            "SP500": "^GSPC",
        }

        yf_symbol = yf_map.get(series_id)
        if not yf_symbol:
            return None

        try:
            import yfinance as yf
            data = yf.download(yf_symbol, start=start_date, end=end_date,
                               progress=False, auto_adjust=True)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [col[0] for col in data.columns]
            df = data[["Close"]].dropna()
            df.columns = [series_id]
            return df
        except Exception:
            return None

    def get_vix(self, start_date=None, end_date=None):
        """جلب بيانات VIX"""
        return self.get_series("VIXCLS", start_date, end_date)

    def get_dxy(self, start_date=None, end_date=None):
        """جلب بيانات مؤشر الدولار"""
        return self.get_series("DTWEXBGS", start_date, end_date)

    def get_fed_rate(self, start_date=None, end_date=None):
        """جلب سعر الفائدة الفيدرالي"""
        return self.get_series("FEDFUNDS", start_date, end_date)

    def get_us10y(self, start_date=None, end_date=None):
        """جلب عوائد السندات 10 سنوات"""
        return self.get_series("DGS10", start_date, end_date)

    def get_cpi_yoy(self, start_date=None, end_date=None):
        """جلب التضخم السنوي"""
        return self.get_series("CPALTT01USM657N", start_date, end_date)

    def get_all_macro(self, start_date=None, end_date=None):
        """
        جلب كل بيانات الماكرو الأساسية ودمجها بجدول واحد

        يرجع DataFrame يومي مع:
        VIX, DXY, FED_RATE, US10Y, CPI_YOY
        """
        key_series = {
            "VIX": "VIXCLS",
            "DXY": "DTWEXBGS",
            "FED_RATE": "FEDFUNDS",
            "US10Y": "DGS10",
        }

        frames = []
        for name, series_id in key_series.items():
            df = self.get_series(series_id, start_date, end_date)
            if df is not None:
                df.columns = [name]
                frames.append(df)
                print(f"   ✅ {name}: {len(df)} نقطة")

        if not frames:
            print("❌ لم يتم جلب أي بيانات ماكرو!")
            return None

        # دمج كل البيانات
        combined = frames[0]
        for df in frames[1:]:
            combined = combined.join(df, how="outer")

        # تعبئة القيم المفقودة (forward fill لأن البيانات الماكرو شهرية/أسبوعية)
        combined = combined.ffill()

        print(f"📊 إجمالي بيانات الماكرو: {len(combined)} يوم")
        return combined

    def get_macro_at_date(self, date, macro_df=None):
        """
        جلب حالة الماكرو في تاريخ محدد

        مفيد للباكتست — يرجع dict مع كل القيم
        """
        if macro_df is None:
            macro_df = self.get_all_macro()

        if macro_df is None:
            return None

        # إيجاد أقرب تاريخ
        date = pd.Timestamp(date)
        mask = macro_df.index <= date
        if mask.sum() == 0:
            return None

        row = macro_df.loc[mask].iloc[-1]
        return row.to_dict()


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    macro = MacroData()

    print("═══ جلب بيانات ماكرو (3 سنوات) ═══\n")
    all_data = macro.get_all_macro()

    if all_data is not None:
        print(f"\n📊 الفترة: {all_data.index[0].date()} → {all_data.index[-1].date()}")
        print(f"\nآخر القيم:")
        print(all_data.tail(3))

        # اختبار get_macro_at_date
        test_date = "2025-01-15"
        state = macro.get_macro_at_date(test_date, all_data)
        if state:
            print(f"\n📅 حالة الماكرو في {test_date}:")
            for k, v in state.items():
                print(f"   {k}: {v:.2f}")
