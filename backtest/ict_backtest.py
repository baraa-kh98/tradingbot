"""
ICT Backtest — اختبار استراتيجية ICT على بيانات تاريخية

يقارن بين:
1. استراتيجية ICT الجديدة
2. استراتيجية EMA القديمة
"""

import yfinance as yf
import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
from backtesting.lib import crossover

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    SYMBOL_YF,
    SWING_LOOKBACK,
    OB_DISPLACEMENT_MULTIPLIER,
    FVG_MIN_SIZE_PIPS,
    PIP_VALUE,
    MIN_RR_RATIO,
    OB_BUFFER_PIPS,
)


# ═══════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════

def get_data(period="6mo", interval="1h"):
    """جلب بيانات USDJPY مع VIX و DXY"""
    usdjpy = yf.download(SYMBOL_YF, period=period, interval=interval, auto_adjust=True)

    if isinstance(usdjpy.columns, pd.MultiIndex):
        usdjpy.columns = [col[0] if isinstance(col, tuple) else col for col in usdjpy.columns]

    usdjpy = usdjpy[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return usdjpy


# ═══════════════════════════════════════════════════════════════
# ICT STRATEGY (Backtesting.py compatible)
# ═══════════════════════════════════════════════════════════════

class ICTStrategy(Strategy):
    """
    استراتيجية ICT للباكتست

    تستخدم:
    - Market Structure (Swing Highs/Lows + BOS)
    - Order Blocks
    - Fair Value Gaps
    - Premium/Discount Zones
    """

    swing_lookback = SWING_LOOKBACK
    ob_displacement_mult = OB_DISPLACEMENT_MULTIPLIER
    min_rr = MIN_RR_RATIO
    ob_buffer_pips = OB_BUFFER_PIPS

    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low

        # ATR
        self.atr = self.I(self._calc_atr, high, low, close, name="ATR")

    def _calc_atr(self, high, low, close, period=14):
        """ATR calculation for backtesting"""
        tr = np.zeros(len(high))
        for i in range(1, len(high)):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1])
            )
        atr = pd.Series(tr).rolling(window=period).mean().values
        return atr

    def _find_swing_highs(self, high, end_idx, lookback=5):
        """إيجاد Swing Highs"""
        swings = []
        for i in range(lookback, end_idx - lookback):
            is_sh = True
            for j in range(1, lookback + 1):
                if high[i] <= high[i - j] or high[i] <= high[i + j]:
                    is_sh = False
                    break
            if is_sh:
                swings.append((i, high[i]))
        return swings

    def _find_swing_lows(self, low, end_idx, lookback=5):
        """إيجاد Swing Lows"""
        swings = []
        for i in range(lookback, end_idx - lookback):
            is_sl = True
            for j in range(1, lookback + 1):
                if low[i] >= low[i - j] or low[i] >= low[i + j]:
                    is_sl = False
                    break
            if is_sl:
                swings.append((i, low[i]))
        return swings

    def _detect_trend(self, idx):
        """تحديد الاتجاه من آخر Swing Points"""
        high = self.data.High
        low = self.data.Low

        swing_highs = self._find_swing_highs(high, idx, self.swing_lookback)
        swing_lows = self._find_swing_lows(low, idx, self.swing_lookback)

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
        """البحث عن Order Block قريب"""
        open_p = self.data.Open
        high = self.data.High
        low = self.data.Low
        close = self.data.Close
        atr = self.atr

        search_range = min(30, idx - 2)

        if direction == "BULLISH":
            for i in range(idx - 1, idx - search_range, -1):
                if i < 2 or np.isnan(atr[i + 1]):
                    continue
                body = abs(close[i + 1] - open_p[i + 1])
                if (close[i + 1] > open_p[i + 1] and
                        body > atr[i + 1] * self.ob_displacement_mult):
                    if close[i] < open_p[i]:  # شمعة هبوطية قبل displacement
                        ob_top = open_p[i]
                        ob_bottom = close[i]
                        # تأكد ما تم اختراقها
                        mitigated = False
                        for k in range(i + 2, idx + 1):
                            if low[k] < ob_bottom:
                                mitigated = True
                                break
                        if not mitigated:
                            return {"top": ob_top, "bottom": ob_bottom, "low": low[i]}
            return None

        else:  # BEARISH
            for i in range(idx - 1, idx - search_range, -1):
                if i < 2 or np.isnan(atr[i + 1]):
                    continue
                body = abs(close[i + 1] - open_p[i + 1])
                if (close[i + 1] < open_p[i + 1] and
                        body > atr[i + 1] * self.ob_displacement_mult):
                    if close[i] > open_p[i]:  # شمعة صعودية قبل displacement
                        ob_top = close[i]
                        ob_bottom = open_p[i]
                        mitigated = False
                        for k in range(i + 2, idx + 1):
                            if high[k] > ob_top:
                                mitigated = True
                                break
                        if not mitigated:
                            return {"top": ob_top, "bottom": ob_bottom, "high": high[i]}
            return None

    def _find_fvg(self, idx, direction):
        """البحث عن Fair Value Gap قريب"""
        high = self.data.High
        low = self.data.Low
        min_size = FVG_MIN_SIZE_PIPS * PIP_VALUE

        search_range = min(20, idx - 2)

        if direction == "BULLISH":
            for i in range(idx, idx - search_range, -1):
                if i < 2:
                    continue
                gap_top = low[i]
                gap_bottom = high[i - 2]
                if gap_top > gap_bottom and (gap_top - gap_bottom) >= min_size:
                    # تأكد ما تم ملؤها
                    filled = False
                    for k in range(i + 1, min(idx + 1, len(self.data))):
                        if low[k] <= gap_bottom:
                            filled = True
                            break
                    if not filled:
                        return {"top": gap_top, "bottom": gap_bottom}
            return None

        else:  # BEARISH
            for i in range(idx, idx - search_range, -1):
                if i < 2:
                    continue
                gap_top = low[i - 2]
                gap_bottom = high[i]
                if gap_top > gap_bottom and (gap_top - gap_bottom) >= min_size:
                    filled = False
                    for k in range(i + 1, min(idx + 1, len(self.data))):
                        if high[k] >= gap_top:
                            filled = True
                            break
                    if not filled:
                        return {"top": gap_top, "bottom": gap_bottom}
            return None

    def _get_pd_zone(self, swing_highs, swing_lows, current_price):
        """Premium/Discount zone"""
        if not swing_highs or not swing_lows:
            return "NEUTRAL"

        sh = max(swing_highs[-3:], key=lambda x: x[1])[1] if len(swing_highs) >= 3 else swing_highs[-1][1]
        sl = min(swing_lows[-3:], key=lambda x: x[1])[1] if len(swing_lows) >= 3 else swing_lows[-1][1]

        if sh <= sl:
            return "NEUTRAL"

        eq = sl + (sh - sl) * 0.5

        if current_price < eq:
            return "DISCOUNT"
        elif current_price > eq:
            return "PREMIUM"
        return "EQUILIBRIUM"

    def next(self):
        idx = len(self.data) - 1
        if idx < 30:
            return

        current_price = self.data.Close[-1]
        atr_val = self.atr[-1]

        if np.isnan(atr_val) or atr_val == 0:
            return

        # تحديد الاتجاه
        trend, swing_highs, swing_lows = self._detect_trend(idx)

        if trend == "NEUTRAL":
            return

        # Premium/Discount
        pd_zone = self._get_pd_zone(swing_highs, swing_lows, current_price)

        ob_buffer = self.ob_buffer_pips * PIP_VALUE

        # ──── BUY Setup ────
        if trend == "BULLISH" and pd_zone == "DISCOUNT":
            ob = self._find_order_block(idx, "BULLISH")
            fvg = self._find_fvg(idx, "BULLISH")

            if ob and ob["bottom"] <= current_price <= ob["top"] * 1.002:
                sl = ob["low"] - ob_buffer
                risk = current_price - sl
                tp = current_price + risk * self.min_rr
                if risk > 0 and not self.position:
                    self.buy(sl=sl, tp=tp)

            elif fvg and fvg["bottom"] <= current_price <= fvg["top"]:
                if swing_lows:
                    sl = min(s[1] for s in swing_lows[-2:]) - ob_buffer
                else:
                    sl = current_price - atr_val * 2
                risk = current_price - sl
                tp = current_price + risk * self.min_rr
                if risk > 0 and not self.position:
                    self.buy(sl=sl, tp=tp)

        # ──── SELL Setup ────
        elif trend == "BEARISH" and pd_zone == "PREMIUM":
            ob = self._find_order_block(idx, "BEARISH")
            fvg = self._find_fvg(idx, "BEARISH")

            if ob and ob["bottom"] * 0.998 <= current_price <= ob["top"]:
                sl = ob["high"] + ob_buffer
                risk = sl - current_price
                tp = current_price - risk * self.min_rr
                if risk > 0 and not self.position:
                    self.sell(sl=sl, tp=tp)

            elif fvg and fvg["bottom"] <= current_price <= fvg["top"]:
                if swing_highs:
                    sl = max(s[1] for s in swing_highs[-2:]) + ob_buffer
                else:
                    sl = current_price + atr_val * 2
                risk = sl - current_price
                tp = current_price - risk * self.min_rr
                if risk > 0 and not self.position:
                    self.sell(sl=sl, tp=tp)


# ═══════════════════════════════════════════════════════════════
# EMA STRATEGY (للمقارنة)
# ═══════════════════════════════════════════════════════════════

class EMAStrategy(Strategy):
    """الاستراتيجية القديمة (للمقارنة)"""

    ema_fast = 20
    ema_slow = 50

    def init(self):
        close = self.data.Close
        self.ema20 = self.I(lambda x: pd.Series(x).ewm(span=self.ema_fast).mean(), close)
        self.ema50 = self.I(lambda x: pd.Series(x).ewm(span=self.ema_slow).mean(), close)

    def next(self):
        if crossover(self.ema20, self.ema50):
            self.buy(
                sl=self.data.Close[-1] - 0.5,
                tp=self.data.Close[-1] + 1.0
            )
        elif crossover(self.ema50, self.ema20):
            self.sell(
                sl=self.data.Close[-1] + 0.5,
                tp=self.data.Close[-1] - 1.0
            )


# ═══════════════════════════════════════════════════════════════
# RUN BACKTEST
# ═══════════════════════════════════════════════════════════════

def run_comparison():
    """تشغيل المقارنة بين ICT و EMA"""

    print("⏳ جاري جلب البيانات...")
    data = get_data(period="6mo", interval="1h")
    print(f"✅ تم جلب {len(data)} شمعة\n")

    # ──── ICT Backtest ────
    print("═══════════════════════════════════")
    print("   🧠 ICT Strategy Backtest")
    print("═══════════════════════════════════")

    bt_ict = Backtest(data, ICTStrategy, cash=10000, commission=0.0002)
    results_ict = bt_ict.run()

    print(f"عدد الصفقات:     {results_ict['# Trades']}")
    print(f"نسبة الفوز:       {round(results_ict['Win Rate [%]'], 2)}%")
    print(f"الربح الكلي:      {round(results_ict['Return [%]'], 2)}%")
    print(f"أكبر خسارة:       {round(results_ict['Max. Drawdown [%]'], 2)}%")
    print(f"نسبة شارب:        {round(results_ict['Sharpe Ratio'], 2)}")
    print(f"Profit Factor:    {round(results_ict.get('Profit Factor', 0), 2)}")

    # ──── EMA Backtest ────
    print("\n═══════════════════════════════════")
    print("   📊 EMA Strategy Backtest")
    print("═══════════════════════════════════")

    bt_ema = Backtest(data, EMAStrategy, cash=10000, commission=0.0002)
    results_ema = bt_ema.run()

    print(f"عدد الصفقات:     {results_ema['# Trades']}")
    print(f"نسبة الفوز:       {round(results_ema['Win Rate [%]'], 2)}%")
    print(f"الربح الكلي:      {round(results_ema['Return [%]'], 2)}%")
    print(f"أكبر خسارة:       {round(results_ema['Max. Drawdown [%]'], 2)}%")
    print(f"نسبة شارب:        {round(results_ema['Sharpe Ratio'], 2)}")

    # ──── المقارنة ────
    print("\n═══════════════════════════════════")
    print("   ⚖️  المقارنة")
    print("═══════════════════════════════════")

    metrics = ["# Trades", "Win Rate [%]", "Return [%]", "Max. Drawdown [%]", "Sharpe Ratio"]
    for m in metrics:
        ict_val = round(results_ict[m], 2)
        ema_val = round(results_ema[m], 2)
        winner = "ICT ✅" if (ict_val > ema_val if m != "Max. Drawdown [%]" else ict_val > ema_val) else "EMA"
        if m == "Max. Drawdown [%]":
            winner = "ICT ✅" if abs(ict_val) < abs(ema_val) else "EMA"
        print(f"{m:25s} | ICT: {ict_val:>10} | EMA: {ema_val:>10} | {winner}")

    # حفظ الشارت ICT
    print("\n📈 جاري حفظ شارت ICT...")
    bt_ict.plot(filename="ICTStrategy", open_browser=False)
    print("✅ تم حفظ الشارت: ICTStrategy.html")

    return results_ict, results_ema


if __name__ == "__main__":
    run_comparison()
