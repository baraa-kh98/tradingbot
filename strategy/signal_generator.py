"""
ICT Signal Generator — مولّد إشارات ICT

يجمع كل تحليلات ICT ويعطي إشارة تداول واحدة
بناءً على نظام نقاط الالتقاء (Confluence Scoring)
"""

from strategy.ict_core import run_full_ict_analysis
from strategy.ict_advanced import run_advanced_ict_analysis
from strategy.volatility import VolatilityAnalyzer
from strategy.order_flow import OrderFlowAnalyzer
from strategy.kill_zones import is_kill_zone, get_current_session
from config import (
    SWING_LOOKBACK,
    OB_BUFFER_PIPS,
    PIP_VALUE,
    MIN_CONFLUENCE_SCORE,
    KILL_ZONE_FILTER,
    MIN_RR_RATIO,
)


class ICTSignalGenerator:
    """
    مولّد إشارات ICT

    يستخدم نظام نقاط الالتقاء:
    - Market Structure (BOS/CHoCH): 25 نقطة
    - Order Block: 20 نقطة
    - Fair Value Gap: 15 نقطة
    - Breaker Block: 15 نقطة          ← جديد
    - Premium/Discount Zone: 15 نقطة
    - Liquidity Sweep: 15 نقطة
    - Silver Bullet: 10 نقاط           ← جديد
    - AMD Confirmation: 10 نقاط       ← جديد
    - Kill Zone: 10 نقطة
    - Inducement: 5 نقاط              ← جديد
    ──────────────────────
    المجموع: 140 نقطة

    الحد الأدنى للدخول: MIN_CONFLUENCE_SCORE (60 نقطة)
    """

    def __init__(self, htf_data, ltf_data=None):
        """
        htf_data: بيانات الإطار الزمني الأعلى (H1/H4) — لتحديد الاتجاه
        ltf_data: بيانات الإطار الزمني الأدنى (M15) — للدخول الدقيق
                  إذا None، يستخدم htf_data لكل شي
        """
        self.htf_data = htf_data
        self.ltf_data = ltf_data if ltf_data is not None else htf_data

        # تحليل HTF للاتجاه العام
        self.htf_analysis = run_full_ict_analysis(self.htf_data, SWING_LOOKBACK)

        # تحليل LTF للدخول
        self.ltf_analysis = run_full_ict_analysis(self.ltf_data, SWING_LOOKBACK)

        # تحليل متقدم
        self.advanced = run_advanced_ict_analysis(self.ltf_data, self.ltf_analysis)

        # تحليل التقلبات والأوردر فلو
        self.vol_analyzer = VolatilityAnalyzer(self.ltf_data)
        self.flow_analyzer = OrderFlowAnalyzer(self.ltf_data)

        # حالة الجلسة
        self.session = get_current_session()
        self.in_kill_zone, self.kz_name = is_kill_zone()

    def get_bias(self):
        """
        تحديد الاتجاه العام (HTF Bias) من Market Structure

        يعتمد على الإطار الزمني الأعلى فقط
        """
        structure = self.htf_analysis["structure"]
        trend = structure["trend"]
        last_event = structure.get("last_event")

        confidence = "LOW"
        if last_event:
            if "CHoCH" in last_event["type"]:
                confidence = "HIGH"  # تغيير طابع = إشارة قوية
            elif "BOS" in last_event["type"]:
                confidence = "MEDIUM"

        return {
            "direction": trend,
            "confidence": confidence,
            "last_event": last_event,
        }

    def _calculate_confluence(self, direction):
        """
        حساب نقاط الالتقاء لاتجاه معين

        direction: "BUY" أو "SELL"
        """
        score = 0
        reasons = []
        htf = self.htf_analysis
        ltf = self.ltf_analysis

        # ──────────────────────────────────────────────
        # 1. Market Structure (25 نقطة)
        # ──────────────────────────────────────────────
        structure = htf["structure"]
        last_event = structure.get("last_event")

        if direction == "BUY":
            if structure["trend"] == "BULLISH":
                score += 15
                reasons.append("📈 هيكل السوق صاعد (HTF)")
            if last_event and last_event["type"] in ("BOS_BULLISH", "CHoCH_BULLISH"):
                score += 10
                reasons.append(f"🔷 {last_event['type']}")
        else:  # SELL
            if structure["trend"] == "BEARISH":
                score += 15
                reasons.append("📉 هيكل السوق هابط (HTF)")
            if last_event and last_event["type"] in ("BOS_BEARISH", "CHoCH_BEARISH"):
                score += 10
                reasons.append(f"🔶 {last_event['type']}")

        # ──────────────────────────────────────────────
        # 2. Order Blocks (20 نقطة)
        # ──────────────────────────────────────────────
        obs = ltf["order_blocks"]
        close_vals = self.ltf_data["Close"].values if hasattr(self.ltf_data["Close"], 'values') else self.ltf_data["Close"].squeeze().values
        current_price = float(close_vals[-1])

        self._active_ob = None

        if direction == "BUY" and obs["bullish"]:
            # البحث عن OB قريب من السعر الحالي
            for ob in reversed(obs["bullish"]):
                if ob["bottom"] <= current_price <= ob["top"] * 1.002:
                    score += 20
                    reasons.append(f"🟢 السعر عند Bullish OB ({ob['bottom']:.3f}-{ob['top']:.3f})")
                    self._active_ob = ob
                    break
                elif current_price < ob["bottom"] and (ob["bottom"] - current_price) / current_price < 0.003:
                    score += 10
                    reasons.append(f"🟢 Bullish OB قريب ({ob['bottom']:.3f}-{ob['top']:.3f})")
                    self._active_ob = ob
                    break

        elif direction == "SELL" and obs["bearish"]:
            for ob in reversed(obs["bearish"]):
                if ob["bottom"] * 0.998 <= current_price <= ob["top"]:
                    score += 20
                    reasons.append(f"🔴 السعر عند Bearish OB ({ob['bottom']:.3f}-{ob['top']:.3f})")
                    self._active_ob = ob
                    break
                elif current_price > ob["top"] and (current_price - ob["top"]) / current_price < 0.003:
                    score += 10
                    reasons.append(f"🔴 Bearish OB قريب ({ob['bottom']:.3f}-{ob['top']:.3f})")
                    self._active_ob = ob
                    break

        # ──────────────────────────────────────────────
        # 3. Fair Value Gaps (15 نقطة)
        # ──────────────────────────────────────────────
        fvgs = ltf["fvgs"]
        self._active_fvg = None

        if direction == "BUY" and fvgs["bullish"]:
            for fvg in reversed(fvgs["bullish"]):
                if fvg["bottom"] <= current_price <= fvg["top"]:
                    score += 15
                    reasons.append(f"📊 السعر في Bullish FVG ({fvg['bottom']:.3f}-{fvg['top']:.3f})")
                    self._active_fvg = fvg
                    break
                elif current_price < fvg["bottom"] and (fvg["bottom"] - current_price) / current_price < 0.002:
                    score += 8
                    reasons.append(f"📊 Bullish FVG قريب ({fvg['bottom']:.3f})")
                    self._active_fvg = fvg
                    break

        elif direction == "SELL" and fvgs["bearish"]:
            for fvg in reversed(fvgs["bearish"]):
                if fvg["bottom"] <= current_price <= fvg["top"]:
                    score += 15
                    reasons.append(f"📊 السعر في Bearish FVG ({fvg['bottom']:.3f}-{fvg['top']:.3f})")
                    self._active_fvg = fvg
                    break
                elif current_price > fvg["top"] and (current_price - fvg["top"]) / current_price < 0.002:
                    score += 8
                    reasons.append(f"📊 Bearish FVG قريب ({fvg['top']:.3f})")
                    self._active_fvg = fvg
                    break

        # ──────────────────────────────────────────────
        # 4. Premium / Discount Zone (15 نقطة)
        # ──────────────────────────────────────────────
        pd_zones = ltf["pd_zones"]
        if pd_zones:
            if direction == "BUY" and pd_zones["zone"] == "DISCOUNT":
                score += 15
                reasons.append("💰 السعر في Discount Zone (شراء مثالي)")
                if pd_zones["in_buy_ote"]:
                    reasons.append("🎯 السعر في OTE Zone!")
            elif direction == "SELL" and pd_zones["zone"] == "PREMIUM":
                score += 15
                reasons.append("💰 السعر في Premium Zone (بيع مثالي)")
                if pd_zones["in_sell_ote"]:
                    reasons.append("🎯 السعر في OTE Zone!")

        # ──────────────────────────────────────────────
        # 5. Liquidity Sweep (15 نقطة)
        # ──────────────────────────────────────────────
        sweeps = ltf["sweeps"]
        if sweeps:
            recent_sweeps = [s for s in sweeps if s["index"] >= len(self.ltf_data) - 5]
            for sweep in recent_sweeps:
                if direction == "BUY" and sweep["type"] == "BULLISH_SWEEP":
                    score += 15
                    reasons.append(f"💧 اكتساح سيولة بيعية عند {sweep['level']:.3f}")
                    break
                elif direction == "SELL" and sweep["type"] == "BEARISH_SWEEP":
                    score += 15
                    reasons.append(f"💧 اكتساح سيولة شرائية عند {sweep['level']:.3f}")
                    break

        # ──────────────────────────────────────────────
        # 6. Kill Zone (10 نقاط)
        # ──────────────────────────────────────────────
        if self.in_kill_zone:
            score += 10
            kz_names = {"london": "لندن", "new_york": "نيويورك", "asian": "آسيا"}
            reasons.append(f"⏰ ضمن Kill Zone — {kz_names.get(self.kz_name, self.kz_name)}")

        # ──────────────────────────────────────────────
        # 7. Breaker Blocks (15 نقطة) — جديد
        # ──────────────────────────────────────────────
        breakers = self.advanced.get("breaker_blocks", {})
        self._active_breaker = None

        if direction == "BUY" and breakers.get("bullish"):
            for bb in reversed(breakers["bullish"]):
                if bb["bottom"] <= current_price <= bb["top"] * 1.002:
                    score += 15
                    reasons.append(f"🔄 السعر عند Bullish Breaker ({bb['bottom']:.3f}-{bb['top']:.3f})")
                    self._active_breaker = bb
                    break
        elif direction == "SELL" and breakers.get("bearish"):
            for bb in reversed(breakers["bearish"]):
                if bb["bottom"] * 0.998 <= current_price <= bb["top"]:
                    score += 15
                    reasons.append(f"🔄 السعر عند Bearish Breaker ({bb['bottom']:.3f}-{bb['top']:.3f})")
                    self._active_breaker = bb
                    break

        # ──────────────────────────────────────────────
        # 8. Silver Bullet (10 نقاط) — جديد
        # ──────────────────────────────────────────────
        sb = self.advanced.get("silver_bullet", {})
        if sb.get("active"):
            window_names = {
                "LONDON_SB": "لندن 🇬🇧",
                "NY_AM_SB": "نيويورك صباحاً 🇺🇸",
                "NY_PM_SB": "نيويورك مساءً 🇺🇸",
            }
            # إذا في FVG بنفس اتجاه الصفقة ضمن النافذة
            for fvg in sb.get("fvgs_in_window", []):
                if direction == "BUY" and fvg["direction"] == "BULLISH":
                    score += 10
                    reasons.append(f"🔫 Silver Bullet — {window_names.get(sb['window'], sb['window'])}")
                    break
                elif direction == "SELL" and fvg["direction"] == "BEARISH":
                    score += 10
                    reasons.append(f"🔫 Silver Bullet — {window_names.get(sb['window'], sb['window'])}")
                    break

        # ──────────────────────────────────────────────
        # 9. AMD Confirmation (10 نقاط) — جديد
        # ──────────────────────────────────────────────
        amd = self.advanced.get("amd", {})
        if amd.get("detected") and amd.get("bias"):
            if amd["bias"] == direction:
                score += 10
                reasons.append(f"📊 AMD يؤكد: {amd['phase']} → {amd['bias']}")
                if amd.get("distribution_move"):
                    reasons.append(f"   حركة التوزيع: {amd['distribution_move']} pips")
            elif amd["bias"] != "NEUTRAL":
                score -= 5
                reasons.append(f"⚠️ AMD يعارض: {amd['phase']} → {amd['bias']}")

        # ──────────────────────────────────────────────
        # 10. Inducement (5 نقاط)
        # ──────────────────────────────────────────────
        inducements = self.advanced.get("inducements", [])
        for ind in inducements:
            if direction == "BUY" and ind["type"] == "BULLISH_INDUCEMENT":
                score += 5
                reasons.append(f"🪤 Inducement bullish عند {ind['level']:.3f}")
                break
            elif direction == "SELL" and ind["type"] == "BEARISH_INDUCEMENT":
                score += 5
                reasons.append(f"🪤 Inducement bearish عند {ind['level']:.3f}")
                break

        # ──────────────────────────────────────────────
        # 11. Order Flow (10 نقاط) — جديد
        # ──────────────────────────────────────────────
        try:
            flow_bias, flow_score, flow_reasons = self.flow_analyzer.get_bias()
            if direction == "BUY" and flow_bias == "BULLISH":
                score += 10
                reasons.append(f"📊 Order Flow يؤكد شراء (Delta +{flow_score})")
            elif direction == "SELL" and flow_bias == "BEARISH":
                score += 10
                reasons.append(f"📊 Order Flow يؤكد بيع (Delta {flow_score})")

            # Divergence
            delta = self.flow_analyzer.estimate_delta()
            if delta.get("divergence"):
                if direction == "BUY" and delta["divergence_type"] == "BULLISH_DIV":
                    score += 5
                    reasons.append("🔄 Divergence صعودي في Order Flow")
                elif direction == "SELL" and delta["divergence_type"] == "BEARISH_DIV":
                    score += 5
                    reasons.append("🔄 Divergence هبوطي في Order Flow")
        except Exception:
            pass

        # ──────────────────────────────────────────────
        # 12. Volatility (5 نقاط أو -5) — جديد
        # ──────────────────────────────────────────────
        try:
            squeeze = self.vol_analyzer.detect_squeeze()
            if squeeze.get("squeeze") and squeeze["squeeze_bars"] >= 3:
                if direction == "BUY" and squeeze["momentum_bias"] == "BULLISH":
                    score += 5
                    reasons.append(f"🔋 Squeeze ({squeeze['squeeze_bars']} bars) → انفجار صعودي")
                elif direction == "SELL" and squeeze["momentum_bias"] == "BEARISH":
                    score += 5
                    reasons.append(f"🔋 Squeeze ({squeeze['squeeze_bars']} bars) → انفجار هبوطي")

            regime = self.vol_analyzer.get_volatility_regime()
            if regime["regime"] == "HIGH" and regime["ratio"] > 1.5:
                score -= 5
                reasons.append(f"⚠️ تقلبات عالية ({regime['ratio']}x) — حذر!")
        except Exception:
            pass

        return score, reasons

    def get_signal(self):
        """
        توليد إشارة التداول النهائية

        يحسب confluence لكل اتجاه ويختار الأقوى
        """
        bias = self.get_bias()

        # إذا kill zone filter مفعّل واحنا بره kill zone
        if KILL_ZONE_FILTER and not self.in_kill_zone:
            return {
                "action": "WAIT",
                "reason": "⏳ خارج Kill Zone — انتظر London أو New York",
                "confluence_score": 0,
                "session": self.session,
                "bias": bias,
                "details": [],
            }

        # حساب confluence لكل اتجاه
        buy_score, buy_reasons = self._calculate_confluence("BUY")
        sell_score, sell_reasons = self._calculate_confluence("SELL")

        # اختيار الاتجاه الأقوى المتوافق مع HTF bias
        if bias["direction"] == "BULLISH" and buy_score >= MIN_CONFLUENCE_SCORE:
            action = "BUY"
            score = buy_score
            reasons = buy_reasons
        elif bias["direction"] == "BEARISH" and sell_score >= MIN_CONFLUENCE_SCORE:
            action = "SELL"
            score = sell_score
            reasons = sell_reasons
        elif buy_score >= MIN_CONFLUENCE_SCORE and buy_score > sell_score:
            # حتى لو الـ bias محايد، إذا الالتقاء قوي جداً
            action = "BUY"
            score = buy_score
            reasons = buy_reasons
            reasons.append("⚠️ الدخول عكس HTF Bias — حذر!")
        elif sell_score >= MIN_CONFLUENCE_SCORE and sell_score > buy_score:
            action = "SELL"
            score = sell_score
            reasons = sell_reasons
            reasons.append("⚠️ الدخول عكس HTF Bias — حذر!")
        else:
            action = "WAIT"
            score = max(buy_score, sell_score)
            reasons = [f"📊 الالتقاء ضعيف: BUY={buy_score}, SELL={sell_score} (الحد الأدنى: {MIN_CONFLUENCE_SCORE})"]

        return {
            "action": action,
            "confluence_score": score,
            "bias": bias,
            "session": self.session,
            "details": reasons,
        }

    def get_levels(self):
        """
        تحديد مستويات الدخول ووقف الخسارة والهدف

        - Entry: عند Order Block أو FVG
        - Stop Loss: تحت/فوق OB + buffer
        - Take Profit: عند مستوى سيولة مقابل أو OB مقابل
        """
        signal = self.get_signal()
        close_vals = self.ltf_data["Close"].values if hasattr(self.ltf_data["Close"], 'values') else self.ltf_data["Close"].squeeze().values
        current_price = float(close_vals[-1])

        if signal["action"] == "WAIT":
            return None

        ltf = self.ltf_analysis
        liquidity = ltf["liquidity"]
        pd_zones = ltf["pd_zones"]
        ob_buffer = OB_BUFFER_PIPS * PIP_VALUE

        if signal["action"] == "BUY":
            # ── Entry ──
            entry = current_price
            if self._active_ob:
                # دخول عند midpoint الـ OB
                entry = round((self._active_ob["top"] + self._active_ob["bottom"]) / 2, 3)
            elif self._active_fvg:
                entry = round(self._active_fvg["midpoint"], 3)

            # ── Stop Loss ──
            if self._active_ob:
                stop_loss = round(self._active_ob["low"] - ob_buffer, 3)
            elif ltf["liquidity"]["swing_lows"]:
                stop_loss = round(min(ltf["liquidity"]["swing_lows"][-2:]) - ob_buffer, 3)
            else:
                stop_loss = round(current_price - 0.50, 3)

            # ── Take Profit ──
            # الهدف: أقرب مستوى سيولة فوق أو PDH
            tp_candidates = []
            if liquidity["pdh"] > current_price:
                tp_candidates.append(liquidity["pdh"])
            for sh in liquidity.get("swing_highs", []):
                if sh > current_price:
                    tp_candidates.append(sh)
            for eh in liquidity.get("equal_highs", []):
                if eh["price"] > current_price:
                    tp_candidates.append(eh["price"])

            if tp_candidates:
                take_profit = round(min(tp_candidates), 3)
            elif pd_zones and pd_zones["swing_high"] > current_price:
                take_profit = round(pd_zones["swing_high"], 3)
            else:
                take_profit = round(current_price + 1.00, 3)

        else:  # SELL
            # ── Entry ──
            entry = current_price
            if self._active_ob:
                entry = round((self._active_ob["top"] + self._active_ob["bottom"]) / 2, 3)
            elif self._active_fvg:
                entry = round(self._active_fvg["midpoint"], 3)

            # ── Stop Loss ──
            if self._active_ob:
                stop_loss = round(self._active_ob["high"] + ob_buffer, 3)
            elif ltf["liquidity"]["swing_highs"]:
                stop_loss = round(max(ltf["liquidity"]["swing_highs"][-2:]) + ob_buffer, 3)
            else:
                stop_loss = round(current_price + 0.50, 3)

            # ── Take Profit ──
            tp_candidates = []
            if liquidity["pdl"] < current_price:
                tp_candidates.append(liquidity["pdl"])
            for sl in liquidity.get("swing_lows", []):
                if sl < current_price:
                    tp_candidates.append(sl)
            for el in liquidity.get("equal_lows", []):
                if el["price"] < current_price:
                    tp_candidates.append(el["price"])

            if tp_candidates:
                take_profit = round(max(tp_candidates), 3)
            elif pd_zones and pd_zones["swing_low"] < current_price:
                take_profit = round(pd_zones["swing_low"], 3)
            else:
                take_profit = round(current_price - 1.00, 3)

        # التأكد من RR
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        rr = round(reward / risk, 2) if risk > 0 else 0

        # تعديل TP إذا RR ضعيف
        if rr < MIN_RR_RATIO and risk > 0:
            if signal["action"] == "BUY":
                take_profit = round(entry + risk * MIN_RR_RATIO, 3)
            else:
                take_profit = round(entry - risk * MIN_RR_RATIO, 3)
            rr = MIN_RR_RATIO

        return {
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rr_ratio": rr,
            "entry_type": "OB" if self._active_ob else ("FVG" if self._active_fvg else "MARKET"),
        }

    def get_full_report(self):
        """
        تقرير كامل عن الوضع الحالي — للإرسال عبر Telegram
        """
        signal = self.get_signal()
        levels = self.get_levels()
        bias = signal["bias"]

        report_lines = [
            "═══ تحليل ICT ═══",
            f"🔍 الاتجاه (HTF): {bias['direction']} ({bias['confidence']})",
            f"⏰ الجلسة: {self.session['session']} ({self.session['ny_time']})",
        ]

        if self.session["is_kill_zone"]:
            report_lines.append(f"🎯 Kill Zone: {self.session['kill_zone_name']}")

        report_lines.append(f"\n📊 الالتقاء: {signal['confluence_score']}/140")

        if signal["details"]:
            report_lines.append("\n── التفاصيل ──")
            for detail in signal["details"]:
                report_lines.append(detail)
        elif signal["action"] == "WAIT" and signal.get("reason"):
            report_lines.append(f"\n⚠️ {signal['reason']}")

        # تفاصيل متقدمة
        sb = self.advanced.get("silver_bullet", {})
        amd = self.advanced.get("amd", {})
        breakers = self.advanced.get("breaker_blocks", {})
        inducements = self.advanced.get("inducements", [])

        advanced_lines = []
        if sb.get("active"):
            advanced_lines.append(f"🔫 Silver Bullet: {sb['window']}")
        if amd.get("detected"):
            advanced_lines.append(f"📊 AMD: {amd['phase']} → {amd.get('bias', '?')}")
        bb_count = len(breakers.get('bullish', [])) + len(breakers.get('bearish', []))
        if bb_count > 0:
            advanced_lines.append(f"🔄 Breaker Blocks: {bb_count}")
        if inducements:
            advanced_lines.append(f"🪤 Inducements: {len(inducements)}")

        if advanced_lines:
            report_lines.append("\n── ICT متقدم ──")
            report_lines.extend(advanced_lines)

        # تقرير التقلبات والأوردر فلو
        try:
            report_lines.append("\n" + self.vol_analyzer.get_report())
        except Exception:
            pass
        try:
            report_lines.append("\n" + self.flow_analyzer.get_report())
        except Exception:
            pass

        report_lines.append(f"\n🎬 الإشارة: {signal['action']}")

        if levels:
            report_lines.extend([
                f"\n── مستويات الصفقة ──",
                f"📍 الدخول: {levels['entry']} ({levels['entry_type']})",
                f"🛑 وقف الخسارة: {levels['stop_loss']}",
                f"🎯 هدف الربح: {levels['take_profit']}",
                f"📐 RR: 1:{levels['rr_ratio']}",
            ])

        return "\n".join(report_lines)


# ══════════════════════════════════════════════════════════════

# للتوافق مع الكود القديم (optional)
class SignalGenerator(ICTSignalGenerator):
    """Backward compatibility wrapper"""

    def __init__(self, data):
        super().__init__(htf_data=data, ltf_data=data)

    def get_trend(self):
        bias = self.get_bias()
        return bias["direction"]


# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from data.data_feed import DataFeed

    feed = DataFeed()
    htf_data = feed.get_candles(period="60d", interval="1h")
    ltf_data = feed.get_candles(period="30d", interval="15m")

    signal_gen = ICTSignalGenerator(htf_data, ltf_data)
    print(signal_gen.get_full_report())
