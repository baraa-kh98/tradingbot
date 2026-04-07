"""
GBPUSD Fine-Tune — NY Open Breakout
=====================================
Winner: NYOpen, min_range_pips=60, atr_sl=1.8, min_rr=3.0
Goal: improve Sharpe + trade count with finer grid.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json, warnings, itertools
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

DATA_FILE   = "backtest_data/GBPUSD_H1_2years.csv"
RESULTS_FILE = "journal/gbpusd_finetune_results.json"
BALANCE  = 10_000
RISK_PCT = 0.01
SPREAD   = 0.00018

# ── Data & Indicators ─────────────────────────────────────────────────────────

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

def build_daily_range_table(df, start_h, end_h):
    df2 = df.copy()
    df2["_date"] = df2["datetime"].dt.normalize()
    df2["_hour"] = df2["datetime"].dt.hour
    mask = (df2["_hour"] >= start_h) & (df2["_hour"] < end_h)
    grp  = df2[mask].groupby("_date").agg(
        rh=("High","max"), rl=("Low","min"), cnt=("Close","count"))
    grp  = grp[grp["cnt"] >= 2]
    return grp["rh"].to_dict(), grp["rl"].to_dict()

def calc_atr(df, period=14):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    tr = np.array([max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                   for i in range(1, len(h))])
    tr = np.concatenate([[tr[0]], tr])
    return pd.Series(tr).rolling(period).mean().values

def calc_ema(series, span):
    return pd.Series(series).ewm(span=span, adjust=False).mean().values

def precompute(df):
    return {
        "atr":    calc_atr(df, 14),
        "ema100": calc_ema(df["Close"].values, 100),
        "dates":  df["datetime"].dt.normalize().values,
        "hours":  df["datetime"].dt.hour.values,
    }

# ── Backtest Engine ───────────────────────────────────────────────────────────

def run_backtest(signals, df):
    balance = BALANCE
    equity  = [balance]
    trades  = []
    in_trade = False
    direction = entry = sl = tp = None
    H = df["High"].values; L = df["Low"].values; C = df["Close"].values

    for i in range(len(df)):
        if in_trade:
            if direction == "BUY":
                if L[i] <= sl:
                    risk = max(entry - sl, 1e-9)
                    balance += (sl - entry - SPREAD) * (balance * RISK_PCT / risk)
                    trades.append(sl - entry - SPREAD); in_trade = False
                elif H[i] >= tp:
                    risk = max(entry - sl, 1e-9)
                    balance += (tp - entry - SPREAD) * (balance * RISK_PCT / risk)
                    trades.append(tp - entry - SPREAD); in_trade = False
            else:
                if H[i] >= sl:
                    risk = max(sl - entry, 1e-9)
                    balance += (entry - sl - SPREAD) * (balance * RISK_PCT / risk)
                    trades.append(entry - sl - SPREAD); in_trade = False
                elif L[i] <= tp:
                    risk = max(sl - entry, 1e-9)
                    balance += (entry - tp - SPREAD) * (balance * RISK_PCT / risk)
                    trades.append(entry - tp - SPREAD); in_trade = False
            equity.append(balance); continue

        sig = signals[i]
        if sig:
            direction, sl, tp = sig
            entry = C[i] + (SPREAD if direction == "BUY" else -SPREAD)
            in_trade = True
        equity.append(balance)

    if len(trades) < 5: return None
    eq = np.array(equity)
    returns = np.diff(eq) / (eq[:-1] + 1e-9)
    sharpe = (returns.mean() / (returns.std() + 1e-9)) * np.sqrt(8760)
    roll_max = np.maximum.accumulate(eq)
    dd = (eq - roll_max) / (roll_max + 1e-9) * 100
    wins = [t for t in trades if t > 0]; losses = [abs(t) for t in trades if t < 0]
    return {
        "trades": len(trades),
        "win_rate": round(len(wins)/len(trades)*100, 1),
        "return_pct": round((balance - BALANCE)/BALANCE*100, 2),
        "sharpe": round(float(sharpe), 3),
        "max_dd_pct": round(float(dd.min()), 2),
        "profit_factor": round(sum(wins)/(sum(losses)+1e-9), 3),
    }

# ── Signal Builder ────────────────────────────────────────────────────────────

def build_signals(df, ind, range_highs, range_lows,
                  session_h_end, session_h_close,
                  min_range_pips, atr_sl, min_rr, ema_filter):
    PIP = 0.0001
    C = df["Close"].values
    sigs = [None] * len(df)
    for i in range(1, len(df)):
        hour = ind["hours"][i]
        if not (session_h_end <= hour < session_h_close): continue
        day = ind["dates"][i]
        rh = range_highs.get(day); rl = range_lows.get(day)
        if rh is None: continue
        r_pips = (rh - rl) / PIP
        if r_pips < min_range_pips: continue
        atr = ind["atr"][i]
        if atr <= 0: continue
        sl_dist = atr_sl * atr
        price = C[i]; prev_c = C[i-1]
        if ema_filter:
            ema100 = ind["ema100"][i]
        if prev_c <= rh and price > rh:
            if ema_filter and price < ema100: continue
            sigs[i] = ("BUY", price - sl_dist, price + sl_dist * min_rr)
        elif prev_c >= rl and price < rl:
            if ema_filter and price > ema100: continue
            sigs[i] = ("SELL", price + sl_dist, price - sl_dist * min_rr)
    return sigs

# ── Grid Search ───────────────────────────────────────────────────────────────

def grid_search(df, ind, range_highs, range_lows, param_grid, label):
    keys   = list(param_grid.keys())
    combos = list(itertools.product(*[param_grid[k] for k in keys]))
    print(f"\n{'─'*65}")
    print(f"  {label} — {len(combos)} combos")
    print(f"{'─'*65}")
    best = None; best_score = -999; all_res = []

    for idx, vals in enumerate(combos):
        p = dict(zip(keys, vals))
        sigs = build_signals(df, ind, range_highs, range_lows,
                              p["session_end"], p["session_close"],
                              p["min_range_pips"], p["atr_sl"], p["min_rr"], p["ema_filter"])
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
    return best, sorted(all_res, key=lambda x: -x["score"])[:20]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading GBPUSD H1 data...")
    df = load_data()
    print(f"  {len(df)} candles | {df['datetime'].iloc[0].date()} → {df['datetime'].iloc[-1].date()}")
    ind = precompute(df)
    rh, rl = build_daily_range_table(df, 7, 13)

    # Phase 1 — fine grid around research winner
    best1, top1 = grid_search(
        df, ind, rh, rl,
        {
            "session_end":    [13],
            "session_close":  [15, 16, 17],
            "min_range_pips": [40, 45, 50, 55, 60, 65, 70, 75, 80],
            "atr_sl":         [1.4, 1.6, 1.8, 2.0, 2.2, 2.5],
            "min_rr":         [2.5, 3.0, 3.5, 4.0],
            "ema_filter":     [False],
        },
        "Phase1_Core",
    )

    # Phase 2 — add EMA filter around champion
    if best1:
        bp = best1["params"]
        best2, top2 = grid_search(
            df, ind, rh, rl,
            {
                "session_end":    [bp["session_end"]],
                "session_close":  [bp["session_close"]],
                "min_range_pips": [max(30, bp["min_range_pips"]-10),
                                   bp["min_range_pips"],
                                   bp["min_range_pips"]+10],
                "atr_sl":         [bp["atr_sl"] - 0.2, bp["atr_sl"], bp["atr_sl"] + 0.2],
                "min_rr":         [bp["min_rr"]],
                "ema_filter":     [False, True],
            },
            "Phase2_Filters",
        )
    else:
        best2, top2 = None, []

    # Summary
    print(f"\n{'═'*65}")
    print("  GBPUSD FINE-TUNE — FINAL RESULTS")
    print(f"{'═'*65}")
    ACCEPT = dict(sharpe=0.8, return_pct=15.0, max_dd_pct=-15.0, profit_factor=1.4, trades=40)
    champion = None; champ_score = -999

    for label, b in [("Phase1", best1), ("Phase2_Filters", best2)]:
        if b is None: continue
        ok = (b["sharpe"] >= ACCEPT["sharpe"] and b["return_pct"] >= ACCEPT["return_pct"] and
              b["max_dd_pct"] >= ACCEPT["max_dd_pct"] and b["profit_factor"] >= ACCEPT["profit_factor"] and
              b["trades"] >= ACCEPT["trades"])
        flag = "✅" if ok else "⚠️"
        print(f"  {flag} {label:20s}: Sharpe={b['sharpe']:.3f} Ret={b['return_pct']:.1f}% "
              f"DD={b['max_dd_pct']:.1f}% PF={b['profit_factor']:.2f} T={b['trades']}")
        print(f"       Params: {b['params']}")
        if ok and b["score"] > champ_score:
            champion = b; champ_score = b["score"]

    if champion:
        print(f"\n  🏆 CHAMPION:")
        print(f"     Sharpe : {champion['sharpe']}")
        print(f"     Return : {champion['return_pct']}%")
        print(f"     Max DD : {champion['max_dd_pct']}%")
        print(f"     PF     : {champion['profit_factor']}")
        print(f"     Trades : {champion['trades']}")
        print(f"     Params : {champion['params']}")

    os.makedirs("journal", exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump({"phase1_best": best1, "phase1_top20": top1,
                   "phase2_best": best2, "phase2_top20": top2},
                  f, indent=2, default=str)
    print(f"\n  Results saved → {RESULTS_FILE}")

if __name__ == "__main__":
    main()
