"""
Parameter Optimizer — تحسين معاملات الاستراتيجية

يختبر مجموعات مختلفة من المعاملات على بيانات تاريخية
ويحدد الأفضل بناءً على Sharpe, Profit Factor, Win Rate
"""

import json
import os
import itertools
from datetime import datetime
import pandas as pd
import numpy as np


def _run_ict_backtest(data, params):
    """باكتست سريع مع معاملات محددة"""
    import strategy.ict_core as ict

    high = data["High"].values if isinstance(data["High"], pd.Series) else data["High"].squeeze().values
    low = data["Low"].values if isinstance(data["Low"], pd.Series) else data["Low"].squeeze().values
    close = data["Close"].values if isinstance(data["Close"], pd.Series) else data["Close"].squeeze().values
    open_p = data["Open"].values if isinstance(data["Open"], pd.Series) else data["Open"].squeeze().values

    pip = params.get("pip_value", 0.01)
    min_rr = params.get("min_rr", 2.0)
    sl_buffer = params.get("ob_buffer_pips", 10) * pip
    lookback = params.get("swing_lookback", 5)
    ob_disp = params.get("ob_displacement", 1.5)
    ob_age = params.get("ob_max_age", 50)
    n = len(data)
    trades = []
    i = lookback + 20

    while i < n - 10:
        window = data.iloc[max(0, i - 200):i + 1]
        if len(window) < 50:
            i += 1
            continue
        try:
            swing_highs, swing_lows = ict.detect_swing_points(window, lookback)
            if len(swing_highs) < 2 or len(swing_lows) < 2:
                i += 1
                continue
            structure = ict.detect_market_structure(window, lookback)
            trend = structure["trend"]
            if trend == "NEUTRAL":
                i += 1
                continue

            w_open = window["Open"].values if isinstance(window["Open"], pd.Series) else window["Open"].squeeze().values
            w_close = window["Close"].values if isinstance(window["Close"], pd.Series) else window["Close"].squeeze().values
            w_high = window["High"].values if isinstance(window["High"], pd.Series) else window["High"].squeeze().values
            w_low = window["Low"].values if isinstance(window["Low"], pd.Series) else window["Low"].squeeze().values
            atr = ict._calculate_atr(window)
            w_n = len(window)
            current_price = float(w_close[-1])

            active_ob = None
            for j in range(w_n - 2, max(w_n - ob_age, 2), -1):
                if np.isnan(atr[j]):
                    continue
                body = abs(w_close[j] - w_open[j])
                disp_th = atr[j] * ob_disp
                if trend == "BULLISH" and w_close[j] > w_open[j] and body > disp_th:
                    for k in range(j - 1, max(j - 4, 0), -1):
                        if w_close[k] < w_open[k]:
                            ob_top = float(w_open[k])
                            ob_bot = float(w_close[k])
                            if ob_bot <= current_price <= ob_top * 1.003:
                                active_ob = {"type": "BULLISH", "top": ob_top, "bottom": ob_bot, "low": float(w_low[k])}
                            break
                    if active_ob:
                        break
                elif trend == "BEARISH" and w_close[j] < w_open[j] and body > disp_th:
                    for k in range(j - 1, max(j - 4, 0), -1):
                        if w_close[k] > w_open[k]:
                            ob_top = float(w_close[k])
                            ob_bot = float(w_open[k])
                            if ob_bot * 0.997 <= current_price <= ob_top:
                                active_ob = {"type": "BEARISH", "top": ob_top, "bottom": ob_bot, "high": float(w_high[k])}
                            break
                    if active_ob:
                        break

            if not active_ob:
                i += 3
                continue

            if active_ob["type"] == "BULLISH":
                entry = current_price
                sl = active_ob["low"] - sl_buffer
                risk = entry - sl
                if risk <= 0:
                    i += 1
                    continue
                tp = entry + risk * min_rr
                direction = "BUY"
            else:
                entry = current_price
                sl = active_ob.get("high", active_ob["top"]) + sl_buffer
                risk = sl - entry
                if risk <= 0:
                    i += 1
                    continue
                tp = entry - risk * min_rr
                direction = "SELL"

            hit_tp = False
            hit_sl = False
            for k in range(i + 1, min(i + 50, n)):
                if direction == "BUY":
                    if low[k] <= sl:
                        hit_sl = True
                        break
                    if high[k] >= tp:
                        hit_tp = True
                        break
                else:
                    if high[k] >= sl:
                        hit_sl = True
                        break
                    if low[k] <= tp:
                        hit_tp = True
                        break

            if hit_tp or hit_sl:
                if hit_tp:
                    pips = (tp - entry) / pip if direction == "BUY" else abs((entry - tp) / pip)
                else:
                    pips = -(abs(risk) / pip)

                # خصم تكلفة الـ spread (واقعي)
                spread_pips = params.get("spread_pips", 1.5)
                slippage_pips = 0.65  # متوسط الانزلاق
                pips -= (spread_pips + slippage_pips)

                trades.append({"win": hit_tp, "pips": float(pips), "index": i})
                i += 10
            else:
                i += 3
        except Exception:
            i += 1

    if not trades:
        return {"trades": 0, "win_rate": 0, "profit_factor": 0, "total_pips": 0, "sharpe": 0, "max_dd": 0}

    wins = [t for t in trades if t["win"]]
    losses = [t for t in trades if not t["win"]]
    total_pips = sum(t["pips"] for t in trades)
    gross_profit = sum(t["pips"] for t in wins)
    gross_loss = abs(sum(t["pips"] for t in losses))
    returns = [t["pips"] for t in trades]
    std_ret = np.std(returns) if len(returns) > 1 else 1
    sharpe = round(np.mean(returns) / std_ret * np.sqrt(len(returns)), 2) if std_ret > 0 else 0
    cumulative = np.cumsum(returns)
    peak = np.maximum.accumulate(cumulative)
    max_dd = round(float(np.max(peak - cumulative)), 1) if len(cumulative) > 0 else 0

    return {
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "total_pips": round(total_pips, 1),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999,
        "sharpe": sharpe, "max_dd": max_dd,
        "avg_win": round(gross_profit / len(wins), 1) if wins else 0,
        "avg_loss": round(-gross_loss / len(losses), 1) if losses else 0,
    }


RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "journal")
RESULTS_FILE = os.path.join(RESULTS_DIR, "optimization_results.json")


class ParameterOptimizer:
    """تحسين معاملات الاستراتيجية عبر Grid Search"""

    PARAM_GRID = {
        "swing_lookback":   [3, 5, 7],
        "ob_displacement":  [1.0, 1.5, 2.0],
        "ob_max_age":       [30, 50, 70],
        "ob_buffer_pips":   [5, 10, 15],
        "min_rr":           [1.5, 2.0, 2.5, 3.0],
        "spread_pips":      [1.5],   # ثابت للـ USDJPY (لا يُحسّن)
    }

    def __init__(self, data):
        self.data = data
        self.results = []

    def optimize(self, param_grid=None, metric="sharpe", top_n=10):
        """تشغيل التحسين — يختبر كل المجموعات"""
        grid = param_grid or self.PARAM_GRID
        keys = list(grid.keys())
        values = list(grid.values())
        combinations = list(itertools.product(*values))
        total = len(combinations)
        print(f"\n⚙️ تحسين المعاملات — {total} مجموعة")
        print(f"📊 المقياس: {metric}\n{'═' * 50}")

        self.results = []
        for idx, combo in enumerate(combinations):
            params = dict(zip(keys, combo))
            params["pip_value"] = 0.01
            params["fvg_min_size"] = 5
            result = _run_ict_backtest(self.data, params)
            result["params"] = params
            self.results.append(result)
            if (idx + 1) % 20 == 0 or idx == total - 1:
                print(f"  ⏳ {round((idx+1)/total*100)}% ({idx+1}/{total})")

        valid = [r for r in self.results if r["trades"] >= 5]
        if metric == "sharpe":
            valid.sort(key=lambda r: r["sharpe"], reverse=True)
        elif metric == "profit_factor":
            valid.sort(key=lambda r: r["profit_factor"], reverse=True)
        elif metric == "win_rate":
            valid.sort(key=lambda r: r["win_rate"], reverse=True)
        elif metric == "total_pips":
            valid.sort(key=lambda r: r["total_pips"], reverse=True)
        else:
            valid.sort(key=lambda r: r["sharpe"] * r["profit_factor"] / max(r["max_dd"], 1), reverse=True)

        best = valid[:top_n]
        self._save_results(best)
        return best

    def optimize_quick(self, metric="sharpe"):
        """تحسين سريع — أقل مجموعات"""
        return self.optimize({
            "swing_lookback": [3, 5, 7],
            "ob_displacement": [1.0, 1.5, 2.0],
            "min_rr": [1.5, 2.0, 3.0],
        }, metric=metric, top_n=5)

    def _save_results(self, results):
        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(RESULTS_FILE, "w") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "data_points": len(self.data),
                       "total_combinations": len(self.results), "top_results": results}, f, indent=2, default=str)

    def get_report(self, results=None):
        """تقرير التحسين"""
        results = results or self.results[:5]
        if not results:
            return "⚠️ لا توجد نتائج"
        lines = ["═══ ⚙️ تحسين المعاملات ═══", f"📊 اختبار {len(self.results)} مجموعة | {len(self.data)} شمعة\n"]
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for rank, r in enumerate(results[:5], 1):
            p = r["params"]
            lines.extend([
                f"{medals[rank-1]} المرتبة {rank}:",
                f"   Swing={p.get('swing_lookback',5)} | OB_Disp={p.get('ob_displacement',1.5)} | RR={p.get('min_rr',2.0)}",
                f"   OB_Age={p.get('ob_max_age',50)} | Buffer={p.get('ob_buffer_pips',10)}",
                f"   {r['trades']} صفقة | فوز {r['win_rate']}% | {r['total_pips']}p",
                f"   PF={r['profit_factor']} | Sharpe={r['sharpe']} | DD={r['max_dd']}p\n",
            ])
        best = results[0]
        lines.extend(["── أفضل إعدادات ──",
            f"SWING_LOOKBACK = {best['params'].get('swing_lookback', 5)}",
            f"OB_DISPLACEMENT_MULTIPLIER = {best['params'].get('ob_displacement', 1.5)}",
            f"OB_MAX_AGE = {best['params'].get('ob_max_age', 50)}",
            f"OB_BUFFER_PIPS = {best['params'].get('ob_buffer_pips', 10)}",
            f"MIN_RR_RATIO = {best['params'].get('min_rr', 2.0)}"])
        return "\n".join(lines)

    def compare_with_current(self, results=None):
        """مقارنة مع الإعدادات الحالية"""
        from config import SWING_LOOKBACK, OB_DISPLACEMENT_MULTIPLIER, OB_MAX_AGE, OB_BUFFER_PIPS, MIN_RR_RATIO
        current_params = {"swing_lookback": SWING_LOOKBACK, "ob_displacement": OB_DISPLACEMENT_MULTIPLIER,
            "ob_max_age": OB_MAX_AGE, "ob_buffer_pips": OB_BUFFER_PIPS, "min_rr": MIN_RR_RATIO,
            "pip_value": 0.01, "fvg_min_size": 5}
        current_result = _run_ict_backtest(self.data, current_params)
        best = (results or self.results)
        if not best:
            return "⚠️ شغّل optimize أولاً"
        best = best[0]

        lines = ["═══ ⚖️ المقارنة ═══", f"{'المقياس':20s} | {'حالي':>10s} | {'محسّن':>10s}", "─" * 50]
        for label, key in [("صفقات","trades"),("فوز %","win_rate"),("النقاط","total_pips"),
                           ("PF","profit_factor"),("Sharpe","sharpe"),("MaxDD","max_dd")]:
            c, o = current_result.get(key, 0), best.get(key, 0)
            lines.append(f"{label:20s} | {c:>10} | {o:>10}")

        changes = []
        for key in ["swing_lookback","ob_displacement","ob_max_age","ob_buffer_pips","min_rr"]:
            curr_val = current_params.get(key)
            opt_val = best.get("params", {}).get(key, curr_val)
            if curr_val != opt_val:
                changes.append(f"  {key}: {curr_val} → {opt_val}")
        if changes:
            lines.append("\n── تغييرات مقترحة ──")
            lines.extend(changes)
        else:
            lines.append("\n✅ الإعدادات الحالية هي الأفضل!")
        return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="تحسين سريع")
    parser.add_argument("--metric", default="sharpe", help="sharpe, profit_factor, win_rate, total_pips")
    parser.add_argument("--days", type=int, default=365, help="عدد أيام البيانات")
    args = parser.parse_args()

    from data.data_feed import DataFeed
    feed = DataFeed()
    print(f"⏳ جلب بيانات {args.days} يوم...")
    data = feed.get_candles(interval="1h", period_days=args.days)
    if data is None:
        print("❌ فشل جلب البيانات!")
        exit(1)
    print(f"✅ {len(data)} شمعة")

    optimizer = ParameterOptimizer(data)
    results = optimizer.optimize_quick(metric=args.metric) if args.quick else optimizer.optimize(metric=args.metric)
    print(f"\n{optimizer.get_report(results)}")
    print(f"\n{optimizer.compare_with_current(results)}")
