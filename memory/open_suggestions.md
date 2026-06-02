# اقتراحات مفتوحة — قيد الدراسة

> آخر تحديث: 2026-06-02 (روتين صباحي — الثلاثاء | أسبوع NFP | Factory Orders 14:00 UTC اليوم)

---

## 🟡 متوسطة الأولوية

### [4] XAUUSD — `_in_trade` check قبل `_regime_check()` *(2026-05-20، 17 أيام)* ⚡⚡⚡ ESCALATED CRITICAL — الأسواق مفتوحة الآن
- **الملف:** `strategy/xauusd_signal.py:186-191`
- **المشكلة:** `_regime_check()` تُستدعى قبل فحص `self._in_trade` → طلبان HTTP في كل دورة حتى عند وجود صفقة مفتوحة
- **الإصلاح المقترح:**
  ```python
  if self._in_trade:
      return None
  if not self._regime_check():
      return None
  ```
- **تاريخ الاكتشاف:** 2026-05-20
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**17 يوم** — الأسواق مفتوحة | طبّقه هذا الأسبوع)

### [4b] XAUUSD Regime Check — Cache مفقود *(منذ 2026-05-16، 17 يوم)* 🚨🚨🚨 CRITICAL — رقم قياسي مطلق — الأسواق مفتوحة الآن
- **الملف:** `strategy/xauusd_signal.py:129`
- **المشكلة:** `_regime_check()` تستدعي yfinance API في كل دورة (كل 15 دقيقة) بدون Cache
  - 24-96 طلب HTTP يومياً بدون داعٍ
  - عند فشل API → fail-open (كل الصفقات مسموحة بدون فلتر)
  - يُسبّب Dead Code Import (from datetime import timedelta) لا يُستخدم
- **الإصلاح المقترح:** إضافة `_regime_cache` مع TTL = 3600 ثانية + نقل المنطق لـ `_fetch_regime_live()`
- **تاريخ الاكتشاف:** 2026-05-16
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**17 يوم** ← الأسواق مفتوحة | أطول انتظار في كل السجل)

---

## 🔵 منخفضة الأولوية

### [1] ~~دقة الإغلاق الجزئي~~ — ✅ طُبّق 2026-05-17
### [2] ~~MT5 Connection Error Handling~~ — ✅ طُبّق 2026-05-17
### [10] ~~SELL Break-Even Offset~~ — ✅ **طُبّق 2026-05-22**
- **الملف:** `risk/risk_manager.py:163`
- **الإصلاح:** `entry + offset` → `entry - offset` (SL تحت entry = ربح 2 pip عند الضرب)

### [3] إضافة "strategy" key لكل Signal Generator *(منذ 2026-05-12، 21 يوم)* ← الأقدم في كل السجل
- **الملفات:** `strategy/eurusd_signal.py`, `gbpusd_signal.py`, `xauusd_signal.py`, `london_signal.py`
- **المشكلة:** إشعار Telegram يعرض "Breakout" لكل الأزواج بدل الاسم الفعلي
- **الإصلاح:** إضافة `"strategy": "EURUSD NY Breakout"` إلخ. في كل dict إشارة
- **تاريخ الاكتشاف:** 2026-05-12
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**21 يوم** ← **الأقدم في كل السجل**)

### [5] CPI مُثبَّت يدوياً في XAUUSD
- **الملف:** `strategy/xauusd_signal.py:150`
- **المشكلة:** `estimated_cpi = 2.8` — قيمة ثابتة ستُصبح قديمة
- **الإصلاح المقترح:** جلب CPI من FRED API أو تحديثه يدوياً كل ربع سنة
- **تاريخ الاكتشاف:** 2026-05-16
- **الحالة:** 🔍 تحت المراقبة — أولوية منخفضة

---

## 👁️ تحت المراقبة

### [11] XAUUSD — datetime.now() vs candle index للـ session filter *(2026-05-21)*
- **الملف:** `strategy/xauusd_signal.py:176-180`
- **خطورة:** منخفضة (live OK، backtest script على الأرجح يمتلك فلترة خاصة)
- **التوصية:** عند أي تعديل على `xauusd_backtest.py`، تحقق من أنه لا يستدعي `get_signal()` مباشرةً
- **الحالة:** 🔍 تحت المراقبة

### [17] Dead Code Import في xauusd_signal.py *(2026-05-30، جديد)*
- **الملف:** `strategy/xauusd_signal.py:133`
- **المشكلة:** `from datetime import datetime, timedelta` داخل `_regime_check()` — لا يُستخدم أبداً
- **الإصلاح:** حذف هذا السطر عند تطبيق Cache [4b]
- **الحالة:** 🔍 يُحل تلقائياً مع تطبيق [4b]

### [19] NFP — Non-Farm Payrolls *(2026-06-02، تحذير أسبوعي)*
- **الموضوع:** NFP الجمعة 5 يونيو 2026 | 12:30 UTC — أهم حدث شهري للدولار
- **الأزواج المتأثرة:** كل الأزواج — EURUSD/GBPUSD/XAUUSD/USDJPY
- **التوصية:** لا تدخل في EURUSD/GBPUSD في نافذة 13:00 UTC يوم الجمعة (NFP يصدر قبلها بـ 30 دقيقة)
- **ملاحظة XAUUSD:** إذا NFP ضعيف → VIX ترتفع → قد تُفعَّل إشارة XAUUSD
- **الحالة:** 🔴 تحذير أسبوعي — يُحذف بعد الجمعة 5 يونيو

### [20] Factory Orders (April 2026) — اليوم *(2026-06-02)*
- **الموضوع:** Factory Orders يصدر اليوم ~14:00 UTC — تأثير متوسط على USD في جلسة NY
- **الأزواج المتأثرة:** EURUSD/GBPUSD (NY Breakout 13:00-15:00)
- **التوصية:** إذا تزامنت الإشارة مع 14:00 UTC بدقائق → انتظر 15 دقيقة بعد الرقم
- **الحالة:** 🔍 تنبيه اليوم — يُحذف غداً

### [14] تأثير الأعياد الأمريكية على السيولة *(2026-05-25، 1 يوم)*
- **الموضوع:** US Memorial Day أمس — سيولة منخفضة في جلسة NY
- **الأزواج المتأثرة:** EURUSD/GBPUSD (NY Breakout 13:00-15:00) + XAUUSD
- **الملاحظة:** False breakouts أكثر شيوعاً في أيام السيولة المنخفضة
- **متى نقرر؟:** بعد 3-4 أيام أمريكية مغلقة للمقارنة
- **الحالة:** 🔍 تحت المراقبة

### [15] ما بعد Core PCE (صدر أمس 28 مايو) *(مراجعة 2026-05-29)*
- **الموضوع:** Core PCE Deflator صدر أمس 12:30 UTC — لا نعرف الرقم الفعلي من هذه البيئة
- **للتحقق على VPS:** هل VIX > 24 الآن؟ → هل XAUUSD Regime Filter مفعّل؟
- **إذا VIX > 24:** راقب XAUUSD في جلسة NY اليوم (13:00-16:00 UTC) — أول إشارة حقيقية محتملة
- **إذا VIX < 24:** XAUUSD يبقى محجوباً — ركّز على EURUSD/GBPUSD فقط اليوم
- **متى نقرر؟:** بعد مراقبة 3 جلسات NY متتالية مع VIX > 24
- **الحالة:** 🟡 مراقبة — تحقق من VPS اليوم

### [12] تأثير يوم الجمعة على الأداء *(2026-05-22)*
- **الموضوع:** خطر Weekend Gap لأي صفقة مفتوحة بعد 15:00 UTC يوم الجمعة
- **الأزواج الأكثر تأثراً:** XAUUSD > EURUSD/GBPUSD
- **الجمعة 29 مايو:** الجمعة الرابعة قيد المراقبة — تزامنت مع Month-End + Post-PCE
- **ملاحظة Month-End:** آخر يوم تداول في مايو → تدفقات مؤسسية قُرب 16:00 UTC → false breakouts محتملة
- **متى نقرر؟:** 4 أجمعة مراقبة اكتملت — **انتظر بيانات VPS لتحليل صفقات الجمعة قبل القرار**
- **الحالة:** 🔍 تحت المراقبة — 4 أجمعة مكتملة، ينتظر data من VPS

### [16] EURUSD/GBPUSD — Month-End Filter (فكرة جديدة) *(2026-05-29)*
- **الموضوع:** في آخر 2 يوم تداول من كل شهر، التدفقات المؤسسية (month-end rebalancing) تُشوّه إشارات NY Breakout
- **الفرضية:** تصفية الدخول في آخر يومَي التداول قد تُحسّن Sharpe لـ EURUSD/GBPUSD
- **الاختبار المقترح:** في backtest، فصل صفقات month-end عن بقية الشهر ومقارنة Sharpe
- **الأولوية:** منخفضة — تحتاج بيانات أولاً
- **تاريخ الاكتشاف:** 2026-05-29
- **الحالة:** 💡 فكرة قيد الدراسة — تحتاج backtest للتحقق

### [13] print() في connect()/disconnect() — executor.py *(مستمر)*
- **الملف:** `execution/executor.py:67-118`
- **الحالة:** 🔍 للـ Refactoring الشامل مستقبلاً

---

## ✅ مكتملة (للمرجع)

| # | المشكلة | التاريخ |
|---|---------|---------|
| E1 | datetime index vs column — EURUSD/GBPUSD | 2026-05-12 |
| E2 | Break-Even SELL — منطق معكوس (v1) | v2.1.0 (2026-05-01) |
| E3 | قسمة على صفر في Position Sizing | v2.1.0 (2026-05-01) |
| E4 | ATR Defaults خاطئة | v2.1.0 (2026-05-01) |
| E5 | signal['asia_high'] KeyError | 2026-05-12 |
| E6 | LondonSignalGenerator غير مستوردة | 2026-05-12 |
| E7 | print() في trade_monitor | 2026-05-12 |
| E8 | datetime.now() Local Time بدل UTC | 2026-05-15 |
| E9 | partial lots round → math.floor | 2026-05-17 |
| E10 | MT5 أخطاء الاتصال تُسجَّل في logs | 2026-05-17 |
| E11 | order validation print → logger | 2026-05-18 |
| E12 | Dead code BUY_LIMIT overwrite | 2026-05-18 |
| E13 | close/modify print → logger | 2026-05-19 |
| E14 | duplicate import داخل main loop | 2026-05-19 |
| **E15** | **SELL Break-Even: entry+offset → entry-offset (2 pip offset)** | **2026-05-22** |
| **E16** | **Exception logging في _regime_check() — xauusd_signal.py** | **2026-05-28** |
