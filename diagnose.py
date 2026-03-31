"""
سكربت تشخيص — شغّله على الـ VPS لتحديد مشاكل الاتصال

python diagnose.py
"""

import sys
import os

print("═" * 50)
print("   🔍 تشخيص بوت ICT Trading")
print("═" * 50)

# ─── 1. Python ───
print(f"\n✅ Python: {sys.version}")
print(f"   المسار: {sys.executable}")
print(f"   النظام: {sys.platform}")

# ─── 2. المكتبات ───
print("\n── المكتبات ──")
libs = ["pandas", "numpy", "dotenv", "twelvedata", "yfinance",
        "MetaTrader5", "requests", "anthropic", "backtesting"]
for lib in libs:
    try:
        mod = __import__(lib)
        ver = getattr(mod, "__version__", "OK")
        print(f"   ✅ {lib}: {ver}")
    except ImportError:
        print(f"   ❌ {lib}: مش مثبّت!")

# ─── 3. ملف .env ───
print("\n── ملف .env ──")
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    print(f"   ✅ موجود: {env_path}")
    from dotenv import load_dotenv
    load_dotenv(env_path)

    keys = ["MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER",
            "TWELVE_DATA_API_KEY", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]
    for key in keys:
        val = os.getenv(key, "")
        if val and val not in ["0", ""]:
            masked = val[:4] + "***" if len(val) > 4 else "***"
            print(f"   ✅ {key}: {masked}")
        else:
            print(f"   ❌ {key}: فارغ!")
else:
    print(f"   ❌ ملف .env مش موجود!")

# ─── 4. MetaTrader 5 ───
print("\n── MetaTrader 5 ──")
try:
    import MetaTrader5 as mt5

    # محاولة 1: بدون مسار
    print("   جاري التهيئة...")
    result = mt5.initialize()
    print(f"   initialize(): {result}")

    if not result:
        error = mt5.last_error()
        print(f"   ❌ خطأ: {error}")

        # محاولة 2: مع مسارات شائعة
        paths = [
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
            r"C:\Program Files\BabilFinancial MT5\terminal64.exe",
            r"C:\Program Files (x86)\BabilFinancial MT5\terminal64.exe",
        ]

        # البحث عن terminal64.exe
        print("\n   🔍 البحث عن MT5...")
        for drive in ["C:", "D:"]:
            for root_dir in [f"{drive}\\Program Files", f"{drive}\\Program Files (x86)"]:
                if os.path.exists(root_dir):
                    for folder in os.listdir(root_dir):
                        check = os.path.join(root_dir, folder, "terminal64.exe")
                        if os.path.exists(check):
                            paths.insert(0, check)
                            print(f"   📍 وجدت: {check}")

        for path in paths:
            if os.path.exists(path):
                print(f"\n   جاري التهيئة مع: {path}")
                result = mt5.initialize(path=path)
                print(f"   initialize(): {result}")
                if result:
                    break
                else:
                    print(f"   ❌ {mt5.last_error()}")

    if result:
        # معلومات الحساب
        account = mt5.account_info()
        if account:
            print(f"\n   ✅ متصل!")
            print(f"   السيرفر: {account.server}")
            print(f"   الحساب: {account.login}")
            print(f"   الرصيد: ${account.balance}")
            print(f"   النوع: {'Demo' if account.trade_mode == 0 else 'Contest' if account.trade_mode == 1 else 'Real'}")

            # اختبار الرمز
            sym = mt5.symbol_info("USDJPY.BL")
            if sym:
                print(f"\n   ✅ USDJPY.BL: Bid={sym.bid} Ask={sym.ask}")
            else:
                print(f"\n   ❌ USDJPY.BL مش موجود!")
                # عرض الرموز المتاحة
                symbols = mt5.symbols_get()
                if symbols:
                    usd_syms = [s.name for s in symbols if "USD" in s.name and "JPY" in s.name]
                    print(f"   رموز USDJPY المتاحة: {usd_syms}")
        else:
            print(f"   ❌ فشل جلب معلومات الحساب")

        # تسجيل الدخول
        login = int(os.getenv("MT5_LOGIN", "0"))
        password = os.getenv("MT5_PASSWORD", "")
        server = os.getenv("MT5_SERVER", "")
        if login and password and server:
            print(f"\n   جاري تسجيل الدخول: {login}@{server}")
            auth = mt5.login(login=login, password=password, server=server)
            print(f"   login(): {auth}")
            if not auth:
                print(f"   ❌ {mt5.last_error()}")

        mt5.shutdown()
    else:
        print("\n   ❌ MT5 مش شغّال أو مش موجود!")
        print("   💡 تأكد إن:")
        print("      1. برنامج MT5 مفتوح")
        print("      2. شغّل CMD كـ Administrator")
        print("      3. MT5 و Python بنفس الصلاحيات")

except ImportError:
    print("   ❌ MetaTrader5 مش مثبّت: pip install MetaTrader5")

# ─── 5. Telegram ───
print("\n── Telegram ──")
try:
    import requests
    token = os.getenv("TELEGRAM_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if token:
        r = requests.post(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
        data = r.json()
        if data.get("ok"):
            print(f"   ✅ البوت: @{data['result']['username']}")
        else:
            print(f"   ❌ التوكن غلط: {data}")

        if chat_id:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": "🔍 اختبار تشخيصي — البوت شغّال!"},
                timeout=5
            )
            if r.json().get("ok"):
                print(f"   ✅ Chat ID: {chat_id} — تم إرسال رسالة تجريبية")
            else:
                print(f"   ❌ Chat ID غلط: {r.json()}")
    else:
        print("   ❌ TELEGRAM_TOKEN فارغ")
except Exception as e:
    print(f"   ❌ خطأ: {e}")

# ─── 6. Twelve Data ───
print("\n── Twelve Data ──")
try:
    td_key = os.getenv("TWELVE_DATA_API_KEY", "")
    if td_key and td_key != "your_twelvedata_api_key_here":
        from twelvedata import TDClient
        td = TDClient(apikey=td_key)
        ts = td.time_series(symbol="USD/JPY", interval="1h", outputsize=5)
        data = ts.as_pandas()
        if data is not None and len(data) > 0:
            print(f"   ✅ Twelve Data يعمل! جلب {len(data)} شموع")
        else:
            print(f"   ❌ Twelve Data رجع بيانات فاضية")
    else:
        print("   ⚠️ API Key مش محطوط — سيستخدم yfinance")
except Exception as e:
    print(f"   ❌ خطأ: {e}")

print("\n" + "═" * 50)
print("   ✅ انتهى التشخيص")
print("═" * 50)
