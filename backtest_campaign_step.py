import os
import sys
import json
from dotenv import load_dotenv
from backtest.simulation_engine import SimulationEngine
from risk.trade_journal import TradeJournal
from data.macro_analyzer import MacroAnalyzer
from utils.email_sender import EmailReporter

# نحتاج لتحميل مفتاح API لـ Claude
load_dotenv()
API_KEY = os.getenv("ANTHROPIC_API_KEY")

def run_campaign_step(symbol="USDJPY.BL", chunk_index=1, chunk_size=30000):
    m5_path = f"backtest_data/{symbol}_M5_history.csv"
    h1_path = f"backtest_data/{symbol}_H1_history.csv"
    memory_path = "journal/campaign_memory.json"
    
    if not os.path.exists(m5_path):
        print(f"❌ لم يتم العثور على بيانات {symbol}")
        return

    print("===========================================")
    print(f"🕰️ بدء آلة الزمن: حملة المحاكاة للقطاع (الربع) رقم {chunk_index}")
    print("===========================================")
    
    start_idx = chunk_index * chunk_size
    end_idx = start_idx + chunk_size
    engine = SimulationEngine(m5_path, h1_path, chunk_size)
    
    # تحديد التواريخ
    real_start_idx = max(300, start_idx) # نتجاوز شمعات النافذة الأولى دائماً
    real_end_idx = min(end_idx, len(engine.m5_df)) - 1
    
    try:
        start_date = engine.m5_df.iloc[real_start_idx]['time'].strftime("%Y-%m-%d")
        end_date = engine.m5_df.iloc[real_end_idx]['time'].strftime("%Y-%m-%d")
    except Exception as e:
        start_date = "Unknown"
        end_date = "Unknown"
        
    print(f"📅 معالجة الربع من تاريخ: {start_date} حتى {end_date}")
    
    # 1. المحاكاة
    engine.run_chunk(start_idx, real_end_idx + 1)
    
    simulated_trades = []
    for t in engine.journal_trades:
        t["status"] = "CLOSED" 
        t["lessons"] = []
        simulated_trades.append(t)

    # 2. استخراج الإحصائيات     
    journal = TradeJournal()
    journal.trades = simulated_trades
    stats = journal.get_stats()
    
    print("\n📊 إحصائيات الربع الحالي:")
    print(f"الربح الصافي: ${stats.get('total_pnl', 0)}")
    print(f"نسبة النجاح: {stats.get('win_rate', 0)}%")
    
    # 3. معالجة الذاكرة التاريخية
    past_memory = ""
    memory_store = []
    if os.path.exists(memory_path):
        with open(memory_path, "r", encoding="utf-8") as f:
            try:
                memory_store = json.load(f)
                past_memory = "\n".join(memory_store)
            except:
                pass
                
    # 4. التوجه إلى Claude API للتحليل وكتابة التقرير
    if not API_KEY:
        print("⚠️ لم يتم العثور على ANTHROPIC_API_KEY. لن يتم إرسال الإيميل.")
        return
        
    print("\n🤖 يتم الآن استدعاء Claude لإنشاء الرؤية الاقتصادية وبناء الذاكرة التاريخية...")
    analyzer = MacroAnalyzer(API_KEY)
    html_report = analyzer.generate_campaign_report(start_date, end_date, stats, past_memory)
    
    # 5. استخراج إضافة الذاكرة الحالية (Update to System Memory)
    new_memory = f"Memory for {start_date} to {end_date}: Winrate {stats.get('win_rate')}%, PnL ${stats.get('total_pnl')}."
    try:
        for line in html_report.split('\n'):
            if "Memory" in line and not line.startswith("<h"):
                new_memory += f" AI Logic: {line.strip()[:100]}"
                break
    except:
        pass
        
    memory_store.append(new_memory)
    os.makedirs("journal", exist_ok=True)
    with open(memory_path, "w", encoding="utf-8") as f:
        json.dump(memory_store, f, indent=4, ensure_ascii=False)
        
    # 6. إرسال الإيميل
    print("\n📧 جاري إرسال التقرير للإيميل...")
    reporter = EmailReporter()
    subject = f"Sequential Backtest Report: Q{chunk_index} ({start_date} to {end_date})"
    
    # تنسيق الـ HTML النهائي
    final_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
        <h1 style="color: #2c3e50; text-align: center;">🕰️ AI Trading Time Machine</h1>
        <h3 style="text-align: center;">Period: {start_date}  =>  {end_date}</h3>
        <hr>
        {html_report}
    </body>
    </html>
    """
    
    if reporter.send_vision_report(subject, final_html):
        print("✅ اكتمل الجزء بامتياز!")
    else:
        print("⚠️ حدث خطأ في إرسال الإيميل. تم حفظ الذاكرة وإتمام التحليل الداخلي.")

if __name__ == "__main__":
    c_index = 1
    if len(sys.argv) > 1:
        try:
            c_index = int(sys.argv[1])
        except:
            pass
            
    run_campaign_step("USDJPY.BL", chunk_index=c_index)
