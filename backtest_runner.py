import os
import json
from backtest.simulation_engine import SimulationEngine
from risk.trade_journal import TradeJournal
from strategy.self_optimizer import SelfOptimizer

def run_chunked_backtest(symbol="USDJPY.BL", chunk_index=0, chunk_size=30000):
    m5_path = f"backtest_data/{symbol}_M5_history.csv"
    h1_path = f"backtest_data/{symbol}_H1_history.csv"
    
    if not os.path.exists(m5_path) or not os.path.exists(h1_path):
        print(f"❌ لم يتم العثور على بيانات {symbol}. قم بتشغيل data_fetcher.py أولاً على سيرفرك.")
        return

    print("===========================================")
    print(f"🚀 بدء محاكاة الباكتيست (الجولة {chunk_index + 1}) لـ {symbol}")
    print("===========================================")
    
    # 1. التهيئة والمحاكاة
    start_idx = chunk_index * chunk_size
    end_idx = start_idx + chunk_size
    engine = SimulationEngine(m5_path, h1_path, chunk_size)
    
    # محاكاة القراءة وتوليد الصفقات (تأخذ وقتاً طويلاً)
    # سيتم تشغيلها وهمياً أو حقيقياً هنا:
    # engine.run_chunk(start_idx, min(end_idx, len(engine.m5_df)))
    print("⚠️ (تم تخطي المحاكاة التفصيلية هنا في الكود التوضيحي، يتطلب تفعيل loop المحرك)")
    
    # محاكاة دفتر يوميات بصيغة كاملة لتشغيل محرك الدروس
    simulated_trades = [
        {"ticket": 1, "pair": "USDJPY", "status": "CLOSED", "direction": "BUY", "close_reason": "TP", 
         "pips": 40, "pnl": 40, "entry": 140.0, "sl": 139.8, "tp": 140.4, 
         "rr_achieved": 2.0, "confluence_score": 85, "entry_type": "OB", "session": "LONDON", "lessons": []},
         
        {"ticket": 2, "pair": "USDJPY", "status": "CLOSED", "direction": "SELL", "close_reason": "SL", 
         "pips": -15, "pnl": -15, "entry": 141.0, "sl": 141.15, "tp": 140.7, 
         "rr_achieved": -1.0, "confluence_score": 60, "entry_type": "MARKET", "session": "NY_PM", "lessons": []},
    ]
    
    # 2. ترحيل النتائج لدفتر افتراضي
    journal = TradeJournal()
    journal.trades = simulated_trades  # ملء الدفتر بالصفقات الوهمية
    
    # 3. إرسال لـ SelfOptimizer لاستخلاص الدروس (لا يستهلك Claude tokens)
    opt = SelfOptimizer(journal)
    suggestions = opt.analyze_and_suggest(min_trades=2)
    
    print("\n💡 الدروس المستفادة من هذا الجزء (بدون استخدام توكنز API):")
    for s in suggestions:
        print(f" - {s}")
        
    print("\n✅ انتهت الجولة. لتشغيل الجزء التالي يمكنك تغيير chunk_index في السكريبت.")

if __name__ == "__main__":
    # تشغيل الدفعة الأولى (أول 30,000 شمعة = تقريباً 100 يوم)
    run_chunked_backtest("USDJPY.BL", chunk_index=0)
