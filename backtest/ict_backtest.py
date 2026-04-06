"""
Pro Backtest v3 — استراتيجيات احترافية متكيّفة على بيانات حقيقية (2 سنة)

الاستراتيجيات:
1. AdaptiveEMA  — ترند في الترند + ارتداد في الـ Range (ADX يحدد)
2. LondonBreak  — London/NY Breakout (تم إصلاح bug الـ timezone)
3. DualMomentum — EMA + RSI معاً للتصفية
4. EMAFixed     — EMA بسيطة SL/TP ثابتة (كانت الأفضل سابقاً)
"""

import pandas as pd
import numpy as np
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting import Backtest, Strategy
from backtesting.lib import crossover
from config import PIP_VALUE

# ═══════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════

H1_CSV = "backtest_data/USDJPY_H1_2years.csv"
H4_CSV = "backtest_data/USDJPY_H4_3years.csv"


def load_h1():
    if not os.path.exists(H1_CSV):
        print(f"❌ ملف غير موجود: {H1_CSV}")
        return None
    df = pd.read_csv(H1_CSV, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    cols = [c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]
    df = df[cols].dropna()
    print(f"✅ H1: {len(df)} شمعة | {df.index[0].date()} → {df.index[-1].date()}")
    return df


def load_h4():
    if not os.path.exists(H4_CSV):
        return None
    df = pd.read_csv(H4_CSV, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    cols = [c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]
    return df[cols].dropna()


# ═══════════════════════════════════════════════════════════════
# BASE — مشترك بين الاستراتيجيات
# ═══════════════════════════════════════════════════════════════

class _Base(Strategy):

    _h4: pd.DataFrame = None
    KILL_ZONES = [(7, 10), (13, 16)]     # UTC

    def _in_kz(self, dt) -> bool:
        h = getattr(dt, "hour", 0)
        return any(s <= h < e for s, e in self.KILL_ZONES)

    def _h4_bias(self, ts) -> str:
        """H4 EMA20 vs EMA50 — الاتجاه الكبير"""
        if self._h4 is None or len(self._h4) < 55:
            return "NEUTRAL"
        try:
            past = self._h4[self._h4.index <= ts]
            if len(past) < 55:
                return "NEUTRAL"
            c   = past["Close"].values.astype(float)
            e20 = float(pd.Series(c).ewm(span=20, adjust=False).mean().iloc[-1])
            e50 = float(pd.Series(c).ewm(span=50, adjust=False).mean().iloc[-1])
            if e20 > e50 * 1.0005:   return "BULLISH"
            if e20 < e50 * 0.9995:   return "BEARISH"
            return "NEUTRAL"
        except Exception:
            return "NEUTRAL"

    def _adx_val(self, period=14) -> float:
        """ADX من arrays مباشرة — لا DataFrame"""
        try:
            n  = min(len(self.data) - 1, period * 4)
            h  = np.array(self.data.High[-n:],  dtype=float)
            l  = np.array(self.data.Low[-n:],   dtype=float)
            c  = np.array(self.data.Close[-n:], dtype=float)
            if len(h) < period + 2:
                return 0.0
            dh = np.diff(h);  dl = -np.diff(l)
            dm_p = np.where((dh > dl) & (dh > 0), dh, 0.0)
            dm_m = np.where((dl > dh) & (dl > 0), dl, 0.0)
            tr   = np.array([max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                             for i in range(1, len(h))])
            def smma(arr, p):
                out = np.zeros(len(arr))
                out[p-1] = arr[:p].mean()
                for i in range(p, len(arr)):
                    out[i] = (out[i-1] * (p-1) + arr[i]) / p
                return out
            atr_s = smma(tr,   period)
            dip   = smma(dm_p, period) / (atr_s + 1e-9) * 100
            dim   = smma(dm_m, period) / (atr_s + 1e-9) * 100
            dx    = np.abs(dip - dim) / (dip + dim + 1e-9) * 100
            return float(np.mean(dx[-period:]))
        except Exception:
            return 0.0

    def _rsi(self, period=14) -> float:
        """RSI من Close array"""
        try:
            c    = np.array(self.data.Close[-(period*3):], dtype=float)
            diff = np.diff(c)
            gain = np.where(diff > 0, diff, 0.0)
            loss = np.where(diff < 0, -diff, 0.0)
            ag   = np.mean(gain[-period:]) if len(gain) >= period else 0.0
            al   = np.mean(loss[-period:]) if len(loss) >= period else 0.0
            if al == 0:
                return 100.0
            return 100 - 100 / (1 + ag / al)
        except Exception:
            return 50.0

    def _asia_range_from_arrays(self, idx):
        """حساب Range آسيا من arrays بدون DataFrame"""
        try:
            ts   = self.data.index[idx]
            hour = getattr(ts, "hour", 0)
            # شموع آسيا هي الـ 7 ساعات قبل hour 7 UTC
            # نرجع في arrays ونأخذ شموع 00:00-06:00
            lookback = min(idx, 14)
            highs, lows = [], []
            for k in range(lookback, 0, -1):
                bar_ts   = self.data.index[idx - k]
                bar_hour = getattr(bar_ts, "hour", 0)
                bar_date = getattr(bar_ts, "date", lambda: None)()
                ts_date  = getattr(ts,     "date", lambda: None)()
                if bar_date == ts_date and 0 <= bar_hour < 7:
                    highs.append(float(self.data.High[idx - k]))
                    lows.append(float(self.data.Low[idx - k]))
            if len(highs) < 3:
                return None, None
            return max(highs), min(lows)
        except Exception:
            return None, None


# ═══════════════════════════════════════════════════════════════
# 1. ADAPTIVE EMA — ترند + ارتداد حسب ADX
# ═══════════════════════════════════════════════════════════════

class AdaptiveEMA(_Base):
    """
    ADX > 25  → Trend Mode: EMA crossover + H4 bias
    ADX < 20  → Range Mode: RSI Oversold/Overbought + EMA mean reversion
    Kill Zone: London + NY
    SL/TP: ديناميكي بناءً على ATR
    """

    adx_trend  = 25    # فوق هذا = ترند
    adx_range  = 20    # تحت هذا = range
    rsi_ob     = 65    # overbought (للبيع في الـ range)
    rsi_os     = 35    # oversold  (للشراء في الـ range)
    atr_sl     = 1.2
    atr_tp_tr  = 2.5   # في الترند: RR = 2.08
    atr_tp_rng = 1.0   # في الـ Range: RR = 0.83 (صفقات كثيرة أسرع)

    def init(self):
        self.e20 = self.I(
            lambda x: pd.Series(x).ewm(span=20, adjust=False).mean().values,
            self.data.Close, name="EMA20")
        self.e50 = self.I(
            lambda x: pd.Series(x).ewm(span=50, adjust=False).mean().values,
            self.data.Close, name="EMA50")
        self.atr_i = self.I(
            lambda h,l,c: pd.Series([
                max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) if i > 0 else h[i]-l[i]
                for i in range(len(h))
            ]).rolling(14).mean().values,
            self.data.High, self.data.Low, self.data.Close, name="ATR")

    def next(self):
        if len(self.data) < 60 or self.position:
            return
        ts  = self.data.index[-1]
        if not self._in_kz(ts):
            return

        atr = self.atr_i[-1]
        if np.isnan(atr) or atr == 0:
            return

        adx  = self._adx_val()
        rsi  = self._rsi()
        bias = self._h4_bias(ts)
        p    = float(self.data.Close[-1])

        # ── TREND MODE ────────────────────────────────────────
        if adx >= self.adx_trend:
            if bias != "BEARISH" and crossover(self.e20, self.e50):
                self.buy( sl=p - self.atr_sl*atr, tp=p + self.atr_tp_tr*atr)
            elif bias != "BULLISH" and crossover(self.e50, self.e20):
                self.sell(sl=p + self.atr_sl*atr, tp=p - self.atr_tp_tr*atr)

        # ── RANGE MODE ────────────────────────────────────────
        elif adx <= self.adx_range:
            e20 = float(self.e20[-1])
            e50 = float(self.e50[-1])
            mid = (e20 + e50) / 2    # وسط الـ range

            # BUY: RSI oversold + سعر تحت EMA + H4 مو هابط
            if rsi < self.rsi_os and p < e20 and bias != "BEARISH":
                tp_dist = abs(mid - p)                # TP = العودة للمتوسط
                tp_dist = max(tp_dist, self.atr_tp_rng * atr)
                self.buy(sl=p - self.atr_sl*atr, tp=p + tp_dist)

            # SELL: RSI overbought + سعر فوق EMA + H4 مو صاعد
            elif rsi > self.rsi_ob and p > e20 and bias != "BULLISH":
                tp_dist = abs(p - mid)
                tp_dist = max(tp_dist, self.atr_tp_rng * atr)
                self.sell(sl=p + self.atr_sl*atr, tp=p - tp_dist)


# ═══════════════════════════════════════════════════════════════
# 2. LONDON BREAKOUT — مُصلح (بدون DataFrame)
# ═══════════════════════════════════════════════════════════════

class LondonBreakout(_Base):
    """
    Asia Range Breakout عند فتح لندن:
    - يحسب H/L من شموع 00:00-06:59 UTC
    - Break فوق High + buffer → BUY  (إذا H4 مو Bearish)
    - Break تحت Low  + buffer → SELL (إذا H4 مو Bullish)
    - SL: الطرف الآخر من الـ Range | TP: 2× Range
    """
    buffer_pips = 5
    min_rr      = 2.0

    def init(self):
        self.atr_i = self.I(
            lambda h,l,c: pd.Series([
                max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) if i > 0 else h[i]-l[i]
                for i in range(len(h))
            ]).rolling(14).mean().values,
            self.data.High, self.data.Low, self.data.Close, name="ATR")

    def next(self):
        idx = len(self.data) - 1
        if idx < 20 or self.position:
            return
        ts   = self.data.index[-1]
        hour = getattr(ts, "hour", -1)
        if not (7 <= hour < 10):
            return

        atr = self.atr_i[-1]
        if np.isnan(atr) or atr == 0:
            return

        ah, al = self._asia_range_from_arrays(idx)
        if ah is None:
            return

        rng = ah - al
        if rng < PIP_VALUE * 10:
            return

        buf   = self.buffer_pips * PIP_VALUE
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
# 3. DUAL MOMENTUM — EMA + RSI تأكيد مزدوج
# ═══════════════════════════════════════════════════════════════

class DualMomentum(_Base):
    """
    EMA Crossover + RSI تأكيد + H4 + Kill Zone:
    BUY:  EMA20 يعبر EMA50 للأعلى + RSI < 60 (مو overbought) + H4 Bullish
    SELL: EMA20 يعبر EMA50 للأسفل + RSI > 40 (مو oversold)  + H4 Bearish
    SL = 1.0×ATR | TP = 2.0×ATR | RR = 2.0
    """

    rsi_max_buy  = 60
    rsi_min_sell = 40
    atr_sl       = 1.0
    atr_tp       = 2.0

    def init(self):
        self.e20 = self.I(
            lambda x: pd.Series(x).ewm(span=20, adjust=False).mean().values,
            self.data.Close, name="EMA20")
        self.e50 = self.I(
            lambda x: pd.Series(x).ewm(span=50, adjust=False).mean().values,
            self.data.Close, name="EMA50")
        self.atr_i = self.I(
            lambda h,l,c: pd.Series([
                max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) if i > 0 else h[i]-l[i]
                for i in range(len(h))
            ]).rolling(14).mean().values,
            self.data.High, self.data.Low, self.data.Close, name="ATR")

    def next(self):
        if len(self.data) < 55 or self.position:
            return
        ts  = self.data.index[-1]
        if not self._in_kz(ts):
            return

        atr  = self.atr_i[-1]
        if np.isnan(atr) or atr == 0:
            return

        rsi  = self._rsi()
        bias = self._h4_bias(ts)
        p    = float(self.data.Close[-1])

        if bias == "BULLISH" and crossover(self.e20, self.e50) and rsi < self.rsi_max_buy:
            self.buy( sl=p - self.atr_sl*atr, tp=p + self.atr_tp*atr)

        elif bias == "BEARISH" and crossover(self.e50, self.e20) and rsi > self.rsi_min_sell:
            self.sell(sl=p + self.atr_sl*atr, tp=p - self.atr_tp*atr)


# ═══════════════════════════════════════════════════════════════
# 4. EMA FIXED — EMA بسيطة SL/TP ثابتة (الفائزة السابقة)
# ═══════════════════════════════════════════════════════════════

class EMAFixed(Strategy):
    """EMA 20/50 crossover — SL/TP ثابتان نسبياً (50pip SL / 100pip TP)"""

    def init(self):
        self.e20 = self.I(
            lambda x: pd.Series(x).ewm(span=20, adjust=False).mean().values,
            self.data.Close, name="EMA20")
        self.e50 = self.I(
            lambda x: pd.Series(x).ewm(span=50, adjust=False).mean().values,
            self.data.Close, name="EMA50")

    def next(self):
        if self.position:
            return
        p = float(self.data.Close[-1])
        if crossover(self.e20, self.e50):
            self.buy( sl=p - 0.5, tp=p + 1.0)
        elif crossover(self.e50, self.e20):
            self.sell(sl=p + 0.5, tp=p - 1.0)


# ═══════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════

def show(name, r):
    pf  = r.get("Profit Factor", 0) or 0
    pf  = 0.0 if (isinstance(pf, float) and np.isnan(pf)) else pf
    wr  = r["Win Rate [%]"]
    wr  = 0.0 if (isinstance(wr, float) and np.isnan(wr)) else wr
    sh  = r["Sharpe Ratio"]
    sh  = 0.0 if (isinstance(sh, float) and np.isnan(sh)) else sh
    print(f"\n{'═'*52}")
    print(f"  {name}")
    print(f"{'═'*52}")
    print(f"  📊 الصفقات     : {r['# Trades']}")
    print(f"  🎯 Win Rate    : {wr:.1f}%")
    print(f"  💰 الربح       : {r['Return [%]']:.2f}%")
    print(f"  📉 Max DD      : {r['Max. Drawdown [%]']:.2f}%")
    print(f"  📐 Sharpe      : {sh:.2f}")
    if pf:
        print(f"  ⚖️  ProfitFact : {pf:.2f}")
    return r


def run():
    print("\n" + "═"*60)
    print("  🚀 Pro Backtest v3 — USDJPY — 2 سنة")
    print("═"*60)

    h1 = load_h1()
    if h1 is None or len(h1) < 500:
        print("❌ فشل تحميل H1"); return

    h4 = load_h4()
    if h4 is not None:
        print(f"✅ H4: {len(h4)} شمعة ({h4.index[0].date()} → {h4.index[-1].date()})")

    for cls in [AdaptiveEMA, LondonBreakout, DualMomentum]:
        cls._h4 = h4

    cash = 10_000
    comm = 0.0002

    bt1 = Backtest(h1, AdaptiveEMA,   cash=cash, commission=comm, finalize_trades=True)
    r1  = show("⭐ Adaptive EMA (Trend+Range+KZ+H4)", bt1.run())

    bt2 = Backtest(h1, LondonBreakout, cash=cash, commission=comm, finalize_trades=True)
    r2  = show("🇬🇧 London Breakout (Asia Range+H4)", bt2.run())

    bt3 = Backtest(h1, DualMomentum,  cash=cash, commission=comm, finalize_trades=True)
    r3  = show("🔀 Dual Momentum (EMA+RSI+H4+KZ)", bt3.run())

    bt4 = Backtest(h1, EMAFixed,      cash=cash, commission=comm, finalize_trades=True)
    r4  = show("📊 EMA Fixed (SL=50pip TP=100pip)", bt4.run())

    # ── جدول المقارنة ──────────────────────────────────────────
    results = {"Adaptive": r1, "London": r2, "DualMom": r3, "EMAFixed": r4}

    def safe(r, k):
        try:
            v = float(r[k])
            return 0.0 if np.isnan(v) else round(v, 2)
        except Exception:
            return 0.0

    print(f"\n{'═'*78}")
    print(f"  📊 المقارنة النهائية — {len(h1):,} شمعة H1 ({h1.index[0].date()} → {h1.index[-1].date()})")
    print(f"{'═'*78}")

    cols = list(results.keys())
    hdr  = f"{'المقياس':17s}"
    for c in cols: hdr += f" | {c:>10s}"
    hdr += " | 🏆"
    print(hdr); print("─"*78)

    metrics = [
        ("الصفقات",   "# Trades",          False),
        ("Win Rate%",  "Win Rate [%]",       True),
        ("الربح%",    "Return [%]",          True),
        ("Max DD%",   "Max. Drawdown [%]",   False),
        ("Sharpe",    "Sharpe Ratio",        True),
        ("ProfitFact","Profit Factor",        True),
    ]

    for label, key, higher in metrics:
        vals = {n: safe(r, key) for n, r in results.items()}
        best = (min if not higher else max)(vals, key=lambda k: vals[k])
        row  = f"{label:17s}"
        for c in cols:
            mark = "✅" if c == best else "  "
            row += f" | {vals[c]:>9.2f}{mark}"
        row += f" | {best}"
        print(row)

    # ── حفظ ──────────────────────────────────────────────────
    print("\n💾 حفظ الشارتات...")
    bt1.plot(filename="AdaptiveEMA",    open_browser=False)
    bt2.plot(filename="LondonBreakout", open_browser=False)
    bt3.plot(filename="DualMomentum",   open_browser=False)
    bt4.plot(filename="EMAFixed",       open_browser=False)
    print("✅ AdaptiveEMA.html | LondonBreakout.html | DualMomentum.html | EMAFixed.html")

    return results


if __name__ == "__main__":
    run()
