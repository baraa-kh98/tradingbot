# اقتراحات مفتوحة — قيد الدراسة

> آخر تحديث: 2026-05-14 (روتين صباحي)

---

## 🟡 متوسطة الأولوية

### [5] Refactor run_bot(rm) — إصلاح كامل لحد الصفقات اليومية
- **الملف:** `main.py` (دالتا `run_bot()` والـ main loop)
- **المشكلة:** `rm = RiskManager()` داخل `run_bot()` ينشئ instance جديد كل 15 دقيقة → `daily_trades` يُصفَّر كل دورة → حد الـ 3 صفقات/يوم لا يعمل بين الدورات
- **الإصلاح المقترح:** نقل `rm` للخارج وتمريره كـ parameter
  ```python
  def run_bot(rm=None):  # يقبل rm خارجي
      if rm is None:
          rm = RiskManager(...)  # fallback
  # في main loop:
  rm = RiskManager(balance=BALANCE, risk_percent=RISK_PERCENT)
  ...run_bot(rm)
  ```
- **التأثير المتوقع:** حد الـ 3 صفقات/يوم يعمل فعلياً
- **تاريخ الاكتشاف:** 2026-05-14
- **الحالة:** ⏳ ينتظر الموافقة (تغيير متوسط الحجم)

---

## 🔵 منخفضة الأولوية (مراقبة)

### [1] دقة الإغلاق الجزئي
- **الملف:** `risk/risk_manager.py` السطر 247
- **المشكلة:** `round(lots * 0.5, 2)` → 0.5 × 0.03 = 0.015 → يُقرَّب لـ 0.02 (66% مش 50%)
- **الإصلاح المقترح:**
  ```python
  import math
  partial_lots = max(0.01, math.floor(lots * 0.5 * 100) / 100)
  ```
- **التأثير:** صغير — يؤثر فقط على lots صغيرة (0.01-0.05)
- **تاريخ الاكتشاف:** 2026-05-12
- **الحالة:** 🔍 تحت المراقبة

### [2] MT5 Connection Error Handling ضعيف
- **الملف:** `execution/executor.py:46`
- **المشكلة:** يكمل التنفيذ بعد فشل initialize مع رسائل خطأ مبهمة
- **التأثير:** يؤثر فقط عند مشاكل تثبيت MT5
- **تاريخ الاكتشاف:** 2026-05-05
- **الحالة:** 🔍 تحت المراقبة

### [3] إضافة "strategy" key لكل Signal Generator
- **الملفات:** `strategy/eurusd_signal.py`, `gbpusd_signal.py`, `xauusd_signal.py`, `london_signal.py`
- **المشكلة:** إشعار Telegram يعرض "Breakout" لكل الأزواج بدل الاسم الفعلي
- **الإصلاح:** إضافة `"strategy": "EURUSD NY Breakout"` إلخ. في كل dict إشارة
- **تاريخ الاكتشاف:** 2026-05-12
- **الحالة:** 🔍 تحت المراقبة

### [4] heartbeat يستخدم local time بدل UTC
- **الملف:** `main.py` السطر 659
- **المشكلة:** `_now_h = datetime.now().hour` — local time، إذا VPS في timezone مختلف الـ heartbeat يُرسل في وقت خاطئ
- **الإصلاح:** `_now_h = datetime.now(timezone.utc).hour`
- **تاريخ الاكتشاف:** 2026-05-12
- **الحالة:** ⏳ ينتظر تأكيد timezone الـ VPS

---

## ✅ مكتملة (للمرجع)

### [E1] datetime index vs column — EURUSD/GBPUSD
- **طُبّق:** 2026-05-12
- **النتيجة:** الزوجان بدآ يولّدان إشارات بشكل صحيح ✅

### [E2] Break-Even SELL — منطق معكوس
- **طُبّق:** v2.1.0 (2026-05-01)
- **النتيجة:** السطر 161 في risk_manager.py: `entry + offset` ✅

### [E3] قسمة على صفر في Position Sizing
- **طُبّق:** v2.1.0 (2026-05-01)
- **النتيجة:** guard في السطر 73-74: `if not entry or entry == 0: return 0.01` ✅

### [E4] ATR Defaults خاطئة
- **طُبّق:** v2.1.0 (2026-05-01)
- **النتيجة:** `_ATR_DEFAULTS` dict في trade_monitor.py ✅

### [E5] signal['asia_high'] KeyError — يمنع تنفيذ EURUSD/GBPUSD/XAUUSD
- **طُبّق:** 2026-05-12 (روتين صباحي)
- **النتيجة:** استخدام `.get()` مع conditional line في main.py:384 ✅

### [E6] LondonSignalGenerator غير مستوردة في cmd_analyze
- **طُبّق:** 2026-05-12 (روتين صباحي)
- **النتيجة:** استبدال بـ `get_strategy()` في main.py:523 ✅

### [E7] print() في trade_monitor — الأخطاء لا تُسجَّل
- **طُبّق:** 2026-05-12 (روتين صباحي)
- **النتيجة:** إضافة `get_logger` واستبدال print → logger في trade_monitor.py ✅
