"""
Data Feed — جلب بيانات الأسعار

يدعم Multi-Timeframe لاستراتيجية ICT:
- HTF (Higher Timeframe): لتحديد الاتجاه العام
- LTF (Lower Timeframe): للدخول الدقيق
"""

import yfinance as yf
import pandas as pd
from config import (
    SYMBOL_YF,
    HTF_INTERVAL,
    HTF_PERIOD,
    LTF_INTERVAL,
    LTF_PERIOD,
)


class DataFeed:

    def __init__(self, symbol=None):
        self.symbol = symbol or SYMBOL_YF

    def get_candles(self, period=None, interval=None):
        """
        جلب بيانات الشموع مع المؤشرات الأساسية

        period: فترة البيانات (مثل '60d', '6mo')
        interval: الإطار الزمني (مثل '1h', '15m', '1d')
        """
        if period is None:
            period = HTF_PERIOD
        if interval is None:
            interval = HTF_INTERVAL

        data = yf.download(self.symbol, period=period, interval=interval, auto_adjust=True)

        # التأكد من أعمدة بسيطة (بدون MultiIndex)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]

        # حذف الصفوف الفارغة
        data = data.dropna()

        # حساب ATR
        data["ATR"] = self._calculate_atr(data)

        # إضافة EMAs للمرجع (اختياري)
        close = data["Close"].squeeze() if isinstance(data["Close"], pd.DataFrame) else data["Close"]
        data["EMA_20"] = close.ewm(span=20).mean()
        data["EMA_50"] = close.ewm(span=50).mean()

        return data

    def get_htf_data(self):
        """جلب بيانات الإطار الزمني الأعلى (للاتجاه العام)"""
        return self.get_candles(period=HTF_PERIOD, interval=HTF_INTERVAL)

    def get_ltf_data(self):
        """جلب بيانات الإطار الزمني الأدنى (للدخول الدقيق)"""
        return self.get_candles(period=LTF_PERIOD, interval=LTF_INTERVAL)

    def get_latest_price(self):
        """جلب آخر سعر"""
        data = yf.download(self.symbol, period="1d", interval="1m", auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]
        close = data["Close"].squeeze() if isinstance(data["Close"], pd.DataFrame) else data["Close"]
        return round(float(close.iloc[-1]), 3)

    def _calculate_atr(self, data, period=14):
        """حساب Average True Range"""
        high = data["High"].squeeze() if isinstance(data["High"], pd.DataFrame) else data["High"]
        low = data["Low"].squeeze() if isinstance(data["Low"], pd.DataFrame) else data["Low"]
        close = data["Close"].squeeze() if isinstance(data["Close"], pd.DataFrame) else data["Close"]

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        return tr.rolling(window=period).mean()


if __name__ == "__main__":
    feed = DataFeed()

    print("═══ HTF Data (H1) ═══")
    htf = feed.get_htf_data()
    print(f"الشموع: {len(htf)}")
    print(htf[["Close", "ATR"]].tail(5))

    print("\n═══ LTF Data (M15) ═══")
    ltf = feed.get_ltf_data()
    print(f"الشموع: {len(ltf)}")
    print(ltf[["Close", "ATR"]].tail(5))

    print(f"\nالسعر الحالي: {feed.get_latest_price()}")