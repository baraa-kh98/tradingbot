"""
GBPUSD Strategy Research — 4 approaches on H1 (2 years)
=========================================================
Optimised: precomputes daily ranges once → 10× faster than naive mask.

GBPUSD characteristics:
  - High volatility (~100 pips/day)
  - Sharp moves on UK/US macro data
  - Liquidity sweeps before major moves
  - Strong trending during London & NY sessions

Tests:
  1. NYOpenBreakout      — London range (07–13 UTC) broken at NY open (13–15 UTC)
  2. ATRChannelBreakout  — N-bar high/low + ADX
  3. LiquiditySweepRev   — Asia high/low sweep → reversal (ICT-style)
  4. LondonATRBreakout   — Asia range broken at London open + ATR SL

Acceptance: Sharpe > 0.5 | Return > 10% | MaxDD < 15% | PF > 1.3 | Trades > 40
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json, warnings, itertools
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

DATA_FILE = "backtest_data/GBPUSD_H1_2years.csv"
RESULTS_FILE = "journal/gbpusd_research_results.json"
BALANCE = 10_000
RISK_PCT = 0.01
SPREAD = 0.00018   # 1.8 pips

# ── Data ─────────────────────────────────────────────────────────────────────

def load_data():
    df = pd.read_csv(DATA_FILE, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    rename = {}
    for c in df.columns:
        cl = c.lower()
        if cl in ("open","o"): rename[c] = "Open"
        elif cl in ("high","h"): rename[c] = "High"
        elif cl in ("low","l"): rename[c] = "Low"
        elif cl in ("close","c"): rename[c] = "Close"
        elif cl == "datetime": rename[c] = "datetime"
    return df.rename(columns=rename)

# ── Precompute daily range tables ─────────────────────────────────────────────

def build_daily_range_table(df, start_h, end_h):
    """
    Returns dict: date_str → (range_high, range_low)
    Only includes dates where candles in [start_h, end_h) exist.
    """
    df2 = df.copy()
    df2["_date"] = df2["datetime"].dt.normalize()
    df2["_hour"] = df2["datetime"].dt.hour
    mask = (df2["_hour"] >= start_h) & (df2["_hour"] < end_h)
    grp = df2[mask].groupby("_date").agg(
        range_high=("High", "max"),
        range_low=("Low", "min"),
        count=("Close", "count"),
    )
    grp = grp[grp["count"] >= 2]
    return grp["range_high"].to_dict(), grp["range_low"].to_dict()

# ── Indicators ────────────────────────────────────────────────────────────────

def calc_atr(df, period=14):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    tr = np.array([max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                   for i in range(1, len(h))])
    tr = np.concatenate([[tr[0]], tr])
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
        out = np.zeros(len(arr)); out[p-1] = arr[:p].mean()
        for i in range(p, len(arr)): out[i] = (out[i-1]*(p-1) + arr[i]) / p
        return out
    atr_s = smma(tr_arr, period)
    dip = smma(dmp, period) / (atr_s + 1e-9) * 100
    dim = smma(dmm, period) / (atr_s + 1e-9) * 100
    dx  = np.abs(dip - dim) / (dip + dim + 1e-9) * 100
    adx_out[1:] = smma(dx, period)
    return adx_out

def precompute(df):
    return {
        "atr":  calc_atr(df, 14),
        "adx":  calc_adx(df, 14),
        "dates": df["datetime"].dt.normalize().values,
        "hours": df["datetime"].dt.hour.values,
    }

# ── Backtest Engine ───────────────────────────────────────────────────────────

def run_backtest(signal_array, df):
    """
    signal_array[i] = ('BUY'|'SELL', sl, tp) or None  — precomputed.
    """
    balance = BALANCE
    equity = [balance]
    trades = []
    in_trade = False
    direction = entry = sl = tp = None
    H = df["High"].values; L = df["Low"].values

    for i in range(len(df)):
        if in_trade:
            if direction == "BUY":
                if L[i] <= sl:
                    risk = max(entry - sl, 1e-9)
                    lot = balance * RISK_PCT / risk
                    balance += (sl - entry - SPREAD) * lot
                    trades.append(sl - entry - SPREAD)
                    in_trade = False
                elif H[i] >= tp:
                    risk = max(entry - sl, 1e-9)
                    lot = balance * RISK_PCT / risk
                    balance += (tp - entry - SPREAD) * lot
                    trades.append(tp - entry - SPREAD)
                    in_trade = False
            else:
                if H[i] >= sl:
                    risk = max(sl - entry, 1e-9)
                    lot = balance * RISK_PCT / risk
                    balance += (entry - sl - SPREAD) * lot
                    trades.append(entry - sl - SPREAD)
                    in_trade = False
                elif L[i] <= tp:
                    risk = max(sl - entry, 1e-9)
                    lot = balance * RISK_PCT / risk
                    balance += (entry - tp - SPREAD) * lot
                    trades.append(entry - tp - SPREAD)
                    in_trade = False
            equity.append(balance)
            continue

        sig = signal_array[i]
        if sig:
            direction, sl, tp = sig
            c = df["Close"].values[i]
            entry = c + SPREAD if direction == "BUY" else c - SPREAD
            in_trade = True
        equity.append(balance)

    if len(trades) < 5:
        return None

    eq = np.array(equity)
    returns = np.diff(eq) / (eq[:-1] + 1e-9)
    sharpe = (returns.mean() / (returns.std() + 1e-9)) * np.sqrt(8760)
    roll_max = np.maximum.accumulate(eq)
    dd = (eq - roll_max) / (roll_max + 1e-9) * 100
    wins   = [t for t in trades if t > 0]
    losses = [abs(t) for t in trades if t < 0]

    return {
        "trades": len(trades),
        "win_rate": round(len(wins)/len(trades)*100, 1),
        "return_pct": round((balance-BALANCE)/BALANCE*100, 2),
        "sharpe": round(float(sharpe), 3),
        "max_dd_pct": round(float(dd.min()), 2),
        "profit_factor": round(sum(wins)/(sum(losses)+1e-9), 3),
    }

# ── Signal builders (vectorised-friendly) ────────────────────────────────────

def build_ny_signals(df, ind, range_highs, range_lows, session_h_start,
                     session_h_end, min_range_pips, atr_sl, min_rr):
    signals = [None] * len(df)
    C = df["Close"].values
    PIP = 0.0001
    for i in range(1, len(df)):
        hour = ind["hours"][i]
        if not (session_h_start <= hour < session_h_end): continue
        day = ind["dates"][i]
        r_high = range_highs.get(day); r_low = range_lows.get(day)
        if r_high is None: continue
        r_pips = (r_high - r_low) / PIP
        if r_pips < min_range_pips: continue
        atr = ind["atr"][i]
        if atr <= 0: continue
        sl_dist = atr_sl * atr
        price = C[i]; prev_c = C[i-1]
        if prev_c <= r_high and price > r_high:
            signals[i] = ("BUY", price - sl_dist, price + sl_dist * min_rr)
        elif prev_c >= r_low and price < r_low:
            signals[i] = ("SELL", price + sl_dist, price - sl_dist * min_rr)
    return signals

def build_atr_channel_signals(df, ind, nbar, adx_min, atr_sl, min_rr):
    signals = [None] * len(df)
    H = df["High"].values; L = df["Low"].values; C = df["Close"].values
    for i in range(nbar + 20, len(df)):
        adx = ind["adx"][i]; atr = ind["atr"][i]
        if adx < adx_min or atr <= 0: continue
        ch_high = float(np.max(H[i-nbar:i]))
        ch_low  = float(np.min(L[i-nbar:i]))
        price = C[i]; prev_c = C[i-1]
        sl_dist = atr_sl * atr
        if prev_c <= ch_high and price > ch_high:
            signals[i] = ("BUY", price - sl_dist, price + sl_dist * min_rr)
        elif prev_c >= ch_low and price < ch_low:
            signals[i] = ("SELL", price + sl_dist, price - sl_dist * min_rr)
    return signals

def build_sweep_signals(df, ind, asia_highs, asia_lows, sweep_pips, atr_sl, min_rr):
    signals = [None] * len(df)
    H = df["High"].values; L = df["Low"].values; C = df["Close"].values
    sweep_size = sweep_pips * 0.0001
    for i in range(1, len(df)):
        hour = ind["hours"][i]
        if not (7 <= hour <= 16): continue
        day = ind["dates"][i]
        a_high = asia_highs.get(day); a_low = asia_lows.get(day)
        if a_high is None: continue
        atr = ind["atr"][i]
        if atr <= 0: continue
        sl_dist = atr_sl * atr
        price = C[i]
        # Sweep high → SELL reversal
        if H[i-1] > a_high + sweep_size and price < a_high:
            signals[i] = ("SELL", price + sl_dist, price - sl_dist * min_rr)
        # Sweep low → BUY reversal
        elif L[i-1] < a_low - sweep_size and price > a_low:
            signals[i] = ("BUY", price - sl_dist, price + sl_dist * min_rr)
    return signals

def build_london_atr_signals(df, ind, asia_highs, asia_lows, session_h_start,
                              session_h_end, min_range_pips, atr_sl, min_rr):
    signals = [None] * len(df)
    C = df["Close"].values; PIP = 0.0001
    for i in range(1, len(df)):
        hour = ind["hours"][i]
        if not (session_h_start <= hour < session_h_end): continue
        day = ind["dates"][i]
        r_high = asia_highs.get(day); r_low = asia_lows.get(day)
        if r_high is None: continue
        r_pips = (r_high - r_low) / PIP
        if r_pips < min_range_pips: continue
        atr = ind["atr"][i]; adx = ind["adx"][i]
        if atr <= 0 or adx < 18: continue
        sl_dist = atr_sl * atr
        price = C[i]; prev_c = C[i-1]
        if prev_c <= r_high and price > r_high:
            signals[i] = ("BUY", price - sl_dist, price + sl_dist * min_rr)
        elif prev_c >= r_low and price < r_low:
            signals[i] = ("SELL", price + sl_dist, price - sl_dist * min_rr)
    return signals

# ── Grid Search ───────────────────────────────────────────────────────────────

def grid_search_ny(df, ind, param_grid, label):
    # Precompute range tables for all range_start/range_end combos
    range_tables = {}
    for rs, re in set(zip(param_grid.get("range_start",[7]), param_grid.get("range_end",[13]))):
        range_tables[(rs,re)] = build_daily_range_table(df, rs, re)

    keys = list(param_grid.keys())
    combos = list(itertools.product(*[param_grid[k] for k in keys]))
    print(f"\n{'─'*65}")
    print(f"  {label} — {len(combos)} combos")
    print(f"{'─'*65}")
    best = None; best_score = -999; all_res = []

    for idx, vals in enumerate(combos):
        p = dict(zip(keys, vals))
        rh, rl = range_tables[(p["range_start"], p["range_end"])]
        sigs = build_ny_signals(df, ind, rh, rl,
                                 p["range_end"], p["session_end"],
                                 p["min_range_pips"], p["atr_sl"], p["min_rr"])
        r = run_backtest(sigs, df)
        if r is None: continue
        score = r["sharpe"] * np.log(max(r["trades"], 1))
        r["params"] = p; r["score"] = round(score, 4)
        all_res.append(r)
        if score > best_score:
            best_score = score; best = r
            print(f"  ✓ [{idx+1:3d}/{len(combos)}] {p}")
            print(f"       → Sharpe={r['sharpe']:.3f} Ret={r['return_pct']:.1f}% "
                  f"DD={r['max_dd_pct']:.1f}% PF={r['profit_factor']:.2f} T={r['trades']}")
    return best, sorted(all_res, key=lambda x: -x["score"])[:10]

def grid_search_atr(df, ind, param_grid, label):
    keys = list(param_grid.keys())
    combos = list(itertools.product(*[param_grid[k] for k in keys]))
    print(f"\n{'─'*65}")
    print(f"  {label} — {len(combos)} combos")
    print(f"{'─'*65}")
    best = None; best_score = -999; all_res = []
    for idx, vals in enumerate(combos):
        p = dict(zip(keys, vals))
        sigs = build_atr_channel_signals(df, ind, p["nbar"], p["adx_min"], p["atr_sl"], p["min_rr"])
        r = run_backtest(sigs, df)
        if r is None: continue
        score = r["sharpe"] * np.log(max(r["trades"], 1))
        r["params"] = p; r["score"] = round(score, 4)
        all_res.append(r)
        if score > best_score:
            best_score = score; best = r
            print(f"  ✓ [{idx+1:3d}/{len(combos)}] {p}")
            print(f"       → Sharpe={r['sharpe']:.3f} Ret={r['return_pct']:.1f}% "
                  f"DD={r['max_dd_pct']:.1f}% PF={r['profit_factor']:.2f} T={r['trades']}")
    return best, sorted(all_res, key=lambda x: -x["score"])[:10]

def grid_search_sweep(df, ind, asia_highs, asia_lows, param_grid, label):
    keys = list(param_grid.keys())
    combos = list(itertools.product(*[param_grid[k] for k in keys]))
    print(f"\n{'─'*65}")
    print(f"  {label} — {len(combos)} combos")
    print(f"{'─'*65}")
    best = None; best_score = -999; all_res = []
    for idx, vals in enumerate(combos):
        p = dict(zip(keys, vals))
        sigs = build_sweep_signals(df, ind, asia_highs, asia_lows,
                                    p["sweep_pips"], p["atr_sl"], p["min_rr"])
        r = run_backtest(sigs, df)
        if r is None: continue
        score = r["sharpe"] * np.log(max(r["trades"], 1))
        r["params"] = p; r["score"] = round(score, 4)
        all_res.append(r)
        if score > best_score:
            best_score = score; best = r
            print(f"  ✓ [{idx+1:3d}/{len(combos)}] {p}")
            print(f"       → Sharpe={r['sharpe']:.3f} Ret={r['return_pct']:.1f}% "
                  f"DD={r['max_dd_pct']:.1f}% PF={r['profit_factor']:.2f} T={r['trades']}")
    return best, sorted(all_res, key=lambda x: -x["score"])[:10]

def grid_search_london(df, ind, asia_highs, asia_lows, param_grid, label):
    keys = list(param_grid.keys())
    combos = list(itertools.product(*[param_grid[k] for k in keys]))
    print(f"\n{'─'*65}")
    print(f"  {label} — {len(combos)} combos")
    print(f"{'─'*65}")
    best = None; best_score = -999; all_res = []
    for idx, vals in enumerate(combos):
        p = dict(zip(keys, vals))
        sigs = build_london_atr_signals(df, ind, asia_highs, asia_lows,
                                         p["session_start"], p["session_end"],
                                         p["min_range_pips"], p["atr_sl"], p["min_rr"])
        r = run_backtest(sigs, df)
        if r is None: continue
        score = r["sharpe"] * np.log(max(r["trades"], 1))
        r["params"] = p; r["score"] = round(score, 4)
        all_res.append(r)
        if score > best_score:
            best_score = score; best = r
            print(f"  ✓ [{idx+1:3d}/{len(combos)}] {p}")
            print(f"       → Sharpe={r['sharpe']:.3f} Ret={r['return_pct']:.1f}% "
                  f"DD={r['max_dd_pct']:.1f}% PF={r['profit_factor']:.2f} T={r['trades']}")
    return best, sorted(all_res, key=lambda x: -x["score"])[:10]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading GBPUSD H1 data...")
    df = load_data()
    print(f"  {len(df)} candles | {df['datetime'].iloc[0].date()} → {df['datetime'].iloc[-1].date()}")
    ind = precompute(df)

    # Precompute Asia range (00–07 UTC) and London range (07–13 UTC) once
    asia_h, asia_l = build_daily_range_table(df, 0, 7)
    london_h, london_l = build_daily_range_table(df, 7, 13)

    # 1. NY Open Breakout (London range → NY entry)
    best1, top1 = grid_search_ny(
        df, ind,
        {
            "range_start":    [7],
            "range_end":      [13],
            "session_end":    [15, 16, 17],
            "min_range_pips": [30, 40, 50, 60, 70, 80],
            "atr_sl":         [1.5, 1.8, 2.0, 2.2, 2.5],
            "min_rr":         [2.5, 3.0, 3.5],
        },
        "NYOpenBreakout",
    )

    # 2. ATR Channel Breakout
    best2, top2 = grid_search_atr(
        df, ind,
        {
            "nbar":    [20, 30, 40, 50],
            "adx_min": [20, 25, 30],
            "atr_sl":  [1.5, 2.0, 2.5],
            "min_rr":  [2.0, 2.5, 3.0],
        },
        "ATRChannelBreakout",
    )

    # 3. Asia Liquidity Sweep Reversal
    best3, top3 = grid_search_sweep(
        df, ind, asia_h, asia_l,
        {
            "sweep_pips": [3, 5, 8, 12, 15],
            "atr_sl":     [1.5, 2.0, 2.5],
            "min_rr":     [2.0, 2.5, 3.0],
        },
        "LiquiditySweepReversal",
    )

    # 4. London ATR Breakout (Asia range → London entry)
    best4, top4 = grid_search_london(
        df, ind, asia_h, asia_l,
        {
            "session_start":  [7, 8],
            "session_end":    [10, 11],
            "min_range_pips": [30, 40, 50, 60],
            "atr_sl":         [1.5, 2.0, 2.5],
            "min_rr":         [2.0, 2.5, 3.0],
        },
        "LondonATRBreakout",
    )

    # Summary
    print(f"\n{'═'*65}")
    print("  GBPUSD STRATEGY RESEARCH — SUMMARY")
    print(f"{'═'*65}")
    ACCEPT = dict(sharpe=0.5, return_pct=10.0, max_dd_pct=-15.0, profit_factor=1.3, trades=40)
    winner = None; winner_score = -999
    name_best_map = [("NYOpenBreakout",best1),("ATRChannelBreakout",best2),
                     ("LiquiditySweep",best3),("LondonATRBreakout",best4)]

    for name, b in name_best_map:
        if b is None: print(f"  {name:25s} → NO RESULTS"); continue
        ok = (b["sharpe"] >= ACCEPT["sharpe"] and b["return_pct"] >= ACCEPT["return_pct"] and
              b["max_dd_pct"] >= ACCEPT["max_dd_pct"] and b["profit_factor"] >= ACCEPT["profit_factor"] and
              b["trades"] >= ACCEPT["trades"])
        flag = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {name:25s} → Sharpe={b['sharpe']:6.3f} Ret={b['return_pct']:6.1f}% "
              f"DD={b['max_dd_pct']:6.1f}% PF={b['profit_factor']:.2f} T={b['trades']:3d}  {flag}")
        if ok and b["score"] > winner_score:
            winner = name; winner_score = b["score"]

    if winner:
        wb = dict(name_best_map)[winner]
        print(f"\n  🏆 WINNER: {winner}")
        print(f"     Params: {wb['params']}")
    else:
        ranked = [(n, b) for n, b in name_best_map if b]
        ranked.sort(key=lambda x: -x[1]["sharpe"])
        print(f"\n  ⚠️  No strategy passed all criteria.")
        print(f"     Best: {ranked[0][0]} → Sharpe={ranked[0][1]['sharpe']:.3f}")

    os.makedirs("journal", exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump({n: b for n, b in [("NYOpenBreakout",best1),("ATRChannelBreakout",best2),
                                       ("LiquiditySweep",best3),("LondonATRBreakout",best4)]},
                  f, indent=2, default=str)
    print(f"\n  Results saved → {RESULTS_FILE}")

if __name__ == "__main__":
    main()
