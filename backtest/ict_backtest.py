"""
ICT Backtest v2 — باكتست طويل مع فلتر ماكرو وأخبار

ميزات جديدة:
- بيانات 2+ سنة (بدل 6 أشهر)
- فلتر ماكرو (VIX, DXY, Fed Rate)
- فلتر أخبار (يوقف التداول وقت NFP, CPI, FOMC)
- مقارنة: ICT vs ICT+Macro vs EMA
"""

import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
from backtesting.lib import crossover

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    SWING_LOOKBACK,
    OB_DISPLACEMENT_MULTIPLIER,
    FVG_MIN_SIZE_PIPS,
    PIP_VALUE,
    MIN_RR_RATIO,
    OB_BUFFER_PIPS,
    BACKTEST_PERIOD_DAYS,
)


# ═══════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════

def get_data(period_days=None):
    """جلب بيانات USDJPY للباكتست (Twelve Data أو yfinance)"""
    days = period_days or BACKTEST_PERIOD_DAYS

    # محاولة Twelve Data
    try:
        from data.data_feed import DataFeed
        feed = DataFeed()
        data = feed.get_backtest_data(period_days=days)
        if data is not None and len(data) > 500:
            # إزالة أعمدة إضافية (backtesting.py يحتاج فقط OHLCV)
            cols_to_keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
            return data[cols_to_keep].dropna()
    except Exception:
        pass

    # yfinance fallback
    import yfinance as yf
    period = f"{min(days, 730)}d"
    data = yf.download("USDJPY=X", period=period, interval="1h", auto_adjust=True)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] for col in data.columns]
    return data[["Open", "High", "Low", "Close", "Volume"]].dropna()


def get_macro_data(start_date, end_date):
    """جلب بيانات ماكرو تاريخية"""
    try:
        from data.macro_data import MacroData
        macro = MacroData()
        return macro.get_all_macro(start_date, end_date)
    except Exception as e:
        print(f"⚠️ فشل جلب بيانات ماكرو: {e}")
        return None


def get_news_calendar(start_date, end_date):
    """توليد تقويم أخبار"""
    try:
        from data.news_calendar import NewsCalendar
        cal = NewsCalendar()
        return cal.generate_calendar(start_date, end_date), cal
    except Exception as e:
        print(f"⚠️ فشل توليد التقويم: {e}")
        return None, None


# ═══════════════════════════════════════════════════════════════
# ICT STRATEGY — بدون ماكرو (المرجع)
# ═══════════════════════════════════════════════════════════════

class ICTStrategy(Strategy):
    """استراتيجية ICT الأساسية"""

    swing_lookback = SWING_LOOKBACK
    ob_displacement_mult = OB_DISPLACEMENT_MULTIPLIER
    min_rr = MIN_RR_RATIO
    ob_buffer_pips = OB_BUFFER_PIPS

    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low
        self.atr = self.I(self._calc_atr, high, low, close, name="ATR")

    def _calc_atr(self, high, low, close, period=14):
        tr = np.zeros(len(high))
        for i in range(1, len(high)):
            tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
        return pd.Series(tr).rolling(window=period).mean().values

    def _find_swing_highs(self, high, end_idx, lookback=5):
        swings = []
        for i in range(lookback, end_idx - lookback):
            if all(high[i] > high[i-j] and high[i] > high[i+j] for j in range(1, lookback+1)):
                swings.append((i, high[i]))
        return swings

    def _find_swing_lows(self, low, end_idx, lookback=5):
        swings = []
        for i in range(lookback, end_idx - lookback):
            if all(low[i] < low[i-j] and low[i] < low[i+j] for j in range(1, lookback+1)):
                swings.append((i, low[i]))
        return swings

    def _detect_trend(self, idx):
        swing_highs = self._find_swing_highs(self.data.High, idx, self.swing_lookback)
        swing_lows = self._find_swing_lows(self.data.Low, idx, self.swing_lookback)
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "NEUTRAL", swing_highs, swing_lows
        h1, h2 = swing_highs[-2][1], swing_highs[-1][1]
        l1, l2 = swing_lows[-2][1], swing_lows[-1][1]
        if h2 > h1 and l2 > l1:
            return "BULLISH", swing_highs, swing_lows
        elif h2 < h1 and l2 < l1:
            return "BEARISH", swing_highs, swing_lows
        return "NEUTRAL", swing_highs, swing_lows

    def _find_order_block(self, idx, direction):
        open_p, high, low, close, atr = self.data.Open, self.data.High, self.data.Low, self.data.Close, self.atr
        search_range = min(30, idx - 2)

        if direction == "BULLISH":
            for i in range(idx - 1, idx - search_range, -1):
                if i < 2 or np.isnan(atr[i+1]):
                    continue
                body = abs(close[i+1] - open_p[i+1])
                if close[i+1] > open_p[i+1] and body > atr[i+1] * self.ob_displacement_mult:
                    if close[i] < open_p[i]:
                        ob_top, ob_bottom = open_p[i], close[i]
                        if not any(low[k] < ob_bottom for k in range(i+2, idx+1)):
                            return {"top": ob_top, "bottom": ob_bottom, "low": low[i]}
        else:
            for i in range(idx - 1, idx - search_range, -1):
                if i < 2 or np.isnan(atr[i+1]):
                    continue
                body = abs(close[i+1] - open_p[i+1])
                if close[i+1] < open_p[i+1] and body > atr[i+1] * self.ob_displacement_mult:
                    if close[i] > open_p[i]:
                        ob_top, ob_bottom = close[i], open_p[i]
                        if not any(high[k] > ob_top for k in range(i+2, idx+1)):
                            return {"top": ob_top, "bottom": ob_bottom, "high": high[i]}
        return None

    def _find_fvg(self, idx, direction):
        high, low = self.data.High, self.data.Low
        min_size = FVG_MIN_SIZE_PIPS * PIP_VALUE
        search_range = min(20, idx - 2)

        if direction == "BULLISH":
            for i in range(idx, idx - search_range, -1):
                if i < 2: continue
                gap_top, gap_bottom = low[i], high[i-2]
                if gap_top > gap_bottom and (gap_top - gap_bottom) >= min_size:
                    if not any(low[k] <= gap_bottom for k in range(i+1, min(idx+1, len(self.data)))):
                        return {"top": gap_top, "bottom": gap_bottom}
        else:
            for i in range(idx, idx - search_range, -1):
                if i < 2: continue
                gap_top, gap_bottom = low[i-2], high[i]
                if gap_top > gap_bottom and (gap_top - gap_bottom) >= min_size:
                    if not any(high[k] >= gap_top for k in range(i+1, min(idx+1, len(self.data)))):
                        return {"top": gap_top, "bottom": gap_bottom}
        return None

    def _get_pd_zone(self, swing_highs, swing_lows, price):
        if not swing_highs or not swing_lows:
            return "NEUTRAL"
        sh = max(swing_highs[-3:], key=lambda x: x[1])[1] if len(swing_highs) >= 3 else swing_highs[-1][1]
        sl = min(swing_lows[-3:], key=lambda x: x[1])[1] if len(swing_lows) >= 3 else swing_lows[-1][1]
        if sh <= sl: return "NEUTRAL"
        eq = sl + (sh - sl) * 0.5
        return "DISCOUNT" if price < eq else "PREMIUM"

    def next(self):
        idx = len(self.data) - 1
        if idx < 30: return

        price = self.data.Close[-1]
        atr_val = self.atr[-1]
        if np.isnan(atr_val) or atr_val == 0: return

        trend, swing_highs, swing_lows = self._detect_trend(idx)
        if trend == "NEUTRAL": return

        pd_zone = self._get_pd_zone(swing_highs, swing_lows, price)
        ob_buffer = self.ob_buffer_pips * PIP_VALUE

        if trend == "BULLISH" and pd_zone == "DISCOUNT":
            ob = self._find_order_block(idx, "BULLISH")
            fvg = self._find_fvg(idx, "BULLISH")
            if ob and ob["bottom"] <= price <= ob["top"] * 1.002:
                sl = ob["low"] - ob_buffer
                risk = price - sl
                if risk > 0 and not self.position:
                    self.buy(sl=sl, tp=price + risk * self.min_rr)
            elif fvg and fvg["bottom"] <= price <= fvg["top"]:
                sl = min(s[1] for s in swing_lows[-2:]) - ob_buffer if swing_lows else price - atr_val * 2
                risk = price - sl
                if risk > 0 and not self.position:
                    self.buy(sl=sl, tp=price + risk * self.min_rr)

        elif trend == "BEARISH" and pd_zone == "PREMIUM":
            ob = self._find_order_block(idx, "BEARISH")
            fvg = self._find_fvg(idx, "BEARISH")
            if ob and ob["bottom"] * 0.998 <= price <= ob["top"]:
                sl = ob["high"] + ob_buffer
                risk = sl - price
                if risk > 0 and not self.position:
                    self.sell(sl=sl, tp=price - risk * self.min_rr)
            elif fvg and fvg["bottom"] <= price <= fvg["top"]:
                sl = max(s[1] for s in swing_highs[-2:]) + ob_buffer if swing_highs else price + atr_val * 2
                risk = sl - price
                if risk > 0 and not self.position:
                    self.sell(sl=sl, tp=price - risk * self.min_rr)


# ═══════════════════════════════════════════════════════════════
# ICT + MACRO FILTER
# ═══════════════════════════════════════════════════════════════

class ICTMacroStrategy(ICTStrategy):
    """ICT مع فلتر ماكرو وأخبار"""

    # سيتم تعيينها قبل التشغيل
    _macro_scorer = None
    _news_calendar = None
    _news_cal_obj = None

    def next(self):
        idx = len(self.data) - 1
        if idx < 30: return

        current_time = self.data.index[-1]

        # فلتر الأخبار — لا نتداول وقت أخبار عالية التأثير
        if self._news_cal_obj and self._news_calendar is not None:
            blocked, reason = self._news_cal_obj.is_blackout_for_candle(current_time, self._news_calendar)
            if blocked:
                return  # ممنوع التداول

        # فلتر الماكرو — لا نتداول عند VIX عالي
        if self._macro_scorer:
            can_trade, _ = self._macro_scorer.should_trade(current_time)
            if not can_trade:
                return  # ظروف ماكرو سيئة

        # نداء الاستراتيجية الأساسية
        super().next()


# ═══════════════════════════════════════════════════════════════
# EMA STRATEGY (للمقارنة)
# ═══════════════════════════════════════════════════════════════

class EMAStrategy(Strategy):
    ema_fast = 20
    ema_slow = 50

    def init(self):
        self.ema20 = self.I(lambda x: pd.Series(x).ewm(span=self.ema_fast).mean(), self.data.Close)
        self.ema50 = self.I(lambda x: pd.Series(x).ewm(span=self.ema_slow).mean(), self.data.Close)

    def next(self):
        if crossover(self.ema20, self.ema50):
            self.buy(sl=self.data.Close[-1] - 0.5, tp=self.data.Close[-1] + 1.0)
        elif crossover(self.ema50, self.ema20):
            self.sell(sl=self.data.Close[-1] + 0.5, tp=self.data.Close[-1] - 1.0)


# ═══════════════════════════════════════════════════════════════
# RUN BACKTEST
# ═══════════════════════════════════════════════════════════════

def print_results(name, results):
    """طباعة نتائج باكتست"""
    print(f"\n{'═' * 45}")
    print(f"   {name}")
    print(f"{'═' * 45}")
    print(f"  📊 عدد الصفقات:      {results['# Trades']}")
    print(f"  🎯 نسبة الفوز:        {round(results['Win Rate [%]'], 1)}%")
    print(f"  💰 الربح الكلي:       {round(results['Return [%]'], 2)}%")
    print(f"  📉 أكبر خسارة:        {round(results['Max. Drawdown [%]'], 2)}%")
    print(f"  📐 نسبة شارب:         {round(results['Sharpe Ratio'], 2)}")
    pf = results.get('Profit Factor', 0)
    if pf:
        print(f"  ⚖️  Profit Factor:     {round(pf, 2)}")
    return results


def run_comparison(period_days=None):
    """تشغيل المقارنة: ICT vs ICT+Macro vs EMA"""

    days = period_days or BACKTEST_PERIOD_DAYS

    print("╔═══════════════════════════════════════════════╗")
    print("║   🧠 ICT Backtest v2 — مع ماكرو وأخبار       ║")
    print("╚═══════════════════════════════════════════════╝")

    # ─── جلب البيانات ───
    print(f"\n⏳ جلب بيانات الأسعار ({days} يوم)...")
    data = get_data(period_days=days)
    print(f"✅ تم جلب {len(data)} شمعة")
    print(f"   الفترة: {data.index[0]} → {data.index[-1]}")

    start_date = str(data.index[0].date())
    end_date = str(data.index[-1].date())

    # ─── بيانات ماكرو ───
    print(f"\n⏳ جلب بيانات ماكرو...")
    macro_df = get_macro_data(start_date, end_date)

    # ─── تقويم أخبار ───
    print(f"\n⏳ توليد تقويم الأخبار...")
    news_df, news_cal = get_news_calendar(start_date, end_date)
    if news_df is not None:
        high_events = news_df[news_df["impact"] == "HIGH"]
        print(f"📅 أحداث عالية التأثير: {len(high_events)} | أحداث متوسطة: {len(news_df) - len(high_events)}")

    # ─── 1. ICT بدون ماكرو ───
    bt_ict = Backtest(data, ICTStrategy, cash=10000, commission=0.0002)
    r_ict = bt_ict.run()
    print_results("🧠 ICT Strategy (بدون ماكرو)", r_ict)

    # ─── 2. ICT مع ماكرو وأخبار ───
    if macro_df is not None or news_df is not None:
        # تعيين البيانات للاستراتيجية
        if macro_df is not None:
            from strategy.macro_scorer import MacroScorer
            ICTMacroStrategy._macro_scorer = MacroScorer(macro_df)

        if news_df is not None:
            ICTMacroStrategy._news_calendar = news_df
            ICTMacroStrategy._news_cal_obj = news_cal

        bt_macro = Backtest(data, ICTMacroStrategy, cash=10000, commission=0.0002)
        r_macro = bt_macro.run()
        print_results("🧠📰 ICT + Macro + News Filter", r_macro)
    else:
        r_macro = None

    # ─── 3. EMA (مرجع) ───
    bt_ema = Backtest(data, EMAStrategy, cash=10000, commission=0.0002)
    r_ema = bt_ema.run()
    print_results("📊 EMA Strategy (المرجع)", r_ema)

    # ─── المقارنة ───
    print(f"\n{'═' * 65}")
    print(f"   ⚖️  المقارنة النهائية ({days} يوم)")
    print(f"{'═' * 65}")

    header = f"{'المقياس':25s} | {'ICT':>10s}"
    if r_macro is not None:
        header += f" | {'ICT+Macro':>10s}"
    header += f" | {'EMA':>10s} | الأفضل"
    print(header)
    print("─" * 65)

    metrics = [
        ("عدد الصفقات", "# Trades", False),
        ("نسبة الفوز %", "Win Rate [%]", True),
        ("الربح الكلي %", "Return [%]", True),
        ("أكبر خسارة %", "Max. Drawdown [%]", False),  # أقل = أفضل
        ("نسبة شارب", "Sharpe Ratio", True),
    ]

    for label, key, higher_better in metrics:
        vals = {"ICT": round(r_ict[key], 2)}
        if r_macro is not None:
            vals["ICT+Macro"] = round(r_macro[key], 2)
        vals["EMA"] = round(r_ema[key], 2)

        if key == "Max. Drawdown [%]":
            best = min(vals, key=lambda k: abs(vals[k]))
        elif higher_better:
            best = max(vals, key=lambda k: vals[k])
        else:
            best = max(vals, key=lambda k: vals[k])

        row = f"{label:25s} | {vals['ICT']:>10}"
        if r_macro is not None:
            row += f" | {vals.get('ICT+Macro', 'N/A'):>10}"
        row += f" | {vals['EMA']:>10} | {best} ✅"
        print(row)

    # ─── حفظ الشارت ───
    print("\n📈 جاري حفظ الشارت...")
    bt_ict.plot(filename="ICT_Backtest_v2", open_browser=False)
    print("✅ تم حفظ: ICT_Backtest_v2.html")

    return r_ict, r_macro, r_ema


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=None, help="فترة الباكتست بالأيام")
    args = parser.parse_args()

    run_comparison(period_days=args.days)
