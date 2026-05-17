# اقتراحات مفتوحة — قيد الدراسة

> آخر تحديث: 2026-05-17 (روتين صباحي — السبت)

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

### [1] ~~دقة الإغلاق الجزئي~~ — ✅ طُبّق 2026-05-17
- **الملف:** `risk/risk_manager.py:248`
- **طُبّق:** `math.floor(lots * self.partial_tp_ratio * 100) / 100`

### [2] ~~MT5 Connection Error Handling~~ — ✅ طُبّق 2026-05-17
- **الملف:** `execution/executor.py`
- **طُبّق:** أخطاء initialize/login/order_send تُسجَّل الآن بـ `_log.error()`

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

## 👁️ تحت المراقبة (جديدة — 2026-05-17)

### [6] Dead Code في executor.py Limit Order
- **الملف:** `execution/executor.py:286`
- **الملاحظة:** `ORDER_TYPE_BUY_LIMIT` تُعيَّن في السطر 286 ثم تُلغى بـ `ORDER_TYPE_BUY_STOP` في السطر 288
- **التأثير:** لا تأثير وظيفي — فقط مربك للقارئ
- **تاريخ الاكتشاف:** 2026-05-17
- **الحالة:** 🔍 للتنظيف عند أول Refactoring

### [7] import مكرر داخل Main Loop
- **الملف:** `main.py:620,676`
- **الملاحظة:** `timezone` مستورد مرتين داخل الـ while loop (620 كـ `timezone`، 676 كـ `_tz_fix`)
- **التأثير:** لا تأثير وظيفي — Python يخزّن modules في cache
- **تاريخ الاكتشاف:** 2026-05-17
- **الحالة:** 🔍 للتنظيف عند أول فرصة

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

### [E9] partial lots round → math.floor
- **طُبّق:** 2026-05-17 (روتين صباحي — السبت)
- **التفاصيل:** `risk_manager.py:248` — `round()` → `math.floor()` + إضافة `import math`
- **النتيجة:** الإغلاق الجزئي دائماً ≤ 50% بدلاً من التقريب للأعلى ✅

### [E10] MT5 أخطاء الاتصال تُسجَّل في logs
- **طُبّق:** 2026-05-17 (روتين صباحي — السبت)
- **التفاصيل:** `executor.py` — إضافة `_log = get_logger("executor")` + 6 print() → `_log.error/warning()`
- **النتيجة:** أخطاء MT5 الحرجة تظهر الآن في `errors_*.log` ✅
