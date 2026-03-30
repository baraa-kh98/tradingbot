import yfinance as yf
import pandas as pd
from backtesting import Backtest, Strategy
from backtesting.lib import crossover


def get_data():
    usdjpy = yf.download("USDJPY=X", period="6mo", interval="1h", auto_adjust=True)
    vix = yf.download("^VIX", period="6mo", interval="1h", auto_adjust=True)
    dxy = yf.download("DX-Y.NYB", period="6mo", interval="1h", auto_adjust=True)

    usdjpy.columns = [col[0] if isinstance(col, tuple) else col for col in usdjpy.columns]
    usdjpy = usdjpy[["Open", "High", "Low", "Close", "Volume"]].dropna()

    vix_close = vix["Close"].squeeze() if isinstance(vix["Close"], pd.DataFrame) else vix["Close"]
    dxy_close = dxy["Close"].squeeze() if isinstance(dxy["Close"], pd.DataFrame) else dxy["Close"]

    vix_close = vix_close.reindex(usdjpy.index, method="ffill")
    dxy_close = dxy_close.reindex(usdjpy.index, method="ffill")

    usdjpy["VIX"] = vix_close.values
    usdjpy["DXY"] = dxy_close.values
    usdjpy = usdjpy.dropna()

    return usdjpy


class MacroEMAStrategy(Strategy):

    ema_fast = 20
    ema_slow = 50
    vix_limit = 25

    def init(self):
        close = self.data.Close
        self.ema20 = self.I(lambda x: pd.Series(x).ewm(span=self.ema_fast).mean(), close)
        self.ema50 = self.I(lambda x: pd.Series(x).ewm(span=self.ema_slow).mean(), close)
        self.vix = self.I(lambda x: x, self.data.VIX)
        self.dxy = self.I(lambda x: x, self.data.DXY)

    def next(self):
        if len(self.data) < 6:
            return

        macro_bullish = self.vix[-1] < self.vix_limit and self.dxy[-1] > self.dxy[-5]
        macro_bearish = self.vix[-1] > self.vix_limit

        if crossover(self.ema20, self.ema50) and macro_bullish:
            self.buy(
                sl=self.data.Close[-1] - 0.5,
                tp=self.data.Close[-1] + 1.0
            )

        elif crossover(self.ema50, self.ema20) and macro_bearish:
            self.sell(
                sl=self.data.Close[-1] + 0.5,
                tp=self.data.Close[-1] - 1.0
            )


data = get_data()
bt = Backtest(data, MacroEMAStrategy, cash=10000, commission=0.0002)
results = bt.run()

print("النتائج مع فلتر الماكرو:")
print("عدد الصفقات:", results["# Trades"])
print("نسبة الربح:", round(results["Win Rate [%]"], 2), "%")
print("الربح الكلي:", round(results["Return [%]"], 2), "%")
print("أكبر خسارة:", round(results["Max. Drawdown [%]"], 2), "%")
print("نسبة شارب:", round(results["Sharpe Ratio"], 2))

bt.plot()
