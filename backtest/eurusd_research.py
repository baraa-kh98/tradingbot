"""
EURUSD Strategy Research — 4 approaches on H1 (2 years)
=========================================================
Tests:
  1. ATRChannelBreakout  — N-bar high/low + ADX (same DNA as Gold winner)
  2. NYOpenBreakout      — Pre-NY range (09–13 UTC) breakout at NY open (13–16 UTC)
  3. EMATrendFollow      — EMA20×EMA50 cross + ADX + ATR SL
  4. DailyRangeBreakout  — Previous day high/low + momentum

Acceptance (same bar as Gold):
  Sharpe > 0.5 | Return > 10% | MaxDD < 15% | PF > 1.3 | Trades > 40
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

DATA_FILE = "backtest_data/EURUSD_H1_2years.csv"
RESULTS_FILE = "journal/eurusd_research_results.json"
BALANCE = 10_000
RISK_PCT = 0.01    # 1% per trade
SPREAD = 0.00012   # 1.2 pips EURUSD typical spread

# ── Load Data ────────────────────────────────────────────────────────────────

def load_data():
    df = pd.read_csv(DATA_FILE, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df.columns = [c.strip() for c in df.columns]
    # Normalise column names
    rename = {}
    for c in df.columns:
        cl = c.lower()
        if cl in ("open","o"): rename[c] = "Open"
        elif cl in ("high","h"): rename[c] = "High"
        elif cl in ("low","l"): rename[c] = "Low"
        elif cl in ("close","c"): rename[c] = "Close"
        elif cl == "datetime": rename[c] = "datetime"
    df = df.rename(columns=rename)
    return df

# ── Indicators ────────────────────────────────────────────────────────────────

def calc_atr(df, period=14):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    tr = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(h))]
    tr = np.array([tr[0]] + tr)
    atr = pd.Series(tr).rolling(period).mean().values
    return atr

def calc_adx(df, period=14):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    adx_out = np.zeros(len(h))
    if len(h) < period + 2:
        return adx_out
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
    dx_s = smma(dx, period)
    adx_out[1:] = smma(dx, period)
    return adx_out

def calc_ema(series, span):
    return pd.Series(series).ewm(span=span, adjust=False).mean().values

# ── Backtest Engine ───────────────────────────────────────────────────────────

def run_backtest(signals_fn, df):
    """
    signals_fn(i, df, indicators) → ('BUY'|'SELL', sl, tp) or None
    Returns metrics dict.
    """
    balance = BALANCE
    equity_curve = [balance]
    trades = []
    in_trade = False
    direction = None
    entry = sl = tp = 0.0

    indicators = precompute(df)

    for i in range(50, len(df)):
        c = df["Close"].values[i]

        if in_trade:
            if direction == "BUY":
                if df["Low"].values[i] <= sl:
                    pnl = (sl - entry - SPREAD) / entry
                    balance *= (1 + pnl * RISK_PCT / ((entry - sl) / entry))
                    trades.append(pnl)
                    in_trade = False
                elif df["High"].values[i] >= tp:
                    pnl = (tp - entry - SPREAD) / entry
                    balance *= (1 + pnl * RISK_PCT / ((entry - sl) / entry))
                    trades.append(pnl)
                    in_trade = False
            else:  # SELL
                if df["High"].values[i] >= sl:
                    pnl = (entry - sl - SPREAD) / entry
                    balance *= (1 + pnl * RISK_PCT / ((sl - entry) / entry))
                    trades.append(pnl)
                    in_trade = False
                elif df["Low"].values[i] <= tp:
                    pnl = (entry - tp - SPREAD) / entry
                    balance *= (1 + pnl * RISK_PCT / ((sl - entry) / entry))
                    trades.append(pnl)
                    in_trade = False
            equity_curve.append(balance)
            continue

        sig = signals_fn(i, df, indicators)
        if sig:
            direction, sl, tp = sig
            entry = c + SPREAD if direction == "BUY" else c - SPREAD
            in_trade = True
        equity_curve.append(balance)

    if not trades:
        return None

    eq = np.array(equity_curve)
    returns = np.diff(eq) / eq[:-1]
    sharpe = (returns.mean() / (returns.std() + 1e-9)) * np.sqrt(8760)  # hourly → annual
    roll_max = np.maximum.accumulate(eq)
    dd = (eq - roll_max) / (roll_max + 1e-9) * 100
    max_dd = float(dd.min())
    wins = [t for t in trades if t > 0]
    losses = [abs(t) for t in trades if t < 0]
    pf = sum(wins) / (sum(losses) + 1e-9)
    total_ret = (balance - BALANCE) / BALANCE * 100

    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(trades) * 100,
        "return_pct": round(total_ret, 2),
        "sharpe": round(float(sharpe), 3),
        "max_dd_pct": round(max_dd, 2),
        "profit_factor": round(pf, 3),
    }

def precompute(df):
    return {
        "atr":  calc_atr(df, 14),
        "adx":  calc_adx(df, 14),
        "ema20": calc_ema(df["Close"].values, 20),
        "ema50": calc_ema(df["Close"].values, 50),
    }

# ── Strategy 1: ATR Channel Breakout ─────────────────────────────────────────

def make_atr_breakout(nbar, adx_min, atr_sl, min_rr):
    def signals(i, df, ind):
        if i < nbar + 20: return None
        adx = ind["adx"][i]
        atr = ind["atr"][i]
        if adx < adx_min or atr <= 0: return None

        ch_high = float(np.max(df["High"].values[i-nbar:i]))
        ch_low  = float(np.min(df["Low"].values[i-nbar:i]))
        price   = df["Close"].values[i]
        prev_c  = df["Close"].values[i-1]
        sl_dist = atr_sl * atr

        if prev_c <= ch_high and price > ch_high:
            sl = price - sl_dist
            tp = price + sl_dist * min_rr
            return ("BUY", sl, tp)

        if prev_c >= ch_low and price < ch_low:
            sl = price + sl_dist
            tp = price - sl_dist * min_rr
            return ("SELL", sl, tp)
        return None
    return signals

# ── Strategy 2: NY Open Breakout ──────────────────────────────────────────────

def make_ny_breakout(range_hours, min_range_pips, atr_sl, min_rr):
    """Range window: 09:00–13:00 UTC. Breakout: 13:00–16:00 UTC."""
    def signals(i, df, ind):
        if i < 30: return None
        dt   = df["datetime"].iloc[i]
        hour = dt.hour
        if not (13 <= hour < 16): return None

        # Build pre-NY range (09:00–13:00 same day)
        day_mask = (df["datetime"] >= dt.replace(hour=9, minute=0, second=0)) & \
                   (df["datetime"] < dt.replace(hour=13, minute=0, second=0))
        pre = df[day_mask]
        if len(pre) < 2: return None

        r_high = float(pre["High"].max())
        r_low  = float(pre["Low"].min())
        r_size = (r_high - r_low) / 0.0001  # in pips

        if r_size < min_range_pips: return None

        price  = df["Close"].values[i]
        prev_c = df["Close"].values[i-1]
        atr    = ind["atr"][i]
        sl_dist = atr_sl * atr

        if prev_c <= r_high and price > r_high:
            sl = price - sl_dist
            tp = price + sl_dist * min_rr
            return ("BUY", sl, tp)

        if prev_c >= r_low and price < r_low:
            sl = price + sl_dist
            tp = price - sl_dist * min_rr
            return ("SELL", sl, tp)
        return None
    return signals

# ── Strategy 3: EMA Trend Follow ─────────────────────────────────────────────

def make_ema_trend(adx_min, atr_sl, min_rr):
    prev_cross = [None]
    def signals(i, df, ind):
        if i < 55: return None
        e20 = ind["ema20"][i]; e50 = ind["ema50"][i]
        pe20 = ind["ema20"][i-1]; pe50 = ind["ema50"][i-1]
        adx  = ind["adx"][i]
        atr  = ind["atr"][i]

        if adx < adx_min or atr <= 0: return None

        price = df["Close"].values[i]
        sl_dist = atr_sl * atr

        # Golden cross — bullish
        if pe20 <= pe50 and e20 > e50:
            sl = price - sl_dist
            tp = price + sl_dist * min_rr
            return ("BUY", sl, tp)

        # Death cross — bearish
        if pe20 >= pe50 and e20 < e50:
            sl = price + sl_dist
            tp = price - sl_dist * min_rr
            return ("SELL", sl, tp)
        return None
    return signals

# ── Strategy 4: Daily Range Breakout ─────────────────────────────────────────

def make_daily_breakout(lookback_days, atr_sl, min_rr, session_start=13):
    """Breakout of previous N days' consolidated high/low. Enter during session_start hour."""
    def signals(i, df, ind):
        if i < lookback_days * 24 + 20: return None
        dt   = df["datetime"].iloc[i]
        hour = dt.hour
        if not (session_start <= hour < session_start + 3): return None

        # Previous day range
        prev_day_end = dt.replace(hour=0, minute=0, second=0)
        prev_day_start = prev_day_end - pd.Timedelta(days=lookback_days)
        mask = (df["datetime"] >= prev_day_start) & (df["datetime"] < prev_day_end)
        prev = df[mask]
        if len(prev) < 8: return None

        r_high = float(prev["High"].max())
        r_low  = float(prev["Low"].min())

        price  = df["Close"].values[i]
        prev_c = df["Close"].values[i-1]
        atr    = ind["atr"][i]
        adx    = ind["adx"][i]
        sl_dist = atr_sl * atr

        if adx < 20: return None

        if prev_c <= r_high and price > r_high:
            sl = price - sl_dist
            tp = price + sl_dist * min_rr
            return ("BUY", sl, tp)

        if prev_c >= r_low and price < r_low:
            sl = price + sl_dist
            tp = price - sl_dist * min_rr
            return ("SELL", sl, tp)
        return None
    return signals

# ── Grid Search ───────────────────────────────────────────────────────────────

def grid_search(strategy_name, make_fn, param_grid, df):
    best = None
    best_score = -999
    results = []

    keys = list(param_grid.keys())
    import itertools
    combos = list(itertools.product(*[param_grid[k] for k in keys]))
    print(f"\n{'─'*60}")
    print(f"  {strategy_name} — {len(combos)} combos")
    print(f"{'─'*60}")

    for idx, vals in enumerate(combos):
        params = dict(zip(keys, vals))
        fn = make_fn(**params)
        try:
            r = run_backtest(fn, df)
        except Exception as e:
            continue
        if r is None: continue

        # Score = Sharpe × log(trades) — reward both quality and quantity
        score = r["sharpe"] * np.log(max(r["trades"], 1))
        r["params"] = params
        r["score"] = round(score, 4)
        results.append(r)

        if score > best_score:
            best_score = score
            best = r
            print(f"  ✓ New best [{idx+1}/{len(combos)}]: {params} → "
                  f"Sharpe={r['sharpe']:.3f} Ret={r['return_pct']:.1f}% "
                  f"DD={r['max_dd_pct']:.1f}% T={r['trades']}")

    return best, sorted(results, key=lambda x: -x["score"])[:10]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading EURUSD H1 data...")
    df = load_data()
    print(f"  {len(df)} candles | {df['datetime'].iloc[0].date()} → {df['datetime'].iloc[-1].date()}")

    all_results = {}

    # ── 1. ATR Channel Breakout ───────────────────────────────────
    best1, top1 = grid_search(
        "ATRChannelBreakout",
        make_atr_breakout,
        {
            "nbar":    [15, 20, 30, 40, 50],
            "adx_min": [20, 25, 30],
            "atr_sl":  [1.2, 1.5, 2.0],
            "min_rr":  [2.0, 2.5, 3.0],
        },
        df,
    )
    all_results["ATRChannelBreakout"] = {"best": best1, "top10": top1}

    # ── 2. NY Open Breakout ───────────────────────────────────────
    best2, top2 = grid_search(
        "NYOpenBreakout",
        make_ny_breakout,
        {
            "range_hours":     [4],   # fixed 09–13 UTC window
            "min_range_pips":  [15, 25, 40],
            "atr_sl":          [1.2, 1.5, 2.0],
            "min_rr":          [2.0, 2.5, 3.0],
        },
        df,
    )
    all_results["NYOpenBreakout"] = {"best": best2, "top10": top2}

    # ── 3. EMA Trend Follow ───────────────────────────────────────
    best3, top3 = grid_search(
        "EMATrendFollow",
        make_ema_trend,
        {
            "adx_min": [20, 25, 30],
            "atr_sl":  [1.5, 2.0, 2.5],
            "min_rr":  [2.0, 2.5, 3.0],
        },
        df,
    )
    all_results["EMATrendFollow"] = {"best": best3, "top10": top3}

    # ── 4. Daily Range Breakout ───────────────────────────────────
    best4, top4 = grid_search(
        "DailyRangeBreakout",
        make_daily_breakout,
        {
            "lookback_days":  [1, 2, 3],
            "atr_sl":         [1.2, 1.5, 2.0],
            "min_rr":         [2.0, 2.5, 3.0],
            "session_start":  [7, 13],
        },
        df,
    )
    all_results["DailyRangeBreakout"] = {"best": best4, "top10": top4}

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print("  EURUSD STRATEGY RESEARCH — SUMMARY")
    print(f"{'═'*60}")
    ACCEPT = {"sharpe": 0.5, "return_pct": 10.0, "max_dd_pct": -15.0, "profit_factor": 1.3, "trades": 40}

    winner = None
    winner_score = -999

    for name, data in all_results.items():
        b = data["best"]
        if b is None:
            print(f"  {name:25s} → NO RESULTS")
            continue
        passed = (
            b["sharpe"]        >= ACCEPT["sharpe"]     and
            b["return_pct"]    >= ACCEPT["return_pct"] and
            b["max_dd_pct"]    >= ACCEPT["max_dd_pct"] and
            b["profit_factor"] >= ACCEPT["profit_factor"] and
            b["trades"]        >= ACCEPT["trades"]
        )
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name:25s} → Sharpe={b['sharpe']:6.3f} Ret={b['return_pct']:6.1f}% "
              f"DD={b['max_dd_pct']:6.1f}% PF={b['profit_factor']:.2f} T={b['trades']:3d}  {status}")
        if passed and b["score"] > winner_score:
            winner = name
            winner_score = b["score"]

    if winner:
        print(f"\n  🏆 WINNER: {winner}")
        print(f"     Params: {all_results[winner]['best']['params']}")
    else:
        # Pick best by Sharpe even if not passing
        ranked = [(n, d["best"]) for n, d in all_results.items() if d["best"]]
        ranked.sort(key=lambda x: -x[1]["sharpe"])
        print(f"\n  ⚠️  No strategy passed all criteria.")
        print(f"     Best by Sharpe: {ranked[0][0]} → {ranked[0][1]['sharpe']:.3f}")

    # Save results
    os.makedirs("journal", exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Results saved → {RESULTS_FILE}")

if __name__ == "__main__":
    main()
