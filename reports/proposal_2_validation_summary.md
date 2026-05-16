# Proposal #2 Validation Summary
# ATR Volatility Quality Filter — USDJPY London Breakout

**Date:** 2026-05-16 03:30 UTC  
**Analyst:** Quant Analyst Agent  
**Status:** ❌ REJECTED

---

## Quick Summary

**Proposal:** Add ATR threshold (0.25) to filter out low-volatility trading days  
**Expected:** Sharpe 0.97 → 1.25-1.40 via quality filtering  
**Actual:** Sharpe 0.98 → 0.82 (best threshold 0.28) — DECLINE

**Decision: REJECT** — ATR filter underperforms baseline across all tested thresholds.

---

## Key Findings

### 1. ATR Not Predictive of Trade Quality

**Correlation Analysis (69 baseline trades):**
- ATR vs Win/Loss: **+0.098** (WEAK, near zero)
- ATR vs Return%: **+0.403** (moderate, but doesn't improve win rate)

**Interpretation:** High ATR doesn't increase win probability, just increases variance.

### 2. Paradoxical Result: Low ATR Days Perform BETTER

| ATR Quartile | Win Rate | Surprise |
|--------------|----------|----------|
| Q1: Low (<0.201) | **47.1%** | 🔺 HIGHEST |
| Q2: Mid-Low (0.201-0.236) | 23.5% | |
| Q3: Mid-High (0.236-0.301) | 29.4% | |
| Q4: High (>0.301) | 44.4% | |

**Why?** USDJPY London Breakout is a **range expansion** strategy:
- Low ATR (quiet Asia) → London breakout has more room to run
- High ATR (volatile Asia) → London may reverse or consolidate

**Hypothesis was backwards:** "High volatility = better breakouts" is wrong for this strategy.

### 3. All Tested Thresholds Underperform

| ATR Threshold | Trades | Sharpe | vs Baseline (0.98) |
|--------------|--------|--------|-------------------|
| 0.20 | 48 | 0.39 | ❌ -60% |
| 0.22 | 39 | 0.72 | ❌ -27% |
| 0.25 (proposed) | 29 | 0.81 | ❌ -17% |
| **0.28 (best)** | **19** | **0.82** | **❌ -16%** |
| 0.30 | 17 | 0.69 | ❌ -30% |

**Best case (0.28):**
- ✅ Win rate improved: 36.2% → 42.1%
- ✅ Profit factor improved: 1.66 → 2.21
- ❌ Sharpe still worse: 0.98 → 0.82
- ❌ Only 19 trades (not statistically significant)

---

## Why Proposal #2 Failed

### 1. Wrong Hypothesis
- **Assumed:** High volatility = directional conviction = better breakouts
- **Reality:** Low volatility = tight range = cleaner breakout levels

### 2. Trade Count vs Quality Tradeoff
- Higher thresholds → fewer trades but not enough Sharpe improvement
- Lower thresholds → more trades but terrible Sharpe (0.39-0.72)
- **No sweet spot exists**

### 3. Strategy Type Mismatch
ATR filtering works for:
- ✅ Momentum strategies (ride trends)
- ✅ News-driven breakouts (NFP, FOMC)
- ❌ Range expansion breakouts (USDJPY London)

---

## Success Criteria Evaluation

| Criterion | Target | Best Result (ATR 0.28) | Status |
|-----------|--------|------------------------|--------|
| Sharpe ≥ 1.25 | 1.25 | 0.82 | ❌ FAIL (-43pp) |
| Win Rate ≥ 40% | 40% | 42.1% | ✅ PASS (+2.1pp) |
| Trades ≥ 30 | 30 | 19 | ❌ FAIL (-37%) |
| Sharpe Improvement ≥ +0.15 | +0.15 | -0.16 | ❌ FAIL (decline) |
| Max DD ≤ 10% | 10% | -5.72% | ✅ PASS |

**Result:** 2/5 criteria met → **REJECT**

---

## Comparison: Proposal #1 vs #2

| Aspect | Proposal #1 (Asia Hybrid) | Proposal #2 (ATR Filter) |
|--------|--------------------------|-------------------------|
| **Approach** | Add trades (quantity) | Remove trades (quality) |
| **Entry Window** | 03:00-10:00 (expand) | 07:00-10:00 (keep) |
| **Trade Count** | 69 → 95 (+38%) | 69 → 19-48 (-30% to -72%) |
| **Sharpe Result** | 0.97 → 0.32 (-67%) | 0.98 → 0.39-0.82 (-16% to -60%) |
| **Decision** | ❌ REJECT | ❌ REJECT |
| **Lesson** | More trades ≠ better | ATR not predictive |

**Pattern:** Both timing expansion AND volatility filtering failed. Current parameters may already be near-optimal.

---

## Recommendations

### Do NOT Implement ATR Filter

**Reasons:**
1. Best threshold still underperforms baseline (Sharpe 0.82 < 0.98)
2. Trade count too low (19) for statistical significance
3. ATR weakly correlated with outcomes (+0.098)
4. Low ATR days perform better (opposite of hypothesis)

### Alternative Quality Filters to Test

| Filter | Description | Rationale | Priority |
|--------|-------------|-----------|----------|
| **Range Size** | Only trade 50-120 pip ranges | Too tight = noise, too wide = already moved | 🔴 HIGH |
| **H4 Momentum** | Require EMA20-EMA50 spread > 0.1% | Strong trend = better follow-through | 🔴 HIGH |
| **Inverse ATR** | Only trade ATR < 0.22 (LOW vol) | Q1 quartile had 47.1% win rate | 🟡 MEDIUM |
| **Calendar Filter** | Skip Fridays, 1st week of month | Avoid low-quality structural days | 🟢 LOW |

**Next Step:** Test Range Size or H4 Momentum filters (both build on existing logic).

---

## Statistical Notes

### Sample Size Validity

| Strategy | Trades | Statistical Validity |
|----------|--------|---------------------|
| Baseline | 69 | ⚠️ Borderline (need 100+ for high confidence) |
| ATR 0.28 | 19 | ❌ Insufficient (need 30+ minimum) |
| ATR 0.25 | 29 | ⚠️ Borderline |
| ATR 0.20 | 48 | ✅ Acceptable |

**Implication:** Even if ATR 0.28 had better Sharpe, 19 trades is too few to trust.

### Walk-Forward Testing: Not Performed

**Reason:** Since all thresholds underperform baseline, walk-forward would only confirm failure. Skipped to save time.

**If we had success:** Would split data into 4 periods and test consistency.

---

## Artifacts

**Backtest Implementation:**  
`/Users/baraakhattab/Desktop/tradingbot/backtest/london_final.py`  
Class: `LondonATRFilter` (lines 500-560)

**Validation Function:**  
`validate_proposal_2()` (lines 620-750)

**ATR Analysis Script:**  
`/Users/baraakhattab/Desktop/tradingbot/backtest/atr_analysis.py`  
(Correlation study: ATR vs trade outcomes)

**Full Report:**  
`/Users/baraakhattab/Desktop/tradingbot/reports/quant_analysis_2026-05-16.md`  
(Section: "PROPOSAL #2 VALIDATION")

---

## Reproduce Results

```bash
# Run full validation (includes ATR sweep)
python3 backtest/london_final.py

# Run correlation analysis
python3 backtest/atr_analysis.py
```

**Expected Output:**
- ATR sweep: Sharpe 0.39-0.82 across thresholds
- Best threshold: 0.28 (Sharpe 0.82, 19 trades)
- Decision: REJECT (underperforms baseline 0.98)

---

## Next Steps for Trading Strategist

### Option 1: Accept Current Strategy
- **LondonTrail** (Sharpe 0.98) is decent
- Both optimization attempts (#1, #2) failed
- Focus effort on EUR/GBP/XAU strategies instead

### Option 2: Test Alternative Filters
- Range Size filter (50-120 pips)
- H4 Momentum filter (stricter bias)
- See "Recommendations" section above

### Option 3: Shift Strategy Type
- NY Session Breakout (13:00-16:00 entry)
- Pure Momentum (abandon range breakout concept)
- Regime-based activation (only trade in carry-trade regimes)

**Recommended:** Option 1 or Option 2. Stop optimizing timing/volatility, focus on trade selection or risk management.

---

## Conclusion

ATR Volatility Quality Filter (Proposal #2) **fails to improve USDJPY London Breakout** performance:

✅ **What Worked:**
- Win rate improved from 36.2% → 42.1% (best threshold)
- Profit factor improved from 1.66 → 2.21

❌ **What Failed:**
- Sharpe declined from 0.98 → 0.82 (worse risk-adjusted returns)
- Trade count dropped to 19 (statistically insufficient)
- No threshold achieves both Sharpe ≥ 1.25 AND Trades ≥ 30

**Final Decision: REJECT**

**Lesson:** Volatility filtering doesn't improve range breakout strategies. Low ATR days (quiet markets) produce better breakout quality than high ATR days (volatile markets).

---

**Report Completed:** 2026-05-16 03:30 UTC  
**Next Action:** Notify Trading Strategist of rejection, suggest alternative approaches  
**Workflow Status:** Both Proposal #1 and #2 rejected — workflow terminated
