"""
Telegram Dashboard — لوحة تحكم عبر Telegram

أوامر متاحة:
/status   — حالة البوت والصفقات المفتوحة
/report   — تقرير الأداء
/scan     — فحص جميع الأزواج
/analyze  — تحليل ICT للزوج الحالي
/pairs    — عرض/تغيير الأزواج المفعّلة
/optimize — تحسين سريع للمعاملات
/lessons  — دروس من الصفقات السابقة
/help     — قائمة الأوامر
/pause    — إيقاف التداول مؤقتاً
/resume   — استئناف التداول
"""

import threading
import time
import requests
from datetime import datetime


class TelegramDashboard:
    """لوحة تحكم Telegram — تستقبل أوامر وتفاعلية"""

    def __init__(self, token, chat_id, bot_state=None):
        self.token = token
        self.chat_id = str(chat_id)
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.last_update_id = 0
        self.running = False
        self.bot_state = bot_state or {}
        self._handlers = {}
        self._register_default_handlers()

    def _register_default_handlers(self):
        """تسجيل الأوامر الافتراضية"""
        self._handlers["help"] = self._cmd_help
        self._handlers["start"] = self._cmd_help
        self._handlers["status"] = self._cmd_status
        self._handlers["pause"] = self._cmd_pause
        self._handlers["resume"] = self._cmd_resume

    def register_handler(self, command, handler):
        """تسجيل معالج أمر جديد"""
        self._handlers[command] = handler

    # ═══════════════════════════════════════════════════════════
    # إرسال الرسائل
    # ═══════════════════════════════════════════════════════════

    def send(self, text, chat_id=None):
        """إرسال رسالة"""
        try:
            # تقسيم الرسائل الطويلة
            max_len = 4000
            messages = [text[i:i+max_len] for i in range(0, len(text), max_len)]

            for msg in messages:
                requests.post(
                    f"{self.base_url}/sendMessage",
                    data={
                        "chat_id": chat_id or self.chat_id,
                        "text": msg,
                        "parse_mode": "HTML",
                    },
                    timeout=10,
                )
        except Exception as e:
            print(f"⚠️ خطأ Telegram: {e}")

    # ═══════════════════════════════════════════════════════════
    # استقبال الأوامر
    # ═══════════════════════════════════════════════════════════

    def _get_updates(self):
        """جلب الرسائل الجديدة"""
        try:
            resp = requests.get(
                f"{self.base_url}/getUpdates",
                params={"offset": self.last_update_id + 1, "timeout": 5},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("result", [])
        except Exception:
            pass
        return []

    def _process_updates(self):
        """معالجة الرسائل الجديدة"""
        updates = self._get_updates()
        for update in updates:
            self.last_update_id = update["update_id"]

            msg = update.get("message", {})
            text = msg.get("text", "").strip()
            from_chat = str(msg.get("chat", {}).get("id", ""))

            # فقط من الـ chat المعتمد
            if from_chat != self.chat_id:
                continue

            if text.startswith("/"):
                cmd = text.split()[0].replace("/", "").lower()
                args = text.split()[1:] if len(text.split()) > 1 else []
                self._handle_command(cmd, args)

    def _handle_command(self, cmd, args):
        """معالجة أمر"""
        handler = self._handlers.get(cmd)
        if handler:
            try:
                response = handler(args)
                if response:
                    self.send(response)
            except Exception as e:
                self.send(f"❌ خطأ: {e}")
        else:
            self.send(f"❓ أمر غير معروف: /{cmd}\nاكتب /help للمساعدة")

    # ═══════════════════════════════════════════════════════════
    # الأوامر الافتراضية
    # ═══════════════════════════════════════════════════════════

    def _cmd_help(self, args=None):
        return (
            "═══ 🤖 أوامر البوت ═══\n\n"
            "📊 /status — حالة البوت\n"
            "📈 /report — تقرير الأداء\n"
            "🔍 /analyze — تحليل ICT الآن\n"
            "🌍 /scan — فحص جميع الأزواج\n"
            "⚙️ /pairs — الأزواج المفعّلة\n"
            "🧠 /optimize — تحسين المعاملات\n"
            "📚 /lessons — دروس الصفقات\n"
            "⏸️ /pause — إيقاف مؤقت\n"
            "▶️ /resume — استئناف\n"
            "❓ /help — هذه القائمة"
        )

    def _cmd_status(self, args=None):
        paused = self.bot_state.get("paused", False)
        cycle = self.bot_state.get("cycle", 0)
        last_scan = self.bot_state.get("last_scan", "?")
        open_trades = self.bot_state.get("open_trades", 0)

        status_icon = "⏸️ متوقف" if paused else "🟢 شغّال"

        return (
            f"═══ 🤖 حالة البوت ═══\n\n"
            f"📡 الحالة: {status_icon}\n"
            f"🔄 الدورة: #{cycle}\n"
            f"⏰ آخر فحص: {last_scan}\n"
            f"📊 صفقات مفتوحة: {open_trades}\n"
            f"🌍 أزواج: {', '.join(self.bot_state.get('active_pairs', ['USDJPY']))}"
        )

    def _cmd_pause(self, args=None):
        self.bot_state["paused"] = True
        return "⏸️ تم إيقاف التداول مؤقتاً\nاكتب /resume للاستئناف"

    def _cmd_resume(self, args=None):
        self.bot_state["paused"] = False
        return "▶️ تم استئناف التداول!"

    # ═══════════════════════════════════════════════════════════
    # التشغيل في الخلفية
    # ═══════════════════════════════════════════════════════════

    def start_polling(self):
        """بدء استقبال الأوامر في thread منفصل"""
        self.running = True

        def poll_loop():
            while self.running:
                try:
                    self._process_updates()
                except Exception as e:
                    print(f"⚠️ Dashboard error: {e}")
                time.sleep(2)

        thread = threading.Thread(target=poll_loop, daemon=True)
        thread.start()
        print("📲 Telegram Dashboard بدأ الاستماع...")
        return thread

    def stop_polling(self):
        """إيقاف الاستماع"""
        self.running = False


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    dash = TelegramDashboard(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    dash.send("🤖 Dashboard يعمل! اكتب /help")
    dash.start_polling()

    # أبقى شغّال
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        dash.stop_polling()
        print("👋 Dashboard توقف")
