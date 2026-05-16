# Risk Management Review — XAUUSD Regime Filter Proposal #3

**Prepared By:** Risk Manager Agent  
**Date:** 2026-05-16 06:30 UTC  
**Proposal Reviewed:** XAUUSD Regime Filter (Macro + Liquidity + ADX)  
**Quant Analysis:** `reports/quant_analysis_2026-05-16.md` — Proposal #3 (Approved Conditional)

---

## Executive Summary

**DECISION: ✅ APPROVE WITH CONDITIONS**

The XAUUSD Regime Filter proposal demonstrates substantial risk-adjusted improvements while maintaining acceptable risk parameters well within policy limits. After thorough analysis of drawdown risk, trade frequency, correlation exposure, and data dependencies, I approve this proposal with **enhanced risk controls** to protect capital during initial deployment.

**Key Risk Assessment:**
- Max Drawdown: -3.61% (✅ Excellent — 76% below -15% policy limit)
- Trade Frequency: 38 trades/2.25 years (⚠️ Low but quality-focused)
- Correlation Risk: ✅ Acceptable (XAUUSD is portfolio diversifier)
- Data Dependency: 🟡 Moderate (VIX + Real Yield feeds)
- Regime Risk: 🟡 Moderate (30-day dry spells possible)

**Required Conditions:**
1. Conservative initial risk: 0.5% per trade (not 1%)
2. Paper trading validation: 2-3 months minimum
3. Real-time data reliability testing: FRED API integration + staleness alerts
4. Enhanced monitoring: 30-day no-trade alerts, regime dashboard
5. Walk-forward validation: Review after 20 live trades

---

## 1. Proposal Overview

### Current Problem (XAUUSD Baseline)
- **Overtrading:** 336 trades over 2.25 years (149 trades/year)
- **Suboptimal Sharpe:** 0.73 (target: 1.50)
- **Max Drawdown:** -6.77% (acceptable but improvable)
- **Win Rate:** 35.5% (low quality setups)

### Proposed Solution (Optimized Regime Filter)
- **Macro Gate:** VIX > 24 OR Real Yield < 1.2%
- **Trend Quality:** ADX > 28 (stricter than baseline 25)
- **Liquidity Window:** 13:00-16:00 UTC (London/NY overlap only)

### Quant-Approved Configuration
- **Sharpe:** 0.73 → 1.31 (+0.58, +79%)
- **Max DD:** -6.77% → -3.61% (47% improvement)
- **Trades:** 336 → 38 (81% reduction)
- **Win Rate:** 35.5% → 44.7% (+9.2pp quality improvement)
- **Walk-Forward:** 50% → 75% consistency

---

## 2. Risk Parameter Assessment

### 2.1 Maximum Drawdown Analysis

| Scenario | Max DD | Policy Limit | Status | Margin |
|----------|--------|--------------|--------|--------|
| **Optimized Regime Filter** | **-3.61%** | **-15%** | **✅ PASS** | **76% below limit** |
| Baseline (Current) | -6.77% | -15% | ✅ PASS | 55% below limit |
| Walk-Forward Period 1 | 0.00% | -15% | ✅ PASS | No trades (correct filter) |
| Walk-Forward Period 2 | -2.10% | -15% | ✅ PASS | 86% below limit |
| Walk-Forward Period 3 | -2.85% | -15% | ✅ PASS | 81% below limit |
| Walk-Forward Period 4 | -1.92% | -15% | ✅ PASS | 87% below limit |

**Assessment:** ✅ **EXCELLENT**

The proposed strategy reduces max drawdown by 47% while significantly improving returns. All walk-forward periods show consistent risk control with maximum drawdown never exceeding -2.85% — demonstrating robust risk management across different market regimes.

**Key Insight:** Period 1 (2024-04 to 2024-10) shows 0% drawdown because the regime filter correctly identified unfavorable conditions and executed NO trades, avoiding the -1.59% loss experienced by the baseline. This validates the filter's protective function.

### 2.2 Daily Risk Controls

| Control | Current Setting | Policy Limit | Compliance |
|---------|----------------|--------------|------------|
| Risk per Trade | 1.0% | 1.0% max | ✅ At limit |
| Daily Max Loss | -3.0% | -3.0% max | ✅ At limit |
| Max Trades/Day | 3 | 3 max | ✅ At limit |
| Min Risk/Reward | 2.5 | 2.0 min | ✅ Exceeds requirement |

**Assessment:** ✅ **COMPLIANT**

All daily risk controls remain within policy. However, given the experimental nature of regime filtering and low historical trade count (38 trades), **I recommend conservative initial deployment at 0.5% risk per trade** until validation is complete (see Section 7).

### 2.3 Sharpe Ratio Assessment

| Strategy | Sharpe | Policy Minimum | Status | Target Gap |
|----------|--------|----------------|--------|------------|
| **Optimized Regime Filter** | **1.31** | **1.0** | **✅ PASS** | **-0.19 from 1.5 target** |
| Baseline | 0.73 | 1.0 | ❌ FAIL | -0.77 from 1.5 target |

**Assessment:** ✅ **PASS (Meets Policy Minimum)**

Sharpe ratio improves by +79% and now exceeds the 1.0 minimum policy requirement. While still below the 1.5 aspirational target, this represents significant progress. The proposal moves XAUUSD from non-compliant (0.73) to compliant (1.31) status.

---

## 3. Trade Frequency & Statistical Validity

### 3.1 Trade Count Analysis

| Period | Baseline Trades | Regime Filter Trades | Reduction |
|--------|----------------|---------------------|-----------|
| Full Period (2.25 years) | 336 | 38 | -88.7% |
| Annualized | 149 | 17 | -88.7% |
| Per Month | 12.4 | 1.4 | -88.7% |

**Assessment:** ⚠️ **BORDERLINE — Trade Frequency Risk**

**Concerns:**
1. **Low Sample Size:** 38 trades over 2.25 years is at the minimum threshold for statistical significance (30+ trades required). The quant analysis correctly flags this as "borderline."
2. **Dry Spell Risk:** At 17 trades/year (1.4/month), the strategy may go 30+ days without signals during unfavorable macro regimes.
3. **Validation Challenge:** Paper trading will need 2-3 months minimum to collect 10+ trades for meaningful validation.

**Mitigations:**
- The 81% trade reduction is **intentional** — removing low-quality setups to improve win rate (+9.2pp) and Sharpe (+0.58).
- Walk-forward validation shows 75% consistency across periods despite low trade count, suggesting quality > quantity approach is working.
- Grid search tested 45 parameter combinations; the optimized config balances trade frequency with performance.

**Risk Manager Verdict:** Acceptable if:
1. User acknowledges 30-day no-trade periods are expected
2. Monitoring alerts notify if no trades >45 days (possible regime miscalibration)
3. Paper trading validates the strategy generates sufficient opportunities

### 3.2 Walk-Forward Consistency

| Period | Baseline Sharpe | Regime Filter Sharpe | Result |
|--------|----------------|---------------------|--------|
| 1 (2024-04 to 2024-10) | -0.45 | 0.00 (0 trades) | ✅ Filter avoided loss |
| 2 (2024-10 to 2025-04) | 1.06 | 1.20 | ✅ Improved |
| 3 (2025-04 to 2025-10) | 1.68 | 1.12 | ⚠️ Slight decline |
| 4 (2025-10 to 2026-04) | 0.26 | **2.53** | ✅ Major improvement |

**Consistency Score:**
- Baseline: 50% positive periods (2/4)
- Regime Filter: 75% positive periods (3/4)

**Assessment:** ✅ **IMPROVED ROBUSTNESS**

Despite low trade count, the regime filter demonstrates **better consistency** than baseline across different market conditions. Period 4's exceptional Sharpe (2.53) suggests the strategy excels during high-volatility regimes (likely 2025-2026 Gold rally).

---

## 4. Correlation & Portfolio Risk

### 4.1 Current Portfolio Composition

| Pair | Strategy | Sharpe | Allocation | Live Since |
|------|----------|--------|-----------|-----------|
| EURUSD | NY Breakout | 1.61 | 25% | 2026-05-12 |
| GBPUSD | NY Breakout | 1.22 | 25% | 2026-05-12 |
| USDJPY | London Breakout | 0.97 | 25% | 2026-05-05 |
| XAUUSD | ATR Breakout (baseline) | 0.73 | 25% | 2024-04-01 |

**Portfolio Sharpe (Equal-Weighted):** 1.21 (baseline)

### 4.2 XAUUSD Correlation with Portfolio

**Correlation Matrix (Daily Returns, 2-Year Data):**

|        | XAUUSD | EURUSD | GBPUSD | USDJPY |
|--------|--------|--------|--------|--------|
| XAUUSD | 1.000  | +0.349 | +0.377 | -0.226 |
| EURUSD | +0.349 | 1.000  | +0.799 | -0.587 |
| GBPUSD | +0.377 | +0.799 | 1.000  | -0.505 |
| USDJPY | -0.226 | -0.587 | -0.505 | 1.000  |

**Key Findings:**
1. **XAUUSD is a portfolio diversifier:**
   - Low correlation with EURUSD (+0.349) and GBPUSD (+0.377)
   - Near-zero correlation with USDJPY (-0.226)
   - EUR/GBP are highly correlated with each other (+0.799) but NOT with Gold

2. **Portfolio Structure:**
   - EUR/GBP cluster: High intra-correlation (-0.5 to +0.8 with USD pairs)
   - XAUUSD standalone: Independent moves, provides diversification
   - Risk: EUR/GBP/JPY all trade during overlapping sessions (13:00-16:00 UTC)

**Assessment:** ✅ **CORRELATION RISK ACCEPTABLE**

XAUUSD provides **valuable diversification** to the portfolio. Its low/moderate correlations mean Gold losses are unlikely to coincide with EUR/GBP/JPY losses. The proposed regime filter does NOT increase correlation risk — it actually **improves risk-adjusted returns without affecting portfolio structure**.

### 4.3 Session Overlap Risk

**Proposed XAUUSD Entry Window:** 13:00-16:00 UTC (London/NY overlap)

**Overlap with Other Pairs:**
- **EURUSD:** 13:00-15:00 UTC (NY Open Breakout)
- **GBPUSD:** 13:00-15:00 UTC (NY Open Breakout)
- **USDJPY:** 07:00-10:00 UTC (London Open) — NO OVERLAP

**Concern:** If XAUUSD, EURUSD, and GBPUSD all trigger simultaneously during 13:00-15:00 UTC, the portfolio could face 3× simultaneous exposure (3% total risk if all hit stop-losses same day).

**Mitigations:**
1. Daily max loss limit (-3%) already caps this risk
2. XAUUSD regime filter is highly selective (38 trades vs EUR 52, GBP 41) — unlikely to trigger on same days
3. VIX > 24 condition means XAUUSD trades during high-volatility, not normal EUR/GBP breakout days
4. Gold's +0.35 correlation with EUR/GBP suggests occasional but not systematic overlap

**Risk Manager Verdict:** ⚠️ **MODERATE RISK — Monitoring Required**

Add monitoring alert: "Portfolio exposure check: If 2+ pairs signal same hour (13:00-15:00 UTC), flag for manual review before executing 3rd entry."

---

## 5. Data Dependency Risk

### 5.1 Required Data Feeds

| Data Source | Update Frequency | Purpose | Failure Impact |
|-------------|------------------|---------|----------------|
| **VIX (CBOE)** | Real-time | Fear gauge (>24 threshold) | Strategy disabled if stale >6h |
| **US 10Y Yield (FRED)** | Daily | Real Yield calculation | Strategy disabled if stale >24h |
| **CPI (FRED)** | Monthly | Real Yield calculation | Use last available (low risk) |
| **XAUUSD H1 (MT5/Twelvedata)** | Hourly | Price + ADX calculation | Trade execution failure |

**Assessment:** 🟡 **MODERATE DEPENDENCY RISK**

**Concerns:**
1. **Synthetic Real Yield in Backtest:** Quant used estimated Real Yield (US10Y - synthetic inflation). Live deployment requires **FRED API integration** for actual data.
2. **VIX Staleness:** If VIX feed fails during market hours (e.g., CBOE outage), strategy cannot validate regime gate → trades blocked.
3. **Weekend Data Gap:** VIX/FRED do not update on weekends, but XAUUSD trades 24/5. Strategy must handle stale weekend data correctly.

### 5.2 Data Reliability Requirements

**Mandatory Before Live Deployment:**
1. ✅ **FRED API Integration**
   - Endpoint: `/series/observations?series_id=DGS10`
   - Fallback: Cache last 7 days, use most recent if API fails
   - Alert if data >24 hours stale

2. ✅ **VIX Data Feed**
   - Source: FinnHub API (already integrated) or CBOE
   - Update frequency: Real-time (5-min delay acceptable)
   - Alert if data >6 hours stale

3. ✅ **Staleness Handling**
   ```python
   if vix_age_hours > 6 or real_yield_age_hours > 24:
       log_warning("Regime data stale — SKIP TRADE")
       return None
   ```

4. ✅ **Paper Trading Data Validation**
   - Monitor data feed uptime during 2-3 month validation
   - Track: API failures, data gaps, staleness incidents
   - Success criteria: >99% uptime, <5 staleness events

**Risk Manager Verdict:** Acceptable if FRED integration and staleness alerts are implemented BEFORE paper trading begins.

---

## 6. Regime Risk Assessment

### 6.1 No-Trade Scenarios

**Regime Filter Logic:** Trade only if `(VIX > 24) OR (Real Yield < 1.2%)`

**Historical Regime Analysis (from Walk-Forward):**

| Period | Regime Condition | Trades | Result |
|--------|-----------------|--------|--------|
| 2024-04 to 2024-10 | Unfavorable (low vol) | 0 | Avoided -1.59% loss ✅ |
| 2024-10 to 2025-04 | Mixed | 14 | +2.17% ✅ |
| 2025-04 to 2025-10 | Favorable | 15 | +4.46% ✅ |
| 2025-10 to 2026-04 | Highly favorable | 9 | +7.62% ✅ |

**Key Finding:** Period 1 (6 months) produced ZERO trades — the regime filter correctly identified unfavorable conditions and stayed out of the market.

**Assessment:** ⚠️ **MODERATE REGIME RISK**

**Concerns:**
1. **Extended Dry Spells:** The strategy may go 30-90 days without trades during low-volatility, positive-real-yield regimes (e.g., "Goldilocks economy").
2. **User Expectations:** If user expects consistent weekly signals, this strategy will disappoint.
3. **Opportunity Cost:** If Gold rallies during "unfavorable" regime (false negative), strategy misses profit.

**Mitigations:**
1. **Monitoring Alert:** Notify if no trades >30 days → review regime calibration
2. **Regime Dashboard:** Display current VIX, Real Yield, and whether gate is open/closed
3. **Parameter Review:** After 50 live trades, re-evaluate VIX 24 and Real Yield 1.2% thresholds

**Risk Manager Verdict:** Acceptable if user acknowledges this is a **selective, regime-aware strategy** — not a high-frequency trading system.

### 6.2 Regime Overfitting Risk

**Quant Assessment:** 🟡 Moderate overfitting risk (low trade count, Period 4 outlier Sharpe 2.53)

**My Assessment:** ⚠️ **MODERATE RISK — Paper Trading Critical**

**Evidence FOR Overfitting:**
- VIX 24 and Real Yield 1.2% are **data-driven optimizations** from grid search on same backtest data
- Period 4's exceptional Sharpe (2.53) may be a lucky outlier (only 9 trades)
- No true out-of-sample validation (all data 2024-2026 used for optimization)

**Evidence AGAINST Overfitting:**
- Economic logic is sound (VIX = fear, Real Yield = opportunity cost of Gold)
- Walk-forward shows 75% consistency (not 100% = not overfit to single period)
- Period 1 correctly avoided loss (filter works as designed, not just lucky)

**Risk Manager Verdict:** Paper trading is MANDATORY to validate regime filter performs in true out-of-sample conditions (2026-05-16 onward).

---

## 7. Conditional Approval — Required Risk Controls

### 7.1 Initial Deployment Phase (Paper Trading)

**Duration:** 2-3 months (minimum 10 trades, target 15-20)

**Conservative Risk Settings:**
| Parameter | Standard | Initial (Conservative) | Rationale |
|-----------|----------|----------------------|-----------|
| Risk per Trade | 1.0% | **0.5%** | Reduce exposure during validation |
| Daily Max Loss | -3.0% | **-1.5%** | Tighter safety net |
| Max Trades/Day | 3 | **2** | Limit rapid drawdown |

**Success Criteria (Paper Trading):**
- Minimum 10 trades executed
- Sharpe ratio ≥ 1.0 (target 1.31, allow 20% tolerance)
- Max drawdown ≤ -5% (target -3.61%, allow 40% tolerance)
- Win rate ≥ 38% (target 44.7%, allow 15% tolerance)
- No data staleness incidents >5 events

**Escalation:** If any criterion fails, return to quant for re-evaluation before live deployment.

### 7.2 Graduated Risk Increase

**After Paper Trading Success:**

| Milestone | Risk per Trade | Review Trigger |
|-----------|---------------|----------------|
| Initial (paper) | 0.5% | After 10 trades |
| Phase 1 (live) | 0.5% | After 20 trades, if Sharpe >1.0 |
| Phase 2 (scale) | 0.75% | After 40 trades, if Sharpe >1.2 |
| Phase 3 (full) | 1.0% | After 60 trades, if Sharpe >1.25 |

**Rollback Condition:** If at ANY phase, rolling Sharpe (last 20 trades) drops below 0.8, revert to previous risk level.

### 7.3 Monitoring & Alert Requirements

**Real-Time Alerts (Mandatory):**
1. **Data Staleness Alert**
   - VIX data >6 hours old
   - Real Yield data >24 hours old
   - Action: Block trades, notify SRE

2. **No-Trade Alert**
   - No signals for 30 consecutive days
   - Action: Review regime calibration, check data feeds

3. **Drawdown Alert**
   - Strategy drawdown exceeds -5% (live)
   - Action: Pause trading, escalate to Risk Manager

4. **Portfolio Overlap Alert**
   - 2+ pairs signal within same hour (13:00-15:00 UTC)
   - Action: Flag for manual review before 3rd entry

**Daily Reports (Mandatory):**
1. Regime status (VIX, Real Yield, gate open/closed)
2. Days since last trade (if >20 days, highlight)
3. Rolling Sharpe (last 20 trades)
4. Data feed uptime (VIX, FRED)

### 7.4 Walk-Forward Re-Validation

**After 20 Live Trades:**
- Compare live Sharpe vs backtest Sharpe (1.31 target)
- Acceptable range: 0.9 to 1.7 (±30%)
- If outside range: Return to quant for recalibration

**After 50 Live Trades:**
- Full walk-forward re-validation using live data
- Re-optimize VIX/Real Yield thresholds if performance degrades
- Consider expanding trade universe (M15 timeframe, additional entry window)

---

## 8. Comparison with Quant's Conditions

**Quant Analyst's Conditions:**
1. ✅ FRED API for Real Yield data
2. ✅ Paper trading 2-3 months validation
3. ✅ Conservative risk: 0.5% per trade initially
4. ✅ Monitoring alerts for data staleness

**Risk Manager's ADDITIONAL Conditions:**
1. ✅ Graduated risk increase (0.5% → 0.75% → 1.0%) based on performance milestones
2. ✅ Portfolio overlap alert (EUR/GBP/XAU simultaneous signals)
3. ✅ No-trade alert (>30 days dry spell)
4. ✅ Drawdown alert (-5% live threshold, stricter than -15% policy)
5. ✅ Walk-forward re-validation checkpoints (20 trades, 50 trades)
6. ✅ Rollback condition (rolling Sharpe <0.8)

**Assessment:** Quant's conditions are **necessary but not sufficient**. Risk Manager adds **operational safeguards** to protect capital during live deployment.

---

## 9. Alternative Scenarios & Stress Testing

### 9.1 Worst-Case Scenario: All 38 Backtest Trades Failed

**Calculation:**
- 38 trades × 0.5% risk = -19% total drawdown
- With 2.5:1 RR and 44.7% win rate, expected drawdown from losing streak:
  - Worst 10-trade losing streak: -5% (10 × 0.5%)
  - Probability of 10 consecutive losses at 55.3% loss rate: 0.3%

**Backtest Max Drawdown:** -3.61%  
**Expected Worst-Case (0.5% risk):** -5% to -7%

**Policy Limit:** -15%

**Assessment:** ✅ **Safe** — Even under severe stress (10 consecutive losses), drawdown remains well below policy limit.

### 9.2 What if VIX/Real Yield Thresholds Are Wrong?

**Scenario:** Optimized thresholds (VIX 24, RY 1.2%) are overfit to 2024-2026 data.

**Mitigation:**
1. Paper trading will reveal if thresholds are too restrictive (no trades) or too loose (poor performance)
2. Grid search showed "smooth" parameter space (top 5 configs clustered) → suggests thresholds are robust, not fragile
3. Walk-forward re-validation after 50 trades allows recalibration

**Risk Manager Verdict:** Acceptable risk — paper trading serves as out-of-sample test.

### 9.3 What if Gold Enters Multi-Month Consolidation?

**Scenario:** Low VIX (<24) + High Real Yield (>1.2%) persists for 90+ days → zero trades.

**Impact:**
- No losses (strategy stays out)
- Opportunity cost (Gold may still move, but below regime threshold)
- User frustration (no activity)

**Mitigation:**
1. No-trade alert (>30 days) triggers regime review
2. After 60 days, quant reviews if regime filter is too conservative
3. User can manually override (not recommended) or accept strategy is regime-dependent

**Risk Manager Verdict:** Acceptable — capital preservation > forced activity.

---

## 10. Final Risk Assessment

### 10.1 Risk Scorecard

| Risk Category | Level | Mitigated? | Notes |
|--------------|-------|-----------|-------|
| **Max Drawdown** | 🟢 LOW | ✅ YES | -3.61% is 76% below policy limit |
| **Trade Frequency** | 🟡 MODERATE | ✅ YES | Low count (38) but quality-focused + monitoring |
| **Statistical Validity** | 🟡 MODERATE | ⚠️ PARTIAL | Borderline sample size, paper trading required |
| **Correlation Risk** | 🟢 LOW | ✅ YES | XAUUSD diversifies portfolio (+0.35 with EUR/GBP) |
| **Data Dependency** | 🟡 MODERATE | ✅ YES | FRED integration + staleness alerts mandatory |
| **Regime Risk** | 🟡 MODERATE | ✅ YES | User educated on dry spells + monitoring |
| **Overfitting Risk** | 🟡 MODERATE | ⚠️ PARTIAL | Paper trading critical for validation |
| **Session Overlap** | 🟡 MODERATE | ✅ YES | EUR/GBP/XAU overlap alert added |

**Overall Risk Level:** 🟡 **MODERATE (ACCEPTABLE WITH CONDITIONS)**

### 10.2 Risk vs Reward Assessment

**Potential Upside:**
- Sharpe improvement: +0.58 (+79%)
- Drawdown reduction: -47% (from -6.77% to -3.61%)
- Win rate improvement: +9.2pp
- Portfolio Sharpe: 1.21 → ~1.30 (XAUUSD contributes 25% allocation)

**Potential Downside:**
- If regime filter fails: Max -5% to -7% drawdown (with 0.5% risk/trade)
- If overfit: Performance degrades to baseline (Sharpe 0.73) or worse
- Opportunity cost: Missed trades during "false negative" regimes

**Risk/Reward Ratio:** ✅ **FAVORABLE** — Substantial upside with manageable, policy-compliant downside.

---

## 11. FINAL DECISION

### ✅ APPROVE WITH CONDITIONS

**Reasoning:**
1. **Max Drawdown:** -3.61% is excellent (76% below -15% policy limit)
2. **Sharpe Improvement:** +79% improvement moves XAUUSD from non-compliant (0.73) to compliant (1.31)
3. **Walk-Forward Consistency:** 75% positive periods validates robustness
4. **Correlation Risk:** XAUUSD provides portfolio diversification, no increase in correlation risk
5. **Data Dependency:** Moderate risk, fully mitigated by FRED integration + staleness alerts
6. **Quant Validation:** Proposal passed rigorous backtesting, grid search, and walk-forward analysis

**Conditions for Live Deployment:**
1. ✅ **FRED API Integration** (Real Yield: US10Y - CPI)
2. ✅ **Paper Trading Validation** (2-3 months, minimum 10 trades)
3. ✅ **Conservative Initial Risk** (0.5% per trade, increase gradually)
4. ✅ **Monitoring Alerts** (data staleness, no-trade >30 days, drawdown -5%, portfolio overlap)
5. ✅ **Walk-Forward Checkpoints** (review at 20 trades, 50 trades)
6. ✅ **Rollback Condition** (if rolling Sharpe <0.8, revert to previous risk level)

---

## 12. Implementation Authorization

### Can We Proceed to STEP 8 (Implementation)?

**ANSWER:** ⚠️ **CONDITIONAL YES**

**Proceed to STEP 8 IF:**
1. ✅ Trading Strategist confirms FRED API integration is ready
2. ✅ SRE confirms monitoring alerts can be deployed
3. ✅ User acknowledges and approves:
   - Initial 0.5% risk per trade (not 1%)
   - Expected 30-day dry spells during unfavorable regimes
   - Paper trading 2-3 months before live

**HOLD IF:**
- FRED API not integrated (strategy will fail without Real Yield data)
- Monitoring infrastructure not ready (critical for risk management)
- User expects high-frequency trading (this is selective, regime-aware strategy)

**Next Steps:**
1. Trading Strategist: Integrate FRED API, update `strategy/xauusd_signal.py` with regime filter
2. SRE: Deploy monitoring alerts (data staleness, no-trade, drawdown, overlap)
3. Risk Manager: Review paper trading results after 10+ trades, authorize Phase 1 if success criteria met

---

## 13. Risk Manager Notes for Record

**Comparison with Failed USDJPY Proposals:**
- Proposal #1 (Asia Hybrid): Sharpe declined 67% → REJECTED
- Proposal #2 (ATR Filter): Sharpe declined 16% → REJECTED
- **Proposal #3 (XAUUSD Regime):** Sharpe improved 79% → **APPROVED**

**Why #3 Succeeded Where #1/#2 Failed:**
1. Clear problem (overtrading) with proven solution (macro regime filters)
2. Strong economic foundation (VIX, Real Yield)
3. Significant improvement across ALL metrics (Sharpe, DD, WR, consistency)
4. Risk reduction (DD -47%) paired with performance improvement

**Lessons for Future Proposals:**
1. Target strategies with clear, diagnosable problems
2. Prefer economically-grounded solutions over technical indicators alone
3. Validate with walk-forward consistency, not just full-period Sharpe
4. Accept trade-offs (lower frequency for higher quality) when justified

---

**Report Completed:** 2026-05-16 06:30 UTC  
**Risk Manager:** Agent (Conservative Capital Preservation Mandate)  
**Distribution:** Trading Strategist, Quant Analyst, SRE, User  
**Status:** ✅ CONDITIONAL APPROVAL — Proceed to Implementation with Enhanced Risk Controls

---

## Appendix: Policy Compliance Checklist

| Policy Requirement | Proposal Value | Compliant? |
|-------------------|---------------|-----------|
| Max Drawdown ≤ -15% | -3.61% | ✅ YES |
| Daily Max Loss ≤ -3% | -3% (unchanged) | ✅ YES |
| Risk per Trade ≤ 1% | 0.5% (initial) | ✅ YES |
| Min Risk/Reward ≥ 2.0 | 2.5 | ✅ YES |
| Min Sharpe ≥ 1.0 | 1.31 | ✅ YES |
| Max Trades/Day ≤ 3 | 2 (initial) | ✅ YES |

**VERDICT:** ✅ **FULLY COMPLIANT** with all risk management policies.
