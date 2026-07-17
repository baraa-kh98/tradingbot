"""
GBPUSD ADX Filter Backtest — 2026-07-17
=========================================
الفرضية: إضافة ADX(14) filter على قمة H4 RSI filter الموجود
  - مشابه لـ [I] EURUSD ADX_MIN=18 الناجح (Sharpe +0.179)
  - الباراميترات الثابتة (best from finetune): min_range_pips=60, atr_sl=1.8, min_rr=4.0
  - RSI filter موجود بالفعل (RSI_HI=75, RSI_LO=25)
  - نختبر ADX thresholds: 0 (baseline), 15, 18, 20, 22, 25
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

DATA_FILE = "backtest_data/GBPUSD_H1_2years.csv"
BALANCE   = 10_000
RISK_PCT  = 0.01
SPREAD    = 0.00018
PIP       = 0.0001

# ── Best params from finetune (with H4 RSI filter) ────────────────────────────
MIN_RANGE_PIPS = 60
ATR_SL         = 1.8
MIN_RR         = 4.0
RANGE_START    = 7     # London range build start
RANGE_END      = 13    # NY session start
SESSION_CLOSE  = 15    # NY session end
RSI_HI         = 75    # BUY blocked above this
RSI_LO         = 25    # SELL blocked below this
RSI_PERIOD     = 14

# ── Data Loading ──────────────────────────────────────────────────────────────

def load_data():
    df = pd.read_csv(DATA_FILE, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    rename = {}
    for c in df.columns:
        cl = c.lower()
        if cl in ("open","o"):    rename[c] = "Open"
        elif cl in ("high","h"): rename[c] = "High"
        elif cl in ("low","l"):  rename[c] = "Low"
        elif cl in ("close","c"):rename[c] = "Close"
        elif cl == "datetime":   rename[c] = "datetime"
    return df.rename(columns=rename)

# ── Indicators ────────────────────────────────────────────────────────────────

def calc_atr(df, period=14):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    tr = np.array([max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                   for i in range(1, len(h))])
    tr = np.concatenate([[tr[0]], tr])
    return pd.Series(tr).rolling(period).mean().values

def calc_adx(df, period=14):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    adx_out = np.full(len(h), 0.0)
    if len(h) < period + 2:
        return adx_out
    dh  = np.diff(h); dl = -np.diff(l)
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
    dip   = smma(dmp, period) / (atr_s + 1e-9) * 100
    dim   = smma(dmm, period) / (atr_s + 1e-9) * 100
    dx    = np.abs(dip - dim) / (dip + dim + 1e-9) * 100
    dx_s  = smma(dx, period)
    fill_len = min(len(dx_s), len(adx_out) - period)
    adx_out[period:period + fill_len] = dx_s[:fill_len]
    return adx_out

def calc_rsi_h4(close_h1, period=14):
    """Resample H1 → H4 RSI"""
    s = pd.Series(close_h1)
    # resample every 4 rows
    h4_close = s.groupby(np.arange(len(s)) // 4).last().values
    delta = np.diff(h4_close, prepend=h4_close[0])
    gain  = np.where(delta > 0, delta, 0.0)
    loss  = np.where(delta < 0, -delta, 0.0)
    avg_g = pd.Series(gain).rolling(period).mean().values
    avg_l = pd.Series(loss).rolling(period).mean().values
    rs    = avg_g / (avg_l + 1e-9)
    rsi_h4 = 100 - (100 / (1 + rs))
    # map back to H1 length (repeat each H4 value 4 times)
    rsi_h1 = np.repeat(rsi_h4, 4)[:len(close_h1)]
    return rsi_h1

def build_daily_range(df):
    df2 = df.copy()
    df2["_date"] = df2["datetime"].dt.normalize()
    df2["_hour"] = df2["datetime"].dt.hour
    mask = (df2["_hour"] >= RANGE_START) & (df2["_hour"] < RANGE_END)
    grp  = df2[mask].groupby("_date").agg(rh=("High","max"), rl=("Low","min"), cnt=("Close","count"))
    grp  = grp[grp["cnt"] >= 2]
    return grp["rh"].to_dict(), grp["rl"].to_dict()

# ── Backtest Engine ───────────────────────────────────────────────────────────

def run_backtest(df, atr, adx, rsi, range_highs, range_lows, adx_min):
    balance  = BALANCE
    equity   = [balance]
    trades   = []
    in_trade = False
    direction = entry = sl = tp = None
    dates = df["datetime"].dt.normalize().values
    hours = df["datetime"].dt.hour.values
    H = df["High"].values; L = df["Low"].values; C = df["Close"].values

    for i in range(1, len(df)):
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

        hour = hours[i]
        if not (RANGE_END <= hour < SESSION_CLOSE):
            equity.append(balance); continue

        day = dates[i]
        rh = range_highs.get(day); rl = range_lows.get(day)
        if rh is None:
            equity.append(balance); continue

        r_pips = (rh - rl) / PIP
        if r_pips < MIN_RANGE_PIPS:
            equity.append(balance); continue

        atr_val = atr[i]
        adx_val = adx[i]
        rsi_val = rsi[i]
        if atr_val <= 0:
            equity.append(balance); continue

        # ADX filter
        if adx_min > 0 and adx_val < adx_min:
            equity.append(balance); continue

        sl_dist = ATR_SL * atr_val
        price   = C[i]; prev_c = C[i-1]

        if prev_c <= rh and price > rh:
            # RSI filter: block BUY if overbought
            if rsi_val > RSI_HI:
                equity.append(balance); continue
            sl_ = price - sl_dist
            tp_ = price + sl_dist * MIN_RR
            direction = "BUY"; sl = sl_; tp = tp_; entry = price; in_trade = True

        elif prev_c >= rl and price < rl:
            # RSI filter: block SELL if oversold
            if rsi_val < RSI_LO:
                equity.append(balance); continue
            sl_ = price + sl_dist
            tp_ = price - sl_dist * MIN_RR
            direction = "SELL"; sl = sl_; tp = tp_; entry = price; in_trade = True

        equity.append(balance)

    if len(trades) < 5:
        return None

    eq      = np.array(equity)
    returns = np.diff(eq) / (eq[:-1] + 1e-9)
    sharpe  = (returns.mean() / (returns.std() + 1e-9)) * np.sqrt(8760)
    roll_max= np.maximum.accumulate(eq)
    dd      = (eq - roll_max) / (roll_max + 1e-9) * 100
    wins    = [t for t in trades if t > 0]
    losses  = [abs(t) for t in trades if t < 0]
    return {
        "adx_min":      adx_min,
        "trades":       len(trades),
        "win_rate":     round(len(wins)/len(trades)*100, 1),
        "return_pct":   round((balance - BALANCE)/BALANCE*100, 2),
        "sharpe":       round(float(sharpe), 3),
        "max_dd_pct":   round(float(dd.min()), 2),
        "profit_factor":round(sum(wins)/(sum(losses)+1e-9), 3),
    }

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  GBPUSD ADX Filter Backtest — 2026-07-17")
    print("  (على قمة H4 RSI filter المطبَّق 2026-07-05)")
    print("=" * 65)

    print("\nLoading GBPUSD H1 data...")
    df = load_data()
    print(f"  {len(df)} candles | {df['datetime'].iloc[0].date()} → {df['datetime'].iloc[-1].date()}")

    print("Computing indicators...")
    atr = calc_atr(df)
    adx = calc_adx(df)
    rsi = calc_rsi_h4(df["Close"].values)
    rh, rl = build_daily_range(df)

    print(f"\n  Baseline params: range={RANGE_START}-{RANGE_END}h, min_range={MIN_RANGE_PIPS}pips, "
          f"atr_sl={ATR_SL}, min_rr={MIN_RR}, RSI_HI={RSI_HI}/RSI_LO={RSI_LO}")
    print("\n  Testing ADX thresholds: 0 (baseline), 15, 18, 20, 22, 25\n")

    results = []
    for adx_thresh in [0, 15, 18, 20, 22, 25]:
        r = run_backtest(df, atr, adx, rsi, rh, rl, adx_thresh)
        if r:
            label = "BASELINE (no ADX)" if adx_thresh == 0 else f"ADX_MIN={adx_thresh}"
            results.append(r)
            tag = " ⭐" if r["sharpe"] > (results[0]["sharpe"] if len(results) > 1 else 0) else ""
            print(f"  {label:22s}: Sharpe={r['sharpe']:.3f}  Ret={r['return_pct']:+.1f}%  "
                  f"DD={r['max_dd_pct']:.1f}%  WR={r['win_rate']:.1f}%  T={r['trades']}{tag}")

    if len(results) < 2:
        print("\n  ❌ Not enough results for comparison")
        return

    baseline = results[0]
    print(f"\n{'─'*65}")
    print("  COMPARISON vs BASELINE:")
    print(f"{'─'*65}")
    best_improvement = None
    for r in results[1:]:
        delta_sharpe = r["sharpe"] - baseline["sharpe"]
        delta_ret    = r["return_pct"] - baseline["return_pct"]
        delta_dd     = r["max_dd_pct"] - baseline["max_dd_pct"]
        delta_wr     = r["win_rate"] - baseline["win_rate"]
        accept = (delta_sharpe > 0.05 and r["trades"] >= 25 and
                  r["max_dd_pct"] >= -15.0)
        flag = "✅" if accept else "❌"
        print(f"  {flag} ADX_MIN={r['adx_min']:2d}: ΔSharpe={delta_sharpe:+.3f}  ΔRet={delta_ret:+.1f}%  "
              f"ΔDD={delta_dd:+.1f}%  ΔWR={delta_wr:+.1f}%  T={r['trades']}")
        if accept and (best_improvement is None or r["sharpe"] > best_improvement["sharpe"]):
            best_improvement = r

    print(f"\n{'─'*65}")
    if best_improvement:
        print(f"  🏆 BEST: ADX_MIN={best_improvement['adx_min']}")
        print(f"     Sharpe: {baseline['sharpe']:.3f} → {best_improvement['sharpe']:.3f} "
              f"(+{best_improvement['sharpe']-baseline['sharpe']:.3f})")
        print(f"     Return: {baseline['return_pct']:+.1f}% → {best_improvement['return_pct']:+.1f}%")
        print(f"     Max DD: {baseline['max_dd_pct']:.1f}% → {best_improvement['max_dd_pct']:.1f}%")
        print(f"     WR    : {baseline['win_rate']:.1f}% → {best_improvement['win_rate']:.1f}%")
        print(f"     Trades: {baseline['trades']} → {best_improvement['trades']}")
        print(f"\n  ✅ RECOMMENDATION: Apply ADX_MIN={best_improvement['adx_min']} to strategy/gbpusd_signal.py")
    else:
        print("  ❌ No ADX threshold improves GBPUSD enough (ΔSharpe < 0.05 or trades < 25)")
        print("  ⏳ Decision: Do NOT apply ADX filter to GBPUSD at this time")

    print(f"\n{'='*65}")

if __name__ == "__main__":
    main()
