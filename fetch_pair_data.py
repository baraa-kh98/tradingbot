"""
fetch_pair_data.py — جلب بيانات H1 لسنتين لأي زوج
Usage: python fetch_pair_data.py EURUSD
"""

import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.data_feed import DataFeed
from config import TRADING_PAIRS


def fetch(pair: str):
    pair = pair.upper()

    if pair not in TRADING_PAIRS:
        print(f"❌ الزوج '{pair}' مش موجود في config. الأزواج المتاحة: {list(TRADING_PAIRS.keys())}")
        sys.exit(1)

    output_path = f"backtest_data/{pair}_H1_2years.csv"

    if os.path.exists(output_path):
        import pandas as pd
        existing = pd.read_csv(output_path, index_col=0)
        print(f"✅ البيانات موجودة: {output_path} ({len(existing)} شمعة) — تخطي الجلب")
        return

    td_symbol = TRADING_PAIRS[pair]["td"]
    end_date   = date.today().strftime("%Y-%m-%d")
    start_date = (date.today() - timedelta(days=730)).strftime("%Y-%m-%d")

    print(f"\n{'='*50}")
    print(f"جلب بيانات: {pair} ({td_symbol})")
    print(f"الفترة: {start_date} → {end_date}")
    print(f"{'='*50}")

    feed = DataFeed(symbol=td_symbol)
    df = feed.get_long_history(start_date=start_date, end_date=end_date, interval="1h")

    if df is None or df.empty:
        print(f"❌ فشل جلب البيانات لـ {pair}")
        sys.exit(1)

    os.makedirs("backtest_data", exist_ok=True)
    df.to_csv(output_path)
    print(f"\n✅ تم الحفظ: {output_path} ({len(df)} شمعة)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_pair_data.py EURUSD")
        sys.exit(1)
    fetch(sys.argv[1])
