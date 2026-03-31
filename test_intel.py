import os
from config import FINNHUB_API_KEY
from data.market_intelligence import FinnHubNews, MarketMood, CurrencyStrength, EconomicCalendar

print(f"🔑 مفتاح FinnHub المستخدم يبدأ بـ: {FINNHUB_API_KEY[:5] if FINNHUB_API_KEY else 'لم يتم العثور عليه'}")

print("\n--- 1. اختبار أخبار FinnHub ---")
news = FinnHubNews()
raw_news = news.get_forex_news(count=2)
if raw_news:
    print(f"✅ تم جلب {len(raw_news)} أخبار. أول خبر:")
    print(f"   الرأس: {raw_news[0]['headline']}")
    score, bias, high_impact = news.get_sentiment_score()
    print(f"   السنتيمنت المحسوب: Score={score}, Bias={bias}")
else:
    print("❌ فشل في جلب الأخبار أو لا توجد أخبار. تأكد من مفتاح API (FinnHub لا تعطي بيانات في بعض فئاتها للمحسابات المجانية إن لم يكن متاحاً أو تأكد من ال URL).")

print("\n--- 2. اختبار التقويم الاقتصادي (FinnHub) ---")
calendar = EconomicCalendar()
events = calendar.get_today_events()
if events:
    print(f"✅ تم جلب {len(events)} أحداث لليوم والغد. أول حدث:")
    print(f"   {events[0].get('time')} | {events[0].get('country')} - {events[0].get('event')} | Impact: {events[0].get('impact')}")
else:
    print("❌ لم يتم العثور على أحداث في التقويم (قد يكون الـ API Key به مشكلة أو ليس لديك وصول للميزات المطلوبة).")

print("\n--- 3. اختبار قوة العملات (yfinance) ---")
currency = CurrencyStrength()
strength = currency.calculate()
if strength:
    print(f"✅ تم جلب وحساب القوة لـ {len(strength)} عملات.")
    print("   العملات:", ", ".join([f"{k}: {v:.2f}%" for k, v in strength.items()]))
else:
    print("❌ فشل في حساب قوة العملات من yfinance.")

print("\n--- 4. اختبار مزاج السوق (yfinance) ---")
mood = MarketMood()
mood_data = mood.analyze()
print(f"✅ مزاج السوق: {mood_data['mood_label']} | Score: {mood_data['score']}")
if mood_data.get('data'):
    print("   بيانات yfinance التي تم جلبها:")
    for key, val in mood_data['data'].items():
        print(f"   {key}: السعر={val.get('price')}, التغير={val.get('change')}%")
else:
    print("❌ فشل في جلب بيانات DXY, VIX, إلخ.")
