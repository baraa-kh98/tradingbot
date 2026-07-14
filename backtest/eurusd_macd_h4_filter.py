"""
EURUSD H4 MACD Filter Backtest — [H] Proposal (2026-07-13)
============================================================
Hypothesis: Add H4 MACD(12,26,9) directional filter to NY Breakout.
  - No BUY  when H4 MACD Line < Signal Line (Bearish H4 momentum)
  - No SELL when H4 MACD Line > Signal Line (Bullish H4 momentum)

Baseline (current live):
  Sharpe=1.602 | Return=+53.59% | Max DD=-11.81% | WR=31.5% | 124 trades
  (EURUSD NY Breakout: range 07-13 UTC, min_range=25 pip, atr_sl=1.8, min_rr=3.5)

Inspired by [G] GBPUSD H4 RSI Filter (2026-07-05):
  Sharpe 1.273 → 1.664 (+0.391) via H4 momentum filter
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

# EURUSD live params
RANGE_START = 7
RANGE_END   = 13
SESSION_END = 15
MIN_RANGE_PIPS = 25
ATR_SL = 1.8
MIN_RR = 3.5
PIP    = 0.0001

# MACD params
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9


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
    df = df.rename(columns=rename)
    return df


def calc_atr(df, period=14):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    tr = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(h))]
    tr = np.array([tr[0]] + tr)
    return pd.Series(tr).rolling(period).mean().values


def calc_macd(close_series, fast=12, slow=26, signal=9):
    close = pd.Series(close_series)
    ema_fast   = close.ewm(span=fast,   adjust=False).mean()
    ema_slow   = close.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line.values, signal_line.values


def build_h4_macd(df_h1):
    """Resample H1 to H4 and compute MACD. Returns Series indexed by H1 bar idx."""
    df = df_h1.copy()
    df = df.set_index("datetime")
    h4 = df["Close"].resample("4h").last().dropna()
    macd_line, signal_line = calc_macd(h4.values, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    h4_df = pd.DataFrame({
        "macd":   macd_line,
        "signal": signal_line
    }, index=h4.index)
    # For each H1 bar, find the most recent completed H4 bar (use_h4_at_time)
    # We use searchsorted to map each H1 timestamp → latest completed H4 bar
    h4_times = h4_df.index
    h1_times = df_h1["datetime"].values

    macd_at_h1   = np.full(len(h1_times), np.nan)
    signal_at_h1 = np.full(len(h1_times), np.nan)

    for i, t in enumerate(pd.DatetimeIndex(h1_times)):
        # Latest H4 bar that closed BEFORE this H1 bar
        idx = h4_times.searchsorted(t, side="right") - 1
        if idx >= MACD_SLOW + MACD_SIGNAL:  # enough history for MACD
            macd_at_h1[i]   = h4_df["macd"].iloc[idx]
            signal_at_h1[i] = h4_df["signal"].iloc[idx]

    return macd_at_h1, signal_at_h1


def run_backtest(df, atr_vals, macd_arr, signal_arr, use_macd_filter=True):
    balance  = BALANCE
    equity   = [balance]
    trades   = []
    in_trade = False
    direction = None
    entry = sl = tp = 0.0

    range_table_high = {}
    range_table_low  = {}

    H = df["High"].values
    L = df["Low"].values
    C = df["Close"].values

    for i in range(60, len(df)):
        dt   = df["datetime"].iloc[i]
        hour = dt.hour
        date = dt.normalize()

        # ── manage open trade ──────────────────────────────────────
        if in_trade:
            if direction == "BUY":
                if L[i] <= sl:
                    risk = max(entry - sl, 1e-9)
                    pnl_pts = sl - entry - SPREAD
                    balance += (pnl_pts / risk) * balance * RISK_PCT
                    trades.append(pnl_pts)
                    in_trade = False
                elif H[i] >= tp:
                    risk = max(entry - sl, 1e-9)
                    pnl_pts = tp - entry - SPREAD
                    balance += (pnl_pts / risk) * balance * RISK_PCT
                    trades.append(pnl_pts)
                    in_trade = False
            else:
                if H[i] >= sl:
                    risk = max(sl - entry, 1e-9)
                    pnl_pts = entry - sl - SPREAD
                    balance += (pnl_pts / risk) * balance * RISK_PCT
                    trades.append(pnl_pts)
                    in_trade = False
                elif L[i] <= tp:
                    risk = max(sl - entry, 1e-9)
                    pnl_pts = entry - tp - SPREAD
                    balance += (pnl_pts / risk) * balance * RISK_PCT
                    trades.append(pnl_pts)
                    in_trade = False
            equity.append(balance)
            continue

        # ── build range (London session) ──────────────────────────
        if RANGE_START <= hour < RANGE_END:
            if date not in range_table_high:
                range_table_high[date] = H[i]
                range_table_low[date]  = L[i]
            else:
                range_table_high[date] = max(range_table_high[date], H[i])
                range_table_low[date]  = min(range_table_low[date],  L[i])
            equity.append(balance)
            continue

        # ── only enter in NY session ───────────────────────────────
        if not (RANGE_END <= hour < SESSION_END):
            equity.append(balance)
            continue

        if in_trade:
            equity.append(balance)
            continue

        rh = range_table_high.get(date)
        rl = range_table_low.get(date)
        if rh is None or rl is None:
            equity.append(balance)
            continue

        range_pips = (rh - rl) / PIP
        if range_pips < MIN_RANGE_PIPS:
            equity.append(balance)
            continue

        atr = atr_vals[i]
        if atr <= 0:
            equity.append(balance)
            continue

        price = C[i]

        # ── MACD H4 filter ────────────────────────────────────────
        if use_macd_filter:
            m = macd_arr[i]
            s = signal_arr[i]
            if np.isnan(m) or np.isnan(s):
                equity.append(balance)
                continue
            h4_bullish = m > s   # MACD above signal → bullish H4
            h4_bearish = m < s   # MACD below signal → bearish H4
        else:
            h4_bullish = True
            h4_bearish = True

        # ── BUY breakout ──────────────────────────────────────────
        if price > rh and h4_bullish:
            entry = price
            sl    = entry - ATR_SL * atr
            risk  = entry - sl
            if risk <= 0:
                equity.append(balance)
                continue
            rr = MIN_RR * risk
            if rr < MIN_RR * risk:
                equity.append(balance)
                continue
            tp = entry + rr
            direction = "BUY"
            in_trade  = True
            equity.append(balance)
            continue

        # ── SELL breakout ─────────────────────────────────────────
        if price < rl and h4_bearish:
            entry = price
            sl    = entry + ATR_SL * atr
            risk  = sl - entry
            if risk <= 0:
                equity.append(balance)
                continue
            tp = entry - MIN_RR * risk
            direction = "SELL"
            in_trade  = True
            equity.append(balance)
            continue

        equity.append(balance)

    return trades, equity, balance


def calc_metrics(trades, equity, balance):
    n = len(trades)
    if n == 0:
        return {"trades": 0, "sharpe": 0, "return_pct": 0,
                "max_dd": 0, "win_rate": 0, "profit_factor": 0}
    wins  = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    win_rate = len(wins) / n * 100

    eq = np.array(equity)
    peak = np.maximum.accumulate(eq)
    dd   = (eq - peak) / (peak + 1e-9)
    max_dd = float(dd.min() * 100)

    ret_pct = (balance - BALANCE) / BALANCE * 100

    # Sharpe (annualized, assuming 252 trading days, 8 bars/day)
    returns = np.diff(eq) / (eq[:-1] + 1e-9)
    if returns.std() > 0:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252 * 8)
    else:
        sharpe = 0.0

    gross_profit = sum(wins) if wins else 0
    gross_loss   = abs(sum(losses)) if losses else 1e-9
    pf = gross_profit / gross_loss

    return {
        "trades": n,
        "sharpe": round(sharpe, 3),
        "return_pct": round(ret_pct, 2),
        "max_dd": round(max_dd, 2),
        "win_rate": round(win_rate, 1),
        "profit_factor": round(pf, 3),
    }


def main():
    print("=" * 60)
    print("EURUSD H4 MACD Filter Backtest — [H] Proposal")
    print("=" * 60)

    df = load_data()
    print(f"Data: {len(df)} H1 bars | {df['datetime'].iloc[0].date()} → {df['datetime'].iloc[-1].date()}")

    atr_vals = calc_atr(df)
    print("Computing H4 MACD...")
    macd_arr, signal_arr = build_h4_macd(df)

    macd_valid = np.sum(~np.isnan(macd_arr))
    print(f"H4 MACD valid bars: {macd_valid}/{len(macd_arr)}")

    # ── Baseline (no filter) ──────────────────────────────────────
    print("\n[1] Baseline — No MACD Filter")
    t0, eq0, b0 = run_backtest(df, atr_vals, macd_arr, signal_arr, use_macd_filter=False)
    m0 = calc_metrics(t0, eq0, b0)
    print(f"    Trades={m0['trades']} | Sharpe={m0['sharpe']} | Return={m0['return_pct']}% | "
          f"MaxDD={m0['max_dd']}% | WR={m0['win_rate']}% | PF={m0['profit_factor']}")

    # ── With MACD Filter ─────────────────────────────────────────
    print("\n[2] With H4 MACD(12,26,9) Filter")
    t1, eq1, b1 = run_backtest(df, atr_vals, macd_arr, signal_arr, use_macd_filter=True)
    m1 = calc_metrics(t1, eq1, b1)
    print(f"    Trades={m1['trades']} | Sharpe={m1['sharpe']} | Return={m1['return_pct']}% | "
          f"MaxDD={m1['max_dd']}% | WR={m1['win_rate']}% | PF={m1['profit_factor']}")

    # ── Verdict ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    sharpe_delta = m1['sharpe'] - m0['sharpe']
    print(f"Sharpe delta: {sharpe_delta:+.3f}")
    if m1['sharpe'] >= m0['sharpe'] and m1['sharpe'] >= 1.5:
        verdict = "✅ ACCEPT — Sharpe improved AND meets target"
    elif m1['sharpe'] >= m0['sharpe']:
        verdict = "✅ MARGINAL — Sharpe improved but below 1.5 target"
    else:
        verdict = "❌ REJECT — Sharpe degraded"
    print(f"Verdict: {verdict}")
    print("=" * 60)

    return m0, m1, verdict


if __name__ == "__main__":
    main()
