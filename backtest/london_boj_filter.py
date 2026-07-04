"""
USDJPY London Breakout — BOJ Zone Filter Backtest
===================================================
التاريخ: 2026-07-04 (نافذة الصيانة — السبت)
الهدف: رفع Sharpe USDJPY من 0.97 → ≥ 1.5

الفرضية:
  BOJ يتدخل بشكل تاريخي عند مستويات معينة من USDJPY:
  - فوق 155: BOJ يهدد بتدخل لتقوية JPY → فرص SELL أفضل جودة
  - تحت 147: BOJ يريد JPY ضعيف → فرص BUY أفضل جودة
  - 147-155: منطقة تدخل مزدوجة → spreads عالية + false breakouts

الفلتر المقترح [F]:
  - BUY فقط عند price < 147 (JPY قوي — BOJ يدعم الضعف)
  - SELL فقط عند price > 155 (JPY ضعيف — BOJ يهدد بالتدخل)
  - 147-155: لا تداول (منطقة محايدة)

النتائج المستهدفة:
  - Sharpe ≥ 1.5
  - Win Rate ≥ 40%
  - Max DD ≤ 10%
  - Trades ≥ 20 (نعترف أن التصفية ستقلل الصفقات)
"""

import pandas as pd
import numpy as np
import sys, os, warnings
warnings.filterwarnings("ignore")

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


# ═══════════════════════════════════════════════════════════════
# BASELINE — London Clean (مرجع المقارنة)
# ═══════════════════════════════════════════════════════════════

class LondonBaseline(_Base):
    """Baseline بدون فلتر — نفس الاستراتيجية الحالية"""
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

        # Trailing Stop Management
        if self.position and self._risk > 0:
            profit = (price - self._entry) if self._long else (self._entry - price)
            if profit >= self._risk and self._sl_raw < self._entry:
                self._sl_raw = self._entry
                for t in self.trades:
                    if t.is_long == self._long:
                        t.sl = round(self._sl_raw, 5)
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
# BOJ ZONE FILTER — النسخة الرئيسية
# ═══════════════════════════════════════════════════════════════

class LondonBOJFilter(_Base):
    """
    London Breakout + BOJ Zone Filter
    - BUY فقط عند price < boj_buy_zone (< 147)
    - SELL فقط عند price > boj_sell_zone (> 155)
    - 147-155: تجاهل تام (منطقة التدخل المزدوج)
    """
    buffer_pips    = 3
    min_rr         = 3.0
    min_range_pips = 40
    boj_buy_zone   = 147.0   # BUY فقط تحت هذا
    boj_sell_zone  = 155.0   # SELL فقط فوق هذا

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

        # Trailing Stop Management
        if self.position and self._risk > 0:
            profit = (price - self._entry) if self._long else (self._entry - price)
            if profit >= self._risk and self._sl_raw < self._entry:
                self._sl_raw = self._entry
                for t in self.trades:
                    if t.is_long == self._long:
                        t.sl = round(self._sl_raw, 5)
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

        # BUY signal — فقط تحت منطقة BOJ الشرائية
        if price > ah + buf and bias != "BEARISH":
            if price < self.boj_buy_zone:   # ← BOJ Filter: BUY فقط < 147
                sl   = al
                risk = price - sl
                if risk > 0:
                    self._entry  = price
                    self._risk   = risk
                    self._sl_raw = sl
                    self._long   = True
                    self.buy(sl=sl, tp=price + risk * self.min_rr)

        # SELL signal — فقط فوق منطقة BOJ البيعية
        elif price < al - buf and bias != "BULLISH":
            if price > self.boj_sell_zone:  # ← BOJ Filter: SELL فقط > 155
                sl   = ah
                risk = sl - price
                if risk > 0:
                    self._entry  = price
                    self._risk   = risk
                    self._sl_raw = sl
                    self._long   = False
                    self.sell(sl=sl, tp=price - risk * self.min_rr)


# ═══════════════════════════════════════════════════════════════
# RELAXED BOJ FILTER — نطاق أوسع (145-157)
# ═══════════════════════════════════════════════════════════════

class LondonBOJRelaxed(_Base):
    """
    BOJ Filter مخفّف: نطاق أضيق للمنطقة الحيادية
    - BUY فقط عند price < 145
    - SELL فقط عند price > 157
    - 145-157: تجاهل
    """
    buffer_pips    = 3
    min_rr         = 3.0
    min_range_pips = 40
    boj_buy_zone   = 145.0
    boj_sell_zone  = 157.0

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

        if self.position and self._risk > 0:
            profit = (price - self._entry) if self._long else (self._entry - price)
            if profit >= self._risk and self._sl_raw < self._entry:
                self._sl_raw = self._entry
                for t in self.trades:
                    if t.is_long == self._long:
                        t.sl = round(self._sl_raw, 5)
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
            if price < self.boj_buy_zone:
                sl   = al
                risk = price - sl
                if risk > 0:
                    self._entry  = price
                    self._risk   = risk
                    self._sl_raw = sl
                    self._long   = True
                    self.buy(sl=sl, tp=price + risk * self.min_rr)

        elif price < al - buf and bias != "BULLISH":
            if price > self.boj_sell_zone:
                sl   = ah
                risk = sl - price
                if risk > 0:
                    self._entry  = price
                    self._risk   = risk
                    self._sl_raw = sl
                    self._long   = False
                    self.sell(sl=sl, tp=price - risk * self.min_rr)


# ═══════════════════════════════════════════════════════════════
# DIRECTIONAL ONLY — بدون منطقة محايدة، لكن مع تصفية اتجاه
# ═══════════════════════════════════════════════════════════════

class LondonDirectional(_Base):
    """
    بديل: لا منطقة حيادية، لكن الإشارة يجب أن تكون مع اتجاه BOJ:
    - فوق 151: SELL فقط (BUY موقوف — خطر تدخل BOJ لتقوية JPY)
    - تحت 149: BUY فقط (SELL موقوف — JPY قوي ما يناسب)
    - 149-151: كلا الاتجاهين مسموحان
    """
    buffer_pips    = 3
    min_rr         = 3.0
    min_range_pips = 40
    boj_upper      = 151.0   # فوقه: BUY محظور
    boj_lower      = 149.0   # تحته: SELL محظور

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

        if self.position and self._risk > 0:
            profit = (price - self._entry) if self._long else (self._entry - price)
            if profit >= self._risk and self._sl_raw < self._entry:
                self._sl_raw = self._entry
                for t in self.trades:
                    if t.is_long == self._long:
                        t.sl = round(self._sl_raw, 5)
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
            # BUY: حظر إذا السعر فوق boj_upper (BOJ قد يتدخل ضد الارتفاع)
            if price <= self.boj_upper:
                sl   = al
                risk = price - sl
                if risk > 0:
                    self._entry  = price
                    self._risk   = risk
                    self._sl_raw = sl
                    self._long   = True
                    self.buy(sl=sl, tp=price + risk * self.min_rr)

        elif price < al - buf and bias != "BULLISH":
            # SELL: حظر إذا السعر تحت boj_lower (JPY قوي ما يدعم SELL)
            if price >= self.boj_lower:
                sl   = ah
                risk = sl - price
                if risk > 0:
                    self._entry  = price
                    self._risk   = risk
                    self._sl_raw = sl
                    self._long   = False
                    self.sell(sl=sl, tp=price - risk * self.min_rr)


# ═══════════════════════════════════════════════════════════════
# PARAMETER SWEEP — اختبار مستويات مختلفة لـ boj_buy/sell_zone
# ═══════════════════════════════════════════════════════════════

def boj_zone_sweep(h1, h4):
    """Grid search على مستويات BOJ Zone المختلفة"""
    print("\n" + "═"*75)
    print("  🔬 BOJ ZONE PARAMETER SWEEP")
    print("  Testing different buy_zone/sell_zone thresholds")
    print("═"*75)

    # مستويات للاختبار: (buy_zone, sell_zone)
    # المنطق: buy_zone < sell_zone دائماً
    # نختبر 8 مجموعات مختلفة
    param_sets = [
        (145.0, 155.0),  # ضيق جداً
        (146.0, 154.0),
        (147.0, 153.0),
        (147.0, 155.0),  # الأصل المقترح
        (148.0, 155.0),
        (147.0, 157.0),
        (145.0, 157.0),
        (149.0, 156.0),
    ]

    print(f"\n  {'Buy<':>8} {'Sell>':>8} {'Trades':>7} {'Win%':>7} {'Return%':>9} {'DD%':>7} {'Sharpe':>8}")
    print(f"  {'-'*70}")

    results = []
    for buy_z, sell_z in param_sets:
        LondonBOJFilter.boj_buy_zone  = buy_z
        LondonBOJFilter.boj_sell_zone = sell_z
        LondonBOJFilter._h4 = h4

        bt = Backtest(h1, LondonBOJFilter, cash=10_000, commission=0.0002)
        r  = bt.run()

        sh  = float(r["Sharpe Ratio"])  if not np.isnan(r["Sharpe Ratio"])  else 0.0
        wr  = float(r["Win Rate [%]"])  if not np.isnan(r["Win Rate [%]"])  else 0.0
        ret = float(r["Return [%]"])
        dd  = float(r["Max. Drawdown [%]"])
        tr  = r["# Trades"]

        print(f"  {buy_z:>8.1f} {sell_z:>8.1f} {tr:>7} {wr:>7.1f} {ret:>9.2f} {dd:>7.2f} {sh:>8.2f}")
        results.append({"buy": buy_z, "sell": sell_z, "sh": sh, "wr": wr,
                        "ret": ret, "dd": dd, "tr": tr})

    # أفضل نتيجة بـ trades >= 20
    valid = [r for r in results if r["tr"] >= 15]
    if valid:
        best = max(valid, key=lambda x: x["sh"])
        print(f"\n  🏆 BEST (trades ≥ 15): buy < {best['buy']:.1f} | sell > {best['sell']:.1f}")
        print(f"     Sharpe: {best['sh']:.2f} | WR: {best['wr']:.1f}% | Return: {best['ret']:.2f}%")
        print(f"     DD: {best['dd']:.2f}% | Trades: {best['tr']}")
    else:
        best = None
        print("\n  ⚠️  كل الإعدادات أنتجت < 15 صفقة — الفلتر مقيّد جداً")

    return results, best


def fmt_result(r, name):
    pf = r.get("Profit Factor", 0) or 0
    pf = 0.0 if (isinstance(pf, float) and np.isnan(pf)) else float(pf)
    sh  = float(r["Sharpe Ratio"])  if not np.isnan(r["Sharpe Ratio"])  else 0.0
    wr  = float(r["Win Rate [%]"])  if not np.isnan(r["Win Rate [%]"])  else 0.0
    ret = float(r["Return [%]"])
    dd  = float(r["Max. Drawdown [%]"])
    tr  = r["# Trades"]

    print(f"\n{'═'*60}")
    print(f"  {name}")
    print(f"{'═'*60}")
    print(f"  📊 صفقات  : {tr}     |  🎯 WR: {wr:.1f}%")
    print(f"  💰 الربح  : {ret:.2f}%  |  📉 DD: {dd:.2f}%")
    print(f"  📐 Sharpe : {sh:.2f}   |  ⚖️  PF: {pf:.2f}")
    return {"ret": ret, "sh": sh, "dd": dd, "wr": wr, "pf": pf, "tr": tr}


if __name__ == "__main__":
    print("═"*70)
    print("  🔬 BOJ Zone Filter Backtest — USDJPY London Breakout")
    print("  التاريخ: 2026-07-04 | الهدف: Sharpe 0.97 → ≥ 1.5")
    print("═"*70)

    h1 = load_csv(H1_CSV)
    h4 = load_csv(H4_CSV)

    if h1 is None:
        print("❌ H1 data missing — abort")
        sys.exit(1)

    print(f"\n  ✅ H1: {len(h1):,} candles | {h1.index[0].date()} → {h1.index[-1].date()}")

    # Price range statistics
    close_vals = h1["Close"].values
    print(f"\n  📊 USDJPY Price Statistics (2-year data):")
    print(f"     Min:  {close_vals.min():.2f}")
    print(f"     Max:  {close_vals.max():.2f}")
    print(f"     Mean: {close_vals.mean():.2f}")
    pct_above_155 = (close_vals > 155).sum() / len(close_vals) * 100
    pct_below_147 = (close_vals < 147).sum() / len(close_vals) * 100
    pct_zone      = 100 - pct_above_155 - pct_below_147
    print(f"     % above 155: {pct_above_155:.1f}% ({(close_vals > 155).sum()} bars)")
    print(f"     % below 147: {pct_below_147:.1f}% ({(close_vals < 147).sum()} bars)")
    print(f"     % zone 147-155: {pct_zone:.1f}% ({((close_vals >= 147) & (close_vals <= 155)).sum()} bars)")

    cash = 10_000
    comm = 0.0002

    # ── 1. Baseline ───────────────────────────────────────────────
    print("\n" + "─"*70)
    print("  📊 BASELINE — London Trail (الاستراتيجية الحالية)")
    print("─"*70)
    LondonBaseline._h4 = h4
    bt_base = Backtest(h1, LondonBaseline, cash=cash, commission=comm)
    r_base  = bt_base.run()
    base    = fmt_result(r_base, "Baseline: LondonTrail")

    # ── 2. BOJ Zone Filter (Original Proposal) ────────────────────
    print("\n" + "─"*70)
    print("  🔬 [F] BOJ Zone Filter (147/155) — المقترح الأصلي")
    print("─"*70)
    LondonBOJFilter.boj_buy_zone  = 147.0
    LondonBOJFilter.boj_sell_zone = 155.0
    LondonBOJFilter._h4 = h4
    bt_boj = Backtest(h1, LondonBOJFilter, cash=cash, commission=comm)
    r_boj  = bt_boj.run()
    boj    = fmt_result(r_boj, "BOJ Zone Filter (buy<147 | sell>155)")

    # ── 3. BOJ Relaxed Filter ─────────────────────────────────────
    print("\n" + "─"*70)
    print("  🔬 BOJ Relaxed Filter (145/157)")
    print("─"*70)
    LondonBOJRelaxed.boj_buy_zone  = 145.0
    LondonBOJRelaxed.boj_sell_zone = 157.0
    LondonBOJRelaxed._h4 = h4
    bt_relax = Backtest(h1, LondonBOJRelaxed, cash=cash, commission=comm)
    r_relax  = bt_relax.run()
    relaxed  = fmt_result(r_relax, "BOJ Relaxed (buy<145 | sell>157)")

    # ── 4. Directional BOJ Filter ─────────────────────────────────
    print("\n" + "─"*70)
    print("  🔬 Directional BOJ Filter (no-buy>151 | no-sell<149)")
    print("─"*70)
    LondonDirectional._h4 = h4
    bt_dir = Backtest(h1, LondonDirectional, cash=cash, commission=comm)
    r_dir  = bt_dir.run()
    direc  = fmt_result(r_dir, "Directional: BUY≤151 | SELL≥149")

    # ── 5. Parameter Sweep ────────────────────────────────────────
    sweep_results, best_sweep = boj_zone_sweep(h1, h4)

    # ── 6. Summary & Decision ─────────────────────────────────────
    print("\n" + "═"*70)
    print("  📈 RESULTS SUMMARY — BOJ Zone Filter Tests")
    print("═"*70)
    print(f"\n  {'Strategy':<35} {'Sharpe':>8} {'WR%':>6} {'Ret%':>8} {'DD%':>7} {'Trades':>7}")
    print(f"  {'-'*68}")
    print(f"  {'Baseline (no filter)':<35} {base['sh']:>8.2f} {base['wr']:>6.1f} {base['ret']:>8.2f} {base['dd']:>7.2f} {base['tr']:>7}")
    print(f"  {'BOJ Strict (147/155)':<35} {boj['sh']:>8.2f} {boj['wr']:>6.1f} {boj['ret']:>8.2f} {boj['dd']:>7.2f} {boj['tr']:>7}")
    print(f"  {'BOJ Relaxed (145/157)':<35} {relaxed['sh']:>8.2f} {relaxed['wr']:>6.1f} {relaxed['ret']:>8.2f} {relaxed['dd']:>7.2f} {relaxed['tr']:>7}")
    print(f"  {'Directional (149/151 band)':<35} {direc['sh']:>8.2f} {direc['wr']:>6.1f} {direc['ret']:>8.2f} {direc['dd']:>7.2f} {direc['tr']:>7}")

    # ── 7. Decision ───────────────────────────────────────────────
    candidates = [
        ("BOJ Strict (147/155)",     boj),
        ("BOJ Relaxed (145/157)",    relaxed),
        ("Directional (149/151)",    direc),
    ]
    best_candidate = max(candidates, key=lambda x: x[1]["sh"])
    best_name, best_stats = best_candidate

    print("\n" + "═"*70)
    print(f"  🎯 BEST CANDIDATE: {best_name}")
    print(f"     Sharpe: {best_stats['sh']:.2f} | WR: {best_stats['wr']:.1f}% | Return: {best_stats['ret']:.2f}%")
    print(f"     vs Baseline: Sharpe {best_stats['sh'] - base['sh']:+.2f} | Return {best_stats['ret'] - base['ret']:+.2f}%")

    sharpe_ok = best_stats["sh"] >= 1.5
    improvement = best_stats["sh"] > base["sh"]
    dd_ok = abs(best_stats["dd"]) <= 15.0
    trades_ok = best_stats["tr"] >= 15

    print(f"\n  ✅/❌ Decision Criteria:")
    print(f"     Sharpe ≥ 1.5:     {'✅' if sharpe_ok else '❌'} ({best_stats['sh']:.2f})")
    print(f"     Sharpe improved:  {'✅' if improvement else '❌'} (vs {base['sh']:.2f})")
    print(f"     Max DD ≤ 15%:     {'✅' if dd_ok else '❌'} ({best_stats['dd']:.2f}%)")
    print(f"     Trades ≥ 15:      {'✅' if trades_ok else '❌'} ({best_stats['tr']})")

    if sharpe_ok and improvement and dd_ok and trades_ok:
        print(f"\n  ✅ DECISION: APPLY BOJ FILTER TO strategy/london_signal.py")
        print(f"     Using: {best_name}")
    elif improvement and dd_ok and trades_ok:
        print(f"\n  ⚠️  PARTIAL: Sharpe improved but didn't reach 1.5 target")
        print(f"     Baseline: {base['sh']:.2f} → Best: {best_stats['sh']:.2f} (+{best_stats['sh'] - base['sh']:.2f})")
        print(f"     RECOMMEND: Apply if improvement ≥ +0.10 Sharpe")
    else:
        print(f"\n  ❌ DECISION: REJECT — BOJ Zone Filter doesn't improve performance")
        print(f"     Consider alternative approaches for USDJPY Sharpe improvement")

    print("\n" + "═"*70)
    print("  ✅ BOJ Zone Filter Backtest Complete")
    print("═"*70)
