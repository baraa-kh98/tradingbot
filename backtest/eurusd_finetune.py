"""
EURUSD Fine-Tune — NY Open Breakout
=====================================
Winner from research: range_hours=4, min_range_pips=40, atr_sl=2.0, min_rr=3.0
Goal: squeeze more Sharpe & trades with expanded grid.

Also tests a hybrid: NYOpen + EMA trend confirmation
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json, warnings, itertools
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

DATA_FILE = "backtest_data/EURUSD_H1_2years.csv"
RESULTS_FILE = "journal/eurusd_finetune_results.json"
BALANCE = 10_000
RISK_PCT = 0.01
SPREAD = 0.00012

# ── Data & Indicators ─────────────────────────────────────────────────────────

def load_data():
    df = pd.read_csv(DATA_FILE, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df.columns = [c.strip() for c in df.columns]
    rename = {}
    for c in df.columns:
        cl = c.lower()
        if cl in ("open","o"): rename[c] = "Open"
        elif cl in ("high","h"): rename[c] = "High"
        elif cl in ("low","l"): rename[c] = "Low"
        elif cl in ("close","c"): rename[c] = "Close"
        elif cl == "datetime": rename[c] = "datetime"
    return df.rename(columns=rename)

def calc_atr(df, period=14):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    tr = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(h))]
    tr = np.array([tr[0]] + tr)
    return pd.Series(tr).rolling(period).mean().values

def calc_adx(df, period=14):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    adx_out = np.zeros(len(h))
    if len(h) < period + 2: return adx_out
    dh = np.diff(h); dl = -np.diff(l)
    dmp = np.where((dh > dl) & (dh > 0), dh, 0.0)
    dmm = np.where((dl > dh) & (dl > 0), dl, 0.0)
    tr_arr = np.array([max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                       for i in range(1, len(h))])
    def smma(arr, p):
        out = np.zeros(len(arr))
        out[p-1] = arr[:p].mean()
        for i in range(p, len(arr)):
            out[i] = (out[i-1]*(p-1) + arr[i]) / p
        return out
    atr_s = smma(tr_arr, period)
    dip = smma(dmp, period) / (atr_s + 1e-9) * 100
    dim = smma(dmm, period) / (atr_s + 1e-9) * 100
    dx  = np.abs(dip - dim) / (dip + dim + 1e-9) * 100
    adx_out[1:] = smma(dx, period)
    return adx_out

def calc_ema(series, span):
    return pd.Series(series).ewm(span=span, adjust=False).mean().values

def precompute(df):
    return {
        "atr":   calc_atr(df, 14),
        "adx":   calc_adx(df, 14),
        "ema20": calc_ema(df["Close"].values, 20),
        "ema50": calc_ema(df["Close"].values, 50),
        "ema100":calc_ema(df["Close"].values, 100),
    }

# ── Backtest Engine ───────────────────────────────────────────────────────────

def run_backtest(signals_fn, df, indicators):
    balance = BALANCE
    equity_curve = [balance]
    trades = []
    in_trade = False
    direction = entry = sl = tp = None

    for i in range(100, len(df)):
        c = df["Close"].values[i]

        if in_trade:
            if direction == "BUY":
                if df["Low"].values[i] <= sl:
                    risk = entry - sl
                    lot = (balance * RISK_PCT) / risk if risk > 0 else 0
                    pnl = (sl - entry - SPREAD) * lot
                    balance += pnl; trades.append(sl - entry - SPREAD)
                    in_trade = False
                elif df["High"].values[i] >= tp:
                    risk = entry - sl
                    lot = (balance * RISK_PCT) / risk if risk > 0 else 0
                    pnl = (tp - entry - SPREAD) * lot
                    balance += pnl; trades.append(tp - entry - SPREAD)
                    in_trade = False
            else:  # SELL
                if df["High"].values[i] >= sl:
                    risk = sl - entry
                    lot = (balance * RISK_PCT) / risk if risk > 0 else 0
                    pnl = (entry - sl - SPREAD) * lot
                    balance += pnl; trades.append(entry - sl - SPREAD)
                    in_trade = False
                elif df["Low"].values[i] <= tp:
                    risk = sl - entry
                    lot = (balance * RISK_PCT) / risk if risk > 0 else 0
                    pnl = (entry - tp - SPREAD) * lot
                    balance += pnl; trades.append(entry - tp - SPREAD)
                    in_trade = False
            equity_curve.append(balance)
            continue

        sig = signals_fn(i, df, indicators)
        if sig:
            direction, sl, tp = sig
            entry = c + SPREAD if direction == "BUY" else c - SPREAD
            in_trade = True
        equity_curve.append(balance)

    if len(trades) < 5:
        return None

    eq = np.array(equity_curve)
    returns = np.diff(eq) / (eq[:-1] + 1e-9)
    sharpe = (returns.mean() / (returns.std() + 1e-9)) * np.sqrt(8760)
    roll_max = np.maximum.accumulate(eq)
    dd = (eq - roll_max) / (roll_max + 1e-9) * 100
    wins = [t for t in trades if t > 0]
    losses = [abs(t) for t in trades if t < 0]
    pf = sum(wins) / (sum(losses) + 1e-9)

    return {
        "trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "return_pct": round((balance - BALANCE) / BALANCE * 100, 2),
        "sharpe": round(float(sharpe), 3),
        "max_dd_pct": round(float(dd.min()), 2),
        "profit_factor": round(pf, 3),
    }

# ── NY Open Breakout (enhanced) ───────────────────────────────────────────────

def make_ny_breakout(
    range_start,     # UTC hour range starts (e.g. 7, 8, 9)
    range_end,       # UTC hour range ends = NY open (e.g. 12, 13)
    session_end,     # UTC hour to stop trading (e.g. 15, 16, 17)
    min_range_pips,  # min pre-NY range size
    atr_sl,          # SL = atr_sl × ATR
    min_rr,          # TP = min_rr × risk
    adx_min,         # ADX filter (0 = disabled)
    ema_filter,      # True = require price above/below EMA100
):
    def signals(i, df, ind):
        dt   = df["datetime"].iloc[i]
        hour = dt.hour
        if not (range_end <= hour < session_end): return None

        # Build pre-NY range
        day_start = dt.replace(hour=range_start, minute=0, second=0)
        day_end   = dt.replace(hour=range_end,   minute=0, second=0)
        mask = (df["datetime"] >= day_start) & (df["datetime"] < day_end)
        pre  = df[mask]
        if len(pre) < 2: return None

        r_high = float(pre["High"].max())
        r_low  = float(pre["Low"].min())
        r_size = (r_high - r_low) / 0.0001

        if r_size < min_range_pips: return None

        price  = df["Close"].values[i]
        prev_c = df["Close"].values[i-1]
        atr    = ind["atr"][i]
        adx    = ind["adx"][i]

        if atr <= 0: return None
        if adx_min > 0 and adx < adx_min: return None

        sl_dist = atr_sl * atr

        # EMA100 directional filter
        ema100 = ind["ema100"][i] if ema_filter else None

        if prev_c <= r_high and price > r_high:
            if ema_filter and price < ema100: return None
            sl = price - sl_dist
            tp = price + sl_dist * min_rr
            return ("BUY", sl, tp)

        if prev_c >= r_low and price < r_low:
            if ema_filter and price > ema100: return None
            sl = price + sl_dist
            tp = price - sl_dist * min_rr
            return ("SELL", sl, tp)
        return None
    return signals

# ── Grid Search ───────────────────────────────────────────────────────────────

def grid_search(make_fn, param_grid, df, indicators, label):
    keys  = list(param_grid.keys())
    combos = list(itertools.product(*[param_grid[k] for k in keys]))
    print(f"\n{'─'*65}")
    print(f"  {label} — {len(combos)} combos")
    print(f"{'─'*65}")

    best = None; best_score = -999; all_res = []

    for idx, vals in enumerate(combos):
        params = dict(zip(keys, vals))
        fn = make_fn(**params)
        try:
            r = run_backtest(fn, df, indicators)
        except Exception:
            continue
        if r is None: continue

        score = r["sharpe"] * np.log(max(r["trades"], 1))
        r["params"] = params; r["score"] = round(score, 4)
        all_res.append(r)

        if score > best_score:
            best_score = score; best = r
            print(f"  ✓ [{idx+1:3d}/{len(combos)}] {params}")
            print(f"       → Sharpe={r['sharpe']:.3f} Ret={r['return_pct']:.1f}% "
                  f"DD={r['max_dd_pct']:.1f}% PF={r['profit_factor']:.2f} T={r['trades']}")

    return best, sorted(all_res, key=lambda x: -x["score"])[:20]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading EURUSD H1 data...")
    df = load_data()
    print(f"  {len(df)} candles | {df['datetime'].iloc[0].date()} → {df['datetime'].iloc[-1].date()}")
    indicators = precompute(df)

    # ── Phase 1: Fine-tune core NY Open Breakout ──────────────────
    best1, top1 = grid_search(
        make_ny_breakout,
        {
            "range_start":    [7, 8, 9],
            "range_end":      [12, 13],
            "session_end":    [15, 16, 17],
            "min_range_pips": [25, 30, 35, 40, 45, 50, 55],
            "atr_sl":         [1.5, 1.8, 2.0, 2.2, 2.5],
            "min_rr":         [2.5, 3.0, 3.5],
            "adx_min":        [0],
            "ema_filter":     [False],
        },
        df, indicators, "NYOpen Core Fine-Tune"
    )

    # ── Phase 2: Add EMA filter & ADX filter on best range ────────
    if best1:
        bp = best1["params"]
        best2, top2 = grid_search(
            make_ny_breakout,
            {
                "range_start":    [bp["range_start"]],
                "range_end":      [bp["range_end"]],
                "session_end":    [bp["session_end"]],
                "min_range_pips": [bp["min_range_pips"] - 5, bp["min_range_pips"], bp["min_range_pips"] + 5],
                "atr_sl":         [bp["atr_sl"] - 0.2, bp["atr_sl"], bp["atr_sl"] + 0.2],
                "min_rr":         [bp["min_rr"]],
                "adx_min":        [0, 20, 25],
                "ema_filter":     [False, True],
            },
            df, indicators, "NYOpen + Filters"
        )
    else:
        best2, top2 = None, []

    # ── Final Summary ─────────────────────────────────────────────
    print(f"\n{'═'*65}")
    print("  EURUSD FINE-TUNE — FINAL RESULTS")
    print(f"{'═'*65}")
    ACCEPT = dict(sharpe=0.8, return_pct=15.0, max_dd_pct=-15.0, profit_factor=1.4, trades=40)

    candidates = []
    for label, b in [("Core", best1), ("WithFilters", best2)]:
        if b is None: continue
        ok = (b["sharpe"] >= ACCEPT["sharpe"] and b["return_pct"] >= ACCEPT["return_pct"] and
              b["max_dd_pct"] >= ACCEPT["max_dd_pct"] and b["profit_factor"] >= ACCEPT["profit_factor"] and
              b["trades"] >= ACCEPT["trades"])
        flag = "✅" if ok else "⚠️"
        print(f"  {flag} {label:15s}: Sharpe={b['sharpe']:.3f} Ret={b['return_pct']:.1f}% "
              f"DD={b['max_dd_pct']:.1f}% PF={b['profit_factor']:.2f} T={b['trades']}")
        print(f"       Params: {b['params']}")
        if ok: candidates.append((b["score"], label, b))

    if candidates:
        candidates.sort(key=lambda x: -x[0])
        champion = candidates[0][2]
        print(f"\n  🏆 CHAMPION: {candidates[0][1]}")
        print(f"     Params : {champion['params']}")
        print(f"     Sharpe : {champion['sharpe']}")
        print(f"     Return : {champion['return_pct']}%")
        print(f"     Max DD : {champion['max_dd_pct']}%")
        print(f"     PF     : {champion['profit_factor']}")
        print(f"     Trades : {champion['trades']}")

    # Save
    os.makedirs("journal", exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump({
            "core_best": best1,
            "core_top20": top1,
            "filters_best": best2,
            "filters_top20": top2,
        }, f, indent=2, default=str)
    print(f"\n  Results saved → {RESULTS_FILE}")

if __name__ == "__main__":
    main()
