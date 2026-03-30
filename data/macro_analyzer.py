import anthropic

import yfinance as yf

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

2. أعط score من -100 إلى +100 حيث:

   +100 = USD قوي جداً يجب الشراء

   -100 = JPY قوي جداً يجب البيع

   0 = محايد انتظر

أجب فقط بهذا الشكل:

SCORE: [الرقم]

BIAS: [BULLISH أو BEARISH أو NEUTRAL]

REASON: [سبب واحد مختصر]

"""

        message = self.client.messages.create(

            model="claude-opus-4-5",

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

                    score = int(line.replace("SCORE:", "").strip())

                except:

                    score = 0

            elif line.startswith("BIAS:"):

                bias = line.replace("BIAS:", "").strip()

            elif line.startswith("REASON:"):

                reason = line.replace("REASON:", "").strip()

        return {

            "score": score,

            "bias": bias,

            "reason": reason,

            "data": data

        }

if __name__ == "__main__":

    API_KEY = "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"

    analyzer = MacroAnalyzer(API_KEY)

    result = analyzer.analyze()

    print("Score:", result["score"])

    print("Bias:", result["bias"])

    print("السبب:", result["reason"])

    print("البيانات:", result["data"])

