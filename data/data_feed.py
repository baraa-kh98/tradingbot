"""
Data Feed — جلب بيانات الأسعار من Twelve Data API

Twelve Data يوفّر:
- بيانات تاريخية عميقة (سنوات من M1, M15, H1, H4, Daily)
- Real-time prices
- مؤشرات تقنية جاهزة (ATR, EMA, RSI...)
- تغطية 140+ عملة

Fallback: إذا Twelve Data مش متاح، يستخدم yfinance
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from config import (
    TWELVE_DATA_API_KEY,
    SYMBOL_TD,
    HTF_INTERVAL,
    HTF_PERIOD_DAYS,
    LTF_INTERVAL,
    LTF_PERIOD_DAYS,
    BACKTEST_INTERVAL,
    BACKTEST_PERIOD_DAYS,
)


class DataFeed:
    """مزوّد البيانات — Twelve Data مع fallback لـ yfinance"""

    def __init__(self, symbol=None, api_key=None):
        self.symbol = symbol or SYMBOL_TD
        self.api_key = api_key or TWELVE_DATA_API_KEY
        self._td_client = None

    def _get_td_client(self):
        """إنشاء Twelve Data client (lazy loading)"""
        if self._td_client is None:
            try:
                from twelvedata import TDClient
                self._td_client = TDClient(apikey=self.api_key)
            except ImportError:
                print("⚠️ twelvedata مش مثبّت. استخدم: pip install twelvedata")
                return None
        return self._td_client

    def get_candles(self, interval=None, period_days=None):
        """
        جلب بيانات الشموع

        interval: الإطار الزمني ('1min', '5min', '15min', '30min', '1h', '4h', '1day')
        period_days: عدد أيام البيانات
        """
        if interval is None:
            interval = HTF_INTERVAL
        if period_days is None:
            period_days = HTF_PERIOD_DAYS

        # حاول Twelve Data أولاً
        if self.api_key:
            data = self._fetch_twelve_data(interval, period_days)
            if data is not None and len(data) > 0:
                return data

        # Fallback لـ yfinance
        print("⚠️ Twelve Data مش متاح — Fallback لـ yfinance")
        return self._fetch_yfinance(interval, period_days)

    def _fetch_twelve_data(self, interval, period_days):
        """جلب البيانات من Twelve Data API"""
        td = self._get_td_client()
        if td is None:
            return None

        try:
            # حساب عدد الشموع المطلوبة
            output_size = self._calc_output_size(interval, period_days)

            ts = td.time_series(
                symbol=self.symbol,
                interval=interval,
                outputsize=output_size,
                timezone="UTC",
            )

            data = ts.as_pandas()

            if data is None or len(data) == 0:
                print("⚠️ Twelve Data رجع بيانات فاضية")
                return None

            # ترتيب البيانات من الأقدم للأحدث
            data = data.sort_index()

            # تنظيف أسماء الأعمدة
            data.columns = [col.capitalize() if col.islower() else col for col in data.columns]

            # التأكد من الأعمدة الأساسية
            required = ["Open", "High", "Low", "Close"]
            for col in required:
                if col not in data.columns:
                    # محاولة إيجاد العمود بأي شكل
                    for c in data.columns:
                        if c.lower() == col.lower():
                            data = data.rename(columns={c: col})
                            break

            # تحويل لأرقام
            for col in ["Open", "High", "Low", "Close"]:
                if col in data.columns:
                    data[col] = pd.to_numeric(data[col], errors="coerce")

            if "Volume" in data.columns:
                data["Volume"] = pd.to_numeric(data["Volume"], errors="coerce")
            else:
                data["Volume"] = 0

            data = data.dropna(subset=["Open", "High", "Low", "Close"])

            # حساب ATR
            data["ATR"] = self._calculate_atr(data)

            # EMAs
            data["EMA_20"] = data["Close"].ewm(span=20).mean()
            data["EMA_50"] = data["Close"].ewm(span=50).mean()

            print(f"✅ Twelve Data: {len(data)} شمعة ({interval})")
            return data

        except Exception as e:
            print(f"⚠️ خطأ Twelve Data: {e}")
            return None

    def _fetch_yfinance(self, interval, period_days):
        """Fallback — جلب البيانات من yfinance"""
        try:
            import yfinance as yf

            # تحويل الرمز لصيغة yfinance
            yf_symbol = self.symbol.replace("/", "") + "=X"

            # تحويل interval لصيغة yfinance
            yf_interval = interval.replace("min", "m")

            period = f"{period_days}d"

            data = yf.download(
                yf_symbol, period=period, interval=yf_interval,
                auto_adjust=True, progress=False
            )

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [col[0] for col in data.columns]

            data = data.dropna()

            # حساب ATR
            data["ATR"] = self._calculate_atr(data)
            data["EMA_20"] = data["Close"].ewm(span=20).mean()
            data["EMA_50"] = data["Close"].ewm(span=50).mean()

            print(f"✅ yfinance: {len(data)} شمعة ({yf_interval})")
            return data

        except Exception as e:
            print(f"❌ خطأ yfinance: {e}")
            return None

    def get_htf_data(self):
        """جلب بيانات الإطار الزمني الأعلى (للاتجاه العام)"""
        return self.get_candles(interval=HTF_INTERVAL, period_days=HTF_PERIOD_DAYS)

    def get_ltf_data(self):
        """جلب بيانات الإطار الزمني الأدنى (للدخول الدقيق)"""
        return self.get_candles(interval=LTF_INTERVAL, period_days=LTF_PERIOD_DAYS)

    def get_backtest_data(self, period_days=None):
        """جلب بيانات طويلة للباكتست"""
        days = period_days or BACKTEST_PERIOD_DAYS
        return self.get_candles(interval=BACKTEST_INTERVAL, period_days=days)

    def get_latest_price(self):
        """جلب آخر سعر"""
        if self.api_key:
            td = self._get_td_client()
            if td:
                try:
                    price = td.price(symbol=self.symbol)
                    result = price.as_json()
                    return round(float(result["price"]), 3)
                except Exception:
                    pass

        # Fallback
        try:
            import yfinance as yf
            yf_symbol = self.symbol.replace("/", "") + "=X"
            data = yf.download(yf_symbol, period="1d", interval="1m",
                               auto_adjust=True, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [col[0] for col in data.columns]
            return round(float(data["Close"].iloc[-1]), 3)
        except Exception as e:
            print(f"❌ خطأ جلب السعر: {e}")
            return None

    def _calculate_atr(self, data, period=14):
        """حساب Average True Range"""
        high = data["High"]
        low = data["Low"]
        close = data["Close"]

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        return tr.rolling(window=period).mean()

    def _calc_output_size(self, interval, period_days):
        """حساب عدد الشموع المطلوبة بناءً على الإطار الزمني والفترة"""
        interval_minutes = {
            "1min": 1, "5min": 5, "15min": 15, "30min": 30,
            "1h": 60, "2h": 120, "4h": 240, "1day": 1440,
        }
        mins = interval_minutes.get(interval, 60)
        # عدد ساعات التداول يومياً (فوركس ~24 ساعة 5 أيام)
        trading_hours = 24
        candles_per_day = (trading_hours * 60) // mins
        total = candles_per_day * period_days

        # Twelve Data max outputsize = 5000
        return min(total, 5000)


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    feed = DataFeed()

    print("═══ HTF Data ═══")
    htf = feed.get_htf_data()
    if htf is not None:
        print(f"شموع: {len(htf)}")
        print(htf[["Close", "ATR"]].tail(3))

    print("\n═══ LTF Data ═══")
    ltf = feed.get_ltf_data()
    if ltf is not None:
        print(f"شموع: {len(ltf)}")
        print(ltf[["Close", "ATR"]].tail(3))

    price = feed.get_latest_price()
    print(f"\nالسعر الحالي: {price}")