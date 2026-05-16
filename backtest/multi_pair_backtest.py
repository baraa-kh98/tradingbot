"""
Multi-Pair Backtest Runner
==========================
Runs all four pair backtests and reports consolidated Sharpe ratios.
"""

import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def read_results_file(filepath):
    """Read and parse a research results JSON file - handles multiple formats"""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Format 1: Gold results with "best_overall"
        if "best_overall" in data:
            best = data["best_overall"]
            return {
                "name": best.get("strategy", "Unknown"),
                "sharpe": best["sharpe"],
                "return": best["ret"],
                "drawdown": best["dd"],
                "win_rate": best["wr"],
                "trades": best["trades"],
                "profit_factor": best.get("pf", 0),
                "params": {k: v for k, v in best.items() if k not in ["strategy", "sharpe", "ret", "dd", "wr", "trades", "pf", "ann_ret", "score"]}
            }

        # Format 2: EURUSD with nested "best" and "top10"
        best_strategy = None
        best_sharpe = -999
        for strategy_name, strategy_data in data.items():
            # Check if this is the nested format
            if isinstance(strategy_data, dict) and "best" in strategy_data and strategy_data["best"]:
                best = strategy_data["best"]
                if best.get("sharpe", -999) > best_sharpe:
                    best_sharpe = best["sharpe"]
                    best_strategy = {
                        "name": strategy_name,
                        "sharpe": best["sharpe"],
                        "return": best["return_pct"],
                        "drawdown": best["max_dd_pct"],
                        "win_rate": best["win_rate"],
                        "trades": best["trades"],
                        "profit_factor": best.get("profit_factor", 0),
                        "params": best.get("params", {})
                    }
            # Format 3: GBPUSD with direct strategy data
            elif isinstance(strategy_data, dict) and "sharpe" in strategy_data:
                if strategy_data.get("sharpe", -999) > best_sharpe:
                    best_sharpe = strategy_data["sharpe"]
                    best_strategy = {
                        "name": strategy_name,
                        "sharpe": strategy_data["sharpe"],
                        "return": strategy_data["return_pct"],
                        "drawdown": strategy_data["max_dd_pct"],
                        "win_rate": strategy_data["win_rate"],
                        "trades": strategy_data["trades"],
                        "profit_factor": strategy_data.get("profit_factor", 0),
                        "params": strategy_data.get("params", {})
                    }

        return best_strategy
    except Exception as e:
        print(f"❌ Error reading {filepath}: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_usdjpy_fresh():
    """Run USDJPY London Breakout backtest (fresh)"""
    print("\n" + "="*70)
    print("  USDJPY - London Breakout (Running fresh backtest...)")
    print("="*70)
    try:
        from backtest.london_final import run
        stats, winner = run()
        # Find the best strategy by Sharpe (not by score)
        best_sharpe = -999
        best_stats = None
        best_variant = None
        for variant_name, variant_stats in stats.items():
            if variant_stats["sh"] > best_sharpe:
                best_sharpe = variant_stats["sh"]
                best_stats = variant_stats
                best_variant = variant_name

        if best_stats:
            print(f"\n  ℹ️  Best by Sharpe: {best_variant} (Sharpe {best_stats['sh']:.2f})")
            return {
                "pair": "USDJPY",
                "strategy": f"London {best_variant}",
                "sharpe": best_stats["sh"],
                "return": best_stats["ret"],
                "drawdown": best_stats["dd"],
                "win_rate": best_stats["wr"],
                "trades": best_stats["tr"],
                "profit_factor": best_stats.get("pf", 0)
            }
        return None
    except Exception as e:
        print(f"❌ Error running USDJPY backtest: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_eurusd_fresh():
    """Run EURUSD backtest (fresh)"""
    print("\n" + "="*70)
    print("  EURUSD - NY Breakout (Running fresh backtest...)")
    print("="*70)
    try:
        from backtest import eurusd_research
        eurusd_research.main()
        # Now read the results file it just created
        result = read_results_file("journal/eurusd_research_results.json")
        if result:
            return {
                "pair": "EURUSD",
                "strategy": result["name"],
                "sharpe": result["sharpe"],
                "return": result["return"],
                "drawdown": result["drawdown"],
                "win_rate": result["win_rate"],
                "trades": result["trades"],
                "profit_factor": result.get("profit_factor", 0)
            }
        return None
    except Exception as e:
        print(f"❌ Error running EURUSD backtest: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_gbpusd_fresh():
    """Run GBPUSD backtest (fresh)"""
    print("\n" + "="*70)
    print("  GBPUSD - NY Breakout (Running fresh backtest...)")
    print("="*70)
    try:
        from backtest import gbpusd_research
        gbpusd_research.main()
        # Now read the results file it just created
        result = read_results_file("journal/gbpusd_research_results.json")
        if result:
            return {
                "pair": "GBPUSD",
                "strategy": result["name"],
                "sharpe": result["sharpe"],
                "return": result["return"],
                "drawdown": result["drawdown"],
                "win_rate": result["win_rate"],
                "trades": result["trades"],
                "profit_factor": result.get("profit_factor", 0)
            }
        return None
    except Exception as e:
        print(f"❌ Error running GBPUSD backtest: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_xauusd_fresh():
    """Run XAUUSD backtest (fresh)"""
    print("\n" + "="*70)
    print("  XAUUSD - ATR Channel (Running fresh backtest...)")
    print("="*70)
    try:
        from backtest import gold_research
        gold_research.main()
        # Now read the results file it just created
        result = read_results_file("journal/gold_research_results.json")
        if result:
            return {
                "pair": "XAUUSD",
                "strategy": result["name"],
                "sharpe": result["sharpe"],
                "return": result["return"],
                "drawdown": result["drawdown"],
                "win_rate": result["win_rate"],
                "trades": result["trades"],
                "profit_factor": result.get("profit_factor", 0)
            }
        return None
    except Exception as e:
        print(f"❌ Error running XAUUSD backtest: {e}")
        import traceback
        traceback.print_exc()
        return None

def main(use_cached=False):
    """
    Run all pair backtests and generate consolidated report

    Args:
        use_cached: If True, read from existing JSON files. If False, run fresh backtests.
    """
    print("\n" + "="*70)
    print("  🚀 Multi-Pair Backtest Runner")
    if use_cached:
        print("  Reading cached backtest results...")
    else:
        print("  Running fresh backtests for all four trading pairs...")
    print("="*70)

    results = []

    if use_cached:
        # Read from existing JSON files
        eurusd = read_results_file("journal/eurusd_research_results.json")
        if eurusd:
            results.append({
                "pair": "EURUSD",
                "strategy": eurusd["name"],
                "sharpe": eurusd["sharpe"],
                "return": eurusd["return"],
                "drawdown": eurusd["drawdown"],
                "win_rate": eurusd["win_rate"],
                "trades": eurusd["trades"],
                "profit_factor": eurusd.get("profit_factor", 0)
            })

        gbpusd = read_results_file("journal/gbpusd_research_results.json")
        if gbpusd:
            results.append({
                "pair": "GBPUSD",
                "strategy": gbpusd["name"],
                "sharpe": gbpusd["sharpe"],
                "return": gbpusd["return"],
                "drawdown": gbpusd["drawdown"],
                "win_rate": gbpusd["win_rate"],
                "trades": gbpusd["trades"],
                "profit_factor": gbpusd.get("profit_factor", 0)
            })

        xauusd = read_results_file("journal/gold_research_results.json")
        if xauusd:
            results.append({
                "pair": "XAUUSD",
                "strategy": xauusd["name"],
                "sharpe": xauusd["sharpe"],
                "return": xauusd["return"],
                "drawdown": xauusd["drawdown"],
                "win_rate": xauusd["win_rate"],
                "trades": xauusd["trades"],
                "profit_factor": xauusd.get("profit_factor", 0)
            })

        # For USDJPY, run fresh since it doesn't save to JSON the same way
        usdjpy = run_usdjpy_fresh()
        if usdjpy:
            results.append(usdjpy)
    else:
        # Run all fresh backtests
        for run_func in [run_usdjpy_fresh, run_eurusd_fresh, run_gbpusd_fresh, run_xauusd_fresh]:
            result = run_func()
            if result:
                results.append(result)

    # Generate consolidated report
    print("\n" + "="*70)
    print("  📊 CONSOLIDATED RESULTS")
    print("="*70)
    print(f"\n  {'Pair':8s} {'Strategy':20s} {'Sharpe':>7s} {'Return':>8s} {'MaxDD':>8s} {'WR%':>6s} {'PF':>5s} {'Trades':>7s}")
    print("  " + "-"*80)

    for r in results:
        pf = r.get('profit_factor', 0)
        print(f"  {r['pair']:8s} {r['strategy'][:20]:20s} {r['sharpe']:>7.2f} {r['return']:>7.2f}% {r['drawdown']:>7.2f}% {r['win_rate']:>6.1f} {pf:>5.2f} {r['trades']:>7d}")

    # Summary statistics
    if results:
        avg_sharpe = sum(r['sharpe'] for r in results) / len(results)
        avg_return = sum(r['return'] for r in results) / len(results)
        max_dd = max(abs(r['drawdown']) for r in results)
        avg_pf = sum(r.get('profit_factor', 0) for r in results) / len(results)

        print("\n  " + "-"*80)
        print(f"  {'AVERAGE':8s} {'':20s} {avg_sharpe:>7.2f} {avg_return:>7.2f}% {max_dd:>7.2f}% {'':>6s} {avg_pf:>5.2f} {'':>7s}")

    # Success criteria check
    print("\n" + "="*70)
    print("  🎯 SUCCESS CRITERIA CHECK (from CLAUDE.md)")
    print("="*70)

    target_sharpe = 1.5
    target_wr = 52.0
    target_dd = 15.0
    target_return = 15.0

    meets_all = 0
    for r in results:
        status = []
        all_pass = True

        if r['sharpe'] >= target_sharpe:
            status.append("✅ Sharpe")
        else:
            status.append(f"❌ Sharpe ({r['sharpe']:.2f} < {target_sharpe})")
            all_pass = False

        if r['win_rate'] >= target_wr:
            status.append("✅ WR")
        else:
            status.append(f"❌ WR ({r['win_rate']:.1f}% < {target_wr}%)")
            all_pass = False

        if abs(r['drawdown']) <= target_dd:
            status.append("✅ DD")
        else:
            status.append(f"❌ DD ({abs(r['drawdown']):.2f}% > {target_dd}%)")
            all_pass = False

        if r['return'] >= target_return:
            status.append("✅ Return")
        else:
            status.append(f"❌ Return ({r['return']:.2f}% < {target_return}%)")
            all_pass = False

        if all_pass:
            meets_all += 1

        print(f"\n  {r['pair']} ({r['strategy']}):")
        for s in status:
            print(f"    {s}")

    print(f"\n  Summary: {meets_all}/{len(results)} pairs meet all criteria")
    print("\n" + "="*70 + "\n")

    return results

if __name__ == "__main__":
    import sys
    use_cached = "--cached" in sys.argv
    main(use_cached=use_cached)
