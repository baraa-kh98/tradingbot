"""
XAUUSD Regime Filter Validation — Proposal #3
===============================================
Three-Layer Filter System:
  1. Macro Regime Gate: VIX > 22 OR Real Yield < 1.0%
  2. Stricter ADX: 30 (up from 25)
  3. Peak Liquidity Window: 13:00-16:00 UTC (London/NY overlap)

Goal: Reduce overtrading (336 → 100-150) + Improve Sharpe (1.02 → 1.35-1.50)
"""

import pandas as pd
import numpy as np
import sys, os, json, math, warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting import Backtest, Strategy

# ── Constants ────────────────────────────────────────────────────
H1_CSV = "backtest_data/XAUUSD_H1_2years.csv"
VIX_CSV = "backtest_data/VIX_daily_2years.csv"
REAL_YIELD_CSV = "backtest_data/RealYield_daily_2years.csv"

GOLD_PIP = 0.01
ATR_PERIOD = 14


# ── Data Loading ─────────────────────────────────────────────────

def load_csv(path):
    if not os.path.exists(path):
        print(f"❌ Missing: {path}")
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def merge_regime_data(h1: pd.DataFrame, vix: pd.DataFrame, real_yield: pd.DataFrame) -> pd.DataFrame:
    """Merge VIX and Real Yield into H1 data (forward-fill daily to hourly)"""
    print("\n🔗 Merging regime indicators...")

    # Prepare VIX
    vix = vix[['VIX']].copy()
    vix.index = pd.to_datetime(vix.index, utc=True)

    # Prepare Real Yield
    real_yield = real_yield[['RealYield']].copy()
    real_yield.index = pd.to_datetime(real_yield.index, utc=True)

    # Merge with forward-fill
    h1 = h1.copy()
    h1 = pd.merge_asof(h1.sort_index(), vix.sort_index(),
                       left_index=True, right_index=True, direction='backward')
    h1 = pd.merge_asof(h1.sort_index(), real_yield.sort_index(),
                       left_index=True, right_index=True, direction='backward')

    # Fill any remaining NaNs
    h1['VIX'] = h1['VIX'].ffill()
    h1['RealYield'] = h1['RealYield'].ffill()

    print(f"  ✅ VIX range: {h1['VIX'].min():.2f} - {h1['VIX'].max():.2f}")
    print(f"  ✅ Real Yield range: {h1['RealYield'].min():.2f}% - {h1['RealYield'].max():.2f}%")

    return h1


def safe(v, d=0.0):
    try:
        f = float(v)
        return d if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return d


# ════════════════════════════════════════════════════════════════
# BASE STRATEGY (Current ATR Breakout)
# ════════════════════════════════════════════════════════════════

class _Base(Strategy):
    _h4: pd.DataFrame = None

    def _h4_bias(self, ts) -> str:
        if self._h4 is None or len(self._h4) < 55:
            return "NEUTRAL"
        try:
            past = self._h4[self._h4.index <= ts]
            if len(past) < 55: return "NEUTRAL"
            c = past["Close"].values.astype(float)
            e20 = float(pd.Series(c).ewm(span=20, adjust=False).mean().iloc[-1])
            e50 = float(pd.Series(c).ewm(span=50, adjust=False).mean().iloc[-1])
            if e20 > e50 * 1.0005: return "BULLISH"
            if e20 < e50 * 0.9995: return "BEARISH"
            return "NEUTRAL"
        except Exception:
            return "NEUTRAL"

    def _atr(self, period=ATR_PERIOD) -> float:
        try:
            n = min(len(self.data) - 1, period * 3)
            h = np.array(self.data.High[-n:], dtype=float)
            l = np.array(self.data.Low[-n:], dtype=float)
            c = np.array(self.data.Close[-n:], dtype=float)
            tr = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                  for i in range(1, len(h))]
            return float(np.mean(tr[-period:])) if len(tr) >= period else float(np.mean(tr))
        except Exception:
            return 5.0

    def _adx(self, period=14) -> float:
        try:
            n = min(len(self.data) - 1, period * 4)
            h = np.array(self.data.High[-n:], dtype=float)
            l = np.array(self.data.Low[-n:], dtype=float)
            c = np.array(self.data.Close[-n:], dtype=float)
            if len(h) < period + 2: return 0.0

            dh = np.diff(h); dl = -np.diff(l)
            dm_p = np.where((dh > dl) & (dh > 0), dh, 0.0)
            dm_m = np.where((dl > dh) & (dl > 0), dl, 0.0)
            tr = np.array([max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                           for i in range(1, len(h))])

            def smma(arr, p):
                out = np.zeros(len(arr))
                out[p-1] = arr[:p].mean()
                for i in range(p, len(arr)):
                    out[i] = (out[i-1]*(p-1) + arr[i]) / p
                return out

            atr_s = smma(tr, period)
            dip = smma(dm_p, period) / (atr_s + 1e-9) * 100
            dim = smma(dm_m, period) / (atr_s + 1e-9) * 100
            dx = np.abs(dip - dim) / (dip + dim + 1e-9) * 100
            return float(np.mean(dx[-period:]))
        except Exception:
            return 0.0

    def _swing_low(self, lookback=10) -> float:
        try:
            l = np.array(self.data.Low[-(lookback+1):-1], dtype=float)
            return float(np.min(l))
        except Exception:
            return float(self.data.Low[-1])

    def _swing_high(self, lookback=10) -> float:
        try:
            h = np.array(self.data.High[-(lookback+1):-1], dtype=float)
            return float(np.max(h))
        except Exception:
            return float(self.data.High[-1])


# ════════════════════════════════════════════════════════════════
# BASELINE: Current ATR Breakout (from gold_research.py)
# ════════════════════════════════════════════════════════════════

class GoldATRBreakout_Baseline(_Base):
    """
    Baseline: Current XAUUSD strategy (ATR Channel Breakout)
    - ADX > 25
    - Entry window: 07:00-17:00 (London + NY)
    - N-bar breakout with ATR-based SL
    """
    nbar = 20
    adx_min = 25
    atr_sl = 1.5
    min_rr = 2.5
    entry_start = 7
    entry_end = 17

    def init(self): pass

    def next(self):
        if len(self.data) < self.nbar + 10 or self.position:
            return

        hour = getattr(self.data.index[-1], "hour", 0)
        if not (self.entry_start <= hour < self.entry_end):
            return

        price = float(self.data.Close[-1])
        prev_c = float(self.data.Close[-2])
        atr = self._atr()
        adx = self._adx()

        ch_high = self._swing_high(self.nbar)
        ch_low = self._swing_low(self.nbar)

        if adx < self.adx_min:
            return

        sl_dist = self.atr_sl * atr

        # BUY breakout
        if prev_c <= ch_high and price > ch_high:
            sl = price - sl_dist
            risk = sl_dist
            if risk > 0:
                self.buy(sl=sl, tp=price + risk * self.min_rr)

        # SELL breakout
        elif prev_c >= ch_low and price < ch_low:
            sl = price + sl_dist
            risk = sl_dist
            if risk > 0:
                self.sell(sl=sl, tp=price - risk * self.min_rr)


# ════════════════════════════════════════════════════════════════
# PROPOSAL #3: XAUUSD REGIME FILTER
# ════════════════════════════════════════════════════════════════

class GoldRegimeFilter(_Base):
    """
    XAUUSD Regime Filter — Three-Layer System:

    Layer 1: Macro Regime Gate
      - Only trade when VIX > 22 OR Real Yield < 1.0%
      - Skips range-bound, unfavorable macro conditions

    Layer 2: Stricter ADX
      - ADX > 30 (up from 25)
      - Strong trends only

    Layer 3: Peak Liquidity Window
      - 13:00-16:00 UTC (London/NY overlap)
      - Highest volume, best execution
    """

    # Regime thresholds
    vix_threshold = 22.0
    real_yield_threshold = 1.0

    # Trend filter
    adx_min = 30

    # Entry window (London/NY overlap)
    entry_start = 13
    entry_end = 16

    # ATR breakout params (same as baseline)
    nbar = 20
    atr_sl = 1.5
    min_rr = 2.5

    def init(self): pass

    def _check_gold_regime(self) -> bool:
        """
        Layer 1: Macro Regime Gate
        Returns True if favorable conditions (VIX high OR real yields low)
        """
        try:
            if 'VIX' not in self.data.df.columns or 'RealYield' not in self.data.df.columns:
                return True  # Fallback: allow trade if data missing

            vix = float(self.data.df['VIX'].iloc[-1])
            real_yield = float(self.data.df['RealYield'].iloc[-1])

            # Bullish Gold regime: Risk-off OR low opportunity cost
            return (vix > self.vix_threshold) or (real_yield < self.real_yield_threshold)
        except Exception:
            return True  # Fallback: allow trade

    def next(self):
        if len(self.data) < self.nbar + 10 or self.position:
            return

        # Layer 1: Regime check
        if not self._check_gold_regime():
            return

        # Layer 2: ADX check (stricter)
        adx = self._adx()
        if adx < self.adx_min:
            return

        # Layer 3: Session window (peak liquidity)
        hour = getattr(self.data.index[-1], "hour", 0)
        if not (self.entry_start <= hour < self.entry_end):
            return

        # Same ATR breakout logic as baseline
        price = float(self.data.Close[-1])
        prev_c = float(self.data.Close[-2])
        atr = self._atr()

        ch_high = self._swing_high(self.nbar)
        ch_low = self._swing_low(self.nbar)

        sl_dist = self.atr_sl * atr

        # BUY breakout
        if prev_c <= ch_high and price > ch_high:
            sl = price - sl_dist
            risk = sl_dist
            if risk > 0:
                self.buy(sl=sl, tp=price + risk * self.min_rr)

        # SELL breakout
        elif prev_c >= ch_low and price < ch_low:
            sl = price + sl_dist
            risk = sl_dist
            if risk > 0:
                self.sell(sl=sl, tp=price - risk * self.min_rr)


# ════════════════════════════════════════════════════════════════
# PARAMETER SWEEP (GRID SEARCH)
# ════════════════════════════════════════════════════════════════

def run_grid_search(h1: pd.DataFrame):
    """Test regime filter with different thresholds"""

    param_grid = {
        "vix_threshold": [20, 21, 22, 23, 24],
        "real_yield_threshold": [0.8, 1.0, 1.2],
        "adx_min": [28, 30, 32],
    }

    results = []
    from itertools import product

    combos = list(product(
        param_grid["vix_threshold"],
        param_grid["real_yield_threshold"],
        param_grid["adx_min"]
    ))

    total = len(combos)
    print(f"\n🔍 Grid Search — {total} combinations")
    print(f"{'─'*70}")

    for i, (vix_t, ry_t, adx_t) in enumerate(combos, 1):
        GoldRegimeFilter.vix_threshold = vix_t
        GoldRegimeFilter.real_yield_threshold = ry_t
        GoldRegimeFilter.adx_min = adx_t

        try:
            bt = Backtest(h1, GoldRegimeFilter, cash=10_000,
                         commission=0.0002, finalize_trades=True)
            stats = bt.run()

            trades = int(stats.get("# Trades", 0))
            row = {
                "vix_threshold": vix_t,
                "real_yield_threshold": ry_t,
                "adx_min": adx_t,
                "trades": trades,
                "win_rate": round(safe(stats.get("Win Rate [%]")), 1),
                "return_pct": round(safe(stats.get("Return [%]")), 2),
                "max_dd": round(safe(stats.get("Max. Drawdown [%]")), 2),
                "sharpe": round(safe(stats.get("Sharpe Ratio")), 3),
                "profit_factor": round(safe(stats.get("Profit Factor")), 3),
            }
            results.append(row)

            if i % 5 == 0 or i == total:
                print(f"  [{i:>2}/{total}] VIX={vix_t} RY={ry_t} ADX={adx_t} → "
                      f"T={trades:>3} WR={row['win_rate']:>5.1f}% Sh={row['sharpe']:>5.2f}")

        except Exception as e:
            print(f"  ⚠️ [{i}/{total}] Error: {e}")

    return results


# ════════════════════════════════════════════════════════════════
# MAIN VALIDATION
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "="*70)
    print("  XAUUSD Regime Filter Validation — Proposal #3")
    print("="*70)

    # Load data
    h1 = load_csv(H1_CSV)
    vix = load_csv(VIX_CSV)
    real_yield = load_csv(REAL_YIELD_CSV)

    if h1 is None or vix is None or real_yield is None:
        print("❌ Missing data files")
        sys.exit(1)

    print(f"\n✅ H1: {len(h1)} candles | {h1.index[0].date()} → {h1.index[-1].date()}")
    print(f"✅ VIX: {len(vix)} days")
    print(f"✅ Real Yield: {len(real_yield)} days")

    # Merge regime data
    h1 = merge_regime_data(h1, vix, real_yield)

    # ── BASELINE TEST ────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("  1. BASELINE: Current ATR Breakout (ADX>25, 07:00-17:00)")
    print(f"{'─'*70}")

    bt_baseline = Backtest(h1, GoldATRBreakout_Baseline, cash=10_000,
                          commission=0.0002, finalize_trades=True)
    stats_baseline = bt_baseline.run()

    baseline_metrics = {
        "trades": int(stats_baseline.get("# Trades", 0)),
        "win_rate": safe(stats_baseline.get("Win Rate [%]")),
        "return": safe(stats_baseline.get("Return [%]")),
        "max_dd": safe(stats_baseline.get("Max. Drawdown [%]")),
        "sharpe": safe(stats_baseline.get("Sharpe Ratio")),
        "pf": safe(stats_baseline.get("Profit Factor")),
    }

    print(f"  Sharpe:     {baseline_metrics['sharpe']:.2f}")
    print(f"  Return:     {baseline_metrics['return']:.2f}%")
    print(f"  Max DD:     {baseline_metrics['max_dd']:.2f}%")
    print(f"  Win Rate:   {baseline_metrics['win_rate']:.1f}%")
    print(f"  Trades:     {baseline_metrics['trades']}")
    print(f"  PF:         {baseline_metrics['pf']:.2f}")

    # ── PROPOSED TEST (Default Params) ───────────────────────────
    print(f"\n{'─'*70}")
    print("  2. PROPOSED: Regime Filter (VIX>22 OR RY<1.0, ADX>30, 13:00-16:00)")
    print(f"{'─'*70}")

    GoldRegimeFilter.vix_threshold = 22.0
    GoldRegimeFilter.real_yield_threshold = 1.0
    GoldRegimeFilter.adx_min = 30

    bt_proposed = Backtest(h1, GoldRegimeFilter, cash=10_000,
                          commission=0.0002, finalize_trades=True)
    stats_proposed = bt_proposed.run()

    proposed_metrics = {
        "trades": int(stats_proposed.get("# Trades", 0)),
        "win_rate": safe(stats_proposed.get("Win Rate [%]")),
        "return": safe(stats_proposed.get("Return [%]")),
        "max_dd": safe(stats_proposed.get("Max. Drawdown [%]")),
        "sharpe": safe(stats_proposed.get("Sharpe Ratio")),
        "pf": safe(stats_proposed.get("Profit Factor")),
    }

    print(f"  Sharpe:     {proposed_metrics['sharpe']:.2f}")
    print(f"  Return:     {proposed_metrics['return']:.2f}%")
    print(f"  Max DD:     {proposed_metrics['max_dd']:.2f}%")
    print(f"  Win Rate:   {proposed_metrics['win_rate']:.1f}%")
    print(f"  Trades:     {proposed_metrics['trades']}")
    print(f"  PF:         {proposed_metrics['pf']:.2f}")

    # ── DELTA ANALYSIS ───────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  3. DELTA ANALYSIS (Proposed - Baseline)")
    print(f"{'='*70}")

    delta = {
        "sharpe": proposed_metrics["sharpe"] - baseline_metrics["sharpe"],
        "return": proposed_metrics["return"] - baseline_metrics["return"],
        "max_dd": proposed_metrics["max_dd"] - baseline_metrics["max_dd"],
        "win_rate": proposed_metrics["win_rate"] - baseline_metrics["win_rate"],
        "trades": proposed_metrics["trades"] - baseline_metrics["trades"],
        "pf": proposed_metrics["pf"] - baseline_metrics["pf"],
    }

    print(f"  Sharpe:     {delta['sharpe']:+.2f}  {'✅' if delta['sharpe'] >= 0.25 else '❌'}")
    print(f"  Return:     {delta['return']:+.2f}%")
    print(f"  Max DD:     {delta['max_dd']:+.2f}%  {'✅' if delta['max_dd'] >= 0 else '❌'}")
    print(f"  Win Rate:   {delta['win_rate']:+.1f}pp  {'✅' if delta['win_rate'] >= 5 else '❌'}")
    print(f"  Trades:     {delta['trades']:+d}  ({proposed_metrics['trades']} vs {baseline_metrics['trades']})")

    # ── SUCCESS CRITERIA ─────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  4. SUCCESS CRITERIA CHECK")
    print(f"{'='*70}")

    criteria = {
        "Sharpe ≥ 1.25": (proposed_metrics["sharpe"], 1.25, proposed_metrics["sharpe"] >= 1.25),
        "Win Rate ≥ 44%": (proposed_metrics["win_rate"], 44.0, proposed_metrics["win_rate"] >= 44.0),
        "Trades 80-180": (proposed_metrics["trades"], "80-180", 80 <= proposed_metrics["trades"] <= 180),
        "Max DD ≤ 12%": (abs(proposed_metrics["max_dd"]), 12.0, abs(proposed_metrics["max_dd"]) <= 12.0),
        "Sharpe Δ ≥ +0.25": (delta["sharpe"], 0.25, delta["sharpe"] >= 0.25),
    }

    passed = 0
    for criterion, (value, target, passed_check) in criteria.items():
        status = "✅ PASS" if passed_check else "❌ FAIL"
        print(f"  {criterion:<20} → {value} vs {target}  {status}")
        if passed_check:
            passed += 1

    print(f"\n  Result: {passed}/{len(criteria)} criteria met")

    # ── GRID SEARCH ──────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  5. PARAMETER SWEEP (Finding Optimal Thresholds)")
    print(f"{'='*70}")

    grid_results = run_grid_search(h1)

    if grid_results:
        # Sort by Sharpe
        grid_results.sort(key=lambda x: x["sharpe"], reverse=True)

        print(f"\n{'─'*70}")
        print("  Top 5 Configurations (by Sharpe)")
        print(f"{'─'*70}")
        header = f"{'VIX':>4} {'RY':>4} {'ADX':>4} {'Trades':>7} {'WR%':>6} {'Ret%':>7} {'DD%':>7} {'Sharpe':>7} {'PF':>5}"
        print(header)
        print("─" * len(header))

        for r in grid_results[:5]:
            print(f"{r['vix_threshold']:>4.0f} {r['real_yield_threshold']:>4.1f} {r['adx_min']:>4.0f} "
                  f"{r['trades']:>7} {r['win_rate']:>6.1f} {r['return_pct']:>7.2f} "
                  f"{r['max_dd']:>7.2f} {r['sharpe']:>7.2f} {r['profit_factor']:>5.2f}")

        best = grid_results[0]
        print(f"\n  🏆 Best Config: VIX={best['vix_threshold']} | RY={best['real_yield_threshold']} | ADX={best['adx_min']}")
        print(f"     Sharpe={best['sharpe']:.2f} | WR={best['win_rate']:.1f}% | Trades={best['trades']}")

    # ── FINAL DECISION ───────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  6. FINAL DECISION")
    print(f"{'='*70}")

    if passed >= 4 and proposed_metrics["sharpe"] >= 1.25:
        decision = "✅ APPROVE"
        recommendation = "Regime filter significantly improves XAUUSD strategy. Deploy to strategy/xauusd_signal.py"
    elif passed >= 3 and proposed_metrics["sharpe"] >= 1.15:
        decision = "⚠️  CONDITIONAL APPROVAL"
        recommendation = "Marginal improvement. Consider using best grid search params before deployment"
    else:
        decision = "❌ REJECT"
        recommendation = "Regime filter does not meet success criteria. Explore alternative approaches"

    print(f"  DECISION: {decision}")
    print(f"  Reasoning: {passed}/{len(criteria)} criteria met, Sharpe {proposed_metrics['sharpe']:.2f}")
    print(f"\n  RECOMMENDATION:")
    print(f"    {recommendation}")

    # ── SAVE RESULTS ─────────────────────────────────────────────
    os.makedirs("reports", exist_ok=True)
    out_path = "reports/xauusd_regime_filter_results.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "proposal": "XAUUSD Regime Filter",
            "date": "2026-05-16",
            "baseline": baseline_metrics,
            "proposed": proposed_metrics,
            "delta": delta,
            "success_criteria": {k: {"value": v[0], "target": v[1], "passed": v[2]}
                                for k, v in criteria.items()},
            "decision": decision,
            "grid_search_best": grid_results[0] if grid_results else None,
            "grid_search_top10": grid_results[:10] if grid_results else [],
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  💾 Results saved: {out_path}")
    print(f"\n{'='*70}")
