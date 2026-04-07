"""
XAUUSD Gold ICT Backtest
========================
استراتيجية: NY Session ICT Order Block + FVG
  - H4 bias: EMA20 vs EMA50
  - Kill Zone: NY فقط (13:00-16:00 UTC) — مش London
  - دخول: سعر يدخل Order Block + FVG كتأكيد
  - SL: تحت/فوق OB بـ sl_buffer pips
  - TP: min_rr × risk

Grid Search:
  ob_max_age: [20, 35, 50]
  fvg_required: [True, False]
  sl_buffer_pips: [3, 5, 8]
  min_rr: [2.0, 2.5, 3.0]
"""

import pandas as pd
import numpy as np
import sys, os, json, warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting import Backtest, Strategy

# ── Constants ────────────────────────────────────────────────────
H1_CSV      = "backtest_data/XAUUSD_H1_2years.csv"
PIP         = 0.01      # Gold pip value
NY_START    = 13        # UTC
NY_END      = 16        # UTC
ATR_PERIOD  = 14
OB_DISPLACE = 1.5       # ATR multiplier for displacement detection


# ── Data ─────────────────────────────────────────────────────────

def load_csv(path):
    if not os.path.exists(path):
        print(f"❌ ملف غير موجود: {path}")
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[cols].dropna()
    print(f"✅ {os.path.basename(path)}: {len(df)} شمعة | {df.index[0].date()} → {df.index[-1].date()}")
    return df


# ── Base helpers ─────────────────────────────────────────────────

class _GoldBase(Strategy):
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
            if e20 > e50 * 1.0005: return "BULLISH"
            if e20 < e50 * 0.9995: return "BEARISH"
            return "NEUTRAL"
        except Exception:
            return "NEUTRAL"

    def _calc_atr(self, n=ATR_PERIOD) -> float:
        try:
            h = np.array(self.data.High[-(n*2):], dtype=float)
            l = np.array(self.data.Low[-(n*2):],  dtype=float)
            c = np.array(self.data.Close[-(n*2):], dtype=float)
            tr = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                  for i in range(1, len(h))]
            return float(np.mean(tr[-n:])) if len(tr) >= n else float(np.mean(tr))
        except Exception:
            return 1.0

    def _find_bullish_ob(self, lookback: int, max_age: int):
        """
        آخر OB صعودي نشط:
        - آخر شمعة هبوطية قبل حركة صعودية قوية (displacement > ATR × 1.5)
        - لم يتم اختراقه
        يرجع: (ob_top, ob_bottom) أو (None, None)
        """
        try:
            n = len(self.data)
            h = np.array(self.data.High,  dtype=float)
            l = np.array(self.data.Low,   dtype=float)
            o = np.array(self.data.Open,  dtype=float)
            c = np.array(self.data.Close, dtype=float)
            atr = self._calc_atr()

            # ابحث عن OBs من آخر max_age شمعة
            start = max(2, n - max_age)
            found_obs = []

            for i in range(start, n - 1):
                body = abs(c[i] - o[i])
                # Bullish displacement: شمعة صعودية قوية
                if c[i] > o[i] and body > atr * OB_DISPLACE:
                    # آخر شمعة هبوطية قبلها
                    for j in range(i - 1, max(i - 4, 0), -1):
                        if c[j] < o[j]:  # هبوطية
                            ob_top    = float(o[j])
                            ob_bottom = float(c[j])
                            # تأكد لم يُخترق
                            mitigated = any(l[k] < ob_bottom for k in range(i + 1, n))
                            if not mitigated:
                                found_obs.append((j, ob_top, ob_bottom))
                            break

            # أحدث OB
            if found_obs:
                found_obs.sort(key=lambda x: x[0], reverse=True)
                _, ob_top, ob_bottom = found_obs[0]
                return ob_top, ob_bottom
        except Exception:
            pass
        return None, None

    def _find_bearish_ob(self, lookback: int, max_age: int):
        """
        آخر OB هبوطي نشط
        يرجع: (ob_top, ob_bottom) أو (None, None)
        """
        try:
            n = len(self.data)
            h = np.array(self.data.High,  dtype=float)
            l = np.array(self.data.Low,   dtype=float)
            o = np.array(self.data.Open,  dtype=float)
            c = np.array(self.data.Close, dtype=float)
            atr = self._calc_atr()

            start = max(2, n - max_age)
            found_obs = []

            for i in range(start, n - 1):
                body = abs(c[i] - o[i])
                # Bearish displacement: شمعة هبوطية قوية
                if c[i] < o[i] and body > atr * OB_DISPLACE:
                    for j in range(i - 1, max(i - 4, 0), -1):
                        if c[j] > o[j]:  # صعودية
                            ob_top    = float(c[j])
                            ob_bottom = float(o[j])
                            mitigated = any(h[k] > ob_top for k in range(i + 1, n))
                            if not mitigated:
                                found_obs.append((j, ob_top, ob_bottom))
                            break

            if found_obs:
                found_obs.sort(key=lambda x: x[0], reverse=True)
                _, ob_top, ob_bottom = found_obs[0]
                return ob_top, ob_bottom
        except Exception:
            pass
        return None, None

    def _has_bullish_fvg_near(self, price: float, tolerance: float) -> bool:
        """هل يوجد Bullish FVG قريب من السعر الحالي؟"""
        try:
            n = len(self.data)
            h = np.array(self.data.High,  dtype=float)
            l = np.array(self.data.Low,   dtype=float)
            search = min(30, n - 2)
            for i in range(n - search, n - 1):
                gap_bottom = h[i - 2] if i >= 2 else 0
                gap_top    = l[i]
                if gap_top > gap_bottom:
                    midpoint = (gap_top + gap_bottom) / 2
                    if abs(price - midpoint) <= tolerance:
                        return True
        except Exception:
            pass
        return False

    def _has_bearish_fvg_near(self, price: float, tolerance: float) -> bool:
        """هل يوجد Bearish FVG قريب من السعر الحالي؟"""
        try:
            n = len(self.data)
            h = np.array(self.data.High,  dtype=float)
            l = np.array(self.data.Low,   dtype=float)
            search = min(30, n - 2)
            for i in range(n - search, n - 1):
                gap_top    = l[i - 2] if i >= 2 else float("inf")
                gap_bottom = h[i]
                if gap_top > gap_bottom:
                    midpoint = (gap_top + gap_bottom) / 2
                    if abs(price - midpoint) <= tolerance:
                        return True
        except Exception:
            pass
        return False


# ═══════════════════════════════════════════════════════════════
# GOLD ICT NY STRATEGY
# ═══════════════════════════════════════════════════════════════

class GoldICTNY(_GoldBase):
    """
    Gold ICT — NY Session Order Block + FVG
    ----------------------------------------
    1. H4 bias (EMA20/50) — يحدد الاتجاه
    2. NY Kill Zone فقط (13:00-16:00 UTC)
    3. BUY: سعر يدخل Bullish OB + FVG تأكيد (اختياري)
    4. SELL: سعر يدخل Bearish OB + FVG تأكيد (اختياري)
    """

    ob_max_age      = 35      # عمر الـ OB بالشموع
    sl_buffer_pips  = 5       # هامش SL تحت/فوق الـ OB
    min_rr          = 2.5     # نسبة TP/SL
    fvg_required    = True    # هل FVG إلزامي للدخول؟

    _trade_date = None

    def init(self):
        pass

    def next(self):
        idx = len(self.data) - 1
        if idx < 30 or self.position:
            return

        ts   = self.data.index[-1]
        hour = getattr(ts, "hour", -1)

        # NY Kill Zone فقط
        if not (NY_START <= hour < NY_END):
            return

        # صفقة واحدة يومياً فقط
        today = getattr(ts, "date", lambda: None)()
        if self._trade_date == today:
            return

        bias  = self._h4_bias(ts)
        price = float(self.data.Close[-1])
        buf   = self.sl_buffer_pips * PIP
        atr   = self._calc_atr()
        fvg_tol = atr * 0.3   # تسامح FVG = 30% من ATR

        # ── BUY SETUP ────────────────────────────────────────────
        if bias != "BEARISH":
            ob_top, ob_bottom = self._find_bullish_ob(idx, self.ob_max_age)
            if ob_top is not None and ob_bottom <= price <= ob_top:
                # السعر داخل الـ OB
                if self.fvg_required and not self._has_bullish_fvg_near(price, fvg_tol):
                    pass  # FVG مطلوب لكن غير موجود
                else:
                    sl   = ob_bottom - buf
                    risk = price - sl
                    if risk > 0:
                        tp = price + risk * self.min_rr
                        self._trade_date = today
                        self.buy(sl=sl, tp=tp)
                        return

        # ── SELL SETUP ───────────────────────────────────────────
        if bias != "BULLISH":
            ob_top, ob_bottom = self._find_bearish_ob(idx, self.ob_max_age)
            if ob_top is not None and ob_bottom <= price <= ob_top:
                if self.fvg_required and not self._has_bearish_fvg_near(price, fvg_tol):
                    pass
                else:
                    sl   = ob_top + buf
                    risk = sl - price
                    if risk > 0:
                        tp = price - risk * self.min_rr
                        self._trade_date = today
                        self.sell(sl=sl, tp=tp)


# ═══════════════════════════════════════════════════════════════
# GRID SEARCH
# ═══════════════════════════════════════════════════════════════

def score(stats) -> float:
    """نقاط المقارنة — نفس معيار london_final"""
    import math
    def s(v, d=0.0):
        try:
            f = float(v)
            return d if math.isnan(f) or math.isinf(f) else f
        except Exception:
            return d

    trades = int(stats.get("# Trades", 0))
    if trades < 20:
        return -999.0
    return (
        s(stats.get("Sharpe Ratio")) * 4
        + s(stats.get("Return [%]")) * 0.3
        - abs(s(stats.get("Max. Drawdown [%]"))) * 0.2
        + (s(stats.get("Profit Factor")) - 1) * 3
    )


def run_grid(h1: pd.DataFrame):
    import math

    param_grid = {
        "ob_max_age":     [20, 35, 50],
        "fvg_required":   [True, False],
        "sl_buffer_pips": [3, 5, 8],
        "min_rr":         [2.0, 2.5, 3.0],
    }

    results = []
    total = (len(param_grid["ob_max_age"]) *
             len(param_grid["fvg_required"]) *
             len(param_grid["sl_buffer_pips"]) *
             len(param_grid["min_rr"]))

    print(f"\n🔍 Grid Search — {total} تركيبة\n")
    count = 0

    for ob_age in param_grid["ob_max_age"]:
        for fvg_req in param_grid["fvg_required"]:
            for sl_buf in param_grid["sl_buffer_pips"]:
                for rr in param_grid["min_rr"]:
                    count += 1

                    GoldICTNY.ob_max_age     = ob_age
                    GoldICTNY.fvg_required   = fvg_req
                    GoldICTNY.sl_buffer_pips = sl_buf
                    GoldICTNY.min_rr         = rr

                    try:
                        bt    = Backtest(h1, GoldICTNY, cash=10_000,
                                         commission=0.0002, finalize_trades=True)
                        stats = bt.run()

                        def sf(v, d=0.0):
                            try:
                                f = float(v)
                                return d if math.isnan(f) or math.isinf(f) else f
                            except Exception:
                                return d

                        trades = int(stats.get("# Trades", 0))
                        sc     = score(stats)

                        row = {
                            "ob_max_age":     ob_age,
                            "fvg_required":   fvg_req,
                            "sl_buffer_pips": sl_buf,
                            "min_rr":         rr,
                            "trades":         trades,
                            "win_rate":       round(sf(stats.get("Win Rate [%]")), 1),
                            "return_pct":     round(sf(stats.get("Return [%]")), 2),
                            "max_dd":         round(sf(stats.get("Max. Drawdown [%]")), 2),
                            "sharpe":         round(sf(stats.get("Sharpe Ratio")), 3),
                            "profit_factor":  round(sf(stats.get("Profit Factor")), 3),
                            "score":          round(sc, 3),
                        }
                        results.append(row)

                        if count % 9 == 0 or count == total:
                            print(f"  [{count}/{total}] ob={ob_age} fvg={fvg_req} sl={sl_buf} rr={rr} "
                                  f"→ trades={trades} WR={row['win_rate']}% ret={row['return_pct']}% "
                                  f"sharpe={row['sharpe']} score={sc:.2f}")

                    except Exception as e:
                        print(f"  ⚠️ [{count}/{total}] خطأ: {e}")

    return results


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import math

    h1 = load_csv(H1_CSV)
    if h1 is None:
        sys.exit(1)

    # ── Grid Search ──────────────────────────────────────────────
    results = run_grid(h1)

    if not results:
        print("❌ لا توجد نتائج")
        sys.exit(1)

    # ── ترتيب حسب الـ Score ──────────────────────────────────────
    results.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n{'='*70}")
    print("  أفضل 5 تركيبات — Gold ICT NY Strategy")
    print(f"{'='*70}")
    header = f"{'ob':>4} {'fvg':>5} {'sl':>4} {'rr':>5} {'trades':>7} {'WR%':>6} {'Ret%':>7} {'DD%':>7} {'Sharpe':>7} {'PF':>5} {'Score':>7}"
    print(header)
    print("-" * len(header))
    for r in results[:5]:
        print(
            f"{r['ob_max_age']:>4} {str(r['fvg_required']):>5} {r['sl_buffer_pips']:>4} {r['min_rr']:>5} "
            f"{r['trades']:>7} {r['win_rate']:>6.1f} {r['return_pct']:>7.2f} "
            f"{r['max_dd']:>7.2f} {r['sharpe']:>7.3f} {r['profit_factor']:>5.2f} {r['score']:>7.2f}"
        )

    # ── معايير القبول ────────────────────────────────────────────
    best = results[0]
    print(f"\n{'='*70}")
    print(f"  أفضل تركيبة: ob_max_age={best['ob_max_age']} | fvg={best['fvg_required']} | "
          f"sl_buf={best['sl_buffer_pips']} | rr={best['min_rr']}")
    print(f"  النتائج: {best['trades']} صفقة | WR={best['win_rate']}% | "
          f"Return={best['return_pct']}% | Sharpe={best['sharpe']} | PF={best['profit_factor']}")

    PASS = (
        best["sharpe"] > 0.5 and
        best["return_pct"] > 10 and
        abs(best["max_dd"]) < 15 and
        best["profit_factor"] > 1.3 and
        best["trades"] >= 40
    )
    print(f"\n  {'✅ مرّت معايير القبول — الاستراتيجية جاهزة للتطوير' if PASS else '❌ لم تمر المعايير — نحتاج استراتيجية بديلة'}")

    # ── حفظ النتائج ──────────────────────────────────────────────
    os.makedirs("journal", exist_ok=True)
    out_path = "journal/xauusd_backtest_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "strategy":    "GoldICTNY",
            "pair":        "XAUUSD",
            "data":        H1_CSV,
            "total_tested": len(results),
            "best_params": best,
            "top_results": results[:10],
            "passed":      PASS,
        }, f, indent=2, ensure_ascii=False)
    print(f"  💾 النتائج محفوظة في {out_path}")
