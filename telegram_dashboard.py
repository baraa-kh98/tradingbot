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
/fixes    — عرض خطة الإصلاح اليومية مع أزرار الموافقة
/approve  — تطبيق الإصلاحات (git pull)
/skip     — تجاهل خطة الإصلاح اليوم
/help     — قائمة الأوامر
/pause    — إيقاف التداول مؤقتاً
/resume   — استئناف التداول
"""

import threading
import time
import requests
import os
from datetime import datetime, timezone


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
        self._callback_handlers = {}

        # ── حالة خطة الإصلاح ──────────────────────────────────────
        self._plan_active = False          # True عندما يوجد خطة نشطة
        self._plan_content = ""            # محتوى الخطة
        self._chat_history = []            # تاريخ المحادثة مع Claude

        self._register_default_handlers()

    def _register_default_handlers(self):
        """تسجيل الأوامر الافتراضية"""
        self._handlers["help"]    = self._cmd_help
        self._handlers["start"]   = self._cmd_help
        self._handlers["status"]  = self._cmd_status
        self._handlers["pause"]   = self._cmd_pause
        self._handlers["resume"]  = self._cmd_resume
        self._handlers["fixes"]   = self._cmd_fixes
        self._handlers["approve"] = self._cmd_approve
        self._handlers["skip"]    = self._cmd_skip

        # Callback handlers for inline buttons
        self._callback_handlers["approve_plan"] = self._cb_approve_plan
        self._callback_handlers["skip_plan"]    = self._cb_skip_plan

    def register_handler(self, command, handler):
        """تسجيل معالج أمر جديد"""
        self._handlers[command] = handler

    # ═══════════════════════════════════════════════════════════
    # إرسال الرسائل
    # ═══════════════════════════════════════════════════════════

    def send(self, text, chat_id=None):
        """إرسال رسالة نصية"""
        try:
            max_len = 4000
            messages = [text[i:i+max_len] for i in range(0, len(text), max_len)]
            for msg in messages:
                requests.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": chat_id or self.chat_id,
                        "text": msg,
                        "parse_mode": "HTML",
                    },
                    timeout=10,
                )
        except Exception as e:
            print(f"⚠️ خطأ Telegram send: {e}")

    def send_with_keyboard(self, text, buttons, chat_id=None):
        """
        إرسال رسالة مع أزرار Inline Keyboard.
        buttons: list of rows, each row is a list of dicts:
          [[ {"text": "✅ تطبيق", "callback_data": "approve_plan"},
             {"text": "❌ تجاهل", "callback_data": "skip_plan"} ]]
        """
        try:
            requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": chat_id or self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": buttons},
                },
                timeout=10,
            )
        except Exception as e:
            print(f"⚠️ خطأ Telegram keyboard: {e}")

    def answer_callback_query(self, callback_query_id, text=""):
        """الرد على ضغطة زر (يزيل أيقونة التحميل)"""
        try:
            requests.post(
                f"{self.base_url}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
                timeout=5,
            )
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    # خطة الإصلاح
    # ═══════════════════════════════════════════════════════════

    def activate_fix_plan(self, plan_content: str):
        """
        إرسال خطة الإصلاح اليومية مع أزرار الموافقة.
        يُستدعى من main.py عند الساعة 07:00 UTC.
        """
        self._plan_active = True
        self._plan_content = plan_content
        self._chat_history = []

        # ── إرسال محتوى الخطة (مقسّم إذا كان طويلاً) ──────────
        header = "📋 <b>خطة الإصلاح اليومية — Claude Code Review</b>\n\n"
        preview = plan_content
        if len(preview) > 3500:
            preview = preview[:3500] + "\n\n... (اقرأ الخطة كاملة على GitHub)"

        self.send(header + f"<pre>{preview}</pre>")

        # ── أزرار الموافقة ──────────────────────────────────────
        self.send_with_keyboard(
            "🤔 ما رأيك؟ هل تريد تطبيق الإصلاحات؟\n"
            "أو أرسل رسالة نصية لمناقشة الخطة مع Claude.",
            [[
                {"text": "✅ تطبيق الإصلاحات",  "callback_data": "approve_plan"},
                {"text": "❌ تجاهل اليوم",       "callback_data": "skip_plan"},
            ]]
        )

    def _cmd_fixes(self, args=None):
        """عرض خطة الإصلاح اليومية"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        plan_path = os.path.join("reports", f"fix_plan_{today}.md")

        # جرّب أيضاً آخر خطة موجودة (في حال لم يتم توليد اليوم بعد)
        if not os.path.exists(plan_path):
            reports_dir = "reports"
            if os.path.exists(reports_dir):
                plans = sorted([
                    f for f in os.listdir(reports_dir)
                    if f.startswith("fix_plan_") and f.endswith(".md")
                ], reverse=True)
                if plans:
                    plan_path = os.path.join(reports_dir, plans[0])
                else:
                    return f"❌ لا يوجد خطة إصلاح متاحة لـ {today}"
            else:
                return f"❌ لا يوجد خطة إصلاح لـ {today}"

        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.activate_fix_plan(content)
            return None  # activate_fix_plan ترسل الرسالة مباشرة
        except Exception as e:
            return f"❌ خطأ في قراءة خطة الإصلاح: {e}"

    def _cmd_approve(self, args=None):
        """تطبيق الإصلاحات — git pull"""
        return self._cb_approve_plan()

    def _cmd_skip(self, args=None):
        """تجاهل خطة اليوم"""
        return self._cb_skip_plan()

    def _cb_approve_plan(self):
        """تنفيذ git pull لتطبيق الإصلاحات"""
        self._plan_active = False
        self._chat_history = []

        import subprocess
        try:
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                capture_output=True, text=True, timeout=30,
                encoding="utf-8"
            )
            if result.returncode == 0:
                output = result.stdout.strip()[-600:] if result.stdout else "لا مخرجات"
                return (
                    "✅ <b>تم سحب الإصلاحات بنجاح!</b>\n\n"
                    f"<code>{output}</code>\n\n"
                    "⚠️ <b>تحتاج لإعادة تشغيل البوت لتفعيل التغييرات:</b>\n"
                    "أغلق نافذة البوت الحالية وأعد تشغيل <code>run_bot.bat</code>"
                )
            else:
                err = result.stderr.strip()[-400:] if result.stderr else "خطأ غير معروف"
                return (
                    f"❌ <b>فشل git pull!</b>\n\n"
                    f"<code>{err}</code>\n\n"
                    "تحقق من اتصال الإنترنت واسم المستخدم على GitHub."
                )
        except subprocess.TimeoutExpired:
            return "❌ انتهى وقت انتظار git pull (30 ثانية). تحقق من الاتصال."
        except Exception as e:
            return f"❌ خطأ في تنفيذ git pull: {e}"

    def _cb_skip_plan(self):
        """تجاهل خطة الإصلاح"""
        self._plan_active = False
        self._chat_history = []
        return (
            "⏭️ <b>تم تجاهل خطة الإصلاح اليوم.</b>\n\n"
            "سيتم إرسال خطة جديدة غداً الساعة 07:00 UTC.\n"
            "لعرض الخطة مجدداً: /fixes"
        )

    def _chat_about_plan(self, user_message: str) -> str:
        """
        محادثة مع Claude حول خطة الإصلاح.
        يُستدعى عندما يرسل المستخدم رسالة نصية في حالة وجود خطة نشطة.
        """
        try:
            import anthropic
            try:
                from config import CLAUDE_API_KEY
            except ImportError:
                CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")

            if not CLAUDE_API_KEY:
                return (
                    "❌ CLAUDE_API_KEY غير متوفر.\n"
                    "استخدم /approve لتطبيق الخطة أو /skip لتجاهلها."
                )

            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

            system_prompt = (
                "أنت مراجع تقني خبير لبوت تداول Forex على MetaTrader 5. "
                "يسألك المستخدم عن خطة الإصلاح اليومية التي تم توليدها بمراجعة السجلات.\n\n"
                f"خطة الإصلاح:\n{self._plan_content}\n\n"
                "ناقش الإصلاحات مع المستخدم باللغة العربية. "
                "أجب بإيجاز (3-5 جمل). "
                "إذا طلب تعديلاً، اشرح التأثير التقني بوضوح. "
                "ذكّره باستخدام /approve للتطبيق أو /skip للتجاهل."
            )

            self._chat_history.append({"role": "user", "content": user_message})

            response = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=600,
                system=system_prompt,
                messages=self._chat_history,
            )

            reply = response.content[0].text
            self._chat_history.append({"role": "assistant", "content": reply})

            # حد أقصى 20 رسالة في التاريخ لتجنب overflow
            if len(self._chat_history) > 20:
                self._chat_history = self._chat_history[-20:]

            return reply

        except Exception as e:
            return (
                f"❌ خطأ في الدردشة مع Claude: {e}\n"
                "استخدم /approve لتطبيق الخطة أو /skip لتجاهلها."
            )

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
        """معالجة الرسائل الجديدة (رسائل نصية + ضغطات أزرار)"""
        updates = self._get_updates()
        for update in updates:
            self.last_update_id = update["update_id"]

            # ── معالجة ضغطة زر (callback_query) ──────────────────
            cb = update.get("callback_query")
            if cb:
                self._handle_callback(cb)
                continue

            # ── معالجة رسالة نصية ────────────────────────────────
            msg = update.get("message", {})
            text = msg.get("text", "").strip()
            from_chat = str(msg.get("chat", {}).get("id", ""))

            # فقط من الـ chat المعتمد
            if from_chat != self.chat_id:
                continue

            if not text:
                continue

            if text.startswith("/"):
                # أمر رسمي
                cmd = text.split()[0].replace("/", "").lower()
                args = text.split()[1:] if len(text.split()) > 1 else []
                self._handle_command(cmd, args)
            elif self._plan_active:
                # وضع المحادثة — ناقش خطة الإصلاح مع Claude
                self.send("⏳ جاري التفكير...")
                response = self._chat_about_plan(text)
                self.send(response)
            # else: رسالة عادية خارج وضع المحادثة — نتجاهلها

    def _handle_callback(self, cb):
        """معالجة ضغطة زر Inline"""
        cb_data = cb.get("data", "")
        cb_id   = cb.get("id", "")
        from_cb_chat = str(cb.get("message", {}).get("chat", {}).get("id", ""))

        if from_cb_chat != self.chat_id:
            return

        handler = self._callback_handlers.get(cb_data)
        if handler:
            try:
                self.answer_callback_query(cb_id, "⏳")
                response = handler()
                if response:
                    self.send(response)
            except Exception as e:
                self.answer_callback_query(cb_id, "❌")
                self.send(f"❌ خطأ في تنفيذ الأمر: {e}")
        else:
            self.answer_callback_query(cb_id, "❓ أمر غير معروف")

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
            "📰 /news — ذكاء السوق (أخبار + سنتيمنت)\n"
            "🌍 /scan — فحص جميع الأزواج\n"
            "⚙️ /pairs — الأزواج المفعّلة\n"
            "🧠 /optimize — تحسين المعاملات\n"
            "📚 /lessons — دروس الصفقات\n"
            "📋 /fixes — خطة الإصلاح اليومية\n"
            "✅ /approve — تطبيق الإصلاحات\n"
            "⏭️ /skip — تجاهل خطة اليوم\n"
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
        plan_icon = "📋 يوجد خطة نشطة — أرسل /fixes لعرضها" if self._plan_active else "✅ لا خطة نشطة"

        return (
            f"═══ 🤖 حالة البوت ═══\n\n"
            f"📡 الحالة: {status_icon}\n"
            f"🔄 الدورة: #{cycle}\n"
            f"⏰ آخر فحص: {last_scan}\n"
            f"📊 صفقات مفتوحة: {open_trades}\n"
            f"🌍 أزواج: {', '.join(self.bot_state.get('active_pairs', ['USDJPY']))}\n"
            f"🔧 الإصلاحات: {plan_icon}"
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

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        dash.stop_polling()
        print("👋 Dashboard توقف")
