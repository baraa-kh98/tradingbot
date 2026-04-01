import anthropic
import yfinance as yf
import os
import json

class MacroAnalyzer:

    def __init__(self, api_key):
        self.client = anthropic.Anthropic(api_key=api_key)

    def get_market_data(self):
        usdjpy = yf.download("USDJPY=X", period="5d", interval="1d", auto_adjust=True)
        us10y = yf.download("^TNX", period="5d", interval="1d", auto_adjust=True)
        jp10y = yf.download("^JGB", period="5d", interval="1d", auto_adjust=True)
        vix = yf.download("^VIX", period="5d", interval="1d", auto_adjust=True)
        dxy = yf.download("DX-Y.NYB", period="5d", interval="1d", auto_adjust=True)

        def last_price(df):
            try:
                return round(float(df["Close"].squeeze().iloc[-1]), 3)
            except:
                return "غير متاح"

        return {
            "USDJPY": last_price(usdjpy),
            "US10Y": last_price(us10y),
            "VIX": last_price(vix),
            "DXY": last_price(dxy)
        }

    def analyze(self):
        data = self.get_market_data()
        prompt = f"""
أنت محلل ماكرو اقتصادي متخصص في زوج USDJPY.
البيانات الحالية:
- سعر USDJPY: {data['USDJPY']}
- عائد السندات الأمريكية 10 سنوات: {data['US10Y']}
- مؤشر VIX الخوف: {data['VIX']}
- مؤشر الدولار DXY: {data['DXY']}

بناءً على هذه البيانات:
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
                except: pass
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
5. Output valid HTML ONLY (inline styling is fine). No markdown wrappers. Make it elegant.
"""
        try:
            message = self.client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except Exception as e:
            return f"<h3>Error generating report: {e}</h3>"

if __name__ == "__main__":
    API_KEY = "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"

    analyzer = MacroAnalyzer(API_KEY)

    result = analyzer.analyze()

    print("Score:", result["score"])

    print("Bias:", result["bias"])

    print("السبب:", result["reason"])

    print("البيانات:", result["data"])

