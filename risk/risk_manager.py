class RiskManager:

    def __init__(self, balance=10000, risk_percent=1.0):
        self.balance = balance
        self.risk_percent = risk_percent

    def calculate_position_size(self, entry, stop_loss):
        risk_amount = self.balance * (self.risk_percent / 100)
        pips_at_risk = abs(entry - stop_loss)
        if pips_at_risk == 0:
            return 0
        position_size = round(risk_amount / pips_at_risk, 2)
        return position_size

    def calculate_rr(self, entry, stop_loss, take_profit):
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        if risk == 0:
            return 0
        return round(reward / risk, 2)

    def is_trade_valid(self, entry, stop_loss, take_profit, min_rr=1.5):
        rr = self.calculate_rr(entry, stop_loss, take_profit)
        return rr >= min_rr

    def get_trade_info(self, entry, stop_loss, take_profit):
        size = self.calculate_position_size(entry, stop_loss)
        rr = self.calculate_rr(entry, stop_loss, take_profit)
        valid = self.is_trade_valid(entry, stop_loss, take_profit)
        return {
            "position_size": size,
            "rr_ratio": rr,
            "trade_valid": valid,
            "risk_amount": round(self.balance * self.risk_percent / 100, 2)
        }


if __name__ == "__main__":
    rm = RiskManager(balance=10000, risk_percent=1.0)
    entry = 160.266
    stop_loss = 159.766
    take_profit = 161.266
    info = rm.get_trade_info(entry, stop_loss, take_profit)
    print("حجم الصفقة:", info["position_size"])
    print("نسبة المخاطرة للربح:", info["rr_ratio"])
    print("الصفقة صالحة:", info["trade_valid"])
    print("المبلغ المخاطر به:", info["risk_amount"])
