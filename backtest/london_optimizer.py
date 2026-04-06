"""
London Breakout Optimizer v1
==============================
نحسّن London Breakout من +11.97% إلى هدف > 30% / سنة

التحسينات المختبرة:
1. Grid Search: buffer_pips × min_rr × min_range × hour_end
2. LondonProV2: Trailing Stop + Partial TP + ADX filter
3. SessionBreakout: London + NY معاً
4. Multi-Pair: EURUSD + GBPUSD إذا توفرت البيانات
"""

import pandas as pd
import numpy as np
import sys, os, itertools, warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting import Backtest, Strategy
from config import PIP_VALUE

# ── Data ──────────────────────────────────────────────────────────────────

H1_CSV  = "backtest_data/USDJPY_H1_2years.csv"
H4_CSV  = "backtest_data/USDJPY_H4_3years.csv"

EURUSD_H1 = "backtest_data/EURUSD_H1_2years.csv"
GBPUSD_H1 = "backtest_data/GBPUSD_H1_2years.csv"

def load_csv(path, name=""):
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    cols = [c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]
    df = df[cols].dropna()
    if name:
        print(f"  ✅ {name}: {len(df)} شمعة | {df.index[0].date()} → {df.index[-1].date()}")
    return df


# ── Base ──────────────────────────────────────────────────────────────────

class _Base(Strategy):
    _h4: pd.DataFrame = None
    _pip: float = PIP_VALUE

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

    def _adx_val(self, period=14) -> float:
        try:
            n  = min(len(self.data) - 1, period * 5)
            h  = np.array(self.data.High[-n:],  dtype=float)
            l  = np.array(self.data.Low[-n:],   dtype=float)
            c  = np.array(self.data.Close[-n:], dtype=float)
            if len(h) < period + 2:
                return 0.0
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

    def _rsi(self, period=14) -> float:
        try:
            c    = np.array(self.data.Close[-(period*3):], dtype=float)
            diff = np.diff(c)
            gain = np.where(diff > 0, diff, 0.0)
            loss = np.where(diff < 0, -diff, 0.0)
            ag   = np.mean(gain[-period:]) if len(gain) >= period else 0.0
            al   = np.mean(loss[-period:]) if len(loss) >= period else 0.0
            if al == 0: return 100.0
            return 100 - 100 / (1 + ag/al)
        except Exception:
            return 50.0

    def _asia_range(self, idx):
        """H/L من شموع 00:00-06:59 UTC لنفس اليوم"""
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

    def _prev_day_range(self, idx):
        """H/L من أمس كاملاً — لصفقات NY"""
        try:
            ts   = self.data.index[idx]
            ts_d = getattr(ts, "date", lambda: None)()
            highs, lows = [], []
            lookback = min(idx, 30)
            for k in range(lookback, 0, -1):
                bar  = self.data.index[idx - k]
                bd   = getattr(bar, "date", lambda: None)()
                if bd == ts_d:   # نفس اليوم → يحسب Range اليوم حتى الآن
                    highs.append(float(self.data.High[idx - k]))
                    lows.append(float(self.data.Low[idx - k]))
            if len(highs) < 4:
                return None, None
            return max(highs), min(lows)
        except Exception:
            return None, None


# ═══════════════════════════════════════════════════════════════
# STRATEGY A — London Breakout V2 (محسّنة)
# ═══════════════════════════════════════════════════════════════

class LondonProV2(_Base):
    """
    تحسينات على London Breakout الأصلية:
    1. ADX > adx_min  (بعض الاتجاهية مطلوبة)
    2. Min Asia Range >= min_range_pips
    3. Max Asia Range <= max_range_pips (لا تكسر range ضيقة جداً)
    4. فقط 07:00-hour_end (أضيق = أنقى إشارة)
    5. Trailing Stop بعد 1:1
    6. TP عند 2.5× range (أوسع من الأصلية 2×)
    7. NY Session Breakout (13:00-15:00)
    """

    # ── باراميترات قابلة للتحسين ──
    buffer_pips    = 3      # عازل فوق/تحت الـ Range
    min_rr         = 2.5    # Risk:Reward
    min_range_pips = 25     # الحد الأدنى لحجم آسيا (pip)
    max_range_pips = 150    # الحد الأعلى (pip)
    adx_min        = 15     # ADX أدنى مسموح
    hour_end       = 9      # London: 07-09 فقط (ساعتان أنقى)
    use_ny         = 1      # 1 = أضف NY session

    def init(self):
        self.atr_i = self.I(
            lambda h,l,c: pd.Series([
                max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) if i>0 else h[i]-l[i]
                for i in range(len(h))
            ]).rolling(14).mean().values,
            self.data.High, self.data.Low, self.data.Close, name="ATR")

        self._trade_this_day = None    # نتداول مرة واحدة في اليوم

    def next(self):
        idx = len(self.data) - 1
        if idx < 25:
            return

        ts   = self.data.index[-1]
        hour = getattr(ts, "hour", -1)
        date = getattr(ts, "date", lambda: None)()

        atr = self.atr_i[-1]
        if np.isnan(atr) or atr == 0:
            return

        # ── Trailing Stop للصفقة المفتوحة ────────────────────
        if self.position:
            self._trail()
            return

        # ── منع التداول المتعدد في نفس اليوم ─────────────────
        if self._trade_this_day == date:
            return

        # ── London Session (07:00-hour_end UTC) ──────────────
        if 7 <= hour < self.hour_end:
            self._try_london(idx, ts, date, atr)

        # ── NY Session (13:00-15:00 UTC) ──────────────────────
        elif self.use_ny and 13 <= hour < 15:
            self._try_ny(idx, ts, date, atr)

    def _try_london(self, idx, ts, date, atr):
        ah, al = self._asia_range(idx)
        if ah is None:
            return

        rng = ah - al
        pip = self._pip
        if rng < self.min_range_pips * pip:
            return
        if rng > self.max_range_pips * pip:
            return

        adx = self._adx_val()
        if adx < self.adx_min:
            return

        buf   = self.buffer_pips * pip
        price = float(self.data.Close[-1])
        bias  = self._h4_bias(ts)

        if price > ah + buf and bias != "BEARISH":
            sl   = al - buf * 0.5
            risk = price - sl
            tp   = price + risk * self.min_rr
            self.buy(sl=sl, tp=tp)
            self._trade_this_day = date

        elif price < al - buf and bias != "BULLISH":
            sl   = ah + buf * 0.5
            risk = sl - price
            tp   = price - risk * self.min_rr
            self.sell(sl=sl, tp=tp)
            self._trade_this_day = date

    def _try_ny(self, idx, ts, date, atr):
        """NY Breakout: كسر H/L من اليوم قبل 13:00"""
        dh, dl = self._prev_day_range(idx)
        if dh is None:
            return

        rng = dh - dl
        pip = self._pip
        if rng < self.min_range_pips * pip:
            return
        if rng > self.max_range_pips * pip:
            return

        adx = self._adx_val()
        if adx < self.adx_min:
            return

        buf   = self.buffer_pips * pip
        price = float(self.data.Close[-1])
        bias  = self._h4_bias(ts)

        if price > dh + buf and bias != "BEARISH":
            sl   = dl - buf * 0.5
            risk = price - sl
            tp   = price + risk * (self.min_rr * 0.8)  # NY = أقل طموح
            self.buy(sl=sl, tp=tp)
            self._trade_this_day = date

        elif price < dl - buf and bias != "BULLISH":
            sl   = dh + buf * 0.5
            risk = sl - price
            tp   = price - risk * (self.min_rr * 0.8)
            self.sell(sl=sl, tp=tp)
            self._trade_this_day = date

    def _trail(self):
        """Trailing stop — يحرك SL للـ Breakeven عند 1:1 ثم يتبع السعر"""
        try:
            tr = self.trades[-1]
            entry  = tr.entry_price
            sl_now = tr.sl
            tp     = tr.tp
            price  = float(self.data.Close[-1])

            if tr.is_long:
                risk   = entry - sl_now
                be_trig = entry + risk      # 1:1 = breakeven trigger
                if price >= be_trig:
                    new_sl = max(sl_now, entry)                # عند الأقل: breakeven
                    trail  = price - risk * 0.5                # trail بـ 50% من الـ risk
                    new_sl = max(new_sl, trail)
                    if new_sl > sl_now:
                        tr.sl = round(new_sl, 5)
            else:
                risk   = sl_now - entry
                be_trig = entry - risk
                if price <= be_trig:
                    new_sl = min(sl_now, entry)
                    trail  = price + risk * 0.5
                    new_sl = min(new_sl, trail)
                    if new_sl < sl_now:
                        tr.sl = round(new_sl, 5)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# STRATEGY B — Grid Search على London Breakout الأصلية
# ═══════════════════════════════════════════════════════════════

class LondonGrid(_Base):
    """نسخة بسيطة بدون trailing — للـ grid search"""
    buffer_pips    = 5
    min_rr         = 2.0
    min_range_pips = 20
    adx_min        = 0

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

        pip = self._pip
        rng = ah - al
        if rng < self.min_range_pips * pip:
            return

        if self.adx_min > 0 and self._adx_val() < self.adx_min:
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
# GRID SEARCH
# ═══════════════════════════════════════════════════════════════

def run_grid(h1, h4):
    print("\n" + "═"*70)
    print("  🔍 Grid Search — London Breakout")
    print("  مجموع التركيبات:", end=" ")

    params = {
        "buffer_pips":    [3, 5, 8],
        "min_rr":         [1.5, 2.0, 2.5, 3.0],
        "min_range_pips": [15, 25, 40],
        "adx_min":        [0, 15, 20],
    }

    combos = list(itertools.product(*params.values()))
    print(len(combos))
    print("═"*70)

    LondonGrid._h4 = h4
    best = {"score": -999, "combo": None, "result": None}
    results = []

    for i, combo in enumerate(combos):
        LondonGrid.buffer_pips    = combo[0]
        LondonGrid.min_rr         = combo[1]
        LondonGrid.min_range_pips = combo[2]
        LondonGrid.adx_min        = combo[3]

        bt  = Backtest(h1, LondonGrid, cash=10_000, commission=0.0002, finalize_trades=True)
        r   = bt.run()

        trades = r["# Trades"]
        ret    = float(r["Return [%]"])
        dd     = abs(float(r["Max. Drawdown [%]"]))
        sh     = float(r["Sharpe Ratio"]) if not np.isnan(r["Sharpe Ratio"]) else 0.0
        pf     = float(r["Profit Factor"]) if r.get("Profit Factor") and not np.isnan(r["Profit Factor"]) else 0.0
        wr     = float(r["Win Rate [%]"])   if not np.isnan(r["Win Rate [%]"]) else 0.0

        # score = نعطي وزن للشارب + الربح - الـ DD
        # نريد: ret > 15%، dd < 10%، trades > 50
        score = sh * 3 + ret * 0.5 - dd * 0.3 + (pf - 1) * 5
        if trades < 30:
            score -= 20     # عقوبة للصفقات القليلة

        results.append({
            "buffer": combo[0], "rr": combo[1],
            "min_rng": combo[2], "adx": combo[3],
            "trades": trades, "ret": ret, "dd": dd,
            "sharpe": sh, "pf": pf, "wr": wr, "score": score
        })

        if score > best["score"]:
            best = {"score": score, "combo": combo, "result": r}

        if (i+1) % 10 == 0:
            print(f"  [{i+1}/{len(combos)}] أفضل حتى الآن: score={best['score']:.2f}")

    # ترتيب النتائج
    results.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n{'═'*70}")
    print(f"  🏆 أفضل 10 تركيبات:")
    print(f"{'═'*70}")
    print(f"  {'Buf':>4} {'RR':>5} {'MinRng':>7} {'ADX':>5} | {'Trades':>7} {'Ret%':>7} {'DD%':>6} {'Sharpe':>7} {'PF':>5} {'Score':>7}")
    print(f"  {'-'*65}")
    for r in results[:10]:
        print(f"  {r['buffer']:>4} {r['rr']:>5.1f} {r['min_rng']:>7} {r['adx']:>5} | "
              f"{r['trades']:>7} {r['ret']:>7.2f} {r['dd']:>6.2f} {r['sharpe']:>7.2f} {r['pf']:>5.2f} {r['score']:>7.2f}")

    return best, results


# ═══════════════════════════════════════════════════════════════
# RUN LondonProV2 بالباراميترات المحسّنة
# ═══════════════════════════════════════════════════════════════

def run_pro(h1, h4, best_combo=None):
    """تشغيل LondonProV2 — مع Trailing Stop + NY session"""
    LondonProV2._h4  = h4
    LondonProV2._pip = PIP_VALUE

    # إذا وُجدت أفضل باراميترات من grid، نطبّقها
    if best_combo:
        LondonProV2.buffer_pips    = best_combo[0]
        LondonProV2.min_rr         = best_combo[1]
        LondonProV2.min_range_pips = best_combo[2]
        LondonProV2.adx_min        = best_combo[3]

    print(f"\n{'═'*60}")
    print(f"  🚀 London Pro V2 — Trailing + NY + ADX")
    print(f"  buffer={LondonProV2.buffer_pips}pip | rr={LondonProV2.min_rr} | "
          f"min_rng={LondonProV2.min_range_pips}pip | adx>{LondonProV2.adx_min}")
    print(f"{'═'*60}")

    bt = Backtest(h1, LondonProV2, cash=10_000, commission=0.0002, finalize_trades=True)
    r  = bt.run()

    pf  = r.get("Profit Factor", 0) or 0
    pf  = 0.0 if (isinstance(pf, float) and np.isnan(pf)) else float(pf)
    sh  = float(r["Sharpe Ratio"])  if not np.isnan(r["Sharpe Ratio"])  else 0.0
    wr  = float(r["Win Rate [%]"])  if not np.isnan(r["Win Rate [%]"])  else 0.0
    ret = float(r["Return [%]"])
    dd  = float(r["Max. Drawdown [%]"])

    print(f"  📊 الصفقات     : {r['# Trades']}")
    print(f"  🎯 Win Rate    : {wr:.1f}%")
    print(f"  💰 الربح       : {ret:.2f}%")
    print(f"  📉 Max DD      : {dd:.2f}%")
    print(f"  📐 Sharpe      : {sh:.2f}")
    print(f"  ⚖️  ProfitFact : {pf:.2f}")

    # حفظ
    bt.plot(filename="LondonProV2", open_browser=False)
    print(f"\n  💾 LondonProV2.html محفوظ")

    return r


# ═══════════════════════════════════════════════════════════════
# FETCH EURUSD / GBPUSD إذا لم تكن موجودة
# ═══════════════════════════════════════════════════════════════

def fetch_extra_pairs():
    """جلب بيانات EURUSD + GBPUSD من Twelve Data إذا لم تكن موجودة"""
    pairs_needed = {
        "EURUSD": (EURUSD_H1, "EUR/USD", 0.0001),
        "GBPUSD": (GBPUSD_H1, "GBP/USD", 0.0001),
    }

    fetched = {}
    for pair, (csv_path, td_sym, pip) in pairs_needed.items():
        if os.path.exists(csv_path):
            df = load_csv(csv_path, pair)
            if df is not None and len(df) > 1000:
                fetched[pair] = (df, pip)
                continue

        print(f"  📥 جلب {pair} من Twelve Data...")
        try:
            from data.data_feed import DataFeed
            feed  = DataFeed(td_sym)
            df    = feed.get_long_history("2024-01-01", "2026-04-05", "1h")
            if df is None or len(df) < 100:
                print(f"  ⚠️ {pair}: بيانات غير كافية")
                continue
            os.makedirs("backtest_data", exist_ok=True)
            df.to_csv(csv_path)
            print(f"  ✅ {pair}: {len(df)} شمعة → {csv_path}")
            fetched[pair] = (df, pip)
        except Exception as e:
            print(f"  ❌ {pair}: {e}")

    return fetched


# ═══════════════════════════════════════════════════════════════
# MULTI-PAIR TEST
# ═══════════════════════════════════════════════════════════════

def run_multi_pair(h4, best_combo):
    """اختبار الاستراتيجية الفائزة على أزواج إضافية"""
    extra = fetch_extra_pairs()
    if not extra:
        print("\n  ⚠️ لا توجد بيانات إضافية لـ multi-pair")
        return

    print(f"\n{'═'*60}")
    print(f"  🌍 Multi-Pair Test — الاستراتيجية الفائزة")
    print(f"{'═'*60}")

    for pair, (df, pip) in extra.items():
        LondonProV2._h4  = h4
        LondonProV2._pip = pip
        if best_combo:
            LondonProV2.buffer_pips    = best_combo[0]
            LondonProV2.min_rr         = best_combo[1]
            LondonProV2.min_range_pips = best_combo[2]
            LondonProV2.adx_min        = best_combo[3]

        bt = Backtest(df, LondonProV2, cash=10_000, commission=0.0002, finalize_trades=True)
        r  = bt.run()
        ret = float(r["Return [%]"])
        sh  = float(r["Sharpe Ratio"]) if not np.isnan(r["Sharpe Ratio"]) else 0.0
        pf  = r.get("Profit Factor", 0) or 0
        pf  = 0.0 if (isinstance(pf, float) and np.isnan(pf)) else float(pf)
        print(f"  {pair}: trades={r['# Trades']} | ret={ret:.2f}% | sharpe={sh:.2f} | PF={pf:.2f}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "═"*70)
    print("  🏆 London Breakout Optimizer — هدف: > 30% / سنة")
    print("═"*70)

    print("\n📂 تحميل البيانات...")
    h1 = load_csv(H1_CSV, "USDJPY H1")
    h4 = load_csv(H4_CSV, "USDJPY H4")

    if h1 is None or len(h1) < 500:
        print("❌ H1 غير موجود — شغّل ict_backtest.py أولاً")
        sys.exit(1)

    # ── خطوة 1: Grid Search ───────────────────────────────────
    print("\n🔍 الخطوة 1: Grid Search...")
    best, all_results = run_grid(h1, h4)
    best_combo = best["combo"]
    print(f"\n  🏆 أفضل تركيبة: buffer={best_combo[0]} | rr={best_combo[1]} | "
          f"min_rng={best_combo[2]} | adx={best_combo[3]}")

    # ── خطوة 2: LondonProV2 بالباراميترات الفائزة ─────────────
    print("\n🚀 الخطوة 2: London Pro V2 (Trailing + NY)...")
    r_pro = run_pro(h1, h4, best_combo)

    # ── خطوة 3: مقارنة مع الأصلية ─────────────────────────────
    print(f"\n{'═'*60}")
    print(f"  📊 المقارنة النهائية:")
    print(f"{'═'*60}")

    orig_ret = 11.97
    orig_sh  = 0.65
    orig_dd  = -6.21
    pro_ret  = float(r_pro["Return [%]"])
    pro_sh   = float(r_pro["Sharpe Ratio"]) if not np.isnan(r_pro["Sharpe Ratio"]) else 0.0
    pro_dd   = float(r_pro["Max. Drawdown [%]"])

    print(f"  {'':20s} {'Original':>12} {'ProV2':>12}")
    print(f"  {'الربح':20s} {orig_ret:>12.2f}% {pro_ret:>12.2f}%")
    print(f"  {'Sharpe':20s} {orig_sh:>12.2f} {pro_sh:>12.2f}")
    print(f"  {'Max DD':20s} {orig_dd:>12.2f}% {pro_dd:>12.2f}%")

    improvement = ((pro_ret - orig_ret) / abs(orig_ret)) * 100 if orig_ret != 0 else 0
    print(f"\n  {'التحسن في الربح':20s} {improvement:>+.1f}%")

    # ── خطوة 4: Multi-Pair ────────────────────────────────────
    print("\n🌍 الخطوة 4: Multi-Pair Test...")
    run_multi_pair(h4, best_combo)

    print(f"\n{'═'*70}")
    print("  ✅ الأوبتيمايزر اكتمل!")
    print(f"{'═'*70}\n")
