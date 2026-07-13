"""
Month-End Filter Backtest — EURUSD & GBPUSD
=============================================
Hypothesis: skip last 2-3 trading days of each month (day >= 28)
to avoid False Breakouts from institutional rebalancing.

Baseline params (matching live strategies):
  EURUSD: range 07-13 UTC, min_range=25 pips, atr_sl=1.8, min_rr=3.5
  GBPUSD: range 07-13 UTC, min_range=60 pips, atr_sl=1.8, min_rr=4.0
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

BALANCE   = 10_000
RISK_PCT  = 0.01
SPREAD_EU = 0.00012
SPREAD_GB = 0.00015


def load_data(path):
    df = pd.read_csv(path, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df.columns = [c.strip() for c in df.columns]
    rename = {}
    for c in df.columns:
        cl = c.lower()
        if cl in ("open","o"):     rename[c] = "Open"
        elif cl in ("high","h"):   rename[c] = "High"
        elif cl in ("low","l"):    rename[c] = "Low"
        elif cl in ("close","c"):  rename[c] = "Close"
        elif cl == "datetime":     rename[c] = "datetime"
    return df.rename(columns=rename)


def calc_atr(df, period=14):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    tr = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(h))]
    tr = np.array([tr[0]] + tr)
    return pd.Series(tr).rolling(period).mean().values


def run_backtest(df, range_start, range_end, session_end,
                 min_range_pips, atr_sl, min_rr, spread,
                 month_end_day=None):
    """
    month_end_day: if set, skip entries on day-of-month >= month_end_day
    """
    atr_vals = calc_atr(df)
    balance  = BALANCE
    equity   = [balance]
    trades   = []
    in_trade = False
    direction = None
    entry = sl = tp = 0.0

    for i in range(50, len(df)):
        dt   = df["datetime"].iloc[i]
        hour = dt.hour
        price = df["Close"].values[i]

        # --- manage open trade ---
        if in_trade:
            if direction == "BUY":
                if df["Low"].values[i] <= sl:
                    risk = entry - sl
                    pnl  = (sl - entry - spread) / entry
                    balance *= (1 + pnl * RISK_PCT / (risk / entry + 1e-9))
                    trades.append(sl - entry)
                    in_trade = False
                elif df["High"].values[i] >= tp:
                    risk = entry - sl
                    pnl  = (tp - entry - spread) / entry
                    balance *= (1 + pnl * RISK_PCT / (risk / entry + 1e-9))
                    trades.append(tp - entry)
                    in_trade = False
            else:
                if df["High"].values[i] >= sl:
                    risk = sl - entry
                    pnl  = (entry - sl - spread) / entry
                    balance *= (1 + pnl * RISK_PCT / (risk / entry + 1e-9))
                    trades.append(entry - sl)
                    in_trade = False
                elif df["Low"].values[i] <= tp:
                    risk = sl - entry
                    pnl  = (entry - tp - spread) / entry
                    balance *= (1 + pnl * RISK_PCT / (risk / entry + 1e-9))
                    trades.append(entry - tp)
                    in_trade = False
            equity.append(balance)
            continue

        # --- only enter in session window ---
        if not (range_end <= hour < session_end):
            equity.append(balance)
            continue

        # --- Month-End Filter ---
        if month_end_day is not None and dt.day >= month_end_day:
            equity.append(balance)
            continue

        atr = atr_vals[i]
        if atr <= 0:
            equity.append(balance)
            continue

        # Build range window (range_start:00 – range_end:00 same day)
        day_mask = (df["datetime"] >= dt.replace(hour=range_start, minute=0, second=0,
                                                  microsecond=0)) & \
                   (df["datetime"] < dt.replace(hour=range_end, minute=0, second=0,
                                                 microsecond=0))
        pre = df[day_mask]
        if len(pre) < 2:
            equity.append(balance)
            continue

        r_high = float(pre["High"].max())
        r_low  = float(pre["Low"].min())
        r_size = (r_high - r_low) / 0.0001  # pips

        if r_size < min_range_pips:
            equity.append(balance)
            continue

        prev_c = df["Close"].values[i-1]
        sl_dist = atr_sl * atr

        if prev_c <= r_high and price > r_high:
            entry     = price + spread
            sl        = entry - sl_dist
            tp        = entry + sl_dist * min_rr
            direction = "BUY"
            in_trade  = True
        elif prev_c >= r_low and price < r_low:
            entry     = price - spread
            sl        = entry + sl_dist
            tp        = entry - sl_dist * min_rr
            direction = "SELL"
            in_trade  = True

        equity.append(balance)

    if not trades:
        return None

    eq  = np.array(equity)
    ret = np.diff(eq) / eq[:-1]
    sharpe  = (ret.mean() / (ret.std() + 1e-9)) * np.sqrt(8760)
    rm      = np.maximum.accumulate(eq)
    dd      = (eq - rm) / (rm + 1e-9) * 100
    wins    = [t for t in trades if t > 0]
    losses  = [abs(t) for t in trades if t < 0]
    pf      = sum(wins) / (sum(losses) + 1e-9) if losses else float("inf")
    wr      = len(wins) / len(trades) * 100

    return {
        "sharpe":  round(sharpe, 3),
        "return":  round((balance - BALANCE) / BALANCE * 100, 2),
        "max_dd":  round(float(dd.min()), 2),
        "win_rate": round(wr, 1),
        "trades":  len(trades),
        "pf":      round(pf, 3),
    }


def run_pair(name, data_file, spread, range_start, range_end, session_end,
             min_range_pips, atr_sl, min_rr):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    df = load_data(f"backtest_data/{data_file}")

    base = run_backtest(df, range_start, range_end, session_end,
                        min_range_pips, atr_sl, min_rr, spread,
                        month_end_day=None)
    filt28 = run_backtest(df, range_start, range_end, session_end,
                          min_range_pips, atr_sl, min_rr, spread,
                          month_end_day=28)
    filt27 = run_backtest(df, range_start, range_end, session_end,
                          min_range_pips, atr_sl, min_rr, spread,
                          month_end_day=27)

    header = f"{'Metric':<12} {'Baseline':>10} {'Day>=28':>10} {'Day>=27':>10} {'Delta28':>10}"
    print(header)
    print("-" * len(header))
    for k in ["sharpe","return","max_dd","win_rate","trades","pf"]:
        b  = base[k]  if base  else "N/A"
        f28 = filt28[k] if filt28 else "N/A"
        f27 = filt27[k] if filt27 else "N/A"
        delta28 = f"+{round(f28-b,3)}" if isinstance(b,float) and isinstance(f28,float) else "-"
        print(f"{k:<12} {str(b):>10} {str(f28):>10} {str(f27):>10} {delta28:>10}")

    return {"baseline": base, "day28": filt28, "day27": filt27}


if __name__ == "__main__":
    eurusd = run_pair(
        "EURUSD — NY Breakout + Month-End Filter",
        "EURUSD_H1_2years.csv",
        spread=SPREAD_EU,
        range_start=7, range_end=13, session_end=15,
        min_range_pips=25, atr_sl=1.8, min_rr=3.5,
    )

    gbpusd = run_pair(
        "GBPUSD — NY Breakout + Month-End Filter",
        "GBPUSD_H1_2years.csv",
        spread=SPREAD_GB,
        range_start=7, range_end=13, session_end=15,
        min_range_pips=60, atr_sl=1.8, min_rr=4.0,
    )

    print("\n\n" + "="*60)
    print("  SUMMARY — Month-End Filter Analysis")
    print("="*60)
    for name, res in [("EURUSD", eurusd), ("GBPUSD", gbpusd)]:
        b  = res["baseline"]
        f28 = res["day28"]
        decision = "✅ APPLY" if f28 and b and f28["sharpe"] > b["sharpe"] else "❌ REJECT"
        b_s  = b["sharpe"]  if b  else "N/A"
        f_s  = f28["sharpe"] if f28 else "N/A"
        print(f"  {name}: Baseline Sharpe={b_s} → Day>=28 Filter={f_s} → {decision}")
