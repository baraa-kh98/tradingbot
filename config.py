"""
إعدادات بوت التداول — ICT Strategy
يقرأ المفاتيح من ملف .env (آمن)
"""

import os
from dotenv import load_dotenv

# تحميل المتغيرات من .env
load_dotenv()

# ═══════════════════════════════════════════════════════════════
# API Keys & Accounts (من ملف .env)
# ═══════════════════════════════════════════════════════════════

# MetaTrader 5
MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

# Twelve Data
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")

# Claude AI
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# OANDA (قديم — اختياري)
OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")

# FRED (بيانات ماكرو تاريخية)
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# FinnHub (أخبار + تقويم اقتصادي)
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")


# ═══════════════════════════════════════════════════════════════
# Trading Pairs — أزواج متعددة
# ═══════════════════════════════════════════════════════════════

SYMBOL_MT5 = "USDJPY.BL"        # رمز الزوج على MT5 (الافتراضي)
SYMBOL_TD = "USD/JPY"           # رمز الزوج على Twelve Data
PIP_VALUE = 0.01                # قيمة النقطة لـ JPY pairs

# أزواج التداول المدعومة
TRADING_PAIRS = {
    "USDJPY": {
        "mt5": "USDJPY.BL",
        "td": "USD/JPY",
        "pip": 0.01,
        "spread_pips": 1.5,
        "enabled": True,
    },
    "EURUSD": {
        "mt5": "EURUSD.BL",
        "td": "EUR/USD",
        "pip": 0.0001,
        "spread_pips": 1.2,
        "enabled": False,
    },
    "GBPUSD": {
        "mt5": "GBPUSD.BL",
        "td": "GBP/USD",
        "pip": 0.0001,
        "spread_pips": 1.8,
        "enabled": False,
    },
    "XAUUSD": {
        "mt5": "XAUUSD.BL",
        "td": "XAU/USD",
        "pip": 0.01,
        "spread_pips": 3.0,
        "enabled": False,
    },
}

# الأزواج المفعّلة
ACTIVE_PAIRS = [k for k, v in TRADING_PAIRS.items() if v["enabled"]]

# ═══════════════════════════════════════════════════════════════
# Timeframes (Multi-Timeframe Analysis)
# ═══════════════════════════════════════════════════════════════

# Twelve Data timeframe format
HTF_INTERVAL = "1h"             # Higher Timeframe — لتحديد الاتجاه العام
HTF_PERIOD_DAYS = 180           # 6 أشهر من البيانات

LTF_INTERVAL = "15min"          # Lower Timeframe — للدخول الدقيق
LTF_PERIOD_DAYS = 60            # شهرين من البيانات

# للباكتست (فترات طويلة)
BACKTEST_INTERVAL = "1h"
BACKTEST_PERIOD_DAYS = 730      # سنتين

# ═══════════════════════════════════════════════════════════════
# ICT Parameters
# ═══════════════════════════════════════════════════════════════

# Swing Points
SWING_LOOKBACK = 5              # عدد الشموع لتحديد Swing High/Low

# Order Blocks
OB_DISPLACEMENT_MULTIPLIER = 1.5
OB_MAX_AGE = 50
OB_BUFFER_PIPS = 10

# Fair Value Gaps
FVG_MIN_SIZE_PIPS = 5
FVG_MAX_AGE = 30

# Liquidity
LIQ_EQUAL_THRESHOLD = 0.05
LIQ_SWEEP_PIPS = 5

# Premium/Discount & OTE
OTE_FIB_LOW = 0.62
OTE_FIB_HIGH = 0.79

# ═══════════════════════════════════════════════════════════════
# Risk Management
# ═══════════════════════════════════════════════════════════════

BALANCE = 10000
RISK_PERCENT = 1.0
MIN_RR_RATIO = 2.0
MIN_CONFLUENCE_SCORE = 60

# ═══════════════════════════════════════════════════════════════
# Macro Filter (اختياري)
# ═══════════════════════════════════════════════════════════════

USE_MACRO_FILTER = True
MACRO_MIN_SCORE = 20

# ═══════════════════════════════════════════════════════════════
# Kill Zones (بتوقيت EST / New York)
# ═══════════════════════════════════════════════════════════════

KILL_ZONES = {
    "asian":    {"start": "20:00", "end": "00:00"},
    "london":   {"start": "02:00", "end": "05:00"},
    "new_york": {"start": "07:00", "end": "10:00"},
}

KILL_ZONE_FILTER = True

# ═══════════════════════════════════════════════════════════════
# MT5 Settings
# ═══════════════════════════════════════════════════════════════

MT5_MAGIC_NUMBER = 123456       # رقم تعريف صفقات البوت
MT5_DEVIATION = 20              # أقصى انزلاق سعري مسموح (بالنقاط)
MT5_LOT_MIN = 0.01              # أقل حجم لوت
