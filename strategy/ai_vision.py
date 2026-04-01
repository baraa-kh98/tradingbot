import os
import anthropic
import json
from data.market_intelligence import MarketIntelligence
from risk.trade_journal import TradeJournal
from utils.email_sender import EmailReporter
from config import CLAUDE_API_KEY, ACTIVE_PAIRS

class AIVisionGenerator:
    """كبير الاقتصاديين (Chief Economist) المعتمد على الذكاء الاصطناعي"""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        self.reporter = EmailReporter()

    def gather_data(self):
        # 1. جلب بيانات السوق والاقتصاد
        intel = MarketIntelligence()
        market_data = intel.full_analysis()

        # 2. جلب أداء المحفظة
        journal = TradeJournal()
        portfolio_stats = journal.get_stats()
        recent_trades = journal.trade_history[-10:] if hasattr(journal, "trade_history") else []

        return market_data, portfolio_stats, recent_trades

    def format_prompt(self, market, port, recent_trades):
        mood = market.get('mood', {})
        currency = market.get('currency_strength', [])
        
        prompt = f"""
أنت الآن "كبير الاقتصاديين ومدير المخاطر" (Chief Economist & Risk Manager) لصندوق تحوط تداول آلي متخصص بأسواق العملات والذهب.

مطلوب منك كتابة "الرؤية الصباحية" (Morning Vision Report) لإرسالها لمدير الصندوق (Baraa) عبر الإيميل.

إليك بيانات اليوم:
--- 1. بيانات الاقتصاد الكلي ومزاج السوق ---
- المزاج العام: {mood.get('mood_label', 'محايد')} (Score: {mood.get('score', 0)})
- سنتيمنت الأخبار: {market.get('news_bias', 'محايد')} (Score: {market.get('news_score', 0)})
- أهم الأحداث الاقتصادية القادمة: {len(market.get('high_events', []))} أحداث.
- قوة العملات حالياً:
{json.dumps(currency, ensure_ascii=False, indent=2) if currency else "غير متاحة"}

--- 2. بيانات المحفظة (Portfolio) ---
- إجمالي الصفقات: {port.get('total', 0)}
- صفقات رابحة: {port.get('wins', 0)} | خاسرة: {port.get('losses', 0)}
- نسبة الفوز: {port.get('win_rate', 0)}%
- إجمالي الأرباح بالنقاط: {port.get('total_pips', 0)} Pips
- Profit Factor: {port.get('profit_factor', 0)}
- أزواج التداول النشطة المتوفرة للبوت: {list(ACTIVE_PAIRS)}

المطلوب منك كتابة تقرير احترافي جداً ومفصل باللغة العربية (بتنسيق HTML جاهز ليتم إرساله بالإيميل مباشرة).
التقرير يجب أن يحتوي على الأقسام التالية بترتيب واضح وبتصميم جذاب (استخدم Inline CSS في الـ HTML لجعله أنيقاً، ألوان داكنة راقية كأنه تقرير بلومبيرغ):
1. نظرة الأسواق (Market Vision): حلل قوة العملات ومزاج السوق الحالي.
2. الرؤية الزمنية (Timeframe Vision):
   - المدى القصير (اليوم/غداً).
   - المدى المتوسط (هذا الأسبوع/الأسبوع القادم).
   - المدى الطويل (الشهر الحالي).
3. توقعات المحفظة (Portfolio Forecast): حلل أداء البوت بناءً على نسبة الفوز وأعطِ توقعاتك لمسار الأرباح.
4. توصيات لمدير البوت (Bot Config Recommendations): هل يجب تقليل المخاطرة؟ هل يجب التركيز على أزواج معينة وتجنب أخرى بناءً على قوة العملات؟

ملاحظة هامة: يجب أن يكون المخرج كود HTML فقط (بدون أي نصوص إضافية أو علامات Markdown حول الكود، اخرج كود HTML ليعمل مباشرة كرسالة إيميل).
"""
        return prompt

    def generate_html_report(self):
        print("🧠 جاري إعداد الرؤية الاقتصادية الشاملة بواسطة Claude...")
        market, port, recent = self.gather_data()
        prompt = self.format_prompt(market, port, recent)

        try:
            message = self.client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=2500,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            html_content = message.content[0].text.strip()
            
            # تنظيف الكود إذا أرسل Claude علامات Markdown
            if html_content.startswith("```html"):
                html_content = html_content[7:]
            if html_content.endswith("```"):
                html_content = html_content[:-3]
                
            return html_content
        except Exception as e:
            print(f"❌ فشل توليد التقرير بواسطة Claude: {e}")
            return None

    def execute_daily_vision(self):
        html_report = self.generate_html_report()
        if not html_report:
            return False

        subject = "📊 الرؤية الاستراتيجية الصباحية والاقتصادية الدقيقة (AI Chief Economist)"
        return self.reporter.send_vision_report(subject, html_report)
