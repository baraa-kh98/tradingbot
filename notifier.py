"""
Notifier — إشعارات Telegram
==============================
يرسل رسائل للتيليغرام مع دعم:
  - رسائل عادية (info)
  - تحذيرات (warning)
  - أخطاء حرجة (error) — مع 🚨
  - إشعار crash — مع stack trace
"""

import requests
import traceback
from datetime import datetime


class Notifier:

    def __init__(self, token, chat_id):
        self.token   = token
        self.chat_id = str(chat_id)
        self.url     = f"https://api.telegram.org/bot{token}/sendMessage"

    def _send_raw(self, text: str, parse_mode: str = "HTML") -> bool:
        """إرسال رسالة خام — الدالة الأساسية"""
        # Telegram حد أقصى 4096 حرف
        if len(text) > 4000:
            text = text[:3990] + "\n... (مقطوع)"
        try:
            resp = requests.post(
                self.url,
                data={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode},
                timeout=10,
            )
            if resp.status_code == 200:
                return True
            else:
                print(f"[Notifier] خطأ Telegram {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"[Notifier] فشل الإرسال: {e}")
            return False

    def send(self, message: str) -> bool:
        """رسالة عادية"""
        return self._send_raw(message)

    def send_warning(self, message: str) -> bool:
        """تحذير — مع أيقونة"""
        return self._send_raw(f"⚠️ <b>تحذير</b>\n{message}")

    def send_error(self, message: str, exc: Exception = None) -> bool:
        """
        خطأ حرج — مع تفاصيل الاستثناء إذا موجود
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = f"🚨 <b>خطأ في البوت</b>\n━━━━━━━━━━━━━━━━━━\n🕐 {now}\n❌ {message}"
        if exc:
            tb = traceback.format_exc()
            # أرسل أول 500 حرف من الـ traceback
            short_tb = tb[-500:] if len(tb) > 500 else tb
            text += f"\n\n<pre>{short_tb}</pre>"
        return self._send_raw(text)

    def send_crash(self, error: str, cycle: int = None) -> bool:
        """
        إشعار crash — يُرسَل عند انهيار البوت
        auto-restart سيعيد تشغيله
        """
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cyc  = f" | الدورة #{cycle}" if cycle else ""
        text = (
            f"💥 <b>البوت انهار!</b>{cyc}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕐 {now}\n"
            f"❌ {error}\n"
            f"🔄 auto-restart جاري...\n"
            f"📋 راجع ملف logs/errors_*.log"
        )
        return self._send_raw(text)

    def send_startup(self, balance: float, pairs: list) -> bool:
        """إشعار بدء تشغيل البوت"""
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"🟢 <b>البوت اشتغل</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕐 {now}\n"
            f"💰 الرصيد: ${balance:,.2f}\n"
            f"📊 الأزواج: {', '.join(pairs)}"
        )
        return self._send_raw(text)

    def send_daily_summary(self, pnl: float, trades: int, win_rate: float) -> bool:
        """ملخص يومي"""
        emoji = "🟢" if pnl >= 0 else "🔴"
        now   = datetime.now().strftime("%Y-%m-%d")
        text  = (
            f"📅 <b>ملخص يوم {now}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{emoji} PnL: ${pnl:+.2f}\n"
            f"📊 الصفقات: {trades}\n"
            f"🎯 Win Rate: {win_rate:.0f}%"
        )
        return self._send_raw(text)


if __name__ == "__main__":
    from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    n = Notifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    n.send("✅ البوت شغال وجاهز للتداول")
