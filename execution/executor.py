import oandapyV20
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.positions as positions


class Executor:

    def __init__(self, api_key, account_id, demo=True):
        env = "practice" if demo else "live"
        self.client = oandapyV20.API(access_token=api_key, environment=env)
        self.account_id = account_id

    def place_order(self, signal, units, stop_loss, take_profit):
        if signal == "BUY":
            trade_units = str(units)
        elif signal == "SELL":
            trade_units = str(-units)
        else:
            print("لا توجد اشارة صالحة")
            return None

        data = {
            "order": {
                "type": "MARKET",
                "instrument": "USD_JPY",
                "units": trade_units,
                "stopLossOnFill": {
                    "price": str(round(stop_loss, 3))
                },
                "takeProfitOnFill": {
                    "price": str(round(take_profit, 3))
                }
            }
        }

        request = orders.OrderCreate(self.account_id, data=data)
        response = self.client.request(request)
        print("تم فتح الصفقة:", response)
        return response

    def close_all(self):
        data = {"longUnits": "ALL", "shortUnits": "ALL"}
        request = positions.PositionClose(self.account_id, "USD_JPY", data=data)
        response = self.client.request(request)
        print("تم اغلاق كل الصفقات:", response)
        return response