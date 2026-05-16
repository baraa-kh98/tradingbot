"""
Deep Analysis: Does ATR correlate with trade quality for USDJPY London Breakout?
This will help understand WHY Proposal #2 (ATR filter) failed
"""

import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting import Backtest, Strategy
from config import PIP_VALUE

H1_CSV = "backtest_data/USDJPY_H1_2years.csv"
H4_CSV = "backtest_data/USDJPY_H4_3years.csv"


def load_csv(path):
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    cols = [c for c in ["Open","High","Low","Close","Volume","ATR","EMA_20","EMA_50"] if c in df.columns]
    return df[cols].dropna()


class LondonAnalysis(Strategy):
    """Track all potential trade signals with their ATR levels and outcomes"""

    buffer_pips = 3
    min_rr = 3.0
    min_range_pips = 40
    _h4 = None

    def init(self):
        self.signals = []  # Track all signals

    def next(self):
        idx = len(self.data) - 1
        if idx < 20 or self.position:
            return

        ts = self.data.index[-1]
        hour = getattr(ts, "hour", -1)
        if not (7 <= hour < 10):
            return

        # Get Asia range
        ah, al = self._asia_range(idx)
        if ah is None:
            return

        pip = PIP_VALUE
        rng = ah - al
        if rng < self.min_range_pips * pip:
            return

        # Get ATR
        atr = float(self.data.ATR[-1]) if hasattr(self.data, "ATR") else None

        buf = self.buffer_pips * pip
        price = float(self.data.Close[-1])
        bias = self._h4_bias(ts)

        # Check for signal
        signal_type = None
        if price > ah + buf and bias != "BEARISH":
            signal_type = "LONG"
            sl = al
            risk = price - sl
            if risk > 0:
                self.buy(sl=sl, tp=price + risk * self.min_rr)

        elif price < al - buf and bias != "BULLISH":
            signal_type = "SHORT"
            sl = ah
            risk = sl - price
            if risk > 0:
                self.sell(sl=sl, tp=price - risk * self.min_rr)

        # Log signal with ATR
        if signal_type:
            self.signals.append({
                "datetime": ts,
                "type": signal_type,
                "price": price,
                "atr": atr,
                "asia_range": rng,
                "bias": bias
            })

    def _asia_range(self, idx):
        try:
            ts = self.data.index[idx]
            ts_d = getattr(ts, "date", lambda: None)()
            lookback = min(idx, 20)
            highs, lows = [], []
            for k in range(lookback, 0, -1):
                bar = self.data.index[idx - k]
                bh = getattr(bar, "hour", 0)
                bd = getattr(bar, "date", lambda: None)()
                if bd == ts_d and 0 <= bh < 7:
                    highs.append(float(self.data.High[idx - k]))
                    lows.append(float(self.data.Low[idx - k]))
            if len(highs) < 3:
                return None, None
            return max(highs), min(lows)
        except Exception:
            return None, None

    def _h4_bias(self, ts):
        if self._h4 is None or len(self._h4) < 55:
            return "NEUTRAL"
        try:
            past = self._h4[self._h4.index <= ts]
            if len(past) < 55:
                return "NEUTRAL"
            c = past["Close"].values.astype(float)
            e20 = float(pd.Series(c).ewm(span=20, adjust=False).mean().iloc[-1])
            e50 = float(pd.Series(c).ewm(span=50, adjust=False).mean().iloc[-1])
            if e20 > e50 * 1.0003: return "BULLISH"
            if e20 < e50 * 0.9997: return "BEARISH"
            return "NEUTRAL"
        except Exception:
            return "NEUTRAL"


def analyze():
    print("\n" + "="*70)
    print("  🔬 ATR vs Trade Quality Analysis")
    print("  Question: Do high-ATR days produce better trades?")
    print("="*70)

    h1 = load_csv(H1_CSV)
    h4 = load_csv(H4_CSV)
    if h1 is None:
        print("❌ H1 data missing")
        return

    LondonAnalysis._h4 = h4

    # Run backtest to capture signals and outcomes
    bt = Backtest(h1, LondonAnalysis, cash=10_000, commission=0.0002)
    result = bt.run()

    # Extract trades from _trades DataFrame
    if hasattr(result, '_trades') and isinstance(result._trades, pd.DataFrame):
        trades_df = result._trades
    else:
        print("❌ Could not extract trades DataFrame")
        return

    strategy = result._strategy
    signals = strategy.signals

    print(f"\n✅ Captured {len(signals)} signals, {len(trades_df)} executed trades")

    # Match trades to signals
    trade_outcomes = []
    for idx, trade in trades_df.iterrows():
        entry_time = trade.get("EntryTime", trade.name if hasattr(trade, 'name') else None)
        if entry_time is None:
            continue

        entry_time = pd.to_datetime(entry_time, utc=True) if not isinstance(entry_time, pd.Timestamp) else entry_time

        # Find matching signal
        for sig in signals:
            time_diff = abs((sig["datetime"] - entry_time).total_seconds())
            if time_diff < 3600:  # Within 1 hour
                pnl = trade.get("PnL", trade.get("ReturnPct", 0))
                trade_outcomes.append({
                    "datetime": entry_time,
                    "atr": sig["atr"],
                    "type": sig["type"],
                    "pnl": pnl,
                    "return_pct": trade.get("ReturnPct", pnl),
                    "winner": pnl > 0
                })
                break

    df_trades = pd.DataFrame(trade_outcomes)

    if len(df_trades) == 0:
        print("❌ No trades to analyze")
        return

    print(f"\n📊 Matched {len(df_trades)} trades with ATR data")

    # Split by ATR quartiles
    df_trades = df_trades.dropna(subset=["atr"])
    q25 = df_trades["atr"].quantile(0.25)
    q50 = df_trades["atr"].quantile(0.50)
    q75 = df_trades["atr"].quantile(0.75)

    print(f"\n ATR Quartiles:")
    print(f"  Q1: {q25:.3f} | Q2: {q50:.3f} | Q3: {q75:.3f}")

    # Analyze by quartile
    print(f"\n{'='*70}")
    print(f"  {'ATR Range':20s} {'Trades':>7} {'Win%':>7} {'Avg PnL':>10} {'Avg Return%':>12}")
    print(f"  {'-'*68}")

    ranges = [
        ("Q1: Low (< Q25)", df_trades[df_trades["atr"] < q25]),
        ("Q2: Mid-Low (Q25-Q50)", df_trades[(df_trades["atr"] >= q25) & (df_trades["atr"] < q50)]),
        ("Q3: Mid-High (Q50-Q75)", df_trades[(df_trades["atr"] >= q50) & (df_trades["atr"] < q75)]),
        ("Q4: High (> Q75)", df_trades[df_trades["atr"] >= q75]),
    ]

    for label, subset in ranges:
        if len(subset) == 0:
            continue
        win_rate = subset["winner"].mean() * 100
        avg_pnl = subset["pnl"].mean()
        avg_ret = subset["return_pct"].mean()
        count = len(subset)

        print(f"  {label:20s} {count:>7} {win_rate:>7.1f} {avg_pnl:>10.2f} {avg_ret:>12.2f}")

    # Statistical test: correlation between ATR and outcome
    print(f"\n{'='*70}")
    print(f"  📈 Correlation Analysis")
    print(f"{'='*70}")

    corr_atr_pnl = df_trades["atr"].corr(df_trades["pnl"])
    corr_atr_winner = df_trades["atr"].corr(df_trades["winner"].astype(int))

    print(f"  ATR vs PnL:        {corr_atr_pnl:+.3f} {'(positive = high ATR → better PnL)' if corr_atr_pnl > 0 else '(negative = high ATR → worse PnL)'}")
    print(f"  ATR vs Win/Loss:   {corr_atr_winner:+.3f} {'(positive = high ATR → more wins)' if corr_atr_winner > 0 else '(negative = high ATR → more losses)'}")

    # Insight
    print(f"\n{'='*70}")
    print(f"  💡 INSIGHT")
    print(f"{'='*70}")

    if corr_atr_winner < -0.1:
        print(f"  ❌ NEGATIVE correlation: High ATR days produce WORSE trades!")
        print(f"     This explains why ATR filter FAILED in Proposal #2.")
        print(f"     Recommendation: INVERSE filter (trade LOW ATR days) or abandon ATR approach.")
    elif corr_atr_winner > 0.1:
        print(f"  ✅ POSITIVE correlation: High ATR days produce BETTER trades.")
        print(f"     ATR filter should work in theory. Check implementation bugs.")
    else:
        print(f"  ⚠️  WEAK correlation: ATR is NOT predictive of trade quality.")
        print(f"     ATR filter won't improve performance. Need different approach.")

    # Best/worst trades by ATR
    print(f"\n{'='*70}")
    print(f"  🏆 Top 5 Trades by PnL")
    print(f"{'='*70}")
    top5 = df_trades.nlargest(5, "pnl")
    for idx, row in top5.iterrows():
        print(f"  {row['datetime']} | ATR: {row['atr']:.3f} | PnL: ${row['pnl']:.2f} | {row['type']}")

    print(f"\n{'='*70}")
    print(f"  💔 Bottom 5 Trades by PnL")
    print(f"{'='*70}")
    bottom5 = df_trades.nsmallest(5, "pnl")
    for idx, row in bottom5.iterrows():
        print(f"  {row['datetime']} | ATR: {row['atr']:.3f} | PnL: ${row['pnl']:.2f} | {row['type']}")

    print(f"\n{'='*70}\n")

    return df_trades


if __name__ == "__main__":
    analyze()
