"""
multi_pair_backtest.py — تشغيل London Breakout backtest لزوج واحد
Usage: python multi_pair_backtest.py EURUSD
النتائج تُحفظ في journal/multi_pair_results.json
"""

import sys
import os
import json
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from config import TRADING_PAIRS


def run_backtest(pair: str):
    pair = pair.upper()

    if pair not in TRADING_PAIRS:
        print(f"❌ الزوج '{pair}' مش موجود في config.")
        sys.exit(1)

    h1_path = f"backtest_data/{pair}_H1_2years.csv"
    if not os.path.exists(h1_path):
        print(f"❌ ملف البيانات مش موجود: {h1_path}")
        print(f"   شغّل أولاً: python fetch_pair_data.py {pair}")
        sys.exit(1)

    pair_pip = TRADING_PAIRS[pair]["pip"]

    # ── Monkey-patch PIP_VALUE قبل تشغيل الباكتست ──────────────
    import backtest.london_final as lf_module
    lf_module.PIP_VALUE = pair_pip

    from backtest.london_final import LondonClean, load_csv
    from backtesting import Backtest

    # ── تحميل البيانات ──────────────────────────────────────────
    h1 = load_csv(h1_path)
    if h1 is None or len(h1) < 200:
        print(f"❌ بيانات غير كافية لـ {pair} ({len(h1) if h1 is not None else 0} شمعة)")
        sys.exit(1)

    print(f"\n{'='*55}")
    print(f"  {pair} | {len(h1)} شمعة H1 | {h1.index[0].date()} → {h1.index[-1].date()}")
    print(f"  PIP_VALUE = {pair_pip}")
    print(f"{'='*55}")

    # ── تشغيل الباكتست ──────────────────────────────────────────
    LondonClean._h4 = None  # بدون H4 bias للمقارنة العادلة بين الأزواج
    bt = Backtest(h1, LondonClean, cash=10_000, commission=0.0002, finalize_trades=True)
    stats = bt.run()

    # ── استخراج النتائج ─────────────────────────────────────────
    def safe_float(val, default=0.0):
        try:
            import math
            f = float(val)
            return default if math.isnan(f) or math.isinf(f) else f
        except Exception:
            return default

    result = {
        "pair":           pair,
        "pip_value":      pair_pip,
        "run_date":       datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "candles":        len(h1),
        "data_from":      str(h1.index[0].date()),
        "data_to":        str(h1.index[-1].date()),
        "trades":         int(stats.get("# Trades", 0)),
        "win_rate_pct":   round(safe_float(stats.get("Win Rate [%]")), 1),
        "return_pct":     round(safe_float(stats.get("Return [%]")), 2),
        "annual_return":  round(safe_float(stats.get("Return (Ann.) [%]")), 2),
        "max_dd_pct":     round(safe_float(stats.get("Max. Drawdown [%]")), 2),
        "sharpe":         round(safe_float(stats.get("Sharpe Ratio")), 3),
        "profit_factor":  round(safe_float(stats.get("Profit Factor", 0)), 3),
        "calmar":         round(safe_float(stats.get("Calmar Ratio", 0)), 3),
        "strategy":       "LondonClean",
        "params": {
            "buffer_pips":    LondonClean.buffer_pips,
            "min_rr":         LondonClean.min_rr,
            "min_range_pips": LondonClean.min_range_pips,
        },
    }

    # ── طباعة ملخص ──────────────────────────────────────────────
    print(f"  Trades:       {result['trades']}")
    print(f"  Win Rate:     {result['win_rate_pct']}%")
    print(f"  Return:       {result['return_pct']}%")
    print(f"  Ann. Return:  {result['annual_return']}%")
    print(f"  Max DD:       {result['max_dd_pct']}%")
    print(f"  Sharpe:       {result['sharpe']}")
    print(f"  Profit Factor:{result['profit_factor']}")

    # ── حفظ النتائج (upsert) ────────────────────────────────────
    os.makedirs("journal", exist_ok=True)
    results_path = "journal/multi_pair_results.json"

    existing = []
    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = []

    existing = [r for r in existing if r.get("pair") != pair]
    existing.append(result)

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    print(f"\n  ✅ محفوظ في {results_path}")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python multi_pair_backtest.py EURUSD")
        sys.exit(1)
    run_backtest(sys.argv[1])
