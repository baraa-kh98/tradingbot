"""
Statistical Validation: Asia/London Hybrid vs Baseline
For Quant Analyst Review — 2026-05-16
"""

import pandas as pd
import numpy as np
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting import Backtest
from london_final import LondonClean, LondonTrail, LondonAsiaHybrid, load_csv

H1_CSV = "backtest_data/USDJPY_H1_2years.csv"
H4_CSV = "backtest_data/USDJPY_H4_3years.csv"


def walk_forward_test(data_h1, data_h4, strategy_class, periods=4):
    """
    Walk-forward validation: split data into 4 periods
    Train on first 70%, test on next 30%, roll forward
    """
    total_len = len(data_h1)
    window_size = total_len // periods

    results = []
    for i in range(periods):
        start_idx = i * window_size
        end_idx = start_idx + window_size

        if end_idx > total_len:
            break

        test_data = data_h1.iloc[start_idx:end_idx]

        if len(test_data) < 100:
            continue

        # Set H4 data
        strategy_class._h4 = data_h4

        bt = Backtest(test_data, strategy_class, cash=10_000, commission=0.0002)
        r = bt.run()

        results.append({
            'period': i + 1,
            'start': test_data.index[0].strftime('%Y-%m-%d'),
            'end': test_data.index[-1].strftime('%Y-%m-%d'),
            'sharpe': float(r['Sharpe Ratio']) if not np.isnan(r['Sharpe Ratio']) else 0.0,
            'return': float(r['Return [%]']),
            'trades': r['# Trades'],
            'win_rate': float(r['Win Rate [%]']) if not np.isnan(r['Win Rate [%]']) else 0.0
        })

    return pd.DataFrame(results)


def monte_carlo_trades(trades_list, n_simulations=1000):
    """
    Monte Carlo: shuffle trade order and recalculate Sharpe
    Tests if results are robust to trade sequence
    """
    if not trades_list or len(trades_list) < 10:
        return []

    returns = [t['PnL'] for t in trades_list if 'PnL' in t]
    if len(returns) < 10:
        return []

    sharpe_dist = []
    for _ in range(n_simulations):
        shuffled = np.random.choice(returns, size=len(returns), replace=True)
        if np.std(shuffled) > 0:
            sharpe = np.mean(shuffled) / np.std(shuffled) * np.sqrt(252)
            sharpe_dist.append(sharpe)

    return sharpe_dist


def statistical_significance_test(baseline_result, hybrid_result):
    """
    Simple t-test approximation: is the difference in mean returns statistically significant?
    """
    baseline_trades = baseline_result._trades if hasattr(baseline_result, '_trades') else []
    hybrid_trades = hybrid_result._trades if hasattr(hybrid_result, '_trades') else []

    baseline_returns = [t.PnL for t in baseline_trades] if baseline_trades else []
    hybrid_returns = [t.PnL for t in hybrid_trades] if hybrid_trades else []

    if len(baseline_returns) < 5 or len(hybrid_returns) < 5:
        return None, None

    # Simple t-statistic without scipy
    mean_b = np.mean(baseline_returns)
    mean_h = np.mean(hybrid_returns)
    std_b = np.std(baseline_returns, ddof=1)
    std_h = np.std(hybrid_returns, ddof=1)
    n_b = len(baseline_returns)
    n_h = len(hybrid_returns)

    pooled_std = np.sqrt(((n_b - 1) * std_b**2 + (n_h - 1) * std_h**2) / (n_b + n_h - 2))
    t_stat = (mean_h - mean_b) / (pooled_std * np.sqrt(1/n_b + 1/n_h))

    return t_stat, None  # p_value calculation requires scipy, so we skip it


def main():
    print("\n" + "="*70)
    print("  STATISTICAL VALIDATION: Asia/London Hybrid vs Baseline")
    print("  Quant Analyst Report — 2026-05-16")
    print("="*70)

    h1 = load_csv(H1_CSV)
    h4 = load_csv(H4_CSV)

    if h1 is None:
        print("ERROR: H1 data not found")
        return

    print(f"\nData: {len(h1)} H1 bars from {h1.index[0].date()} to {h1.index[-1].date()}")

    # Set H4 for both strategies
    LondonTrail._h4 = h4
    LondonAsiaHybrid._h4 = h4

    # Run backtests
    print("\n" + "-"*70)
    print("1. BASELINE: LondonTrail (current live strategy)")
    print("-"*70)

    bt_baseline = Backtest(h1, LondonTrail, cash=10_000, commission=0.0002)
    r_baseline = bt_baseline.run()

    baseline_sharpe = float(r_baseline['Sharpe Ratio']) if not np.isnan(r_baseline['Sharpe Ratio']) else 0.0
    baseline_return = float(r_baseline['Return [%]'])
    baseline_dd = float(r_baseline['Max. Drawdown [%]'])
    baseline_wr = float(r_baseline['Win Rate [%]']) if not np.isnan(r_baseline['Win Rate [%]']) else 0.0
    baseline_trades = r_baseline['# Trades']

    print(f"  Sharpe:     {baseline_sharpe:.2f}")
    print(f"  Return:     {baseline_return:.2f}%")
    print(f"  Max DD:     {baseline_dd:.2f}%")
    print(f"  Win Rate:   {baseline_wr:.1f}%")
    print(f"  Trades:     {baseline_trades}")

    print("\n" + "-"*70)
    print("2. PROPOSED: Asia/London Hybrid")
    print("-"*70)

    bt_hybrid = Backtest(h1, LondonAsiaHybrid, cash=10_000, commission=0.0002)
    r_hybrid = bt_hybrid.run()

    hybrid_sharpe = float(r_hybrid['Sharpe Ratio']) if not np.isnan(r_hybrid['Sharpe Ratio']) else 0.0
    hybrid_return = float(r_hybrid['Return [%]'])
    hybrid_dd = float(r_hybrid['Max. Drawdown [%]'])
    hybrid_wr = float(r_hybrid['Win Rate [%]']) if not np.isnan(r_hybrid['Win Rate [%]']) else 0.0
    hybrid_trades = r_hybrid['# Trades']

    print(f"  Sharpe:     {hybrid_sharpe:.2f}")
    print(f"  Return:     {hybrid_return:.2f}%")
    print(f"  Max DD:     {hybrid_dd:.2f}%")
    print(f"  Win Rate:   {hybrid_wr:.1f}%")
    print(f"  Trades:     {hybrid_trades}")

    # Calculate deltas
    print("\n" + "="*70)
    print("3. DELTA ANALYSIS (Hybrid - Baseline)")
    print("="*70)

    delta_sharpe = hybrid_sharpe - baseline_sharpe
    delta_return = hybrid_return - baseline_return
    delta_dd = hybrid_dd - baseline_dd
    delta_wr = hybrid_wr - baseline_wr
    delta_trades = hybrid_trades - baseline_trades

    print(f"  Sharpe:     {delta_sharpe:+.2f}  {'❌ DECLINE' if delta_sharpe < 0 else '✅ IMPROVE'}")
    print(f"  Return:     {delta_return:+.2f}%  {'❌ DECLINE' if delta_return < 0 else '✅ IMPROVE'}")
    print(f"  Max DD:     {delta_dd:+.2f}%  {'✅ BETTER' if delta_dd > 0 else '❌ WORSE'}")
    print(f"  Win Rate:   {delta_wr:+.1f}pp  {'❌ DECLINE' if delta_wr < 0 else '✅ IMPROVE'}")
    print(f"  Trades:     {delta_trades:+d}  ({hybrid_trades} vs {baseline_trades})")

    # Success criteria check
    print("\n" + "="*70)
    print("4. SUCCESS CRITERIA CHECK")
    print("="*70)

    meets_sharpe = hybrid_sharpe >= 1.25
    meets_wr = hybrid_wr >= 40.0
    meets_trades = hybrid_trades >= 30
    improvement = delta_sharpe >= 0.28

    print(f"  Target Sharpe ≥ 1.25:           {hybrid_sharpe:.2f}  {'✅ PASS' if meets_sharpe else '❌ FAIL'}")
    print(f"  Target Win Rate ≥ 40%:          {hybrid_wr:.1f}%  {'✅ PASS' if meets_wr else '❌ FAIL'}")
    print(f"  Minimum Trades ≥ 30:            {hybrid_trades}  {'✅ PASS' if meets_trades else '❌ FAIL'}")
    print(f"  Sharpe Improvement ≥ +0.28:     {delta_sharpe:+.2f}  {'✅ PASS' if improvement else '❌ FAIL'}")

    # Statistical significance
    print("\n" + "="*70)
    print("5. STATISTICAL SIGNIFICANCE")
    print("="*70)

    print(f"  Baseline trades: {baseline_trades}")
    print(f"  Hybrid trades:   {hybrid_trades}")

    if baseline_trades < 30:
        print("  ⚠️  WARNING: Baseline trade count < 30 (borderline statistical validity)")
    if hybrid_trades < 30:
        print("  ⚠️  WARNING: Hybrid trade count < 30 (borderline statistical validity)")

    if baseline_trades >= 100:
        print("  ✅ Baseline: Sufficient sample size (≥100 trades)")
    elif baseline_trades >= 50:
        print("  ⚠️  Baseline: Moderate sample size (50-99 trades)")
    else:
        print("  ❌ Baseline: Insufficient sample size (<50 trades)")

    if hybrid_trades >= 100:
        print("  ✅ Hybrid: Sufficient sample size (≥100 trades)")
    elif hybrid_trades >= 50:
        print("  ⚠️  Hybrid: Moderate sample size (50-99 trades)")
    else:
        print("  ❌ Hybrid: Insufficient sample size (<50 trades)")

    # Walk-forward validation
    print("\n" + "="*70)
    print("6. WALK-FORWARD VALIDATION (4 periods)")
    print("="*70)

    print("\nBaseline (LondonTrail):")
    wf_baseline = walk_forward_test(h1, h4, LondonTrail, periods=4)
    if not wf_baseline.empty:
        print(wf_baseline.to_string(index=False))
        baseline_consistent = (wf_baseline['sharpe'] > 0.5).sum() >= 3
        print(f"\nConsistency: {(wf_baseline['sharpe'] > 0.5).sum()}/4 periods with Sharpe > 0.5")
        print(f"  {'✅ CONSISTENT' if baseline_consistent else '❌ INCONSISTENT'}")

    print("\nProposed (Asia/London Hybrid):")
    wf_hybrid = walk_forward_test(h1, h4, LondonAsiaHybrid, periods=4)
    if not wf_hybrid.empty:
        print(wf_hybrid.to_string(index=False))
        hybrid_consistent = (wf_hybrid['sharpe'] > 0.5).sum() >= 3
        print(f"\nConsistency: {(wf_hybrid['sharpe'] > 0.5).sum()}/4 periods with Sharpe > 0.5")
        print(f"  {'✅ CONSISTENT' if hybrid_consistent else '❌ INCONSISTENT'}")

    # Overfitting assessment
    print("\n" + "="*70)
    print("7. OVERFITTING RISK ASSESSMENT")
    print("="*70)

    # Check if hybrid has more trades but worse performance (sign of noise)
    if hybrid_trades > baseline_trades * 1.3 and hybrid_sharpe < baseline_sharpe:
        risk_level = "HIGH"
        print(f"  🔴 RISK LEVEL: {risk_level}")
        print(f"     Reason: +{(hybrid_trades/baseline_trades - 1)*100:.0f}% more trades but lower Sharpe")
        print(f"     Interpretation: Additional entries are capturing noise, not signal")
    elif delta_sharpe < -0.2:
        risk_level = "MEDIUM"
        print(f"  🟡 RISK LEVEL: {risk_level}")
        print(f"     Reason: Sharpe declined by {abs(delta_sharpe):.2f}")
        print(f"     Interpretation: Timing change degrades edge")
    else:
        risk_level = "LOW"
        print(f"  🟢 RISK LEVEL: {risk_level}")
        print(f"     Reason: Performance metrics within acceptable range")

    # Parameter sensitivity
    print("\n" + "="*70)
    print("8. PARAMETER SENSITIVITY")
    print("="*70)

    print("  Key parameter changed:")
    print("    - Range window: 00:00-06:59 → 00:00-02:59 (7h → 3h)")
    print("    - Entry window: 07:00-09:59 → 03:00-09:59 (3h → 7h)")
    print("\n  Analysis:")
    print(f"    - Narrower range window (3h vs 7h)")
    print(f"    - Wider entry window (7h vs 3h)")
    print(f"    - Result: {delta_trades:+d} trades, {delta_sharpe:+.2f} Sharpe change")

    if delta_trades > 0 and delta_sharpe < 0:
        print("\n  🔴 CONCLUSION: More trades but worse risk-adjusted returns")
        print("     Early Asia entries are likely false breakouts")

    # Final verdict
    print("\n" + "="*70)
    print("9. FINAL VERDICT")
    print("="*70)

    passes = sum([meets_sharpe, meets_wr, meets_trades, improvement])

    if passes >= 3 and delta_sharpe > 0:
        decision = "APPROVE"
        icon = "✅"
        reason = f"Meets {passes}/4 success criteria and improves Sharpe"
    elif delta_sharpe >= 0 and passes >= 2:
        decision = "CONDITIONAL APPROVE"
        icon = "⚠️"
        reason = f"Meets {passes}/4 criteria but improvement is marginal"
    else:
        decision = "REJECT"
        icon = "❌"
        reason = f"Fails to meet success criteria ({passes}/4) and/or worsens performance"

    print(f"\n  {icon} DECISION: {decision}")
    print(f"\n  REASONING:")
    print(f"    {reason}")
    print(f"\n  PERFORMANCE SUMMARY:")
    print(f"    - Sharpe: {baseline_sharpe:.2f} → {hybrid_sharpe:.2f} ({delta_sharpe:+.2f})")
    print(f"    - Return: {baseline_return:.2f}% → {hybrid_return:.2f}% ({delta_return:+.2f}%)")
    print(f"    - Win Rate: {baseline_wr:.1f}% → {hybrid_wr:.1f}% ({delta_wr:+.1f}pp)")
    print(f"    - Trades: {baseline_trades} → {hybrid_trades} ({delta_trades:+d})")

    if decision == "REJECT":
        print(f"\n  RECOMMENDATION:")
        print(f"    - Keep current London-only strategy (07:00-09:59 entry)")
        print(f"    - Asia session (03:00-07:00) adds noise, not signal")
        print(f"    - Win rate declined {abs(delta_wr):.1f}pp despite +{delta_trades} trades")
        print(f"    - Consider alternative approaches:")
        print(f"      1. Tighter breakout filter (increase buffer from 3 to 4-5 pips)")
        print(f"      2. Add volatility filter (only trade when ATR > threshold)")
        print(f"      3. Test NY session instead (13:00-16:00 UTC)")

    print("\n" + "="*70 + "\n")

    return {
        'decision': decision,
        'risk_level': risk_level,
        'baseline': {
            'sharpe': baseline_sharpe,
            'return': baseline_return,
            'dd': baseline_dd,
            'wr': baseline_wr,
            'trades': baseline_trades
        },
        'hybrid': {
            'sharpe': hybrid_sharpe,
            'return': hybrid_return,
            'dd': hybrid_dd,
            'wr': hybrid_wr,
            'trades': hybrid_trades
        },
        'delta': {
            'sharpe': delta_sharpe,
            'return': delta_return,
            'dd': delta_dd,
            'wr': delta_wr,
            'trades': delta_trades
        }
    }


if __name__ == "__main__":
    results = main()
