"""
Market Intelligence — ذكاء السوق الشامل

4 محاور:
1. 📰 FinnHub News — أخبار لحظية مع تحليل سنتيمنت
2. 📅 Economic Calendar — تقويم أحداث (NFP, FOMC, CPI)
3. 💪 Currency Strength — قوة كل عملة من الأزواج
4. 🌡️ Market Mood — DXY + VIX + Gold + Yields

يُنتج:
- درجة سنتيمنت عامة (-100 إلى +100)
- تحذيرات أحداث عالية التأثير
- ترتيب العملات من الأقوى للأضعف
- تقرير شامل لـ Telegram
"""

import requests
import yfinance as yf
from datetime import datetime, timedelta
from config import FINNHUB_API_KEY, TWELVE_DATA_API_KEY


# ═══════════════════════════════════════════════════════════════
# 1. FinnHub News — أخبار فوركس لحظية
# ═══════════════════════════════════════════════════════════════

class FinnHubNews:
    """أخبار فوركس من FinnHub"""

    BASE_URL = "https://finnhub.io/api/v1"

    # كلمات مفتاحية لتحديد التأثير
    HIGH_IMPACT_KEYWORDS = [
        "fed", "fomc", "nfp", "non-farm", "interest rate", "rate decision",
        "cpi", "inflation", "gdp", "employment", "payroll", "boj",
        "central bank", "monetary policy", "quantitative", "recession",
        "tariff", "trade war", "geopolitical", "crisis",
    ]

    BULLISH_USD = [
        "rate hike", "hawkish", "strong dollar", "hot inflation",
        "beat expectations", "above forecast", "strong jobs",
        "higher rates", "tightening", "growth", "optimism",
        "resilient", "expansion", "safe haven"
    ]

    BEARISH_USD = [
        "rate cut", "dovish", "weak dollar", "cool inflation",
        "miss expectations", "below forecast", "weak jobs",
        "lower rates", "easing", "recession", "contraction",
        "crisis", "tension", "conflict", "war", "crash",
        "plunge", "slowdown", "default", "fear"
    ]

    def __init__(self, api_key=None):
        self.api_key = api_key or FINNHUB_API_KEY

    def get_forex_news(self, category="general", count=50):
        """جلب الأخبار (general لأنه للنسخة المجانية يعطي نتائج أكثر من forex)"""
        if not self.api_key:
            return []
        try:
            resp = requests.get(
                f"{self.BASE_URL}/news",
                params={"category": category, "token": self.api_key},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "error" in data:
                    print(f"⚠️ خطأ API أخبار: {data['error']}")
                    return []
                
                news = data[:count]
                return [
                    {
                        "headline": n.get("headline", ""),
                        "source": n.get("source", ""),
                        "time": datetime.fromtimestamp(n.get("datetime", 0)).strftime("%H:%M"),
                        "url": n.get("url", ""),
                        "impact": self._assess_impact(n.get("headline", "")),
                        "sentiment": self._assess_sentiment(n.get("headline", "") + " " + n.get("summary", "")),
                    }
                    for n in news
                ]
        except Exception as e:
            print(f"⚠️ FinnHub News error: {e}")
        return []

    def _assess_impact(self, headline):
        """تقييم تأثير الخبر"""
        text = headline.lower()
        for kw in self.HIGH_IMPACT_KEYWORDS:
            if kw in text:
                return "HIGH"
        return "LOW"

    def _assess_sentiment(self, text):
        """تقييم السنتيمنت (بالنسبة للدولار)"""
        text = text.lower()
        bull_score = sum(1 for kw in self.BULLISH_USD if kw in text)
        bear_score = sum(1 for kw in self.BEARISH_USD if kw in text)
        if bull_score > bear_score:
            return "BULLISH_USD"
        elif bear_score > bull_score:
            return "BEARISH_USD"
        return "NEUTRAL"

    def get_sentiment_score(self):
        """
        درجة سنتيمنت الأخبار (-100 إلى +100)
        + = bullish USD (bearish USDJPY لأن الين أضعف)
        - = bearish USD
        """
        news = self.get_forex_news(count=50)
        if not news:
            return 0, "لا أخبار متاحة", []

        bull = sum(1 for n in news if n["sentiment"] == "BULLISH_USD")
        bear = sum(1 for n in news if n["sentiment"] == "BEARISH_USD")
        high_impact = [n for n in news if n["impact"] == "HIGH"]

        # التركيز فقط على الأخبار التي لها توجه (BULLISH أو BEARISH)
        total_directional = bull + bear
        if total_directional == 0:
            return 0, "NEUTRAL", high_impact

        score = int((bull - bear) / total_directional * 100)
        bias = "BULLISH_USD" if score > 15 else ("BEARISH_USD" if score < -15 else "NEUTRAL")

        return score, bias, high_impact


# ═══════════════════════════════════════════════════════════════
# 2. Economic Calendar — تقويم اقتصادي
# ═══════════════════════════════════════════════════════════════

class EconomicCalendar:
    """تقويم أحداث اقتصادية من FinnHub"""

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key=None):
        self.api_key = api_key or FINNHUB_API_KEY

    def get_today_events(self):
        """أحداث اليوم"""
        if not self.api_key:
            return []
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            resp = requests.get(
                f"{self.BASE_URL}/calendar/economic",
                params={"from": today, "to": tomorrow, "token": self.api_key},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "error" in data:
                    print(f"⚠️ تنبيه التقويم (نسخة مجانية مقيدة): {data['error']}")
                    return []
                
                events = data.get("economicCalendar", [])
                return [
                    {
                        "country": e.get("country", ""),
                        "event": e.get("event", ""),
                        "time": e.get("time", ""),
                        "impact": e.get("impact", "low"),
                        "actual": e.get("actual", None),
                        "estimate": e.get("estimate", None),
                        "prev": e.get("prev", None),
                    }
                    for e in events
                ]
        except Exception as e:
            print(f"⚠️ Calendar error: {e}")
        return []

    def get_high_impact_events(self):
        """أحداث عالية التأثير فقط"""
        events = self.get_today_events()
        return [e for e in events if e.get("impact") in ("high", "medium", 3, 2)]

    def should_stop_trading(self):
        """هل لازم نوقف التداول بسبب حدث قريب؟"""
        high_events = self.get_high_impact_events()

        # فلتر: أحداث USD أو JPY فقط
        relevant = [e for e in high_events if e.get("country") in ("US", "JP")]

        if not relevant:
            return False, "لا أحداث مؤثرة"

        # تحقق إذا حدث قريب (خلال ساعة)
        now = datetime.now()
        for e in relevant:
            try:
                event_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {e['time']}", "%Y-%m-%d %H:%M:%S")
                diff = abs((event_time - now).total_seconds()) / 60
                if diff <= 60:  # خلال 60 دقيقة
                    return True, f"⚠️ {e['event']} خلال {int(diff)} دقيقة"
            except Exception:
                continue

        return False, f"📅 {len(relevant)} حدث مؤثر اليوم (بعيد)"


# ═══════════════════════════════════════════════════════════════
# 3. Currency Strength — قوة العملات
# ═══════════════════════════════════════════════════════════════

class CurrencyStrength:
    """حساب قوة كل عملة — يستخدم Twelve Data أو yfinance"""

    # رموز Twelve Data → (base, quote)
    TD_PAIRS = {
        "EUR/USD": ("EUR", "USD"),
        "GBP/USD": ("GBP", "USD"),
        "USD/JPY": ("USD", "JPY"),
        "USD/CHF": ("USD", "CHF"),
        "AUD/USD": ("AUD", "USD"),
        "NZD/USD": ("NZD", "USD"),
        "USD/CAD": ("USD", "CAD"),
    }

    # رموز yfinance للـ fallback
    YF_PAIRS = {
        "EURUSD=X": ("EUR", "USD"),
        "GBPUSD=X": ("GBP", "USD"),
        "USDJPY=X": ("USD", "JPY"),
        "USDCHF=X": ("USD", "CHF"),
        "AUDUSD=X": ("AUD", "USD"),
        "NZDUSD=X": ("NZD", "USD"),
        "USDCAD=X": ("USD", "CAD"),
    }

    def _fetch_via_twelve_data(self) -> dict:
        """يجلب أسعار الأزواج من Twelve Data"""
        if not TWELVE_DATA_API_KEY:
            return {}
        try:
            from twelvedata import TDClient
            td = TDClient(apikey=TWELVE_DATA_API_KEY)
            strength = {}
            for td_symbol, (base, quote) in self.TD_PAIRS.items():
                try:
                    ts = td.time_series(
                        symbol=td_symbol,
                        interval="1day",
                        outputsize=2,
                        timezone="UTC",
                    ).as_pandas()
                    if ts is None or len(ts) < 2:
                        continue
                    ts = ts.sort_index()
                    prev  = float(ts["close"].iloc[-2])
                    curr  = float(ts["close"].iloc[-1])
                    change = (curr - prev) / prev * 100 if prev != 0 else 0.0
                    strength[base] = strength.get(base, 0) + change
                    strength[quote] = strength.get(quote, 0) - change
                except Exception:
                    continue
            return strength
        except Exception as e:
            print(f"⚠️ Twelve Data CurrencyStrength error: {e}")
            return {}

    def _fetch_via_yfinance(self) -> dict:
        """Fallback: yfinance"""
        try:
            import pandas as pd
            symbols = list(self.YF_PAIRS.keys())
            data = yf.download(symbols, period="5d", interval="1d", auto_adjust=True, progress=False)
            if data.empty:
                return {}
            strength = {}
            for symbol, (base, quote) in self.YF_PAIRS.items():
                try:
                    close = data["Close"][symbol].dropna()
                    if len(close) < 2:
                        continue
                    change = (float(close.iloc[-1]) - float(close.iloc[-2])) / float(close.iloc[-2]) * 100
                    strength[base] = strength.get(base, 0) + change
                    strength[quote] = strength.get(quote, 0) - change
                except Exception:
                    continue
            return strength
        except Exception as e:
            print(f"⚠️ yfinance CurrencyStrength error: {e}")
            return {}

    def calculate(self):
        """حساب قوة كل عملة — Twelve Data أولاً، yfinance كـ fallback"""
        strength = self._fetch_via_twelve_data()
        if not strength:
            strength = self._fetch_via_yfinance()

        if strength:
            return dict(sorted(strength.items(), key=lambda x: x[1], reverse=True))
        return {}

    def get_report(self):
        """تقرير قوة العملات"""
        strength = self.calculate()
        if not strength:
            return "⚠️ فشل حساب قوة العملات"

        lines = ["── 💪 قوة العملات ──"]
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]

        for i, (currency, score) in enumerate(strength.items()):
            icon = medals[i] if i < len(medals) else "  "
            arrow = "📈" if score > 0 else ("📉" if score < 0 else "➡️")
            lines.append(f"{icon} {currency}: {score:+.2f}% {arrow}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 4. Market Mood — نبض السوق
# ═══════════════════════════════════════════════════════════════

class MarketMood:
    """مقياس مزاج السوق العام — يستخدم Twelve Data أو yfinance"""

    # رموز Twelve Data للأصول الكروس
    TD_ASSETS = {
        "DXY":   "DX-Y.NYB",   # Twelve Data يدعم هذا كـ ETF proxy
        "XAU/USD": "XAU/USD",
        "US10Y": "TNX",         # في بعض خطط Twelve Data
    }

    def _fetch_td_price(self, symbol: str) -> dict:
        """يجلب سعر أصل من Twelve Data"""
        if not TWELVE_DATA_API_KEY:
            return {}
        try:
            from twelvedata import TDClient
            td = TDClient(apikey=TWELVE_DATA_API_KEY)
            ts = td.time_series(symbol=symbol, interval="1day", outputsize=2, timezone="UTC").as_pandas()
            if ts is None or len(ts) < 2:
                return {}
            ts = ts.sort_index()
            curr  = float(ts["close"].iloc[-1])
            prev  = float(ts["close"].iloc[-2])
            return {"price": round(curr, 3), "change": round((curr - prev) / prev * 100, 2)}
        except Exception:
            return {}

    def analyze(self):
        """تحليل مزاج السوق"""
        try:
            # حاول Twelve Data للذهب و DXY أولاً (أكثر موثوقية وأسرع)
            gold_td = self._fetch_td_price("XAU/USD")
            dxy_td  = self._fetch_td_price("DX-Y.NYB")

            tickers = ["DX-Y.NYB", "^VIX", "GC=F", "^TNX"]
            data = yf.download(tickers, period="5d", interval="1d", auto_adjust=True, progress=False)

            results = {}
            if not data.empty:
                for ticker in tickers:
                    try:
                        close = data["Close"][ticker].dropna()
                        if len(close) >= 2:
                            current = float(close.iloc[-1])
                            prev = float(close.iloc[-2])
                            change = (current - prev) / prev * 100
                            results[ticker] = {"price": round(current, 2), "change": round(change, 2)}
                    except Exception:
                        continue

            # استخدم Twelve Data إذا نجح، وإلا yfinance
            dxy    = dxy_td  if dxy_td  else results.get("DX-Y.NYB", {})
            vix    = results.get("^VIX", {})
            gold   = gold_td if gold_td else results.get("GC=F", {})
            yields = results.get("^TNX", {})

            # إذا لا بيانات أصلاً
            if not dxy and not vix and not gold and not yields:
                return self._default()

            # نقاط المزاج
            mood_score = 0
            signals = []

            # DXY (قوة الدولار)
            if dxy:
                if dxy["change"] > 0.3:
                    mood_score += 25
                    signals.append(f"💵 DXY صاعد ({dxy['price']}, {dxy['change']:+.2f}%)")
                elif dxy["change"] < -0.3:
                    mood_score -= 25
                    signals.append(f"💵 DXY هابط ({dxy['price']}, {dxy['change']:+.2f}%)")
                else:
                    signals.append(f"💵 DXY مستقر ({dxy['price']})")

            # VIX (مقياس الخوف)
            if vix:
                vix_level = vix["price"]
                if vix_level > 25:
                    mood_score -= 20
                    signals.append(f"😰 VIX عالي ({vix_level}) — خوف!")
                elif vix_level < 15:
                    mood_score += 10
                    signals.append(f"😎 VIX منخفض ({vix_level}) — هدوء")
                else:
                    signals.append(f"😐 VIX عادي ({vix_level})")

            # Gold (ملاذ آمن)
            if gold:
                if gold["change"] > 0.5:
                    mood_score -= 15
                    signals.append(f"🥇 الذهب صاعد ({gold['price']}) — هروب للأمان")
                elif gold["change"] < -0.5:
                    mood_score += 15
                    signals.append(f"🥇 الذهب هابط ({gold['price']}) — شهية مخاطرة")
                else:
                    signals.append(f"🥇 الذهب مستقر ({gold['price']})")

            # US 10Y Yields
            if yields:
                if yields["change"] > 2:
                    mood_score += 20
                    signals.append(f"📊 العوائد ترتفع ({yields['price']}%) — دولار أقوى")
                elif yields["change"] < -2:
                    mood_score -= 20
                    signals.append(f"📊 العوائد تنخفض ({yields['price']}%) — دولار أضعف")
                else:
                    signals.append(f"📊 العوائد مستقرة ({yields['price']}%)")

            # المزاج العام
            if mood_score > 20:
                mood = "RISK_ON"
                mood_label = "🟢 شهية مخاطرة — دولار قوي"
            elif mood_score < -20:
                mood = "RISK_OFF"
                mood_label = "🔴 هروب للأمان — دولار ضعيف"
            else:
                mood = "NEUTRAL"
                mood_label = "🟡 محايد"

            return {
                "mood": mood,
                "mood_label": mood_label,
                "score": mood_score,
                "signals": signals,
                "data": results,
            }

        except Exception as e:
            print(f"⚠️ Market Mood error: {e}")
            return self._default()

    def _default(self):
        return {"mood": "NEUTRAL", "mood_label": "🟡 محايد", "score": 0, "signals": [], "data": {}}


# ═══════════════════════════════════════════════════════════════
# المحرّك الرئيسي — يجمع كل شي
# ═══════════════════════════════════════════════════════════════

class MarketIntelligence:
    """ذكاء السوق الشامل — يجمع الأخبار + التقويم + القوة + المزاج"""

    def __init__(self):
        self.news = FinnHubNews()
        self.calendar = EconomicCalendar()
        self.currency = CurrencyStrength()
        self.mood = MarketMood()

    def full_analysis(self):
        """تحليل شامل"""
        print("🧠 تحليل ذكاء السوق...")

        # 1. أخبار
        news_score, news_bias, high_impact_news = self.news.get_sentiment_score()

        # 2. تقويم
        should_stop, cal_reason = self.calendar.should_stop_trading()
        high_events = self.calendar.get_high_impact_events()

        # 3. قوة العملات
        strength = self.currency.calculate()

        # 4. مزاج السوق
        mood = self.mood.analyze()

        return {
            "news_score": news_score,
            "news_bias": news_bias,
            "high_impact_news": high_impact_news,
            "should_stop": should_stop,
            "calendar_reason": cal_reason,
            "high_events": high_events,
            "currency_strength": strength,
            "mood": mood,
        }

    def should_trade(self):
        """هل الظروف مناسبة للتداول؟"""
        analysis = self.full_analysis()

        # أسباب عدم التداول
        blockers = []

        if analysis["should_stop"]:
            blockers.append(analysis["calendar_reason"])

        mood = analysis["mood"]
        if mood["mood"] == "RISK_OFF" and mood["score"] < -40:
            blockers.append(f"🔴 مزاج السوق سلبي جداً ({mood['score']})")

        if blockers:
            return False, blockers, analysis

        return True, [], analysis

    def get_usdjpy_bias(self):
        """ميل USDJPY بناءً على كل المعطيات"""
        analysis = self.full_analysis()
        total_score = 0

        # أخبار (30%)
        total_score += analysis["news_score"] * 0.3

        # مزاج السوق (40%)
        total_score += analysis["mood"]["score"] * 0.4

        # قوة العملات (30%)
        strength = analysis["currency_strength"]
        usd_str = strength.get("USD", 0)
        jpy_str = strength.get("JPY", 0)
        pair_score = (usd_str - jpy_str) * 10  # تحويل لنطاق مناسب
        total_score += min(max(pair_score, -30), 30)

        total_score = int(total_score)

        if total_score > 15:
            bias = "BULLISH"  # USD قوي = USDJPY صاعد
        elif total_score < -15:
            bias = "BEARISH"  # USD ضعيف = USDJPY هابط
        else:
            bias = "NEUTRAL"

        return bias, total_score, analysis

    def get_report(self):
        """تقرير شامل لـ Telegram"""
        analysis = self.full_analysis()

        lines = ["═══ 🧠 ذكاء السوق ═══\n"]

        # مزاج السوق
        mood = analysis["mood"]
        lines.append(f"🌡️ المزاج: {mood['mood_label']}")
        for sig in mood["signals"]:
            lines.append(f"   {sig}")

        # أخبار
        lines.append(f"\n📰 سنتيمنت الأخبار: {analysis['news_score']:+d} ({analysis['news_bias']})")
        if analysis["high_impact_news"]:
            lines.append("   ⚡ أخبار عالية التأثير:")
            for n in analysis["high_impact_news"][:3]:
                lines.append(f"   • {n['headline'][:60]}...")

        # تقويم
        if analysis["should_stop"]:
            lines.append(f"\n🚫 {analysis['calendar_reason']}")
        elif analysis["high_events"]:
            lines.append(f"\n📅 {len(analysis['high_events'])} حدث مؤثر اليوم")
            for e in analysis["high_events"][:3]:
                lines.append(f"   • {e['time']} — {e['event']} ({e['country']})")

        # قوة العملات
        strength = analysis["currency_strength"]
        if strength:
            lines.append("\n" + self.currency.get_report())

        # الخلاصة
        bias, score, _ = self.get_usdjpy_bias()
        lines.append(f"\n── الخلاصة ──")
        icon = "📈" if bias == "BULLISH" else ("📉" if bias == "BEARISH" else "➡️")
        lines.append(f"{icon} USDJPY: {bias} (درجة: {score:+d})")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    intel = MarketIntelligence()
    print(intel.get_report())
