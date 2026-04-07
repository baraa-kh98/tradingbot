"""
Gold Strategy Research — 3 استراتيجيات مختلفة كلياً
=====================================================
A. EMA Trend Pullback     — ارتداد لـ EMA في ترند واضح
B. ATR Breakout           — اختراق نطاق مع momentum
C. ICT OB Dollar-Based    — OB بمعايير مناسبة للذهب (دولار مش pip)

كل استراتيجية تأخذ H1 فقط — بدون تعقيد.
الهدف: نلاقي استراتيجية Sharpe > 0.8 على 2 سنة.
"""

import pandas as pd
import numpy as np
import sys, os, json, math, warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting import Backtest, Strategy

H1_CSV = "backtest_data/XAUUSD_H1_2years.csv"

# Gold-specific constants
GOLD_PIP = 0.01   # للـ backtesting lib (تحسب الـ return بالدولار تلقائياً)


def load_csv(path):
    if not os.path.exists(path):
        print(f"❌ غير موجود: {path}")
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    cols = [c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]
    return df[cols].dropna()


def safe(v, d=0.0):
    try:
        f = float(v)
        return d if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return d


def score(stats) -> float:
    trades = int(stats.get("# Trades", 0))
    if trades < 25:
        return -999.0
    return (
        safe(stats.get("Sharpe Ratio")) * 5
        + safe(stats.get("Return [%]")) * 0.25
        - abs(safe(stats.get("Max. Drawdown [%]"))) * 0.3
        + (safe(stats.get("Profit Factor")) - 1) * 4
    )


# ════════════════════════════════════════════════════════════════
# BASE
# ════════════════════════════════════════════════════════════════

class _Base(Strategy):
    _h4: pd.DataFrame = None

    def _h4_bias(self, ts) -> str:
        if self._h4 is None or len(self._h4) < 55:
            return "NEUTRAL"
        try:
            past = self._h4[self._h4.index <= ts]
            if len(past) < 55: return "NEUTRAL"
            c   = past["Close"].values.astype(float)
            e20 = float(pd.Series(c).ewm(span=20, adjust=False).mean().iloc[-1])
            e50 = float(pd.Series(c).ewm(span=50, adjust=False).mean().iloc[-1])
            if e20 > e50 * 1.0005: return "BULLISH"
            if e20 < e50 * 0.9995: return "BEARISH"
            return "NEUTRAL"
        except Exception:
            return "NEUTRAL"

    def _atr(self, period=14) -> float:
        try:
            n = min(len(self.data) - 1, period * 3)
            h = np.array(self.data.High[-n:],  dtype=float)
            l = np.array(self.data.Low[-n:],   dtype=float)
            c = np.array(self.data.Close[-n:], dtype=float)
            tr = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                  for i in range(1, len(h))]
            return float(np.mean(tr[-period:])) if len(tr) >= period else float(np.mean(tr))
        except Exception:
            return 5.0   # Gold default ATR fallback ~$5

    def _ema(self, span: int) -> float:
        try:
            c = np.array(self.data.Close[-(span*3):], dtype=float)
            return float(pd.Series(c).ewm(span=span, adjust=False).mean().iloc[-1])
        except Exception:
            return float(self.data.Close[-1])

    def _adx(self, period=14) -> float:
        try:
            n  = min(len(self.data) - 1, period * 4)
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
            atr_s = smma(tr, period)
            dip   = smma(dm_p, period) / (atr_s + 1e-9) * 100
            dim   = smma(dm_m, period) / (atr_s + 1e-9) * 100
            dx    = np.abs(dip - dim) / (dip + dim + 1e-9) * 100
            return float(np.mean(dx[-period:]))
        except Exception:
            return 0.0

    def _swing_low(self, lookback=10) -> float:
        """أدنى نقطة في آخر lookback شمعة"""
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
# A. EMA TREND PULLBACK
# ════════════════════════════════════════════════════════════════

class GoldEMAPullback(_Base):
    """
    الذهب يتبع الترند لفترات طويلة.
    الفكرة: ندخل على ارتدادات EMA20 في ترند واضح.

    شروط BUY:
      - EMA20 > EMA50 (ترند صاعد)
      - ADX > adx_min (ترند قوي مش range)
      - سعر لمس EMA20 (Low <= EMA20) ثم أغلق فوقه
      - لا وقت محدد — الذهب يتحرك 24 ساعة

    SL: آخر Swing Low - atr_sl_mult × ATR
    TP: entry + min_rr × risk
    """
    adx_min    = 20
    atr_sl_mult = 0.5    # SL = swing_low - 0.5×ATR
    min_rr     = 3.0
    ema_fast   = 20
    ema_slow   = 50

    _trade_date = None

    def init(self): pass

    def next(self):
        if len(self.data) < 60 or self.position:
            return

        ts    = self.data.index[-1]
        price = float(self.data.Close[-1])
        low   = float(self.data.Low[-1])

        e20 = self._ema(self.ema_fast)
        e50 = self._ema(self.ema_slow)
        adx = self._adx()
        atr = self._atr()

        # ── BUY ──────────────────────────────────────────────
        if e20 > e50 and adx > self.adx_min:
            # سعر لمس EMA20 أو مرّ منه وأغلق فوقه
            if low <= e20 * 1.001 and price > e20:
                sl   = self._swing_low(8) - self.atr_sl_mult * atr
                risk = price - sl
                if risk > atr * 0.3:   # minimum risk check
                    tp = price + risk * self.min_rr
                    self.buy(sl=sl, tp=tp)
                    return

        # ── SELL ─────────────────────────────────────────────
        high = float(self.data.High[-1])
        if e20 < e50 and adx > self.adx_min:
            if high >= e20 * 0.999 and price < e20:
                sl   = self._swing_high(8) + self.atr_sl_mult * atr
                risk = sl - price
                if risk > atr * 0.3:
                    tp = price - risk * self.min_rr
                    self.sell(sl=sl, tp=tp)


# ════════════════════════════════════════════════════════════════
# B. ATR CHANNEL BREAKOUT (N-Bar High/Low)
# ════════════════════════════════════════════════════════════════

class GoldATRBreakout(_Base):
    """
    الاختراق الحقيقي يكون بعد فترة تراكم.
    الفكرة: كسر N-bar high/low مع ADX momentum.

    BUY:  Close فوق أعلى nbar شمعة + ADX > adx_min
    SELL: Close تحت أدنى nbar شمعة + ADX > adx_min
    SL:   entry ± atr_sl × ATR
    TP:   entry ± min_rr × risk
    """
    nbar       = 20      # عدد الشموع للـ channel
    adx_min    = 22
    atr_sl     = 1.5
    min_rr     = 2.5

    def init(self): pass

    def next(self):
        if len(self.data) < self.nbar + 10 or self.position:
            return

        price    = float(self.data.Close[-1])
        prev_c   = float(self.data.Close[-2])
        atr      = self._atr()
        adx      = self._adx()

        ch_high  = self._swing_high(self.nbar)
        ch_low   = self._swing_low(self.nbar)

        if adx < self.adx_min:
            return

        sl_dist = self.atr_sl * atr

        # ── BUY breakout ─────────────────────────────────────
        if prev_c <= ch_high and price > ch_high:
            sl   = price - sl_dist
            risk = sl_dist
            if risk > 0:
                self.buy(sl=sl, tp=price + risk * self.min_rr)

        # ── SELL breakout ────────────────────────────────────
        elif prev_c >= ch_low and price < ch_low:
            sl   = price + sl_dist
            risk = sl_dist
            if risk > 0:
                self.sell(sl=sl, tp=price - risk * self.min_rr)


# ════════════════════════════════════════════════════════════════
# C. GOLD ICT — DOLLAR-BASED OB (بمعايير صحيحة للذهب)
# ════════════════════════════════════════════════════════════════

class GoldICTDollar(_Base):
    """
    نفس منطق ICT OB لكن بمعايير بالدولار مناسبة للذهب.
    OB displacement = atr_disp × ATR (مش pip-based)
    SL = ob_edge + atr_buf × ATR
    Kill Zone: NY + London

    الفرق عن الاستراتيجية السابقة:
    - FVG بحد أدنى دولار مناسب (fvg_min_dollar)
    - displacement threshold بالـ ATR مش pip
    - نقبل كلا الجلستين
    """
    atr_disp     = 1.2   # displacement = 1.2 × ATR
    atr_buf      = 0.8   # SL buffer = 0.8 × ATR
    fvg_min_usd  = 2.0   # FVG لازم >= $2
    min_rr       = 2.5
    ob_lookback  = 40
    kz_hours     = [(7,10),(13,16)]   # London + NY

    _trade_date  = None

    def init(self): pass

    def _in_kz(self) -> bool:
        h = getattr(self.data.index[-1], "hour", 0)
        return any(s <= h < e for s, e in self.kz_hours)

    def _find_ob(self, direction: str):
        """
        يبحث عن آخر OB غير محرك.
        direction: "BULL" أو "BEAR"
        يرجع (ob_top, ob_bottom) أو (None, None)
        """
        n   = len(self.data)
        h   = np.array(self.data.High,  dtype=float)
        l   = np.array(self.data.Low,   dtype=float)
        o   = np.array(self.data.Open,  dtype=float)
        c   = np.array(self.data.Close, dtype=float)
        atr = self._atr()
        thresh = atr * self.atr_disp

        start = max(2, n - self.ob_lookback)
        obs   = []

        for i in range(start, n - 1):
            body = abs(c[i] - o[i])

            if direction == "BULL" and c[i] > o[i] and body > thresh:
                for j in range(i-1, max(i-5,0), -1):
                    if c[j] < o[j]:
                        top = float(o[j]); bot = float(c[j])
                        if not any(l[k] < bot for k in range(i+1, n)):
                            obs.append((j, top, bot))
                        break

            elif direction == "BEAR" and c[i] < o[i] and body > thresh:
                for j in range(i-1, max(i-5,0), -1):
                    if c[j] > o[j]:
                        top = float(c[j]); bot = float(o[j])
                        if not any(h[k] > top for k in range(i+1, n)):
                            obs.append((j, top, bot))
                        break

        if obs:
            obs.sort(key=lambda x: x[0], reverse=True)
            return obs[0][1], obs[0][2]
        return None, None

    def _fvg_near(self, price: float, direction: str) -> bool:
        """هل يوجد FVG قريب (ضمن 2×fvg_min_usd) من السعر؟"""
        n = len(self.data)
        h = np.array(self.data.High,  dtype=float)
        l = np.array(self.data.Low,   dtype=float)
        search = min(30, n-2)

        for i in range(n-search, n-1):
            if direction == "BULL" and i >= 2:
                bot = h[i-2]; top = l[i]
                if top > bot and (top-bot) >= self.fvg_min_usd:
                    if abs(price - (top+bot)/2) <= self.fvg_min_usd * 2:
                        return True
            elif direction == "BEAR" and i >= 2:
                top = l[i-2]; bot = h[i]
                if top > bot and (top-bot) >= self.fvg_min_usd:
                    if abs(price - (top+bot)/2) <= self.fvg_min_usd * 2:
                        return True
        return False

    def next(self):
        if len(self.data) < 50 or self.position:
            return
        if not self._in_kz():
            return

        ts    = self.data.index[-1]
        price = float(self.data.Close[-1])
        atr   = self._atr()
        bias  = self._h4_bias(ts)

        today = getattr(ts, "date", lambda: None)()
        if self._trade_date == today:
            return

        # ── BUY ──────────────────────────────────────────────
        if bias != "BEARISH":
            ob_top, ob_bot = self._find_ob("BULL")
            if ob_top and ob_bot <= price <= ob_top:
                if self._fvg_near(price, "BULL"):
                    sl   = ob_bot - self.atr_buf * atr
                    risk = price - sl
                    if risk > atr * 0.5:
                        self._trade_date = today
                        self.buy(sl=sl, tp=price + risk * self.min_rr)
                        return

        # ── SELL ─────────────────────────────────────────────
        if bias != "BULLISH":
            ob_top, ob_bot = self._find_ob("BEAR")
            if ob_top and ob_bot <= price <= ob_top:
                if self._fvg_near(price, "BEAR"):
                    sl   = ob_top + self.atr_buf * atr
                    risk = sl - price
                    if risk > atr * 0.5:
                        self._trade_date = today
                        self.sell(sl=sl, tp=price - risk * self.min_rr)


# ════════════════════════════════════════════════════════════════
# D. GOLD MOMENTUM TREND (H4 bias + RSI dip buy)
# ════════════════════════════════════════════════════════════════

class GoldMomentumDip(_Base):
    """
    الذهب يتحرك بـ momentum قوي مع بيانات الماكرو.
    الفكرة: H4 bias + RSI يتراجع لمنطقة oversold خفيفة (40-50) في ترند صاعد
    → دخول على الارتداد من الدعم

    BUY:
      - H4 BULLISH
      - ADX H1 > 20
      - RSI(14) نزل تحت 45 ثم رجع فوقه (momentum dip)
      - Close > EMA(50)

    SELL: عكسه
    SL: swing_low - 0.8×ATR
    TP: 3× risk
    """
    adx_min    = 18
    rsi_dip    = 45      # RSI ينزل تحت هذا ثم يرجع
    min_rr     = 3.0
    ema_trend  = 50
    atr_sl     = 0.8

    def init(self): pass

    def _rsi(self, period=14) -> float:
        try:
            c    = np.array(self.data.Close[-(period*3):], dtype=float)
            diff = np.diff(c)
            g    = np.where(diff > 0, diff, 0.0)
            ls   = np.where(diff < 0, -diff, 0.0)
            ag   = np.mean(g[-period:])
            al   = np.mean(ls[-period:])
            if al == 0: return 100.0
            return 100 - 100 / (1 + ag / al)
        except Exception:
            return 50.0

    def _prev_rsi(self, period=14) -> float:
        """RSI الشمعة السابقة"""
        try:
            c    = np.array(self.data.Close[-(period*3+1):-1], dtype=float)
            diff = np.diff(c)
            g    = np.where(diff > 0, diff, 0.0)
            ls   = np.where(diff < 0, -diff, 0.0)
            ag   = np.mean(g[-period:])
            al   = np.mean(ls[-period:])
            if al == 0: return 100.0
            return 100 - 100 / (1 + ag / al)
        except Exception:
            return 50.0

    def next(self):
        if len(self.data) < 60 or self.position:
            return

        ts    = self.data.index[-1]
        price = float(self.data.Close[-1])
        atr   = self._atr()
        adx   = self._adx()
        rsi   = self._rsi()
        prev_rsi = self._prev_rsi()
        e50   = self._ema(self.ema_trend)
        bias  = self._h4_bias(ts)

        if adx < self.adx_min:
            return

        # RSI dip recovery: كان تحت rsi_dip وعاد فوقه
        rsi_recovered_up   = prev_rsi < self.rsi_dip and rsi > self.rsi_dip
        rsi_recovered_down = prev_rsi > (100 - self.rsi_dip) and rsi < (100 - self.rsi_dip)

        # ── BUY ──────────────────────────────────────────────
        if bias == "BULLISH" and price > e50 and rsi_recovered_up:
            sl   = self._swing_low(10) - self.atr_sl * atr
            risk = price - sl
            if risk > atr * 0.3:
                self.buy(sl=sl, tp=price + risk * self.min_rr)
                return

        # ── SELL ─────────────────────────────────────────────
        if bias == "BEARISH" and price < e50 and rsi_recovered_down:
            sl   = self._swing_high(10) + self.atr_sl * atr
            risk = sl - price
            if risk > atr * 0.3:
                self.sell(sl=sl, tp=price - risk * self.min_rr)


# ════════════════════════════════════════════════════════════════
# GRID SEARCH FOR EACH STRATEGY
# ════════════════════════════════════════════════════════════════

GRIDS = {
    "EMA_Pullback": {
        "cls": GoldEMAPullback,
        "params": {
            "adx_min":     [15, 20, 25],
            "atr_sl_mult": [0.3, 0.5, 0.8],
            "min_rr":      [2.5, 3.0, 3.5],
            "ema_fast":    [20],
            "ema_slow":    [50],
        }
    },
    "ATR_Breakout": {
        "cls": GoldATRBreakout,
        "params": {
            "nbar":    [15, 20, 30],
            "adx_min": [18, 22, 28],
            "atr_sl":  [1.0, 1.5, 2.0],
            "min_rr":  [2.0, 2.5, 3.0],
        }
    },
    "ICT_Dollar": {
        "cls": GoldICTDollar,
        "params": {
            "atr_disp":    [1.0, 1.2, 1.5],
            "atr_buf":     [0.5, 0.8, 1.0],
            "fvg_min_usd": [1.0, 2.0, 3.0],
            "min_rr":      [2.0, 2.5, 3.0],
        }
    },
    "Momentum_Dip": {
        "cls": GoldMomentumDip,
        "params": {
            "adx_min": [15, 18, 22],
            "rsi_dip": [40, 45, 50],
            "min_rr":  [2.5, 3.0, 3.5],
            "atr_sl":  [0.5, 0.8, 1.0],
        }
    },
}


def run_strategy_grid(name, cls, param_grid, h1):
    from itertools import product
    keys   = list(param_grid.keys())
    values = list(param_grid.values())
    combos = list(product(*values))
    total  = len(combos)

    print(f"\n{'─'*55}")
    print(f"  {name} — {total} تركيبة")
    print(f"{'─'*55}")

    results = []
    for i, combo in enumerate(combos, 1):
        params = dict(zip(keys, combo))
        for k, v in params.items():
            setattr(cls, k, v)

        try:
            bt    = Backtest(h1, cls, cash=10_000,
                             commission=0.0002, finalize_trades=True)
            stats = bt.run()
            sc    = score(stats)
            trades = int(stats.get("# Trades", 0))
            row = {
                "strategy": name,
                **params,
                "trades":  trades,
                "wr":      round(safe(stats.get("Win Rate [%]")), 1),
                "ret":     round(safe(stats.get("Return [%]")), 2),
                "dd":      round(safe(stats.get("Max. Drawdown [%]")), 2),
                "sharpe":  round(safe(stats.get("Sharpe Ratio")), 3),
                "pf":      round(safe(stats.get("Profit Factor")), 3),
                "ann_ret": round(safe(stats.get("Return (Ann.) [%]")), 2),
                "score":   round(sc, 3),
            }
            results.append(row)

            if i % max(1, total//5) == 0 or i == total:
                print(f"  [{i:>3}/{total}] {params} → T={trades} WR={row['wr']}% Ret={row['ret']}% Sh={row['sharpe']:.3f}")

        except Exception as e:
            if i <= 3:
                print(f"  ⚠️ [{i}/{total}] {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    h1 = load_csv(H1_CSV)
    if h1 is None:
        sys.exit(1)

    print(f"\n{'═'*55}")
    print(f"  Gold Strategy Research — {len(h1)} شمعة H1")
    print(f"  {h1.index[0].date()} → {h1.index[-1].date()}")
    print(f"{'═'*55}")

    all_results = []
    best_per_strategy = {}

    for name, cfg in GRIDS.items():
        results = run_strategy_grid(name, cfg["cls"], cfg["params"], h1)
        all_results.extend(results)
        if results:
            best_per_strategy[name] = results[0]
            r = results[0]
            print(f"\n  ✅ أفضل {name}: T={r['trades']} WR={r['wr']}% Ret={r['ret']}% Sharpe={r['sharpe']} Score={r['score']:.2f}")

    # ── مقارنة الاستراتيجيات ─────────────────────────────────
    print(f"\n{'═'*65}")
    print("  مقارنة أفضل استراتيجية لكل نوع")
    print(f"{'═'*65}")
    header = f"{'Strategy':<18} {'T':>5} {'WR%':>6} {'Ret%':>7} {'Ann%':>7} {'DD%':>7} {'Sharpe':>7} {'PF':>5} {'Score':>7}"
    print(header)
    print("-" * len(header))

    ranked = sorted(best_per_strategy.values(), key=lambda x: x["score"], reverse=True)
    for r in ranked:
        medal = " 🥇" if r == ranked[0] else ""
        print(f"{r['strategy']:<18} {r['trades']:>5} {r['wr']:>6.1f} {r['ret']:>7.2f} "
              f"{r['ann_ret']:>7.2f} {r['dd']:>7.2f} {r['sharpe']:>7.3f} {r['pf']:>5.2f} "
              f"{r['score']:>7.2f}{medal}")

    best_overall = ranked[0]
    print(f"\n  🏆 الأفضل: {best_overall['strategy']}")
    print(f"  Parameters: {', '.join(f'{k}={v}' for k,v in best_overall.items() if k not in ['strategy','trades','wr','ret','dd','sharpe','pf','ann_ret','score'])}")

    # ── معايير القبول ────────────────────────────────────────
    PASS = (
        best_overall["sharpe"] > 0.5 and
        best_overall["ret"] > 10 and
        abs(best_overall["dd"]) < 15 and
        best_overall["pf"] > 1.3 and
        best_overall["trades"] >= 40
    )
    print(f"\n  {'✅ مرّت المعايير!' if PASS else '⚠️ لم تمر المعايير بعد — نحتاج M15'}")

    # ── حفظ ─────────────────────────────────────────────────
    os.makedirs("journal", exist_ok=True)
    out = "journal/gold_research_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "best_per_strategy": best_per_strategy,
            "best_overall": best_overall,
            "passed": PASS,
            "top_20_all": sorted(all_results, key=lambda x: x["score"], reverse=True)[:20],
        }, f, indent=2, ensure_ascii=False)
    print(f"  💾 {out}")
