"""
Multi-Pair Scanner — فاحص أزواج متعددة

يفحص كل الأزواج المفعّلة ويختار أفضل فرصة
مع فلتر ارتباط لمنع التداول بأزواج متعلقة
"""

from data.data_feed import DataFeed
from strategy.signal_generator import ICTSignalGenerator
from config import TRADING_PAIRS, ACTIVE_PAIRS, SWING_LOOKBACK


# أزواج مرتبطة — لا نتداولها مع بعض
CORRELATED_GROUPS = [
    {"EURUSD", "GBPUSD"},        # عملات أوروبية
]


class MultiPairScanner:
    """فاحص أزواج متعددة — يختار أفضل فرصة"""

    def __init__(self, active_pairs=None):
        self.pairs = active_pairs or ACTIVE_PAIRS
        self.results = {}

    def scan_all(self):
        """فحص كل الأزواج المفعّلة"""
        self.results = {}

        for pair_name in self.pairs:
            pair_config = TRADING_PAIRS.get(pair_name)
            if not pair_config:
                continue

            print(f"\n📊 فحص {pair_name}...")

            try:
                feed = DataFeed(
                    symbol_td=pair_config["td"],
                    pip_value=pair_config["pip"],
                )

                htf = feed.get_htf_data()
                ltf = feed.get_ltf_data()

                if htf is None:
                    print(f"  ❌ فشل جلب بيانات {pair_name}")
                    continue

                gen = ICTSignalGenerator(htf, ltf)
                signal = gen.get_signal()
                levels = gen.get_levels()

                self.results[pair_name] = {
                    "signal": signal,
                    "levels": levels,
                    "config": pair_config,
                    "report": gen.get_full_report(),
                }

                action = signal["action"]
                score = signal["confluence_score"]
                icon = "🟢" if action in ("BUY", "SELL") else "⏳"
                print(f"  {icon} {pair_name}: {action} ({score}/140)")

            except Exception as e:
                print(f"  ❌ خطأ في {pair_name}: {e}")

        return self.results

    def get_best_opportunity(self, open_pairs=None):
        """
        اختيار أفضل فرصة مع فلتر الارتباط

        open_pairs: أزواج مفتوحة حالياً (لمنع الارتباط)
        """
        if not self.results:
            self.scan_all()

        open_pairs = set(open_pairs or [])

        # فلتر: فقط الإشارات الفعّالة  
        candidates = []
        for pair_name, data in self.results.items():
            signal = data["signal"]
            if signal["action"] in ("BUY", "SELL"):
                candidates.append({
                    "pair": pair_name,
                    "action": signal["action"],
                    "score": signal["confluence_score"],
                    "levels": data["levels"],
                    "config": data["config"],
                })

        if not candidates:
            return None

        # ترتيب حسب الالتقاء
        candidates.sort(key=lambda c: c["score"], reverse=True)

        # فلتر الارتباط
        for candidate in candidates:
            pair = candidate["pair"]

            # تحقق إذا مرتبط بزوج مفتوح
            is_correlated = False
            for group in CORRELATED_GROUPS:
                if pair in group and group & open_pairs:
                    is_correlated = True
                    break

            if not is_correlated:
                return candidate

        return None

    def get_report(self):
        """تقرير شامل لكل الأزواج"""
        if not self.results:
            return "⚠️ لم يتم الفحص بعد"

        lines = ["═══ 🌍 فحص أزواج متعددة ═══\n"]

        for pair_name, data in self.results.items():
            signal = data["signal"]
            levels = data["levels"]
            score = signal["confluence_score"]

            icon = "🟢" if signal["action"] in ("BUY", "SELL") else "⏳"
            lines.append(f"{icon} {pair_name}: {signal['action']} ({score}/140)")

            if levels:
                lines.append(f"   📍 Entry: {levels['entry']} | SL: {levels['stop_loss']} | TP: {levels['take_profit']}")
                lines.append(f"   📐 RR: 1:{levels['rr_ratio']}")

            lines.append("")

        # أفضل فرصة
        best = self.get_best_opportunity()
        if best:
            lines.extend([
                "── أفضل فرصة ──",
                f"🏆 {best['pair']}: {best['action']} ({best['score']}/140)",
            ])
        else:
            lines.append("⏳ لا توجد فرص حالياً")

        return "\n".join(lines)


class DataFeed:
    """DataFeed مع دعم أزواج مختلفة"""

    def __init__(self, symbol_td=None, pip_value=None):
        from data.data_feed import DataFeed as OriginalFeed
        self._feed = OriginalFeed(symbol=symbol_td)
        self._symbol_td = symbol_td
        self._pip_value = pip_value

    def get_htf_data(self):
        if self._symbol_td:
            from config import HTF_INTERVAL, HTF_PERIOD_DAYS
            return self._feed.get_candles(
                interval=HTF_INTERVAL,
                period_days=HTF_PERIOD_DAYS,
            )
        return self._feed.get_htf_data()

    def get_ltf_data(self):
        if self._symbol_td:
            from config import LTF_INTERVAL, LTF_PERIOD_DAYS
            return self._feed.get_candles(
                interval=LTF_INTERVAL,
                period_days=LTF_PERIOD_DAYS,
            )
        return self._feed.get_ltf_data()


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    scanner = MultiPairScanner()
    scanner.scan_all()
    print(f"\n{scanner.get_report()}")
