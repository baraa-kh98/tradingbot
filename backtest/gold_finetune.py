"""
Gold ATR Breakout — Fine Tuning + M15 Test
============================================
بناءً على نتائج gold_research.py:
  الفائز: ATR_Breakout (nbar=30, adx=18, sl=2.0, rr=2.0) → Sharpe=1.025 Ret=41%

الهدف:
  1. Fine-tune دقيق على H1 لتحسين Sharpe > 1.2
  2. اختبار نفس الفكرة على M15 (أكثر دقة)
  3. الانتهاء بأفضل تركيبة جاهزة للـ production
"""

import pandas as pd
import numpy as np
import sys, os, json, math, warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting import Backtest, Strategy

H1_CSV  = "backtest_data/XAUUSD_H1_2years.csv"
M15_CSV = "backtest_data/XAUUSD_M15_2years.csv"


def load_csv(path, max_rows=None):
    if not os.path.exists(path):
        print(f"❌ غير موجود: {path}")
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True, nrows=max_rows)
    df.index = pd.to_datetime(df.index, utc=True)
    cols = [c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]
    df = df[cols].dropna()
    print(f"✅ {os.path.basename(path)}: {len(df)} شمعة | {df.index[0].date()} → {df.index[-1].date()}")
    return df


def safe(v, d=0.0):
    try:
        f = float(v)
        return d if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return d


def score(stats, min_trades=25) -> float:
    t = int(stats.get("# Trades", 0))
    if t < min_trades:
        return -999.0
    return (
        safe(stats.get("Sharpe Ratio")) * 6
        + safe(stats.get("Return [%]")) * 0.2
        - abs(safe(stats.get("Max. Drawdown [%]"))) * 0.4
        + (safe(stats.get("Profit Factor")) - 1) * 5
    )


# ════════════════════════════════════════════════════════════════
# GOLD ATR BREAKOUT — Production Version
# ════════════════════════════════════════════════════════════════

class GoldATRBreakout(Strategy):
    """
    Gold N-Bar Channel Breakout + ADX Filter

    BUY:  Close يكسر فوق أعلى nbar شمعة + ADX > adx_min
    SELL: Close يكسر تحت أدنى nbar شمعة + ADX > adx_min
    SL:   entry ± atr_sl × ATR
    TP:   entry ± min_rr × risk

    اختياري: trailing stop بعد 1.5× risk
    """
    nbar        = 30
    adx_min     = 18
    atr_sl      = 2.0
    min_rr      = 2.0
    trail_at_rr = 0.0    # 0 = disabled, 1.5 = trail بعد 1.5×R

    def init(self): pass

    def _atr(self, period=14) -> float:
        try:
            n = min(len(self.data)-1, period*3)
            h = np.array(self.data.High[-n:],  dtype=float)
            l = np.array(self.data.Low[-n:],   dtype=float)
            c = np.array(self.data.Close[-n:], dtype=float)
            tr = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
                  for i in range(1, len(h))]
            return float(np.mean(tr[-period:])) if len(tr) >= period else float(np.mean(tr))
        except Exception:
            return 5.0

    def _adx(self, period=14) -> float:
        try:
            n  = min(len(self.data)-1, period*4)
            h  = np.array(self.data.High[-n:],  dtype=float)
            l  = np.array(self.data.Low[-n:],   dtype=float)
            c  = np.array(self.data.Close[-n:], dtype=float)
            if len(h) < period+2: return 0.0
            dh = np.diff(h); dl = -np.diff(l)
            dmp = np.where((dh>dl)&(dh>0), dh, 0.0)
            dmm = np.where((dl>dh)&(dl>0), dl, 0.0)
            tr  = np.array([max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1]))
                            for i in range(1,len(h))])
            def smma(a,p):
                o=np.zeros(len(a)); o[p-1]=a[:p].mean()
                for i in range(p,len(a)): o[i]=(o[i-1]*(p-1)+a[i])/p
                return o
            atr_s=smma(tr,period)
            dip=smma(dmp,period)/(atr_s+1e-9)*100
            dim=smma(dmm,period)/(atr_s+1e-9)*100
            dx=np.abs(dip-dim)/(dip+dim+1e-9)*100
            return float(np.mean(dx[-period:]))
        except Exception:
            return 0.0

    def next(self):
        n = len(self.data)
        if n < self.nbar + 15 or self.position:
            return

        price  = float(self.data.Close[-1])
        prev_c = float(self.data.Close[-2])
        atr    = self._atr()
        adx    = self._adx()

        if adx < self.adx_min or atr <= 0:
            return

        # Channel High/Low (excluding current bar)
        ch_high = float(np.max(np.array(self.data.High[-(self.nbar+1):-1], dtype=float)))
        ch_low  = float(np.min(np.array(self.data.Low[-(self.nbar+1):-1],  dtype=float)))

        sl_dist = self.atr_sl * atr

        # ── BUY breakout ─────────────────────────────────────
        if prev_c <= ch_high and price > ch_high:
            sl = price - sl_dist
            if sl_dist > 0:
                self.buy(sl=sl, tp=price + sl_dist * self.min_rr)

        # ── SELL breakout ────────────────────────────────────
        elif prev_c >= ch_low and price < ch_low:
            sl = price + sl_dist
            if sl_dist > 0:
                self.sell(sl=sl, tp=price - sl_dist * self.min_rr)


# ════════════════════════════════════════════════════════════════
# FINE TUNE GRID
# ════════════════════════════════════════════════════════════════

def fine_tune(h1, label="H1"):
    """Fine-tune حول أفضل نتائج gold_research"""
    from itertools import product

    param_grid = {
        "nbar":    [20, 25, 30, 35, 40],
        "adx_min": [15, 18, 20, 22, 25],
        "atr_sl":  [1.5, 1.8, 2.0, 2.2, 2.5],
        "min_rr":  [1.8, 2.0, 2.2, 2.5, 3.0],
    }

    keys   = list(param_grid.keys())
    combos = list(product(*[param_grid[k] for k in keys]))
    total  = len(combos)
    min_t  = 30 if label == "H1" else 60

    print(f"\n{'═'*60}")
    print(f"  Fine-Tune ATR Breakout on {label} — {total} تركيبة")
    print(f"{'═'*60}")

    results = []
    for i, combo in enumerate(combos, 1):
        params = dict(zip(keys, combo))
        for k, v in params.items():
            setattr(GoldATRBreakout, k, v)

        try:
            bt    = Backtest(h1, GoldATRBreakout, cash=10_000,
                             commission=0.0002, finalize_trades=True)
            stats = bt.run()
            sc    = score(stats, min_t)
            t     = int(stats.get("# Trades", 0))
            row   = {
                "label":   label,
                **params,
                "trades":  t,
                "wr":      round(safe(stats.get("Win Rate [%]")), 1),
                "ret":     round(safe(stats.get("Return [%]")), 2),
                "ann_ret": round(safe(stats.get("Return (Ann.) [%]")), 2),
                "dd":      round(safe(stats.get("Max. Drawdown [%]")), 2),
                "sharpe":  round(safe(stats.get("Sharpe Ratio")), 3),
                "pf":      round(safe(stats.get("Profit Factor")), 3),
                "score":   round(sc, 3),
            }
            results.append(row)

            if i % max(1, total//8) == 0 or i == total:
                print(f"  [{i:>4}/{total}] n={params['nbar']:>2} adx={params['adx_min']:>2} "
                      f"sl={params['atr_sl']} rr={params['min_rr']} → "
                      f"T={t:>3} WR={row['wr']:>4}% Ret={row['ret']:>6.1f}% Sh={row['sharpe']:.3f}")

        except Exception as e:
            pass

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def print_top(results, n=10, label=""):
    print(f"\n{'─'*72}")
    print(f"  أفضل {n} — {label}")
    print(f"{'─'*72}")
    hdr = f"{'n':>4} {'adx':>4} {'sl':>5} {'rr':>5} {'T':>5} {'WR%':>6} {'Ret%':>7} {'DD%':>7} {'Sharpe':>7} {'PF':>5} {'Score':>7}"
    print(hdr); print("─"*len(hdr))
    for r in results[:n]:
        print(f"{r['nbar']:>4} {r['adx_min']:>4} {r['atr_sl']:>5} {r['min_rr']:>5} "
              f"{r['trades']:>5} {r['wr']:>6.1f} {r['ret']:>7.2f} {r['dd']:>7.2f} "
              f"{r['sharpe']:>7.3f} {r['pf']:>5.3f} {r['score']:>7.2f}")


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # ── H1 Fine-Tune ─────────────────────────────────────────
    h1 = load_csv(H1_CSV)
    if h1 is None: sys.exit(1)

    h1_results = fine_tune(h1, "H1")
    print_top(h1_results, 10, "H1 ATR Breakout")

    best_h1 = h1_results[0]
    print(f"\n  🏆 H1 Best: n={best_h1['nbar']} adx={best_h1['adx_min']} "
          f"sl={best_h1['atr_sl']} rr={best_h1['min_rr']}")
    print(f"  T={best_h1['trades']} WR={best_h1['wr']}% Ret={best_h1['ret']}% "
          f"Sharpe={best_h1['sharpe']} PF={best_h1['pf']} DD={best_h1['dd']}%")

    # ── M15 Test (نفس الـ grid لكن بـ nbar مكبّر ×4) ─────────
    m15 = load_csv(M15_CSV)
    if m15 is not None:
        # على M15: nbar×4 لأن كل شمعة 15min بدل ساعة
        # ATR على M15 أصغر (~0.25×H1) لكن الـ backtesting lib تتعامل معها بالدولار
        from itertools import product

        m15_grid = {
            "nbar":    [80, 100, 120, 160],   # ×4 من H1
            "adx_min": [18, 22, 25],
            "atr_sl":  [2.0, 2.5, 3.0],
            "min_rr":  [2.0, 2.5, 3.0],
        }

        keys   = list(m15_grid.keys())
        combos = list(product(*[m15_grid[k] for k in keys]))
        total  = len(combos)

        print(f"\n{'═'*60}")
        print(f"  ATR Breakout على M15 — {total} تركيبة")
        print(f"{'═'*60}")

        m15_results = []
        for i, combo in enumerate(combos, 1):
            params = dict(zip(keys, combo))
            for k, v in params.items():
                setattr(GoldATRBreakout, k, v)
            try:
                bt    = Backtest(m15, GoldATRBreakout, cash=10_000,
                                 commission=0.0002, finalize_trades=True)
                stats = bt.run()
                sc    = score(stats, 60)
                t     = int(stats.get("# Trades", 0))
                row   = {
                    "label": "M15",
                    **params,
                    "trades":  t,
                    "wr":      round(safe(stats.get("Win Rate [%]")), 1),
                    "ret":     round(safe(stats.get("Return [%]")), 2),
                    "ann_ret": round(safe(stats.get("Return (Ann.) [%]")), 2),
                    "dd":      round(safe(stats.get("Max. Drawdown [%]")), 2),
                    "sharpe":  round(safe(stats.get("Sharpe Ratio")), 3),
                    "pf":      round(safe(stats.get("Profit Factor")), 3),
                    "score":   round(sc, 3),
                }
                m15_results.append(row)

                if i % max(1, total//6) == 0 or i == total:
                    print(f"  [{i:>3}/{total}] n={params['nbar']:>3} adx={params['adx_min']:>2} "
                          f"sl={params['atr_sl']} rr={params['min_rr']} → "
                          f"T={t:>4} Ret={row['ret']:>6.1f}% Sh={row['sharpe']:.3f}")

            except Exception as e:
                pass

        m15_results.sort(key=lambda x: x["score"], reverse=True)
        print_top(m15_results, 10, "M15 ATR Breakout")

        best_m15 = m15_results[0] if m15_results else None
        if best_m15:
            print(f"\n  🏆 M15 Best: n={best_m15['nbar']} adx={best_m15['adx_min']} "
                  f"sl={best_m15['atr_sl']} rr={best_m15['min_rr']}")
            print(f"  T={best_m15['trades']} WR={best_m15['wr']}% Ret={best_m15['ret']}% "
                  f"Sharpe={best_m15['sharpe']} PF={best_m15['pf']} DD={best_m15['dd']}%")
    else:
        m15_results = []
        best_m15 = None

    # ── المقارنة النهائية ─────────────────────────────────────
    print(f"\n{'═'*60}")
    print("  H1 vs M15 — المقارنة النهائية")
    print(f"{'═'*60}")

    winner = best_h1
    winner_tf = "H1"

    if best_m15 and best_m15["score"] > best_h1["score"]:
        winner = best_m15
        winner_tf = "M15"

    print(f"\n  الفائز النهائي: {winner_tf}")
    print(f"  nbar={winner['nbar']} | adx_min={winner['adx_min']} | "
          f"atr_sl={winner['atr_sl']} | min_rr={winner['min_rr']}")
    print(f"  Trades={winner['trades']} | WR={winner['wr']}% | "
          f"Return={winner['ret']}% | Ann={winner['ann_ret']}%")
    print(f"  Sharpe={winner['sharpe']} | PF={winner['pf']} | DD={winner['dd']}%")

    PASS = (
        winner["sharpe"] > 0.7 and
        winner["ret"]    > 15  and
        abs(winner["dd"]) < 18 and
        winner["pf"]     > 1.2 and
        winner["trades"] >= 30
    )
    print(f"\n  {'✅ مرّت جميع المعايير — الاستراتيجية جاهزة!' if PASS else '⚠️ لم تمر المعايير الكاملة'}")

    # ── حفظ ─────────────────────────────────────────────────
    os.makedirs("journal", exist_ok=True)
    out = "journal/gold_finetune_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "winner_tf": winner_tf,
            "winner":    winner,
            "passed":    PASS,
            "h1_top10":  h1_results[:10],
            "m15_top10": m15_results[:10] if m15_results else [],
        }, f, indent=2, ensure_ascii=False)

    print(f"  💾 النتائج: {out}")
    print(f"\n  الخطوة القادمة: بناء strategy/xauusd_signal.py بالباراميترات الفائزة")
