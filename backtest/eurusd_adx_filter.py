"""
EURUSD ADX Threshold Filter Backtest — [I] Proposal (2026-07-14)
=================================================================
Hypothesis: Add H1 ADX minimum threshold to NY Breakout to filter
sideways markets, WITHOUT directional bias (unlike MACD/RSI).

  - No BUY or SELL when ADX < ADX_MIN (market too sideways)
  - Tests ADX_MIN in {15, 18, 20, 22, 25, 28, 30}

Baseline (current live engine, same parameters):
  RANGE_START=7, RANGE_END=13, SESSION_END=15
  MIN_RANGE_PIPS=25, ATR_SL=1.8, MIN_RR=3.5

Inspired by [H] EURUSD MACD ❌ REJECTED (2026-07-14):
  MACD failed because EURUSD breaks symmetrically (BUY+SELL),
  directional filter removes good trades on both sides.
  ADX is direction-neutral — only filters sideways days.

Target: EURUSD Sharpe 1.61 → 1.75+
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

DATA_FILE = "backtest_data/EURUSD_H1_2years.csv"
BALANCE   = 10_000
RISK_PCT  = 0.01
SPREAD    = 0.00012

# EURUSD live params (unchanged)
RANGE_START    = 7
RANGE_END      = 13
SESSION_END    = 15
MIN_RANGE_PIPS = 25
ATR_SL         = 1.8
MIN_RR         = 3.5
PIP            = 0.0001
ATR_PERIOD     = 14
ADX_PERIOD     = 14


def load_data():
    df = pd.read_csv(DATA_FILE, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    rename = {}
    for c in df.columns:
        cl = c.lower()
        if cl in ("open","o"):    rename[c] = "Open"
        elif cl in ("high","h"):  rename[c] = "High"
        elif cl in ("low","l"):   rename[c] = "Low"
        elif cl in ("close","c"): rename[c] = "Close"
        elif cl == "datetime":    rename[c] = "datetime"
    return df.rename(columns=rename)


def calc_atr(df, period=ATR_PERIOD):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    tr = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(h))]
    tr = np.array([tr[0]] + tr)
    return pd.Series(tr).rolling(period).mean().values


def calc_adx(df, period=ADX_PERIOD):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    adx_out = np.zeros(len(h))
    if len(h) < period + 2:
        return adx_out
    dh = np.diff(h)
    dl = -np.diff(l)
    dmp = np.where((dh > dl) & (dh > 0), dh, 0.0)
    dmm = np.where((dl > dh) & (dl > 0), dl, 0.0)
    tr_arr = np.array([max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                       for i in range(1, len(h))])
    def smma(arr, p):
        out = np.zeros(len(arr))
        if p <= len(arr):
            out[p-1] = arr[:p].mean()
            for i in range(p, len(arr)):
                out[i] = (out[i-1]*(p-1) + arr[i]) / p
        return out
    atr_s = smma(tr_arr, period)
    dip   = smma(dmp, period) / (atr_s + 1e-9) * 100
    dim   = smma(dmm, period) / (atr_s + 1e-9) * 100
    dx    = np.abs(dip - dim) / (dip + dim + 1e-9) * 100
    adx_out[1:] = smma(dx, period)
    return adx_out


def run_backtest(df, indicators, adx_min):
    atr_arr = indicators["atr"]
    adx_arr = indicators["adx"]

    balance = BALANCE
    trades  = []
    in_trade = False
    direction = entry = sl = tp = None

    for i in range(100, len(df)):
        dt  = df["datetime"].iloc[i]
        h   = dt.hour
        c   = df["Close"].values[i]

        if in_trade:
            if direction == "BUY":
                if df["Low"].values[i] <= sl:
                    risk = entry - sl
                    lot  = (balance * RISK_PCT) / risk if risk > 0 else 0
                    pnl  = (sl - entry - SPREAD) * lot
                    balance += pnl
                    trades.append(sl - entry - SPREAD)
                    in_trade = False
                elif df["High"].values[i] >= tp:
                    risk = entry - sl
                    lot  = (balance * RISK_PCT) / risk if risk > 0 else 0
                    pnl  = (tp - entry - SPREAD) * lot
                    balance += pnl
                    trades.append(tp - entry - SPREAD)
                    in_trade = False
            else:
                if df["High"].values[i] >= sl:
                    risk = sl - entry
                    lot  = (balance * RISK_PCT) / risk if risk > 0 else 0
                    pnl  = (entry - sl - SPREAD) * lot
                    balance += pnl
                    trades.append(entry - sl - SPREAD)
                    in_trade = False
                elif df["Low"].values[i] <= tp:
                    risk = sl - entry
                    lot  = (balance * RISK_PCT) / risk if risk > 0 else 0
                    pnl  = (entry - tp - SPREAD) * lot
                    balance += pnl
                    trades.append(entry - tp - SPREAD)
                    in_trade = False
            continue

        if not (RANGE_END <= h < SESSION_END):
            continue

        # Build London range
        day   = dt.normalize()
        start = day + pd.Timedelta(hours=RANGE_START)
        end   = day + pd.Timedelta(hours=RANGE_END)
        idx   = pd.DatetimeIndex(df["datetime"])
        mask  = (idx >= start) & (idx < end)
        pre   = df[mask]
        if len(pre) < 2:
            continue

        r_high = float(pre["High"].max())
        r_low  = float(pre["Low"].min())
        r_pips = (r_high - r_low) / PIP
        if r_pips < MIN_RANGE_PIPS:
            continue

        atr = atr_arr[i]
        adx = adx_arr[i]
        if atr <= 0:
            continue

        # ── ADX Filter ─────────────────────────────────────────────
        if adx_min > 0 and adx < adx_min:
            continue  # Skip sideways market

        prev_c = df["Close"].values[i - 1]
        sl_dist = ATR_SL * atr

        if prev_c <= r_high and c > r_high:
            sl_p = c - sl_dist
            tp_p = c + sl_dist * MIN_RR
            entry, sl, tp, direction = c, sl_p, tp_p, "BUY"
            in_trade = True

        elif prev_c >= r_low and c < r_low:
            sl_p = c + sl_dist
            tp_p = c - sl_dist * MIN_RR
            entry, sl, tp, direction = c, sl_p, tp_p, "SELL"
            in_trade = True

    return balance, trades


def metrics(trades, balance):
    if not trades:
        return {"sharpe": 0, "return": 0, "max_dd": 0, "win_rate": 0,
                "trades": 0, "profit_factor": 0}
    arr = np.array(trades)
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    wr  = len(wins) / len(arr) * 100
    ret = (balance - BALANCE) / BALANCE * 100
    mu  = arr.mean(); sd = arr.std()
    sharpe = (mu / sd * np.sqrt(252)) if sd > 0 else 0
    pf = (wins.sum() / abs(losses.sum())) if len(losses) > 0 and losses.sum() != 0 else 999
    # Max drawdown
    equity = BALANCE
    peak   = BALANCE
    max_dd = 0
    for t in arr:
        risk = equity * RISK_PCT
        equity += t / PIP * risk / 10000 if False else (
            equity * RISK_PCT * (t / (ATR_SL * 0.0010))
        )
        peak    = max(peak, equity)
        max_dd  = min(max_dd, (equity - peak) / peak * 100)
    return {
        "sharpe":        round(sharpe, 3),
        "return":        round(ret, 2),
        "max_dd":        round(max_dd, 2),
        "win_rate":      round(wr, 1),
        "trades":        len(arr),
        "profit_factor": round(pf, 3),
    }


if __name__ == "__main__":
    print("Loading EURUSD data...")
    df = load_data()
    print(f"  {len(df)} H1 bars loaded")

    print("Computing indicators...")
    indicators = {
        "atr": calc_atr(df),
        "adx": calc_adx(df),
    }

    ADX_VALUES = [0, 15, 18, 20, 22, 25, 28, 30]

    print("\n" + "="*70)
    print("EURUSD ADX Threshold Filter — Grid Search")
    print("="*70)
    print(f"{'ADX_MIN':>8} | {'Sharpe':>7} | {'Return':>8} | {'MaxDD':>7} | {'WR%':>6} | {'Trades':>7} | {'PF':>6}")
    print("-"*70)

    best = None
    best_sharpe = -999

    for adx_min in ADX_VALUES:
        balance, trades = run_backtest(df, indicators, adx_min)
        m = metrics(trades, balance)
        label = "BASELINE" if adx_min == 0 else f"{adx_min}"
        print(f"{label:>8} | {m['sharpe']:>7.3f} | {m['return']:>7.2f}% | {m['max_dd']:>6.2f}% "
              f"| {m['win_rate']:>5.1f}% | {m['trades']:>7} | {m['profit_factor']:>6.3f}")
        if adx_min > 0 and m["sharpe"] > best_sharpe:
            best_sharpe = m["sharpe"]
            best = (adx_min, m)

    print("="*70)
    if best:
        adx_val, bm = best
        baseline_bal, baseline_trades = run_backtest(df, indicators, 0)
        baseline = metrics(baseline_trades, baseline_bal)
        delta = bm["sharpe"] - baseline["sharpe"]
        print(f"\n✅ Best ADX_MIN = {adx_val}")
        print(f"   Sharpe:  {baseline['sharpe']:.3f} → {bm['sharpe']:.3f} ({delta:+.3f})")
        print(f"   Return:  {baseline['return']:.2f}% → {bm['return']:.2f}%")
        print(f"   Max DD:  {baseline['max_dd']:.2f}% → {bm['max_dd']:.2f}%")
        print(f"   WR:      {baseline['win_rate']:.1f}% → {bm['win_rate']:.1f}%")
        print(f"   Trades:  {baseline['trades']} → {bm['trades']}")
        dd_ok  = bm["max_dd"] >= baseline["max_dd"] - 2.0
        sharpe_ok = delta > 0.05
        if sharpe_ok and dd_ok:
            print(f"\n  → VERDICT: ✅ CONSIDER APPLYING (Δ Sharpe {delta:+.3f})")
        else:
            print(f"\n  → VERDICT: ❌ REJECT (Δ Sharpe {delta:+.3f} — below threshold)")
