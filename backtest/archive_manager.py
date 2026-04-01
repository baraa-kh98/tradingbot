import json
import os
from datetime import datetime
import re

class ArchiveManager:
    """
    نظام أرشفة مزدوج (Dual Archiving System):
    1. مستودع JSON خام للبيانات والصفقات (لعمليات الآلة المستقبلية).
    2. كتاب إلكتروني Markdown للبشر (Captain's Log).
    """

    def __init__(self, journal_dir="journal"):
        self.journal_dir = journal_dir
        os.makedirs(self.journal_dir, exist_ok=True)
        self.json_path = os.path.join(self.journal_dir, "master_trades_archive.json")
        self.md_path = os.path.join(self.journal_dir, "Backtest_Archive.md")

    def append_trades_to_json(self, trades, chunk_index, start_date, end_date):
        """يحفظ الصفقات الخالصة كداتا لتعلم الذكاء الاصطناعي لاحقاً بدون مسح القديم"""
        archive = {}
        if os.path.exists(self.json_path):
            with open(self.json_path, "r", encoding="utf-8") as f:
                try:
                    archive = json.load(f)
                except:
                    pass

        chunk_key = f"Q{chunk_index}_{start_date}_to_{end_date}"
        archive[chunk_key] = trades

        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(archive, f, indent=4, ensure_ascii=False)
        print(f"📁 تم حفظ {len(trades)} صفقة في مستودع الآلة: master_trades_archive.json")

    def append_summary_to_md(self, chunk_index, start_date, end_date, stats, AI_lessons, claude_html=""):
        """يكتب تقرير بشري في كتاب الباكتيست (Captain's Log)"""
        
        # تنظيف مسودات HTML للحصول على نص ملخص من Claude
        clean_narrative = "لم يتم توليد قراءة للسوق."
        if claude_html:
            try:
                # استخراج جزء السرد من الـ HTML
                narrative_match = re.search(r'<h2>Market Narrative & Context</h2>(.*?)(<h2>|$)', claude_html, re.DOTALL | re.IGNORECASE)
                if narrative_match:
                    clean_narrative = narrative_match.group(1).strip()
                    # تنظيف التاجز
                    clean_narrative = re.sub(r'<[^>]+>', '', clean_narrative).strip()
            except:
                pass

        log_entry = f"""
---

## 📈 Quarter {chunk_index}: {start_date} to {end_date}
**🗓️ تاريخ التوليد:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### 📊 Performance Summary (إحصائيات الأداء)
- **Total Trades (إجمالي الصفقات):** {stats.get('total', 0)}
- **Win Rate (نسبة النجاح):** {stats.get('win_rate', 0)}%
- **Net PnL (الربح الصافي):** ${stats.get('total_pnl', 0)}
- **Profit Factor (عامل الربح):** {stats.get('profit_factor', 0)}
- **Total Pips (النقاط):** {stats.get('total_pips', 0)}

### 🧠 Mathematical AI Lessons (دروس البوت الرياضية المُستخلصة)
"""
        if not AI_lessons:
            log_entry += "- لم توجد دروس كافية لاستخلاصها في هذه الفترة.\n"
        else:
            for lesson in AI_lessons:
                if isinstance(lesson, dict):
                    log_entry += f"- **{lesson['action']} {lesson['param']}**: {lesson['reason']} (Priority: {lesson['priority']})\n"
                else:
                    log_entry += f"- {lesson}\n"

        log_entry += f"""
### 🌍 Macro Narrative (قراءة السوق الاقتصادية للمرحلة)
{clean_narrative}

"""

        # كتابة البيانات في الأرشيف (إلحاق/Append)
        mode = "a" if os.path.exists(self.md_path) else "w"
        with open(self.md_path, mode, encoding="utf-8") as f:
            if mode == "w":
                f.write("# 📚 سجل رحلة التداول لآلة الزمن (Trading AI Captain's Log)\n")
                f.write("هذا الملف يحتوي على أرشيف بشري منظم لكافة أرباح وتوصيات وخلفية الماكرو لكل ربع سنة مخصص للبوت.\n\n")
            f.write(log_entry)
            
        print("📝 تم تحديث كتاب الأرشيف البشري: Backtest_Archive.md بنجاح.")
