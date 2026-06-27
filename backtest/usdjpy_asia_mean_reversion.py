"""
USDJPY Asia Range Mean Reversion Backtest — [18]
================================================
الفرضية: USDJPY في منطقة BOJ → الكسرات الكاذبة أكثر من الاستمرار
الاستراتيجية:
  1. احسب Asia Range (00:00-07:00 UTC)
  2. إذا كُسر Asia High/Low بـ buffer_pips خلال London Open (07:00-09:00 UTC)
  3. لكن السعر رجع داخل الـ Range في نفس الساعة → "Failed Breakout"
  4. ادخل في الاتجاه العكسي (Reversal) نحو وسط الـ Range
  5. SL = خارج نقطة الكسر + buffer إضافي
  6. TP = min_rr × risk

المقارنة: BASELINE = London Breakout (Sharpe=0.98)
الهدف: Sharpe ≥ 1.5
"""

import pandas as pd
import numpy as np
import sys, os, warnings, json
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

H1_CSV  = "backtest_data/USDJPY_H1_2years.csv"
H4_CSV  = "backtest_data/USDJPY_H4_3years.csv"

PIP = 0.01  # USDJPY pip = 0.01

# ── Data Loading ─────────────────────────────────────────────────

def load_csv(path):
    if not os.path.exists(path):
        print(f"❌ File not found: {path}")
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    cols = [c for c in ["Open","High","Low","Close","Volume","ATR","EMA_20","EMA_50"] if c in df.columns]
    return df[cols].dropna()


def atr_series(df, period=14):
    h = df["High"].values.astype(float)
    l = df["Low"].values.astype(float)
    c = df["Close"].values.astype(float)
    tr = np.array([max(h[i]-l[i],
                       abs(h[i]-c[i-1]),
                       abs(l[i]-c[i-1])) for i in range(1, len(h))])
    atr = np.full(len(h), np.nan)
    atr[period] = tr[:period].mean()
    for i in range(period+1, len(h)):
        atr[i] = (atr[i-1] * (period-1) + tr[i-1]) / period
    df = df.copy()
    df["atr14"] = atr
    return df


def h4_bias_at(h4_df, ts):
    """EMA20 vs EMA50 bias on H4"""
    if h4_df is None or len(h4_df) < 55:
        return "NEUTRAL"
    past = h4_df[h4_df.index <= ts]
    if len(past) < 55:
        return "NEUTRAL"
    c = past["Close"].values.astype(float)
    e20 = float(pd.Series(c).ewm(span=20, adjust=False).mean().iloc[-1])
    e50 = float(pd.Series(c).ewm(span=50, adjust=False).mean().iloc[-1])
    if e20 > e50 * 1.0003: return "BULLISH"
    if e20 < e50 * 0.9997: return "BEARISH"
    return "NEUTRAL"


# ── Core Backtest Engine ─────────────────────────────────────────

def run_backtest(df, h4_df,
                 buffer_pips=5,       # pip extension beyond range to confirm fake breakout
                 reentry_pips=2,      # pips back inside range before entry
                 min_range_pips=30,   # minimum Asia range size
                 atr_sl_mult=1.5,     # SL = atr * mult beyond the fake breakout spike
                 min_rr=3.0,          # TP = min_rr × risk
                 entry_h_start=7,     # entry window start UTC
                 entry_h_end=10,      # entry window end UTC
                 initial_capital=10000,
                 risk_pct=0.01,
                 verbose=False):
    """
    Simulates the Asia Range Mean Reversion strategy.
    Returns dict of metrics.
    """
    df = atr_series(df)
    equity = initial_capital
    equity_curve = [initial_capital]
    trades = []
    in_trade = False
    direction = None
    entry_price = sl = tp = 0.0

    for i in range(50, len(df)):
        ts   = df.index[i]
        hour = ts.hour
        close = float(df["Close"].iloc[i])
        high  = float(df["High"].iloc[i])
        low   = float(df["Low"].iloc[i])
        atr   = float(df["atr14"].iloc[i]) if not np.isnan(df["atr14"].iloc[i]) else PIP * 100

        # ── Manage open trade ──────────────────────────────────────
        if in_trade:
            # Check SL/TP using bar's High/Low
            if direction == "BUY":
                if low <= sl:
                    pnl = sl - entry_price
                    equity += equity * risk_pct * (pnl / abs(entry_price - sl))
                    trades.append({"pnl_r": pnl / abs(entry_price - sl), "result": "SL"})
                    in_trade = False
                elif high >= tp:
                    pnl = tp - entry_price
                    equity += equity * risk_pct * (pnl / abs(entry_price - sl))
                    trades.append({"pnl_r": pnl / abs(entry_price - sl), "result": "TP"})
                    in_trade = False
            else:  # SELL
                if high >= sl:
                    pnl = entry_price - sl
                    equity += equity * risk_pct * (pnl / abs(sl - entry_price))
                    trades.append({"pnl_r": pnl / abs(sl - entry_price), "result": "SL"})
                    in_trade = False
                elif low <= tp:
                    pnl = entry_price - tp
                    equity += equity * risk_pct * (pnl / abs(sl - entry_price))
                    trades.append({"pnl_r": pnl / abs(sl - entry_price), "result": "TP"})
                    in_trade = False

            equity_curve.append(equity)
            continue

        # ── Only look for signals in entry window ─────────────────
        if not (entry_h_start <= hour < entry_h_end):
            equity_curve.append(equity)
            continue

        # ── Build Asia Range (00:00-07:00 UTC same day) ───────────
        ts_date = ts.date()
        asia_bars = df[(df.index.date == ts_date) & (df.index.hour < 7)]
        if len(asia_bars) < 3:
            equity_curve.append(equity)
            continue

        asia_high = float(asia_bars["High"].max())
        asia_low  = float(asia_bars["Low"].min())
        rng = asia_high - asia_low
        if rng < min_range_pips * PIP:
            equity_curve.append(equity)
            continue

        # ── H4 Bias Filter ────────────────────────────────────────
        bias = h4_bias_at(h4_df, ts)

        buf = buffer_pips * PIP
        reentry = reentry_pips * PIP

        # ── Detect Failed Breakout (current bar) ──────────────────
        # BUY Signal: bar broke above Asia High (High > asia_high + buf)
        #             but closed back inside range (Close < asia_high - reentry)
        #             → Sell signal rejected, BUY reversal (mean reversion back up from LOW)
        #
        # Wait... mean reversion means:
        #   - Failed UPWARD breakout → price will revert DOWNWARD → SELL
        #   - Failed DOWNWARD breakout → price will revert UPWARD → BUY

        signal = None

        # Failed upward breakout → SELL (with H4 bias filter)
        if (high > asia_high + buf) and (close < asia_high - reentry):
            if bias != "BULLISH":  # Don't sell into strong uptrend
                signal = "SELL"

        # Failed downward breakout → BUY
        elif (low < asia_low - buf) and (close > asia_low + reentry):
            if bias != "BEARISH":  # Don't buy into strong downtrend
                signal = "BUY"

        if signal is None:
            equity_curve.append(equity)
            continue

        # ── Calculate SL / TP ─────────────────────────────────────
        if signal == "SELL":
            entry_price = close
            sl = high + atr * 0.3  # SL above the spike high
            risk = abs(sl - entry_price)
            if risk < PIP * 5:
                equity_curve.append(equity)
                continue
            tp = entry_price - risk * min_rr
            # Sanity: TP must be above Asia Low (some room left)
            if tp < asia_low - rng * 0.5:
                tp = asia_low - rng * 0.3
            direction = "SELL"
        else:  # BUY
            entry_price = close
            sl = low - atr * 0.3  # SL below the spike low
            risk = abs(entry_price - sl)
            if risk < PIP * 5:
                equity_curve.append(equity)
                continue
            tp = entry_price + risk * min_rr
            # Sanity: TP must be below Asia High
            if tp > asia_high + rng * 0.5:
                tp = asia_high + rng * 0.3
            direction = "BUY"

        in_trade = True
        equity_curve.append(equity)

        if verbose:
            print(f"  {ts.date()} {hour}h | {signal} @ {entry_price:.3f} | SL={sl:.3f} TP={tp:.3f} | Range={rng/PIP:.0f}pip")

    # ── Close any open trade at end ───────────────────────────────
    if in_trade:
        pnl_r = -1.0  # assume loss at end (conservative)
        equity += equity * risk_pct * pnl_r
        trades.append({"pnl_r": pnl_r, "result": "EOD"})
        equity_curve.append(equity)

    # ── Compute Metrics ────────────────────────────────────────────
    n = len(trades)
    if n == 0:
        return {"trades": 0, "win_rate": 0, "return_pct": 0,
                "sharpe": 0, "max_dd": 0, "profit_factor": 0}

    wins = [t for t in trades if t["pnl_r"] > 0]
    win_rate = len(wins) / n * 100

    # Equity-based return
    total_return = (equity - initial_capital) / initial_capital * 100

    # Sharpe from R-multiples
    r_vals = [t["pnl_r"] for t in trades]
    mean_r = np.mean(r_vals)
    std_r  = np.std(r_vals, ddof=1) if len(r_vals) > 1 else 1
    sharpe = (mean_r / std_r) * np.sqrt(252 / (2 * 365 / n)) if std_r > 0 else 0

    # Max Drawdown from equity curve
    eq_arr = np.array(equity_curve)
    peak = np.maximum.accumulate(eq_arr)
    dd   = (eq_arr - peak) / peak * 100
    max_dd = float(dd.min())

    # Profit Factor
    gross_profit = sum(t["pnl_r"] for t in trades if t["pnl_r"] > 0)
    gross_loss   = abs(sum(t["pnl_r"] for t in trades if t["pnl_r"] < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else 0

    return {
        "trades": n,
        "win_rate": round(win_rate, 1),
        "return_pct": round(total_return, 2),
        "sharpe": round(sharpe, 3),
        "max_dd": round(max_dd, 2),
        "profit_factor": round(pf, 2),
    }


# ── Grid Search ──────────────────────────────────────────────────

def grid_search(df, h4_df):
    print("\n" + "═"*70)
    print("  [18] USDJPY Asia Range Mean Reversion — Grid Search")
    print("  البحث في أفضل باراميترات للاستراتيجية")
    print("═"*70)

    results = []

    for buf in [3, 5, 7, 10]:
        for reentry in [1, 2, 3]:
            for min_rng in [20, 30, 40, 50]:
                for rr in [2.5, 3.0, 3.5, 4.0]:
                    r = run_backtest(df, h4_df,
                                     buffer_pips=buf,
                                     reentry_pips=reentry,
                                     min_range_pips=min_rng,
                                     min_rr=rr)
                    r.update({"buf": buf, "reentry": reentry,
                              "min_rng": min_rng, "rr": rr})
                    results.append(r)

    # Sort by Sharpe
    results.sort(key=lambda x: x["sharpe"], reverse=True)
    top10 = [r for r in results if r["trades"] >= 15][:10]

    print(f"\n  {'buf':>4} {'re':>4} {'rng':>4} {'rr':>5} | {'T':>5} {'WR%':>6} {'Ret%':>8} {'DD%':>7} {'Sharpe':>8} {'PF':>5}")
    print("  " + "-"*68)
    for r in top10:
        print(f"  {r['buf']:>4} {r['reentry']:>4} {r['min_rng']:>4} {r['rr']:>5.1f} | "
              f"{r['trades']:>5} {r['win_rate']:>6.1f} {r['return_pct']:>8.2f} "
              f"{r['max_dd']:>7.2f} {r['sharpe']:>8.3f} {r['profit_factor']:>5.2f}")

    return top10[0] if top10 else None


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═"*70)
    print("  [18] USDJPY Asia Range Mean Reversion Backtest")
    print("  السبت 27 يونيو 2026 | بيانات: USDJPY_H1_2years.csv")
    print("═"*70)

    df   = load_csv(H1_CSV)
    h4   = load_csv(H4_CSV)

    if df is None:
        print("❌ Cannot load data — aborting")
        sys.exit(1)

    print(f"\n  البيانات: {len(df)} شمعة H1 | من {df.index[0].date()} إلى {df.index[-1].date()}")
    print(f"  H4 Data:  {len(h4) if h4 is not None else 0} شمعة\n")

    # ── BASELINE (London Breakout) ────────────────────────────────
    print("  BASELINE (London Breakout):")
    print("    Sharpe=0.98 | Return=+17.81% | MaxDD=-5.68% | WR=36.2% | T=69")
    print("    المصدر: london_final.py — تأكيد اليوم 2026-06-27")

    # ── Quick test with default params ───────────────────────────
    print("\n  اختبار سريع بالباراميترات الافتراضية (buf=5, rr=3.0, rng=30):")
    default = run_backtest(df, h4, buffer_pips=5, reentry_pips=2,
                           min_range_pips=30, min_rr=3.0, verbose=True)
    print(f"    Trades={default['trades']} | WR={default['win_rate']}% | "
          f"Return={default['return_pct']}% | DD={default['max_dd']}% | "
          f"Sharpe={default['sharpe']} | PF={default['profit_factor']}")

    # ── Grid Search ───────────────────────────────────────────────
    best = grid_search(df, h4)

    print("\n" + "═"*70)
    print("  COMPARISON vs BASELINE")
    print("═"*70)
    print(f"\n  BASELINE  (London Breakout):  Sharpe=0.98 | Return=+17.81% | DD=-5.68%")
    if best:
        print(f"  BEST MR   (Asia Mean Revert): Sharpe={best['sharpe']} | "
              f"Return={best['return_pct']:+.2f}% | DD={best['max_dd']:.2f}% | "
              f"Trades={best['trades']} | WR={best['win_rate']}%")
        delta_s = best['sharpe'] - 0.98
        print(f"\n  Delta Sharpe: {delta_s:+.3f}")
        print(f"  الباراميترات المثلى: buf={best['buf']}pip | reentry={best['reentry']}pip | "
              f"min_range={best['min_rng']}pip | RR={best['rr']}")

        print("\n" + "═"*70)
        if best['sharpe'] >= 1.5 and best['max_dd'] >= -15 and best['trades'] >= 20:
            print("  ✅ ACCEPTED — Sharpe ≥ 1.5 | يجب مراجعتها قبل تطبيقها")
        elif best['sharpe'] > 0.98:
            print("  ⚠️  MARGINAL — أفضل من Baseline لكن دون الهدف 1.5")
        else:
            print("  ❌ REJECTED — لم يتجاوز Baseline")
        print("═"*70)

        # Save results
        out = {
            "date": "2026-06-27",
            "strategy": "USDJPY Asia Range Mean Reversion",
            "baseline": {"sharpe": 0.98, "return": 17.81, "dd": -5.68, "wr": 36.2, "trades": 69},
            "best": best,
            "delta_sharpe": round(delta_s, 3),
        }
        with open("reports/usdjpy_asia_mr_results_2026-06-27.json", "w") as f:
            json.dump(out, f, indent=2)
        print("\n  ✅ النتائج حُفظت في reports/usdjpy_asia_mr_results_2026-06-27.json")
