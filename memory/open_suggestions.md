# اقتراحات مفتوحة — قيد الدراسة

> آخر تحديث: 2026-05-23 (روتين صباحي — السبت)

---

## 🟡 متوسطة الأولوية

### [4] XAUUSD — `_in_trade` check قبل `_regime_check()` *(2026-05-20، 4 أيام)*
- **الملف:** `strategy/xauusd_signal.py:185-188`
- **المشكلة:** `_regime_check()` تُستدعى قبل فحص `self._in_trade` → طلبان HTTP في كل دورة حتى عند وجود صفقة مفتوحة
- **الإصلاح المقترح:**
  ```python
  if self._in_trade:
      return None
  if not self._regime_check():
      return None
  ```
- **تاريخ الاكتشاف:** 2026-05-20
- **الحالة:** ⏳ ينتظر موافقة المستخدم (يُفضّل تطبيقه مع Cache #4b)

### [4b] XAUUSD Regime Check — Cache مفقود *(منذ 2026-05-16، 7 أيام — يوصى بالتطبيق اليوم السبت)*
- **الملف:** `strategy/xauusd_signal.py:126`
- **المشكلة:** `_regime_check()` تستدعي yfinance API في كل دورة (كل 15 دقيقة) بدون Cache
  - 24 طلب HTTP في جلسة NY واحدة
  - عند فشل API → fail-open (كل الصفقات مسموحة بدون فلتر)
- **الإصلاح المقترح:** إضافة `_regime_cache` مع TTL = 3600 ثانية
- **تاريخ الاكتشاف:** 2026-05-16
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**6 أيام** ← يُوصى بالتطبيق هذا الأسبوع)

---

## 🔵 منخفضة الأولوية

### [1] ~~دقة الإغلاق الجزئي~~ — ✅ طُبّق 2026-05-17
### [2] ~~MT5 Connection Error Handling~~ — ✅ طُبّق 2026-05-17
### [10] ~~SELL Break-Even Offset~~ — ✅ **طُبّق 2026-05-22**
- **الملف:** `risk/risk_manager.py:163`
- **الإصلاح:** `entry + offset` → `entry - offset` (SL تحت entry = ربح 2 pip عند الضرب)

### [3] إضافة "strategy" key لكل Signal Generator *(منذ 2026-05-12، 11 أيام)*
- **الملفات:** `strategy/eurusd_signal.py`, `gbpusd_signal.py`, `xauusd_signal.py`, `london_signal.py`
- **المشكلة:** إشعار Telegram يعرض "Breakout" لكل الأزواج بدل الاسم الفعلي
- **الإصلاح:** إضافة `"strategy": "EURUSD NY Breakout"` إلخ. في كل dict إشارة
- **تاريخ الاكتشاف:** 2026-05-12
- **الحالة:** ⏳ ينتظر موافقة المستخدم (10 أيام)

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

### [12] تأثير يوم الجمعة على الأداء *(2026-05-22، يوم واحد)*
- **الموضوع:** خطر Weekend Gap لأي صفقة مفتوحة بعد 15:00 UTC يوم الجمعة
- **الأزواج الأكثر تأثراً:** XAUUSD (Regime Filter قد يُبطئ الإشارات) + EURUSD/GBPUSD (TP بعيد للجلسة القصيرة)
- **متى نقرر؟:** بعد 4 أجمعة مراقبة أو 3 صفقات جمعة
- **الحالة:** 🔍 تحت المراقبة

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
