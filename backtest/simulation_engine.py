import os
import pandas as pd
from datetime import datetime
from strategy.signal_generator import ICTSignalGenerator

class SimulationEngine:
    """محرك محاكاة لتجربة التقاء الصفقات على مدى سنتين"""

    def __init__(self, m5_csv, h1_csv, chunk_size=30000):
        self.chunk_size = chunk_size
        self.m5_df = pd.read_csv(m5_csv)
        self.h1_df = pd.read_csv(h1_csv)
        
        self.m5_df['time'] = pd.to_datetime(self.m5_df['time'])
        self.h1_df['time'] = pd.to_datetime(self.h1_df['time'])
        
        self.m5_df.sort_values(by='time', inplace=True)
        self.h1_df.sort_values(by='time', inplace=True)
        
        self.m5_df.reset_index(drop=True, inplace=True)
        self.h1_df.reset_index(drop=True, inplace=True)

        self.journal_trades = []
        self.active_trade = None
        self.ticket_counter = 1

    def evaluate_signal(self, htf_window, ltf_window):
        try:
            gen = ICTSignalGenerator(htf_window, ltf_window)
            gen.evaluate("BUY")
            buy_score = gen.score
            buy_levels = gen.levels
            buy_reasons = gen.reasons

            gen.evaluate("SELL")
            sell_score = gen.score
            sell_levels = gen.levels
            sell_reasons = gen.reasons

            if buy_score >= 70 and buy_score >= sell_score:
                return {"direction": "BUY", "score": buy_score, "levels": buy_levels, "reasons": buy_reasons}
            elif sell_score >= 70 and sell_score > buy_score:
                return {"direction": "SELL", "score": sell_score, "levels": sell_levels, "reasons": sell_reasons}
        except Exception as e:
            pass
        return None

    def run_chunk(self, start_idx, end_idx):
        print(f"🔄 جاري محاكاة الشموع من {start_idx} إلى {end_idx}...")
        
        h1_idx = 0
        h1_len = len(self.h1_df)

        for i in range(start_idx, end_idx):
            if i % 1000 == 0:
                print(f"⏳ فحص الشمعة {i} من أصل {end_idx} (الصفقات المكتشفة: {len(self.journal_trades)})...")

            if i < 300: 
                continue
            
            curr_candle = self.m5_df.iloc[i]
            
            # --- معالجة الصفقة الفعالة (الحالية) ---
            if self.active_trade:
                if self.active_trade['direction'] == 'BUY':
                    if curr_candle['low'] <= self.active_trade['sl']:
                        self.active_trade['close_reason'] = 'SL'
                        self.active_trade['pnl'] = -abs(self.active_trade['entry'] - self.active_trade['sl']) * 10
                        self.active_trade['pips'] = -15  # تقريبي لأغراض AI
                        self.active_trade['rr_achieved'] = -1.0
                        self.journal_trades.append(self.active_trade)
                        self.active_trade = None
                    elif curr_candle['high'] >= self.active_trade['tp']:
                        self.active_trade['close_reason'] = 'TP'
                        self.active_trade['pnl'] = abs(self.active_trade['tp'] - self.active_trade['entry']) * 10
                        self.active_trade['pips'] = 30
                        self.active_trade['rr_achieved'] = 2.0
                        self.journal_trades.append(self.active_trade)
                        self.active_trade = None

                else: # SELL
                    if curr_candle['high'] >= self.active_trade['sl']:
                        self.active_trade['close_reason'] = 'SL'
                        self.active_trade['pnl'] = -abs(self.active_trade['sl'] - self.active_trade['entry']) * 10
                        self.active_trade['pips'] = -15
                        self.active_trade['rr_achieved'] = -1.0
                        self.journal_trades.append(self.active_trade)
                        self.active_trade = None
                    elif curr_candle['low'] <= self.active_trade['tp']:
                        self.active_trade['close_reason'] = 'TP'
                        self.active_trade['pnl'] = abs(self.active_trade['entry'] - self.active_trade['tp']) * 10
                        self.active_trade['pips'] = 30
                        self.active_trade['rr_achieved'] = 2.0
                        self.journal_trades.append(self.active_trade)
                        self.active_trade = None
                        
                continue # نمنع الدخول بصفقة جديدة إذا كانت القديمة قيد التنفيذ
                
            # --- البحث عن فرصة جديدة ---
            ltf_window = self.m5_df.iloc[i-300:i+1].copy()
            current_time = curr_candle['time']

            # مزامنة اطار الساعة
            while h1_idx < h1_len and self.h1_df.iloc[h1_idx]['time'] <= current_time:
                h1_idx += 1
            
            if h1_idx < 50:
                continue

            htf_window = self.h1_df.iloc[h1_idx-50:h1_idx].copy()
            
            # التقييم المستنزف برمجياً
            signal = self.evaluate_signal(htf_window, ltf_window)
            
            if signal and 'levels' in signal and signal['levels']:
                self.active_trade = {
                    "ticket": self.ticket_counter,
                    "pair": "USDJPY",
                    "status": "OPEN", # سيصبح مغلق بعد ضرب الهدف
                    "direction": signal["direction"],
                    "entry": signal["levels"]["entry"],
                    "sl": signal["levels"]["stop_loss"],
                    "tp": signal["levels"]["take_profit"],
                    "confluence_score": signal["score"],
                    "entry_type": "OB" if "OB" in str(signal["reasons"]) else ("FVG" if "FVG" in str(signal["reasons"]) else "MARKET"),
                    "session": "TEST_SESSION",
                    "lessons": [],
                    "close_reason": "",
                    "pips": 0,
                    "pnl": 0,
                    "rr_achieved": 0
                }
                self.ticket_counter += 1

        print(f"✅ اكتمل الجزء. الصفقات المغلقة الملتقطة: {len(self.journal_trades)}")

if __name__ == "__main__":
    pass
