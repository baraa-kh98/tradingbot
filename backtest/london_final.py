"""
London Breakout Final — أفضل استراتيجية مثبتة
=================================================
من Grid Search: buffer=3, rr=3.0, min_rng=40pip
نختبر 3 نسخ:
  A. Clean    — بدون trailing (أثبتته الـ grid: +19.11%)
  B. Trail    — مع trailing stop ذكي
  C. Partial  — partial TP عند 1:1 + trail للباقي
"""

import pandas as pd
import numpy as np
import sys, os, warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting import Backtest, Strategy
from backtesting.lib import crossover
from config import PIP_VALUE

H1_CSV = "backtest_data/USDJPY_H1_2years.csv"
H4_CSV = "backtest_data/USDJPY_H4_3years.csv"


# ── Helpers ────────────────────────────────────────────────────

def load_csv(path):
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    # Keep OHLCV + technical indicators (ATR, EMA)
    cols = [c for c in ["Open","High","Low","Close","Volume","ATR","EMA_20","EMA_50"] if c in df.columns]
    return df[cols].dropna()


class _Base(Strategy):
    _h4: pd.DataFrame = None

    def _h4_bias(self, ts) -> str:
        if self._h4 is None or len(self._h4) < 55:
            return "NEUTRAL"
        try:
            past = self._h4[self._h4.index <= ts]
            if len(past) < 55:
                return "NEUTRAL"
            c   = past["Close"].values.astype(float)
            e20 = float(pd.Series(c).ewm(span=20, adjust=False).mean().iloc[-1])
            e50 = float(pd.Series(c).ewm(span=50, adjust=False).mean().iloc[-1])
            if e20 > e50 * 1.0003: return "BULLISH"
            if e20 < e50 * 0.9997: return "BEARISH"
            return "NEUTRAL"
        except Exception:
            return "NEUTRAL"

    def _asia_range(self, idx):
        try:
            ts   = self.data.index[idx]
            ts_d = getattr(ts, "date", lambda: None)()
            lookback = min(idx, 20)
            highs, lows = [], []
            for k in range(lookback, 0, -1):
                bar  = self.data.index[idx - k]
                bh   = getattr(bar, "hour", 0)
                bd   = getattr(bar, "date", lambda: None)()
                if bd == ts_d and 0 <= bh < 7:
                    highs.append(float(self.data.High[idx - k]))
                    lows.append(float(self.data.Low[idx - k]))
            if len(highs) < 3:
                return None, None
            return max(highs), min(lows)
        except Exception:
            return None, None

    def _adx_val(self, period=14) -> float:
        try:
            n  = min(len(self.data)-1, period*5)
            h  = np.array(self.data.High[-n:],  dtype=float)
            l  = np.array(self.data.Low[-n:],   dtype=float)
            c  = np.array(self.data.Close[-n:], dtype=float)
            if len(h) < period + 2: return 0.0
            dh = np.diff(h); dl = -np.diff(l)
            dm_p = np.where((dh > dl) & (dh > 0), dh, 0.0)
            dm_m = np.where((dl > dh) & (dl > 0), dl, 0.0)
            tr   = np.array([max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                             for i in range(1, len(h))])
            def smma(arr, p):
                out = np.zeros(len(arr))
                out[p-1] = arr[:p].mean()
                for i in range(p, len(arr)):
                    out[i] = (out[i-1]*(p-1) + arr[i]) / p
                return out
            atr_s = smma(tr,   period)
            dip   = smma(dm_p, period) / (atr_s + 1e-9) * 100
            dim   = smma(dm_m, period) / (atr_s + 1e-9) * 100
            dx    = np.abs(dip - dim) / (dip + dim + 1e-9) * 100
            return float(np.mean(dx[-period:]))
        except Exception:
            return 0.0


# ═══════════════════════════════════════════════════════════════
# A. CLEAN — أفضل باراميترات من Grid Search
# ═══════════════════════════════════════════════════════════════

class LondonClean(_Base):
    """أفضل نتيجة Grid Search: buffer=3, rr=3.0, min_rng=40"""

    buffer_pips    = 3
    min_rr         = 3.0
    min_range_pips = 40

    def init(self):
        pass

    def next(self):
        idx = len(self.data) - 1
        if idx < 20 or self.position:
            return

        ts   = self.data.index[-1]
        hour = getattr(ts, "hour", -1)
        if not (7 <= hour < 10):
            return

        ah, al = self._asia_range(idx)
        if ah is None:
            return

        pip = PIP_VALUE
        rng = ah - al
        if rng < self.min_range_pips * pip:
            return

        buf   = self.buffer_pips * pip
        price = float(self.data.Close[-1])
        bias  = self._h4_bias(ts)

        if price > ah + buf and bias != "BEARISH":
            sl   = al
            risk = price - sl
            if risk > 0:
                self.buy(sl=sl, tp=price + risk * self.min_rr)

        elif price < al - buf and bias != "BULLISH":
            sl   = ah
            risk = sl - price
            if risk > 0:
                self.sell(sl=sl, tp=price - risk * self.min_rr)


# ═══════════════════════════════════════════════════════════════
# B. TRAIL — مع Trailing Stop (يتحرك بعد 1:1 للـ Breakeven)
# ═══════════════════════════════════════════════════════════════

class LondonTrail(_Base):
    """
    نفس London Clean + Trailing Stop:
    - عند 1×risk نحرك SL للـ breakeven
    - عند 2×risk نحرك SL لـ 1×risk (lock profit)
    - نبقي TP عند 3×risk
    """

    buffer_pips    = 3
    min_rr         = 3.0
    min_range_pips = 40

    def init(self):
        self._entry  = 0.0
        self._risk   = 0.0
        self._sl_raw = 0.0
        self._long   = True

    def next(self):
        idx = len(self.data) - 1
        if idx < 20:
            return

        ts    = self.data.index[-1]
        hour  = getattr(ts, "hour", -1)
        price = float(self.data.Close[-1])

        # ── Trailing ─────────────────────────────────────────
        if self.position and self._risk > 0:
            profit = (price - self._entry) if self._long else (self._entry - price)
            # Stage 1: profit >= 1×risk → move SL to breakeven
            if profit >= self._risk and self._sl_raw < self._entry:
                self._sl_raw = self._entry
                for t in self.trades:
                    if t.is_long == self._long:
                        t.sl = round(self._sl_raw, 5)
            # Stage 2: profit >= 2×risk → move SL to +1×risk
            elif profit >= 2 * self._risk:
                new_sl = self._entry + self._risk if self._long else self._entry - self._risk
                if (self._long and new_sl > self._sl_raw) or \
                   (not self._long and new_sl < self._sl_raw):
                    self._sl_raw = new_sl
                    for t in self.trades:
                        if t.is_long == self._long:
                            t.sl = round(self._sl_raw, 5)
            return

        if self.position:
            return

        if not (7 <= hour < 10):
            return

        ah, al = self._asia_range(idx)
        if ah is None:
            return

        pip = PIP_VALUE
        rng = ah - al
        if rng < self.min_range_pips * pip:
            return

        buf  = self.buffer_pips * pip
        bias = self._h4_bias(ts)

        if price > ah + buf and bias != "BEARISH":
            sl   = al
            risk = price - sl
            if risk > 0:
                self._entry  = price
                self._risk   = risk
                self._sl_raw = sl
                self._long   = True
                self.buy(sl=sl, tp=price + risk * self.min_rr)

        elif price < al - buf and bias != "BULLISH":
            sl   = ah
            risk = sl - price
            if risk > 0:
                self._entry  = price
                self._risk   = risk
                self._sl_raw = sl
                self._long   = False
                self.sell(sl=sl, tp=price - risk * self.min_rr)


# ═══════════════════════════════════════════════════════════════
# C. PARTIAL — Partial TP عند 1.5:1 + trail للباقي
# ═══════════════════════════════════════════════════════════════

class LondonPartial(_Base):
    """
    نفس الدخول + إدارة الخروج الذكية:
    - TP1 عند 1.5×risk (أخذ 50% من المركز)
    - TP2 عند 3.0×risk (الـ 50% الباقية)
    - لا يوجد trailing (الـ backtesting.py لا يدعم partial close بسهولة)
    بديل: نتداول بـ SL=risk، TP=1.5×risk للنصف + TP=3×risk للنصف
    نحقق هذا بـ 2 صفقات بنفس الاتجاه (size=0.5 لكل واحدة)
    """

    buffer_pips    = 3
    min_rr_1       = 1.5   # TP الأول
    min_rr_2       = 3.0   # TP الثاني
    min_range_pips = 40

    def init(self):
        self._today_traded = None

    def next(self):
        idx = len(self.data) - 1
        if idx < 20 or self.position:
            return

        ts   = self.data.index[-1]
        hour = getattr(ts, "hour", -1)
        date = getattr(ts, "date", lambda: None)()

        if not (7 <= hour < 10):
            return

        if self._today_traded == date:
            return

        ah, al = self._asia_range(idx)
        if ah is None:
            return

        pip = PIP_VALUE
        rng = ah - al
        if rng < self.min_range_pips * pip:
            return

        buf   = self.buffer_pips * pip
        price = float(self.data.Close[-1])
        bias  = self._h4_bias(ts)

        if price > ah + buf and bias != "BEARISH":
            sl   = al
            risk = price - sl
            if risk > 0:
                # صفقة 1: TP عند 1.5× (نصف المكسب بسرعة)
                self.buy(sl=sl, tp=price + risk * self.min_rr_1,  size=0.45)
                # صفقة 2: TP عند 3.0× (ندع الباقي يجري)
                self.buy(sl=sl, tp=price + risk * self.min_rr_2,  size=0.45)
                self._today_traded = date

        elif price < al - buf and bias != "BULLISH":
            sl   = ah
            risk = sl - price
            if risk > 0:
                self.sell(sl=sl, tp=price - risk * self.min_rr_1, size=0.45)
                self.sell(sl=sl, tp=price - risk * self.min_rr_2, size=0.45)
                self._today_traded = date


# ═══════════════════════════════════════════════════════════════
# D. WIDE WINDOW — 07:00-11:00 بدلاً من 07:00-10:00
# ═══════════════════════════════════════════════════════════════

class LondonWide(_Base):
    """نفس الأفضل لكن نافذة أوسع 7-11 لمزيد من الصفقات"""

    buffer_pips    = 3
    min_rr         = 3.0
    min_range_pips = 40
    hour_end       = 11

    def init(self):
        pass

    def next(self):
        idx = len(self.data) - 1
        if idx < 20 or self.position:
            return

        ts   = self.data.index[-1]
        hour = getattr(ts, "hour", -1)
        if not (7 <= hour < self.hour_end):
            return

        ah, al = self._asia_range(idx)
        if ah is None:
            return

        pip = PIP_VALUE
        rng = ah - al
        if rng < self.min_range_pips * pip:
            return

        buf   = self.buffer_pips * pip
        price = float(self.data.Close[-1])
        bias  = self._h4_bias(ts)

        if price > ah + buf and bias != "BEARISH":
            sl   = al
            risk = price - sl
            if risk > 0:
                self.buy(sl=sl, tp=price + risk * self.min_rr)

        elif price < al - buf and bias != "BULLISH":
            sl   = ah
            risk = sl - price
            if risk > 0:
                self.sell(sl=sl, tp=price - risk * self.min_rr)


# ═══════════════════════════════════════════════════════════════
# E. ADX FILTER — ADX > 20 للتداول فقط في الأسواق الاتجاهية
# ═══════════════════════════════════════════════════════════════

class LondonADX(_Base):
    """نفس الأفضل + اشتراط ADX > 20 (لتجنب الأسواق الجانبية)"""

    buffer_pips    = 3
    min_rr         = 3.0
    min_range_pips = 40
    adx_min        = 20

    def init(self):
        pass

    def next(self):
        idx = len(self.data) - 1
        if idx < 25 or self.position:
            return

        ts   = self.data.index[-1]
        hour = getattr(ts, "hour", -1)
        if not (7 <= hour < 10):
            return

        ah, al = self._asia_range(idx)
        if ah is None:
            return

        pip = PIP_VALUE
        rng = ah - al
        if rng < self.min_range_pips * pip:
            return

        if self._adx_val() < self.adx_min:
            return

        buf   = self.buffer_pips * pip
        price = float(self.data.Close[-1])
        bias  = self._h4_bias(ts)

        if price > ah + buf and bias != "BEARISH":
            sl   = al
            risk = price - sl
            if risk > 0:
                self.buy(sl=sl, tp=price + risk * self.min_rr)

        elif price < al - buf and bias != "BULLISH":
            sl   = ah
            risk = sl - price
            if risk > 0:
                self.sell(sl=sl, tp=price - risk * self.min_rr)


# ═══════════════════════════════════════════════════════════════
# F. ASIA/LONDON HYBRID — Proposal from Trading Strategist 2026-05-16
# ═══════════════════════════════════════════════════════════════

class LondonAsiaHybrid(_Base):
    """
    Asia/London Hybrid — Range 00:00-02:59, Entry 03:00-09:59
    Proposed by Trading Strategist 2026-05-16
    Target: Sharpe 0.97 → 1.25-1.45
    """

    buffer_pips    = 3
    min_rr         = 3.0
    min_range_pips = 40
    max_range_pips = 200

    asia_range_start  = 0   # 00:00 UTC (Tokyo morning)
    asia_range_end    = 3   # 02:59 UTC (Tokyo mid-session)
    entry_start       = 3   # 03:00 UTC (late Asia entry begins)
    entry_end         = 10  # 09:59 UTC (London morning entry ends)

    def init(self):
        pass

    def next(self):
        idx = len(self.data) - 1
        if idx < 20 or self.position:
            return

        ts   = self.data.index[-1]
        hour = getattr(ts, "hour", -1)

        # Entry window check: 03:00-09:59 UTC
        if not (self.entry_start <= hour < self.entry_end):
            return

        # Calculate Asia range (00:00-02:59) using custom method
        ah, al = self._asia_range_custom(idx)
        if ah is None:
            return

        pip = PIP_VALUE
        rng = ah - al
        if rng < self.min_range_pips * pip or rng > self.max_range_pips * pip:
            return

        buf   = self.buffer_pips * pip
        price = float(self.data.Close[-1])
        bias  = self._h4_bias(ts)

        # Entry logic (same as LondonClean)
        if price > ah + buf and bias != "BEARISH":
            sl   = al
            risk = price - sl
            if risk > 0:
                self.buy(sl=sl, tp=price + risk * self.min_rr)

        elif price < al - buf and bias != "BULLISH":
            sl   = ah
            risk = sl - price
            if risk > 0:
                self.sell(sl=sl, tp=price - risk * self.min_rr)

    def _asia_range_custom(self, idx):
        """Calculate range for 00:00-02:59 UTC (Tokyo morning core)"""
        try:
            ts   = self.data.index[idx]
            ts_d = getattr(ts, "date", lambda: None)()
            lookback = min(idx, 20)
            highs, lows = [], []
            for k in range(lookback, 0, -1):
                bar  = self.data.index[idx - k]
                bh   = getattr(bar, "hour", 0)
                bd   = getattr(bar, "date", lambda: None)()
                if bd == ts_d and self.asia_range_start <= bh < self.asia_range_end:
                    highs.append(float(self.data.High[idx - k]))
                    lows.append(float(self.data.Low[idx - k]))
            if len(highs) < 2:  # Need at least 2 hours (narrower window)
                return None, None
            return max(highs), min(lows)
        except Exception:
            return None, None


# ═══════════════════════════════════════════════════════════════
# G. ATR FILTER — Proposal #2 from Trading Strategist 2026-05-16
# ═══════════════════════════════════════════════════════════════

class LondonATRFilter(_Base):
    """
    ATR Volatility Quality Filter — Proposal #2 (2026-05-16)
    Same as LondonClean + ATR threshold to filter low-volatility days
    Target: Sharpe 0.97 → 1.25-1.40 via quality filtering
    """

    buffer_pips    = 3
    min_rr         = 3.0
    min_range_pips = 40
    max_range_pips = 200
    min_atr        = 0.25  # ATR threshold (50th-75th percentile)

    def init(self):
        pass

    def next(self):
        idx = len(self.data) - 1
        if idx < 20 or self.position:
            return

        ts   = self.data.index[-1]
        hour = getattr(ts, "hour", -1)
        if not (7 <= hour < 10):
            return

        ah, al = self._asia_range(idx)
        if ah is None:
            return

        pip = PIP_VALUE
        rng = ah - al
        if rng < self.min_range_pips * pip:
            return
        if rng > self.max_range_pips * pip:
            return

        # NEW: ATR quality filter
        if hasattr(self.data, "ATR") and len(self.data.ATR) > idx:
            try:
                current_atr = float(self.data.ATR[-1])
                if current_atr < self.min_atr:
                    return  # Skip low-volatility days
            except Exception:
                pass  # If ATR missing/invalid, proceed without filter

        buf   = self.buffer_pips * pip
        price = float(self.data.Close[-1])
        bias  = self._h4_bias(ts)

        if price > ah + buf and bias != "BEARISH":
            sl   = al
            risk = price - sl
            if risk > 0:
                self.buy(sl=sl, tp=price + risk * self.min_rr)

        elif price < al - buf and bias != "BULLISH":
            sl   = ah
            risk = sl - price
            if risk > 0:
                self.sell(sl=sl, tp=price - risk * self.min_rr)


# ═══════════════════════════════════════════════════════════════
# RUN & COMPARE
# ═══════════════════════════════════════════════════════════════

def fmt(r, name):
    pf = r.get("Profit Factor", 0) or 0
    pf = 0.0 if (isinstance(pf, float) and np.isnan(pf)) else float(pf)
    sh = float(r["Sharpe Ratio"])  if not np.isnan(r["Sharpe Ratio"])  else 0.0
    wr = float(r["Win Rate [%]"])  if not np.isnan(r["Win Rate [%]"])  else 0.0
    ret = float(r["Return [%]"])
    dd  = float(r["Max. Drawdown [%]"])
    tr  = r["# Trades"]
    print(f"\n{'═'*55}")
    print(f"  {name}")
    print(f"{'═'*55}")
    print(f"  📊 صفقات  : {tr}     |  🎯 WR: {wr:.1f}%")
    print(f"  💰 الربح  : {ret:.2f}%  |  📉 DD: {dd:.2f}%")
    print(f"  📐 Sharpe : {sh:.2f}   |  ⚖️  PF: {pf:.2f}")
    return {"ret": ret, "sh": sh, "dd": dd, "wr": wr, "pf": pf, "tr": tr}


def atr_sweep():
    """
    ATR Threshold Parameter Sweep for Proposal #2 Validation
    Tests: [0.20, 0.22, 0.25, 0.28, 0.30]
    Goal: Find optimal threshold that maximizes Sharpe while maintaining ≥40 trades
    """
    print("\n" + "═"*60)
    print("  🔬 ATR FILTER PARAMETER SWEEP (Proposal #2)")
    print("  Testing ATR thresholds: 0.20 → 0.30")
    print("═"*60)

    h1 = load_csv(H1_CSV)
    h4 = load_csv(H4_CSV)
    if h1 is None:
        print("❌ H1 data missing"); return None

    # Check for ATR column
    if "ATR" not in h1.columns:
        print("❌ ATR column missing from data"); return None

    print(f"  ✅ H1: {len(h1):,} candles | {h1.index[0].date()} → {h1.index[-1].date()}")
    print(f"  ✅ ATR column found")

    # ATR statistics
    atr_vals = h1["ATR"].dropna()
    print(f"\n  📊 ATR Statistics (USDJPY H1, {len(atr_vals):,} bars):")
    print(f"     25th percentile: {atr_vals.quantile(0.25):.3f}")
    print(f"     50th percentile: {atr_vals.quantile(0.50):.3f}")
    print(f"     75th percentile: {atr_vals.quantile(0.75):.3f}")
    print(f"     90th percentile: {atr_vals.quantile(0.90):.3f}")

    LondonATRFilter._h4 = h4
    cash = 10_000
    comm = 0.0002

    thresholds = [0.20, 0.22, 0.25, 0.28, 0.30]
    results = {}

    print(f"\n{'═'*78}")
    print(f"  {'ATR':>6} {'Trades':>7} {'Win%':>7} {'Return%':>8} {'DD%':>7} {'Sharpe':>7} {'PF':>5}")
    print(f"  {'-'*72}")

    for threshold in thresholds:
        LondonATRFilter.min_atr = threshold
        bt = Backtest(h1, LondonATRFilter, cash=cash, commission=comm)
        r  = bt.run()

        pf = r.get("Profit Factor", 0) or 0
        pf = 0.0 if (isinstance(pf, float) and np.isnan(pf)) else float(pf)
        sh = float(r["Sharpe Ratio"])  if not np.isnan(r["Sharpe Ratio"])  else 0.0
        wr = float(r["Win Rate [%]"])  if not np.isnan(r["Win Rate [%]"])  else 0.0
        ret = float(r["Return [%]"])
        dd  = float(r["Max. Drawdown [%]"])
        tr  = r["# Trades"]

        results[threshold] = {
            "sh": sh, "ret": ret, "dd": dd, "wr": wr, "pf": pf, "tr": tr
        }

        print(f"  {threshold:>6.2f} {tr:>7} {wr:>7.1f} {ret:>8.2f} {dd:>7.2f} {sh:>7.2f} {pf:>5.2f}")

    # Find optimal threshold
    valid = {k: v for k, v in results.items() if v["tr"] >= 40}
    if not valid:
        print(f"\n⚠️  All thresholds resulted in <40 trades. Lowering criteria to ≥30 trades.")
        valid = {k: v for k, v in results.items() if v["tr"] >= 30}

    if valid:
        best_threshold = max(valid, key=lambda k: valid[k]["sh"])
        best_stats = valid[best_threshold]

        print(f"\n{'═'*60}")
        print(f"  🏆 OPTIMAL THRESHOLD: {best_threshold:.2f}")
        print(f"     Sharpe: {best_stats['sh']:.2f} | Trades: {best_stats['tr']} | Win Rate: {best_stats['wr']:.1f}%")
        print(f"     Return: {best_stats['ret']:.2f}% | DD: {best_stats['dd']:.2f}%")
    else:
        best_threshold = None
        best_stats = None
        print(f"\n❌ No valid threshold found (all have <30 trades)")

    return {
        "threshold": best_threshold,
        "stats": best_stats,
        "all_results": results
    }


def validate_proposal_2():
    """
    Validate Proposal #2: ATR Volatility Quality Filter
    Compare LondonClean (baseline) vs LondonATRFilter (proposed)
    Decision criteria: Sharpe ≥ 1.25, Win Rate ≥ 40%, Trades ≥ 30
    """
    print("\n" + "═"*70)
    print("  🔬 PROPOSAL #2 VALIDATION: ATR Volatility Quality Filter")
    print("  Baseline: LondonTrail (Sharpe 0.97) vs ATR Filter (Target 1.25+)")
    print("═"*70)

    h1 = load_csv(H1_CSV)
    h4 = load_csv(H4_CSV)
    if h1 is None:
        print("❌ H1 data missing"); return None

    if "ATR" not in h1.columns:
        print("❌ ATR column missing from data"); return None

    print(f"  ✅ H1: {len(h1):,} candles | {h1.index[0].date()} → {h1.index[-1].date()}")

    for cls in [LondonTrail, LondonATRFilter]:
        cls._h4 = h4

    cash = 10_000
    comm = 0.0002

    # Step 1: Run baseline (LondonTrail - current best)
    print("\n" + "─"*70)
    print("  📊 BASELINE: LondonTrail (Current Live Strategy)")
    print("─"*70)
    bt_baseline = Backtest(h1, LondonTrail, cash=cash, commission=comm)
    r_baseline  = bt_baseline.run()
    stats_baseline = fmt(r_baseline, "Baseline: LondonTrail")

    # Step 2: Run ATR sweep to find optimal threshold
    print("\n" + "─"*70)
    print("  🔬 ATR THRESHOLD SWEEP")
    print("─"*70)
    sweep_results = atr_sweep()

    if sweep_results is None or sweep_results["threshold"] is None:
        print("\n❌ ATR sweep failed or no valid threshold found")
        return None

    best_threshold = sweep_results["threshold"]
    best_stats = sweep_results["stats"]

    # Step 3: Calculate improvement metrics
    print("\n" + "═"*70)
    print("  📈 RESULTS COMPARISON")
    print("═"*70)

    sharpe_improvement = best_stats["sh"] - stats_baseline["sh"]
    wr_improvement = best_stats["wr"] - stats_baseline["wr"]
    return_improvement = best_stats["ret"] - stats_baseline["ret"]
    dd_change = best_stats["dd"] - stats_baseline["dd"]
    trade_change = best_stats["tr"] - stats_baseline["tr"]

    print(f"\n  Baseline (LondonTrail):")
    print(f"    Sharpe: {stats_baseline['sh']:.2f} | Win Rate: {stats_baseline['wr']:.1f}% | Trades: {stats_baseline['tr']}")
    print(f"    Return: {stats_baseline['ret']:.2f}% | DD: {stats_baseline['dd']:.2f}%")

    print(f"\n  Proposed (ATR Filter @ {best_threshold:.2f}):")
    print(f"    Sharpe: {best_stats['sh']:.2f} | Win Rate: {best_stats['wr']:.1f}% | Trades: {best_stats['tr']}")
    print(f"    Return: {best_stats['ret']:.2f}% | DD: {best_stats['dd']:.2f}%")

    print(f"\n  DELTA (Proposed - Baseline):")
    print(f"    Sharpe:    {sharpe_improvement:+.2f} ({sharpe_improvement/stats_baseline['sh']*100:+.1f}%)")
    print(f"    Win Rate:  {wr_improvement:+.1f}pp")
    print(f"    Return:    {return_improvement:+.2f}pp")
    print(f"    Drawdown:  {dd_change:+.2f}pp")
    print(f"    Trades:    {trade_change:+.0f} ({trade_change/stats_baseline['tr']*100:+.1f}%)")

    # Step 4: Decision logic
    print("\n" + "═"*70)
    print("  🎯 DECISION CRITERIA EVALUATION")
    print("═"*70)

    criteria = {
        "Sharpe ≥ 1.25": best_stats["sh"] >= 1.25,
        "Win Rate ≥ 40%": best_stats["wr"] >= 40.0,
        "Trades ≥ 30": best_stats["tr"] >= 30,
        "Sharpe improvement ≥ +0.15": sharpe_improvement >= 0.15,
        "Max DD ≤ 10%": best_stats["dd"] <= 10.0,
    }

    for criterion, passed in criteria.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {criterion}")

    passed_count = sum(criteria.values())
    total_count = len(criteria)

    print(f"\n  Criteria Met: {passed_count}/{total_count}")

    # Final decision
    if passed_count >= 4:
        decision = "APPROVE"
        recommendation = f"Apply ATR threshold {best_threshold:.2f} to strategy/london_signal.py"
        color = "✅"
    elif passed_count >= 3:
        decision = "CONDITIONAL APPROVE"
        recommendation = f"ATR {best_threshold:.2f} shows improvement but needs paper trading validation"
        color = "⚠️"
    else:
        decision = "REJECT"
        recommendation = "ATR filter insufficient improvement, explore alternative approaches"
        color = "❌"

    print(f"\n{'═'*70}")
    print(f"  {color} FINAL DECISION: {decision}")
    print(f"  Recommendation: {recommendation}")
    print(f"{'═'*70}\n")

    return {
        "decision": decision,
        "baseline": stats_baseline,
        "proposed": best_stats,
        "threshold": best_threshold,
        "improvement": {
            "sharpe": sharpe_improvement,
            "win_rate": wr_improvement,
            "return": return_improvement,
            "drawdown": dd_change,
            "trades": trade_change
        },
        "criteria": criteria
    }


def run():
    print("\n" + "═"*60)
    print("  🏆 London Breakout — Final Comparison")
    print("  هدف: أفضل Sharpe مع > 20% ربح / سنة")
    print("═"*60)

    h1 = load_csv(H1_CSV)
    h4 = load_csv(H4_CSV)
    if h1 is None:
        print("❌ H1 غير موجود"); return

    print(f"  ✅ H1: {len(h1):,} شمعة | {h1.index[0].date()} → {h1.index[-1].date()}")
    if h4 is not None:
        print(f"  ✅ H4: {len(h4):,} شمعة")

    for cls in [LondonClean, LondonTrail, LondonPartial, LondonWide, LondonADX, LondonAsiaHybrid, LondonATRFilter]:
        cls._h4 = h4

    cash = 10_000
    comm = 0.0002

    strategies = [
        ("A. London Clean  (grid best: buf=3,rr=3,rng≥40)",  LondonClean),
        ("B. London Trail  (trailing after 1:1 → breakeven)", LondonTrail),
        ("C. London Partial (50% at 1.5:1, 50% at 3:1)",     LondonPartial),
        ("D. London Wide   (07-11 window, more trades)",      LondonWide),
        ("E. London ADX    (ADX>20 filter)",                  LondonADX),
        ("F. Asia Hybrid   (range 00-03, entry 03-10)",       LondonAsiaHybrid),
        ("G. ATR Filter    (ATR≥0.25 quality filter)",        LondonATRFilter),
    ]

    stats_all = {}
    bts = {}
    for label, cls in strategies:
        bt = Backtest(h1, cls, cash=cash, commission=comm, finalize_trades=True)
        r  = bt.run()
        stats_all[label.split()[1]] = fmt(r, label)
        bts[label.split()[1]] = bt

    # ── نختار الفائز ──────────────────────────────────────────
    def score(s):
        if s["tr"] < 30: return -999
        return s["sh"] * 4 + s["ret"] * 0.3 - abs(s["dd"]) * 0.2 + (s["pf"] - 1) * 3

    winner = max(stats_all, key=lambda k: score(stats_all[k]))
    winner_stats = stats_all[winner]

    print(f"\n{'═'*60}")
    print(f"  🏆 الفائز: {winner}")
    print(f"     الربح: {winner_stats['ret']:.2f}% | Sharpe: {winner_stats['sh']:.2f} | DD: {winner_stats['dd']:.2f}%")

    # ── ملخص المقارنة ────────────────────────────────────────
    print(f"\n{'═'*78}")
    print(f"  {'الاستراتيجية':10s} {'صفقات':>7} {'ربح%':>7} {'DD%':>7} {'Sharpe':>7} {'PF':>5} {'Score':>7}")
    print(f"  {'-'*72}")
    for k, s in stats_all.items():
        sc = score(s)
        mark = " 🏆" if k == winner else ""
        print(f"  {k:10s} {s['tr']:>7} {s['ret']:>7.2f} {s['dd']:>7.2f} {s['sh']:>7.2f} {s['pf']:>5.2f} {sc:>7.2f}{mark}")

    # ── حفظ الشارت للفائز ────────────────────────────────────
    print(f"\n💾 حفظ الشارتات...")
    for k, bt in bts.items():
        bt.plot(filename=f"London_{k}", open_browser=False)
    print(f"  ✅ London_Clean.html | London_Trail.html | London_Partial.html | ...")

    print(f"\n{'═'*60}")
    print(f"  📝 الخطوة التالية: دمج الاستراتيجية الفائزة في main.py")
    print(f"{'═'*60}\n")

    return stats_all, winner


if __name__ == "__main__":
    # Run Proposal #2 validation
    validation_result = validate_proposal_2()

    # Optionally run full comparison
    # run()
