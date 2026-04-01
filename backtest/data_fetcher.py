import os
import pandas as pd
from datetime import datetime
import pytz

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

class HistoricalDataFetcher:
    """أداة سحب البيانات التاريخية العميقة من الخادم"""
    
    def __init__(self):
        self.connected = False
        if mt5 is None:
            print("❌ MetaTrader5 مكتبة غير مثبتة.")
            return

        if not mt5.initialize():
            print(f"⚠️ فشل تهيئة MT5: {mt5.last_error()}")
        else:
            self.connected = True

    def fetch_and_save(self, symbol="USDJPY.BL", days_back=730, chunk_months=3):
        """يسحب الشموع ويقسمها لأجزاء (Chunks) لتفادي انهيار الرام"""
        if not self.connected:
            print("❌ لا يوجد اتصال بـ MT5 لتحميل البيانات!")
            return False

        print(f"\n📥 جاري طلب البيانات لـ {symbol} لآخر {days_back} يوم...")
        now = datetime.now()

        # حساب عدد الشموع التقريبي
        # M5: 24 ساعة * 12 شمعة = 288، ضرب 730 يوم = 210,000 شمعة
        limit_m5 = days_back * 288
        limit_h1 = days_back * 24

        # سحب M5
        rates_m5 = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M5, now, limit_m5)
        if rates_m5 is None or len(rates_m5) == 0:
            print(f"❌ فشل جلب بيانات M5: {mt5.last_error()}")
            return False
            
        df_m5 = pd.DataFrame(rates_m5)
        df_m5['time'] = pd.to_datetime(df_m5['time'], unit='s')
        
        # سحب H1
        rates_h1 = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_H1, now, limit_h1)
        if rates_h1 is None or len(rates_h1) == 0:
            print(f"❌ فشل جلب بيانات H1: {mt5.last_error()}")
            return False
            
        df_h1 = pd.DataFrame(rates_h1)
        df_h1['time'] = pd.to_datetime(df_h1['time'], unit='s')

        # حفظ البيانات
        os.makedirs("backtest_data", exist_ok=True)
        
        m5_path = f"backtest_data/{symbol}_M5_history.csv"
        h1_path = f"backtest_data/{symbol}_H1_history.csv"
        
        df_m5.to_csv(m5_path, index=False)
        df_h1.to_csv(h1_path, index=False)
        
        print(f"✅ تم سحب {len(df_m5)} شمعة M5 وحفظها في {m5_path}")
        print(f"✅ تم سحب {len(df_h1)} شمعة H1 وحفظها في {h1_path}")
        return True

if __name__ == "__main__":
    fetcher = HistoricalDataFetcher()
    fetcher.fetch_and_save("USDJPY.BL", days_back=730)
