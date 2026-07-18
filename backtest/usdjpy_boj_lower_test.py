"""
USDJPY BOJ_LOWER Emergency Test — 2026-07-18
==============================================
الهدف: تحضير خطة طوارئ لاجتماع BOJ 31 يوليو 2026
  - السؤال: إذا رُفعت الفائدة وكُسر 149 → ما الـ BOJ_LOWER الأفضل؟
  - الاستراتيجية الحالية: BOJ_LOWER=149.0 (SELL محظور تحت 149)
  - نختبر: BOJ_LOWER = 147, 148, 149 (الحالي), 150

المنطق:
  - BOJ_LOWER: السعر لازم ≥ هذا المستوى لإنشاء صفقة SELL
  - خفض BOJ_LOWER يسمح بصفقات SELL في منطقة أوسع (أقل تقييداً)
  - رفع BOJ_LOWER يحظر المزيد من صفقات SELL (أكثر تحفظاً)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

DATA_FILE = "backtest_data/USDJPY_H1_2years.csv"
BALANCE   = 10_000
RISK_PCT  = 0.01
SPREAD    = 0.03  # JPY pips (3 pips typical for USDJPY)
PIP       = 0.01  # USDJPY pip = 0.01 (2dp)

# ── Fixed params (from BOJ Filter backtest 2026-07-04) ────────────────────────
BUFFER_PIPS    = 3
MIN_RR         = 3.0
MIN_RANGE_PIPS = 40
BOJ_UPPER      = 151.0  # fixed — only test LOWER
ASIA_START     = 0      # 00:00 UTC
ASIA_END       = 7      # 07:00 UTC
LONDON_START   = 7
LONDON_END     = 10


def load_data():
    df = pd.read_csv(DATA_FILE, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
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
    tr = np.array([max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                   for i in range(1, len(h))])
    tr = np.concatenate([[tr[0]], tr])
    return pd.Series(tr).rolling(period).mean().values


def build_asia_range(df):
    df2 = df.copy()
    df2["_date"] = df2["datetime"].dt.normalize()
    df2["_hour"] = df2["datetime"].dt.hour
    mask = (df2["_hour"] >= ASIA_START) & (df2["_hour"] < ASIA_END)
    grp  = df2[mask].groupby("_date").agg(rh=("High","max"), rl=("Low","min"), cnt=("Close","count"))
    grp  = grp[grp["cnt"] >= 3]
    return grp["rh"].to_dict(), grp["rl"].to_dict()


def run_backtest(df, atr, range_highs, range_lows, boj_lower):
    balance  = BALANCE
    equity   = [balance]
    trades   = []
    in_trade = False
    direction = entry = sl = tp = None
    dates = df["datetime"].dt.normalize().values
    hours = df["datetime"].dt.hour.values
    H = df["High"].values; L = df["Low"].values; C = df["Close"].values
    buf = BUFFER_PIPS * PIP

    for i in range(1, len(df)):
        if in_trade:
            if direction == "BUY":
                if L[i] <= sl:
                    risk = max(entry - sl, 1e-9)
                    pnl  = (sl - entry - SPREAD * PIP) * (balance * RISK_PCT / risk)
                    balance += pnl; trades.append(pnl); in_trade = False
                elif H[i] >= tp:
                    risk = max(entry - sl, 1e-9)
                    pnl  = (tp - entry - SPREAD * PIP) * (balance * RISK_PCT / risk)
                    balance += pnl; trades.append(pnl); in_trade = False
            else:
                if H[i] >= sl:
                    risk = max(sl - entry, 1e-9)
                    pnl  = (entry - sl - SPREAD * PIP) * (balance * RISK_PCT / risk)
                    balance += pnl; trades.append(pnl); in_trade = False
                elif L[i] <= tp:
                    risk = max(sl - entry, 1e-9)
                    pnl  = (entry - tp - SPREAD * PIP) * (balance * RISK_PCT / risk)
                    balance += pnl; trades.append(pnl); in_trade = False
            equity.append(balance); continue

        hour = hours[i]
        if not (LONDON_START <= hour < LONDON_END):
            equity.append(balance); continue

        day = dates[i]
        rh = range_highs.get(day); rl = range_lows.get(day)
        if rh is None:
            equity.append(balance); continue

        r_pips = (rh - rl) / PIP
        if r_pips < MIN_RANGE_PIPS:
            equity.append(balance); continue

        price = C[i]; prev_c = C[i-1]

        # BUY signal
        if prev_c <= rh + buf and price > rh + buf:
            if price <= BOJ_UPPER:  # BOJ_UPPER always 151
                sl_ = rl
                risk = max(price - sl_, 1e-9)
                tp_  = price + risk * MIN_RR
                direction = "BUY"; sl = sl_; tp = tp_; entry = price; in_trade = True

        # SELL signal
        elif prev_c >= rl - buf and price < rl - buf:
            if price >= boj_lower:  # <- the variable we're testing
                sl_ = rh
                risk = max(sl_ - price, 1e-9)
                tp_  = price - risk * MIN_RR
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
        "boj_lower":    boj_lower,
        "trades":       len(trades),
        "win_rate":     round(len(wins)/len(trades)*100, 1),
        "return_pct":   round((balance - BALANCE)/BALANCE*100, 2),
        "sharpe":       round(float(sharpe), 3),
        "max_dd_pct":   round(float(dd.min()), 2),
        "profit_factor":round(sum(wins)/(sum(losses)+1e-9), 3),
    }


def main():
    print("=" * 65)
    print("  USDJPY BOJ_LOWER Emergency Test — 2026-07-18")
    print("  تحضير لاجتماع BOJ 31 يوليو 2026")
    print("  الاستراتيجية الحالية: BOJ_LOWER=149 | BOJ_UPPER=151")
    print("=" * 65)

    print("\nLoading USDJPY H1 data...")
    df = load_data()
    print(f"  {len(df)} candles | {df['datetime'].iloc[0].date()} → {df['datetime'].iloc[-1].date()}")

    # Price distribution
    closes = df["Close"].values
    pct_below_149 = (closes < 149).mean() * 100
    pct_below_148 = (closes < 148).mean() * 100
    pct_below_147 = (closes < 147).mean() * 100
    print(f"\n  📊 توزيع الأسعار:")
    print(f"     % < 149: {pct_below_149:.1f}%  |  % < 148: {pct_below_148:.1f}%  |  % < 147: {pct_below_147:.1f}%")
    print(f"     Min: {closes.min():.2f}  |  Max: {closes.max():.2f}  |  Mean: {closes.mean():.2f}")

    print("\nComputing indicators...")
    atr = calc_atr(df)
    rh, rl = build_asia_range(df)

    thresholds = [145.0, 147.0, 148.0, 149.0, 150.0, 151.0]
    print(f"\n  Testing BOJ_LOWER thresholds: {thresholds}")
    print(f"  (BOJ_UPPER={BOJ_UPPER} ثابت — BUY محظور فوق 151)\n")

    results = []
    for boj_lower in thresholds:
        r = run_backtest(df, atr, rh, rl, boj_lower)
        label = f"BOJ_LOWER={boj_lower:.0f}" if boj_lower != 149.0 else f"BOJ_LOWER={boj_lower:.0f} ← الحالي"
        if r:
            results.append(r)
            print(f"  {label:25s}: Sharpe={r['sharpe']:.3f}  Ret={r['return_pct']:+.1f}%  "
                  f"DD={r['max_dd_pct']:.1f}%  WR={r['win_rate']:.1f}%  T={r['trades']}")
        else:
            print(f"  {label:25s}: ❌ أقل من 5 صفقات")

    current = next((r for r in results if r["boj_lower"] == 149.0), None)
    if not current or len(results) < 2:
        print("\n  ❌ بيانات غير كافية للمقارنة")
        return

    print(f"\n{'─'*65}")
    print("  COMPARISON vs CURRENT (BOJ_LOWER=149):")
    print(f"{'─'*65}")
    for r in results:
        if r["boj_lower"] == 149.0:
            continue
        ds = r["sharpe"] - current["sharpe"]
        dr = r["return_pct"] - current["return_pct"]
        dd = r["max_dd_pct"] - current["max_dd_pct"]
        dw = r["win_rate"] - current["win_rate"]
        flag = "✅" if ds > 0 and r["max_dd_pct"] >= -15.0 else "❌" if ds < -0.1 else "⚖️ "
        print(f"  {flag} BOJ_LOWER={r['boj_lower']:.0f}: ΔSharpe={ds:+.3f}  ΔRet={dr:+.1f}%  "
              f"ΔDD={dd:+.1f}%  ΔWR={dw:+.1f}%  T={r['trades']}")

    print(f"\n{'─'*65}")
    print(f"  الحالي  : Sharpe={current['sharpe']:.3f}  Ret={current['return_pct']:+.1f}%  "
          f"DD={current['max_dd_pct']:.1f}%  WR={current['win_rate']:.1f}%  T={current['trades']}")

    # Recommendation
    better = [r for r in results if r["boj_lower"] != 149.0 and r["sharpe"] > current["sharpe"]
              and r["max_dd_pct"] >= -15.0 and r["trades"] >= 20]
    print(f"\n{'='*65}")
    if better:
        best = max(better, key=lambda x: x["sharpe"])
        print(f"  🏆 إذا كُسر 149 بعد BOJ: افحص BOJ_LOWER={best['boj_lower']:.0f}")
        print(f"     (Sharpe {current['sharpe']:.3f} → {best['sharpe']:.3f}, ΔSharpe={best['sharpe']-current['sharpe']:+.3f})")
    else:
        print(f"  ⚠️  الحالي (BOJ_LOWER=149) هو الأفضل — لا تغيير حتى بعد BOJ")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
