import os
import sys
import argparse
import pandas as pd
from datetime import datetime, timedelta
import pytz

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

# ── Twelvedata fallback ───────────────────────────────────────────────────────
def _fetch_via_twelvedata(symbol, start_date, end_date, interval="1h"):
    """جلب بيانات تاريخية عبر Twelvedata (بدون MT5)"""
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from data.data_feed import DataFeed
        pair = symbol.replace(".BL", "").replace("_", "")
        feed = DataFeed(pair=pair)
        df = feed.get_long_history(start_date=start_date, end_date=end_date, interval=interval)
        return df
    except Exception as e:
        print(f"❌ Twelvedata fetch failed: {e}")
        return None


class HistoricalDataFetcher:
    """أداة سحب البيانات التاريخية العميقة — MT5 أو Twelvedata"""

    def __init__(self):
        self.connected = False
        if mt5 is None:
            print("⚠️ MetaTrader5 غير مثبت — سيُستخدم Twelvedata كبديل.")
            return

        if not mt5.initialize():
            print(f"⚠️ فشل تهيئة MT5: {mt5.last_error()} — سيُستخدم Twelvedata كبديل.")
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
        limit_m5 = min(days_back * 288, 99000) # الحد الأقصى الآمن لمعظم البروكرز هو 100,000 شمعة
        limit_h1 = days_back * 24

        # سحب M5 باستخدام البوزيشن لتفادي أخطاء التوقيت
        rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, limit_m5)
        
        # تجربة كمية أقل إذا تم الرفض (Invalid params بسبب ضخامة الرقم)
        if rates_m5 is None or len(rates_m5) == 0:
            print(f"⚠️ السيرفر رفض جلب {limit_m5} شمعة M5، سيتم المحاولة بـ 50,000 شمعة فقط...")
            limit_m5 = 50000
            rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, limit_m5)
            
        if rates_m5 is None or len(rates_m5) == 0:
            print(f"❌ فشل جلب بيانات M5 نهائياً: {mt5.last_error()}")
            return False
            
        df_m5 = pd.DataFrame(rates_m5)
        df_m5['time'] = pd.to_datetime(df_m5['time'], unit='s')
        
        # سحب H1
        rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, limit_h1)
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

def fetch_long_history(years=10):
    """
    جلب بيانات تاريخية لكل الأزواج عبر Twelvedata (لا يحتاج MT5).
    الاستخدام: python3 backtest/data_fetcher.py --years 10
    """
    pairs = [
        ("EURUSD", "EURUSD"),
        ("GBPUSD", "GBPUSD"),
        ("USDJPY", "USDJPY"),
        ("XAUUSD", "XAU/USD"),
    ]
    end_date   = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365 * years)).strftime("%Y-%m-%d")

    print(f"\n📥 جلب بيانات {years} سنوات ({start_date} → {end_date})")
    os.makedirs("backtest_data", exist_ok=True)

    try:
        import sys, os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
        from data.data_feed import DataFeed
    except ImportError as e:
        print(f"❌ لا يمكن استيراد DataFeed: {e}")
        return

    for pair_name, _ in pairs:
        print(f"\n⏳ {pair_name} ...")
        try:
            feed = DataFeed(pair=pair_name)
            df   = feed.get_long_history(start_date=start_date, end_date=end_date, interval="1h")
            if df is not None and len(df) > 0:
                out = f"backtest_data/{pair_name}_H1_{years}years.csv"
                df.to_csv(out, index=True)
                print(f"  ✅ {len(df):,} شمعة H1 → {out}")
            else:
                print(f"  ⚠️ لا بيانات لـ {pair_name}")
        except Exception as e:
            print(f"  ❌ خطأ في {pair_name}: {e}")

    print("\n✅ اكتمل جلب البيانات الموسّعة.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trading Bot — Historical Data Fetcher")
    parser.add_argument("--years",  type=int, default=2,
                        help="عدد السنوات للبيانات التاريخية (default: 2، max: 10)")
    parser.add_argument("--symbol", type=str, default=None,
                        help="رمز زوج محدد عبر MT5 (اختياري)")
    args = parser.parse_args()

    if args.symbol:
        # وضع MT5 الأصلي
        fetcher = HistoricalDataFetcher()
        fetcher.fetch_and_save(args.symbol, days_back=args.years * 365)
    else:
        # وضع Twelvedata الجديد — كل الأزواج
        fetch_long_history(years=args.years)
