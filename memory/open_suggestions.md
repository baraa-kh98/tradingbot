# اقتراحات مفتوحة — قيد الدراسة

> آخر تحديث: 2026-05-16 (روتين صباحي)

---

## 🟡 متوسطة الأولوية

### [4] XAUUSD Regime Check — Cache مفقود
- **الملف:** `strategy/xauusd_signal.py:126`
- **المشكلة:** `_regime_check()` تستدعي yfinance API في كل دورة (كل 15 دقيقة) بدون Cache
  - 24 طلب HTTP في جلسة NY واحدة
  - عند فشل API → fail-open (كل الصفقات مسموحة بدون فلتر)
- **الإصلاح المقترح:** إضافة `_regime_cache` مع TTL = 3600 ثانية
- **تاريخ الاكتشاف:** 2026-05-16
- **الحالة:** ⏳ ينتظر موافقة المستخدم (ملف استراتيجية)

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

### [5] CPI مُثبَّت يدوياً في XAUUSD
- **الملف:** `strategy/xauusd_signal.py:150`
- **المشكلة:** `estimated_cpi = 2.8` — قيمة ثابتة ستُصبح قديمة
- **الإصلاح المقترح:** جلب CPI من FRED API أو تحديثه يدوياً كل ربع سنة
- **تاريخ الاكتشاف:** 2026-05-16
- **الحالة:** 🔍 تحت المراقبة — أولوية منخفضة

### [3] إضافة "strategy" key لكل Signal Generator
- **الملفات:** `strategy/eurusd_signal.py`, `gbpusd_signal.py`, `xauusd_signal.py`, `london_signal.py`
- **المشكلة:** إشعار Telegram يعرض "Breakout" لكل الأزواج بدل الاسم الفعلي
- **الإصلاح:** إضافة `"strategy": "EURUSD NY Breakout"` إلخ. في كل dict إشارة
- **تاريخ الاكتشاف:** 2026-05-12
- **الحالة:** 🔍 تحت المراقبة

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

### [E8] datetime.now() Local Time بدل UTC في Main Loop
- **طُبّق:** 2026-05-15 (روتين صباحي)
- **التفاصيل:** 3 أسطر في main.py (620, 651, 663) تحوّلت لـ `datetime.now(timezone.utc)`
- **النتيجة:** daily reset و heartbeat و log push تعمل الآن بتوقيت UTC بغض النظر عن timezone الـ VPS ✅
