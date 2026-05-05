"""
Logger — نظام التسجيل المركزي للبوت
======================================
يُنشئ 3 ملفات log يومياً في مجلد logs/:

  logs/bot_YYYY-MM-DD.log     ← كل شي (INFO + WARNING + ERROR)
  logs/errors_YYYY-MM-DD.log  ← الأخطاء فقط
  logs/trades_YYYY-MM-DD.log  ← الصفقات فقط

الاستخدام:
  from utils.logger import get_logger
  logger = get_logger(__name__)
  logger.info("رسالة معلومة")
  logger.warning("تحذير")
  logger.error("خطأ", exc_info=True)
"""

import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

# ── مجلد الـ logs ──────────────────────────────────────────────
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# ── تنسيق الرسائل ─────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── تنسيق الألوان للـ Console ─────────────────────────────────
COLORS = {
    "DEBUG":    "\033[36m",   # cyan
    "INFO":     "\033[32m",   # green
    "WARNING":  "\033[33m",   # yellow
    "ERROR":    "\033[31m",   # red
    "CRITICAL": "\033[35m",   # magenta
    "RESET":    "\033[0m",
}


class ColorFormatter(logging.Formatter):
    """Formatter ملون للـ Console"""
    def format(self, record):
        color = COLORS.get(record.levelname, COLORS["RESET"])
        reset = COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _get_file_handler(filename: str, level: int) -> TimedRotatingFileHandler:
    """Handler يُنشئ ملف جديد كل يوم"""
    path = os.path.join(LOGS_DIR, filename)
    handler = TimedRotatingFileHandler(
        path,
        when="midnight",
        interval=1,
        backupCount=30,      # احتفظ بـ 30 يوم
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    handler.suffix = "%Y-%m-%d"
    return handler


# ── إنشاء الـ root logger مرة واحدة ──────────────────────────
_initialized = False


def _enable_windows_ansi():
    """تفعيل ANSI colors في Windows CMD/PowerShell"""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass  # إذا فشل، الألوان ستظهر كـ escape codes بدون مشاكل في الملفات


def _setup_root_logger():
    global _initialized
    if _initialized:
        return
    _initialized = True

    # تفعيل ANSI على Windows أولاً
    _enable_windows_ansi()

    root = logging.getLogger("tradingbot")
    root.setLevel(logging.DEBUG)

    # 1. Console handler (ملون)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(ColorFormatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(console)

    # 2. ملف bot_YYYY-MM-DD.log (كل شي)
    root.addHandler(_get_file_handler(f"bot_{_today()}.log", logging.DEBUG))

    # 3. ملف errors_YYYY-MM-DD.log (أخطاء فقط)
    root.addHandler(_get_file_handler(f"errors_{_today()}.log", logging.ERROR))


def get_logger(name: str) -> logging.Logger:
    """
    اجلب logger للوحدة.

    مثال:
        logger = get_logger(__name__)
        logger.info("البوت بدأ")
    """
    _setup_root_logger()
    # استخدم tradingbot.name لكي يرث إعدادات الـ root
    logger_name = f"tradingbot.{name}" if not name.startswith("tradingbot") else name
    return logging.getLogger(logger_name)


# ── logger خاص بالصفقات ──────────────────────────────────────
def get_trade_logger() -> logging.Logger:
    """
    Logger خاص لتسجيل كل الصفقات في ملف منفصل.

    مثال:
        trade_log = get_trade_logger()
        trade_log.info("OPEN | USDJPY | BUY | entry=155.50 | sl=154.80 | tp=157.40")
    """
    _setup_root_logger()
    name = "tradingbot.trades"
    tl = logging.getLogger(name)

    if not tl.handlers:
        tl.addHandler(_get_file_handler(f"trades_{_today()}.log", logging.DEBUG))
        tl.propagate = True

    return tl
