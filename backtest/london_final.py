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
    cols = [c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]
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

    for cls in [LondonClean, LondonTrail, LondonPartial, LondonWide, LondonADX]:
        cls._h4 = h4

    cash = 10_000
    comm = 0.0002

    strategies = [
        ("A. London Clean  (grid best: buf=3,rr=3,rng≥40)",  LondonClean),
        ("B. London Trail  (trailing after 1:1 → breakeven)", LondonTrail),
        ("C. London Partial (50% at 1.5:1, 50% at 3:1)",     LondonPartial),
        ("D. London Wide   (07-11 window, more trades)",      LondonWide),
        ("E. London ADX    (ADX>20 filter)",                  LondonADX),
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
    run()
