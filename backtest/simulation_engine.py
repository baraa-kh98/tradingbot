import os
import random
import pandas as pd
import numpy as np
from datetime import datetime
from strategy.signal_generator import ICTSignalGenerator
from config import TRADING_PAIRS, BACKTEST_DEFAULT_LOT


def _calc_pip_value(pair: str, entry_price: float) -> float:
    """
    يحسب قيمة النقطة (pip value) بالدولار لكل lot واحد.
    USDJPY / XAUUSD: pip_value = (100000 * pip_size) / entry_price
    EURUSD / GBPUSD: pip_value = 100000 * pip_size (= $10 دائماً)
    """
    cfg = TRADING_PAIRS.get(pair, {})
    pip_size = cfg.get("pip", 0.01)

    if pair in ("USDJPY", "XAUUSD") and entry_price > 0:
        return (100000 * pip_size) / entry_price
    else:
        return 100000 * pip_size  # $10 per pip per standard lot


class SimulationEngine:
    """
    محرك محاكاة واقعي لتجربة الاستراتيجية على بيانات تاريخية.
    يحسب PnL حقيقي مع spread وslippage.
    """

    def __init__(self, m5_csv, h1_csv, chunk_size=30000, pair="USDJPY", lot_size=None):
        self.chunk_size = chunk_size
        self.pair = pair
        self.lot_size = lot_size or BACKTEST_DEFAULT_LOT
        self.pair_cfg = TRADING_PAIRS.get(pair, TRADING_PAIRS.get("USDJPY", {}))
        self.pip_size = self.pair_cfg.get("pip", 0.01)
        self.spread_pips = self.pair_cfg.get("spread_pips", 1.5)

        self.m5_df = pd.read_csv(m5_csv)
        self.h1_df = pd.read_csv(h1_csv)

        self.m5_df['time'] = pd.to_datetime(self.m5_df['time'])
        self.h1_df['time'] = pd.to_datetime(self.h1_df['time'])

        self.m5_df.sort_values(by='time', inplace=True)
        self.h1_df.sort_values(by='time', inplace=True)

        # توحيد أسماء الأعمدة لتتوافق مع ما ينتظره ICTSignalGenerator
        rename_map = {'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
                      'tick_volume': 'Volume', 'real_volume': 'Volume'}
        self.m5_df.rename(columns=rename_map, inplace=True)
        self.h1_df.rename(columns=rename_map, inplace=True)

        self.m5_df.reset_index(drop=True, inplace=True)
        self.h1_df.reset_index(drop=True, inplace=True)

        self.journal_trades = []
        self.active_trade = None
        self.ticket_counter = 1

    def _pnl_from_pips(self, pips: float, entry_price: float) -> float:
        """يحول عدد pips إلى دولار بناءً على lot size وpip value"""
        pip_val = _calc_pip_value(self.pair, entry_price)
        return round(pips * pip_val * self.lot_size, 2)

    def _apply_spread_and_slippage(self, entry: float, direction: str) -> float:
        """
        يضيف تكلفة الـ spread والـ slippage على سعر الدخول.
        BUY:  entry يرتفع بمقدار spread + slippage (ندفع الـ ask)
        SELL: entry ينخفض بمقدار spread + slippage (نبيع الـ bid)
        """
        spread_price = self.spread_pips * self.pip_size
        slippage_pips = random.uniform(0.3, 1.0)
        slippage_price = slippage_pips * self.pip_size
        total_cost = spread_price + slippage_price

        if direction == "BUY":
            return entry + total_cost
        else:
            return entry - total_cost

    def _spread_cost_pnl(self, entry: float) -> float:
        """تكلفة الـ spread فقط بالدولار (للإحصاء)"""
        return self._pnl_from_pips(self.spread_pips + 0.65, entry)  # متوسط slippage

    def evaluate_signal(self, htf_window, ltf_window):
        try:
            gen = ICTSignalGenerator(htf_window, ltf_window)
            signal = gen.get_signal()

            if signal["action"] != "WAIT" and signal["confluence_score"] >= 70:
                levels = gen.get_levels()
                if levels:
                    return {
                        "direction": signal["action"],
                        "score": signal["confluence_score"],
                        "levels": levels,
                        "reasons": signal["details"],
                    }
        except Exception:
            import traceback
            traceback.print_exc()
        return None

    def run_chunk(self, start_idx, end_idx):
        print(f"🔄 جاري محاكاة الشموع من {start_idx} إلى {end_idx}...")

        h1_idx = 0
        h1_len = len(self.h1_df)

        for i in range(start_idx, end_idx):
            if i % 1000 == 0:
                print(f"⏳ فحص الشمعة {i} من أصل {end_idx} "
                      f"(الصفقات المكتشفة: {len(self.journal_trades)})...")

            if i < 300:
                continue

            curr_candle = self.m5_df.iloc[i]

            # ── معالجة الصفقة الفعالة ──────────────────────────
            if self.active_trade:
                t = self.active_trade
                entry = t["entry_actual"]   # entry بعد spread+slippage
                sl    = t["sl"]
                tp    = t["tp"]

                if t["direction"] == "BUY":
                    hit_sl = curr_candle["Low"]  <= sl
                    hit_tp = curr_candle["High"] >= tp
                else:
                    hit_sl = curr_candle["High"] >= sl
                    hit_tp = curr_candle["Low"]  <= tp

                if hit_sl or hit_tp:
                    if hit_tp:
                        close_price = tp
                        raw_pips = abs(tp - entry) / self.pip_size
                        if t["direction"] == "SELL":
                            raw_pips = abs(entry - tp) / self.pip_size
                        t["pips"]         = round(raw_pips, 1)
                        t["pnl"]          = self._pnl_from_pips(raw_pips, entry)
                        t["rr_achieved"]  = 2.0
                        t["close_reason"] = "TP"
                    else:
                        close_price = sl
                        raw_pips = abs(entry - sl) / self.pip_size
                        t["pips"]         = round(-raw_pips, 1)
                        t["pnl"]          = self._pnl_from_pips(-raw_pips, entry)
                        t["rr_achieved"]  = -1.0
                        t["close_reason"] = "SL"

                    t["close_price"] = round(close_price, 5)
                    t["status"] = "CLOSED"
                    self.journal_trades.append(t)
                    self.active_trade = None

                continue  # لا صفقة جديدة أثناء صفقة مفتوحة

            # ── البحث عن فرصة جديدة ───────────────────────────
            ltf_window = self.m5_df.iloc[i - 300:i + 1].copy()
            current_time = curr_candle["time"]

            while h1_idx < h1_len and self.h1_df.iloc[h1_idx]["time"] <= current_time:
                h1_idx += 1

            if h1_idx < 50:
                continue

            htf_window = self.h1_df.iloc[h1_idx - 50:h1_idx].copy()
            signal = self.evaluate_signal(htf_window, ltf_window)

            if signal and signal.get("levels"):
                raw_entry = signal["levels"]["entry"]
                direction = signal["direction"]

                # تطبيق spread + slippage على سعر الدخول الفعلي
                actual_entry = self._apply_spread_and_slippage(raw_entry, direction)

                self.active_trade = {
                    "ticket":          self.ticket_counter,
                    "pair":            self.pair,
                    "status":          "OPEN",
                    "direction":       direction,
                    "entry":           round(raw_entry, 5),
                    "entry_actual":    round(actual_entry, 5),
                    "sl":              signal["levels"]["stop_loss"],
                    "tp":              signal["levels"]["take_profit"],
                    "lot_size":        self.lot_size,
                    "confluence_score": signal["score"],
                    "entry_type":      (
                        "OB"  if "OB"  in str(signal["reasons"]) else
                        "FVG" if "FVG" in str(signal["reasons"]) else
                        "MARKET"
                    ),
                    "session":         "BACKTEST",
                    "lessons":         [],
                    "close_reason":    "",
                    "close_price":     0.0,
                    "pips":            0.0,
                    "pnl":             0.0,
                    "rr_achieved":     0.0,
                }
                self.ticket_counter += 1

        print(f"✅ اكتمل الجزء. الصفقات المغلقة: {len(self.journal_trades)}")

if __name__ == "__main__":
    pass
