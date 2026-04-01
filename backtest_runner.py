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
    
    # المحاكاة العميقة (Deep Simulation) سيطبع لك تقدمه حتى لا تظن أن السيرفر معلق
    engine.run_chunk(start_idx, min(end_idx, len(engine.m5_df)))
    
    # تفريغ الصفقات التي التقطها المحرك بناءً على 140 نقطة التقاء
    simulated_trades = []
    for t in engine.journal_trades:
        t["status"] = "CLOSED" 
        t["lessons"] = []
        simulated_trades.append(t)
        
    print(f"\n✅ إجمالي الصفقات المكتشفة في هذا القطاع: {len(simulated_trades)}")

    # 2. ترحيل النتائج لدفتر افتراضي لاستخلاص الدروس
    journal = TradeJournal()
    journal.trades = simulated_trades
    # 3. طباعة إحصائيات الأداء الكلية (Statistics)
    stats = journal.get_stats()
    print("\n📊 إحصائيات الأداء لفترة الباكتيست (محاكاة واقعية 100%):")
    print(f" - إجمالي الصفقات المغلقة: {stats.get('total', 0)}")
    print(f" - الصفقات الرابحة: {stats.get('wins', 0)} | الصفقات الخاسرة: {stats.get('losses', 0)}")
    print(f" - نسبة النجاح (Win Rate): {stats.get('win_rate', 0)}%")
    print(f" - إجمالي النقاط (Pips): {stats.get('total_pips', 0)}")
    print(f" - صافي الربح التقديري (PnL): ${stats.get('total_pnl', 0)}")
    print(f" - عامل الربح (Profit Factor): {stats.get('profit_factor', 0)}")
    
    # 4. إرسال لـ SelfOptimizer لاستخلاص الدروس (Zero API Cost)
    opt = SelfOptimizer(journal)
    suggestions = opt.analyze_and_suggest(min_trades=2)
    
    print("\n💡 الدروس المستفادة الحقيقية من هذا الجزء:")
    for s in suggestions:
        print(f" - {s}")
        
    print("\n✅ انتهت الجولة. لتشغيل الجزء التالي يمكنك تغيير chunk_index في السكريبت.")

if __name__ == "__main__":
    # تشغيل الدفعة الأولى مجدداً لطباعة الإحصائيات (أول 30,000 شمعة)
    # بعدها يمكنك تغييرها إلى 1 للربع الثاني
    run_chunked_backtest("USDJPY.BL", chunk_index=0)
