import anthropic
import yfinance as yf
import os
import json

class MacroAnalyzer:

    def __init__(self, api_key):
        self.client = anthropic.Anthropic(api_key=api_key)
        self._tracker = None

    def _get_tracker(self):
        """يُنشئ EconomicTracker عند أول استخدام"""
        if self._tracker is None:
            try:
                from data.economic_tracker import EconomicTracker
                self._tracker = EconomicTracker()
            except Exception:
                self._tracker = None
        return self._tracker

    def get_market_data(self):
        """يجلب بيانات السوق — يستخدم EconomicTracker إذا أمكن، وإلا yfinance مباشرة"""
        tracker = self._get_tracker()
        if tracker:
            try:
                snap = tracker.get_full_snapshot()
                cross = snap.get("cross_asset", {})
                return {
                    "USDJPY":    snap.get("japan", {}).get("jp_us_yield_spread", "غير متاح"),
                    "US10Y":     snap.get("yield_curve", {}).get("US10Y", "غير متاح"),
                    "VIX":       snap.get("vix", "غير متاح"),
                    "DXY":       cross.get("DXY", {}).get("price", "غير متاح"),
                    "FED_RATE":  snap.get("fed_rate", "غير متاح"),
                    "BOJ_RATE":  snap.get("boj_rate", "غير متاح"),
                    "CPI_YOY":   snap.get("cpi", {}).get("cpi_yoy", "غير متاح"),
                    "CURVE":     snap.get("yield_curve", {}).get("curve_shape", "غير متاح"),
                }
            except Exception:
                pass

        # fallback: yfinance مباشرة
        def last_price(df):
            try:
                return round(float(df["Close"].squeeze().iloc[-1]), 3)
            except Exception:
                return "غير متاح"

        usdjpy = yf.download("USDJPY=X", period="5d", interval="1d", auto_adjust=True, progress=False)
        us10y  = yf.download("^TNX",     period="5d", interval="1d", auto_adjust=True, progress=False)
        vix    = yf.download("^VIX",     period="5d", interval="1d", auto_adjust=True, progress=False)
        dxy    = yf.download("DX-Y.NYB", period="5d", interval="1d", auto_adjust=True, progress=False)

        return {
            "USDJPY": last_price(usdjpy),
            "US10Y":  last_price(us10y),
            "VIX":    last_price(vix),
            "DXY":    last_price(dxy),
        }

    def analyze(self):
        data = self.get_market_data()
        fed  = data.get("FED_RATE", "غير متاح")
        boj  = data.get("BOJ_RATE", "غير متاح")
        cpi  = data.get("CPI_YOY", "غير متاح")
        curve = data.get("CURVE", "غير متاح")

        prompt = f"""
أنت محلل ماكرو اقتصادي كوانتي متخصص في زوج USDJPY.
البيانات الحالية:
- سعر USDJPY: {data.get('USDJPY', 'غير متاح')}
- عائد السندات الأمريكية 10 سنوات: {data.get('US10Y', 'غير متاح')}
- مؤشر VIX الخوف: {data.get('VIX', 'غير متاح')}
- مؤشر الدولار DXY: {data.get('DXY', 'غير متاح')}
- سعر الفائدة الأمريكي (Fed): {fed}%
- سعر الفائدة الياباني (BOJ): {boj}%
- التضخم الأمريكي CPI (سنوي): {cpi}%
- شكل منحنى العائد: {curve}

بناءً على هذه البيانات الكمية:
1. حدد اتجاه USDJPY خلال الـ 24 ساعة القادمة
2. أعط score من -100 إلى +100

أجب فقط بهذا الشكل:
SCORE: [الرقم]
BIAS: [BULLISH أو BEARISH أو NEUTRAL]
REASON: [سبب واحد مختصر]
"""
        message = self.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        response = message.content[0].text
        lines = response.strip().split("\n")
        score = 0
        bias = "NEUTRAL"
        reason = ""

        for line in lines:
            if line.startswith("SCORE:"):
                try:
                    score = int(line.split(":")[1].strip())
                except Exception:
                    pass
            elif line.startswith("BIAS:"):
                bias = line.split(":")[1].strip()
            elif line.startswith("REASON:"):
                reason = line.split(":", 1)[1].strip()

        return {"score": score, "bias": bias, "reason": reason, "data": data}

    def generate_campaign_report(self, start_date, end_date, stats, past_memory=""):
        prompt = f"""
You are an elite quantitative analyst running a sequential backtesting time-machine on USDJPY.
We just finished evaluating the market from {start_date} to {end_date}.

Our algorithmic trading performance for this specific geographical quarter (Chunk):
- Total Trades: {stats.get('total', 0)}
- Win Rate: {stats.get('win_rate', 0)}%
- Total Net Profit (PnL estimated): ${stats.get('total_pnl', 0)}
- Profit Factor: {stats.get('profit_factor', 0)}

Previous quarters memory (to build continuity and not repeat yourself):
{past_memory if past_memory else "No previous memory. This is the very first chunk."}

Write an extremely professional, concise Market Backtest HTML email report.
RULES:
1. Headings MUST be in English.
2. The explanation and analysis paragraphs MUST be in Arabic. Professional, strict quantitative tone.
3. Include brief English terms in brackets for financial jargon (e.g. السيولة [Liquidity Sweep]).
4. The HTML must have these sections ONLY (wrap them in standard <h2> or <h3> headers):
   - <h2>Quarter Performance Overview</h2> (List the stats prominently)
   - <h2>Market Narrative & Context</h2> (What likely drove the price action during this chunk based on your economic knowledge of {start_date} to {end_date})
   - <h2>Forecast & Projections</h2> (What do you expect for the next quarter based on this structure and historical context?)
   - <h2>Update to System Memory</h2> (A very short 1-line English summary for me to feed back into your memory log).
5. At the very END of your response, after the HTML, add a JSON block like this (outside the HTML):
   MEMORY_JSON: {{"insights": ["insight1 in English", "insight2 in English", "insight3 in English"]}}
6. Output valid HTML ONLY for the main report (inline styling is fine). No markdown wrappers. Make it elegant.
"""
        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=1800,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except Exception as e:
            return f"<h3>Error generating report: {e}</h3>"

    def extract_memory_insights(self, html_report: str) -> list:
        """
        يستخرج الـ insights من تقرير Claude بشكل موثوق (JSON بدل string parsing).
        يرجع list of strings.
        """
        import json as _json
        marker = "MEMORY_JSON:"
        idx = html_report.rfind(marker)
        if idx == -1:
            return []
        try:
            json_str = html_report[idx + len(marker):].strip()
            # ابحث عن أول { وآخر }
            start = json_str.find("{")
            end   = json_str.rfind("}") + 1
            if start == -1 or end == 0:
                return []
            data = _json.loads(json_str[start:end])
            return data.get("insights", [])
        except Exception:
            return []

if __name__ == "__main__":
    API_KEY = "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"

    analyzer = MacroAnalyzer(API_KEY)

    result = analyzer.analyze()

    print("Score:", result["score"])

    print("Bias:", result["bias"])

    print("السبب:", result["reason"])

    print("البيانات:", result["data"])

