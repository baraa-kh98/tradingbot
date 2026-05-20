# اقتراحات مفتوحة — قيد الدراسة

> آخر تحديث: 2026-05-20 (روتين صباحي — الأربعاء)

---

## 🟡 متوسطة الأولوية

### [4] XAUUSD — `_in_trade` check قبل `_regime_check()` *(جديد 2026-05-20)*
- **الملف:** `strategy/xauusd_signal.py:185-188`
- **المشكلة:** `_regime_check()` تُستدعى قبل فحص `self._in_trade` → طلبان HTTP في كل دورة حتى عند وجود صفقة مفتوحة
- **الإصلاح المقترح:**
  ```python
  # قبل _regime_check:
  if self._in_trade:
      return None
  if not self._regime_check():
      return None
  ```
- **تاريخ الاكتشاف:** 2026-05-20
- **الحالة:** ⏳ ينتظر موافقة المستخدم (يُفضّل تطبيقه مع Cache #4b)

### [4b] XAUUSD Regime Check — Cache مفقود *(منذ 2026-05-16، 4 أيام)*
- **الملف:** `strategy/xauusd_signal.py:126`
- **المشكلة:** `_regime_check()` تستدعي yfinance API في كل دورة (كل 15 دقيقة) بدون Cache
  - 24 طلب HTTP في جلسة NY واحدة
  - عند فشل API → fail-open (كل الصفقات مسموحة بدون فلتر)
- **الإصلاح المقترح:** إضافة `_regime_cache` مع TTL = 3600 ثانية
- **تاريخ الاكتشاف:** 2026-05-16
- **الحالة:** ⏳ ينتظر موافقة المستخدم (4 أيام)

---

## 🔵 منخفضة الأولوية

### [1] ~~دقة الإغلاق الجزئي~~ — ✅ طُبّق 2026-05-17
- **الملف:** `risk/risk_manager.py:248`
- **طُبّق:** `math.floor(lots * self.partial_tp_ratio * 100) / 100`

### [2] ~~MT5 Connection Error Handling~~ — ✅ طُبّق 2026-05-17
- **الملف:** `execution/executor.py`
- **طُبّق:** أخطاء initialize/login/order_send تُسجَّل الآن بـ `_log.error()`

### [3] إضافة "strategy" key لكل Signal Generator *(منذ 2026-05-12، 8 أيام)*
- **الملفات:** `strategy/eurusd_signal.py`, `gbpusd_signal.py`, `xauusd_signal.py`, `london_signal.py`
- **المشكلة:** إشعار Telegram يعرض "Breakout" لكل الأزواج بدل الاسم الفعلي
- **الإصلاح:** إضافة `"strategy": "EURUSD NY Breakout"` إلخ. في كل dict إشارة
- **تاريخ الاكتشاف:** 2026-05-12
- **الحالة:** 🔍 تحت المراقبة

### [5] CPI مُثبَّت يدوياً في XAUUSD
- **الملف:** `strategy/xauusd_signal.py:150`
- **المشكلة:** `estimated_cpi = 2.8` — قيمة ثابتة ستُصبح قديمة
- **الإصلاح المقترح:** جلب CPI من FRED API أو تحديثه يدوياً كل ربع سنة
- **تاريخ الاكتشاف:** 2026-05-16
- **الحالة:** 🔍 تحت المراقبة — أولوية منخفضة

### [10] SELL Break-Even Offset *(جديد 2026-05-20)*
- **الملف:** `risk/risk_manager.py:163`
- **المشكلة:** `new_sl = round(entry + offset, 3)` للـ SELL يضع SL فوق entry بـ 2 pips
  - عند ضرب SL: تُغلق الصفقة بخسارة 2 pip بدل التعادل الحقيقي
  - الأصح: `new_sl = round(entry - offset, 3)` → SL تحت entry بـ 2 pips → ربح 2 pip عند الضرب
- **ملاحظة:** الوضع الحالي أفضل من الوضع قبل v2.1.0 — هذا تحسين نظري فقط
- **تاريخ الاكتشاف:** 2026-05-20
- **الحالة:** ⏳ ينتظر موافقة المستخدم (منخفضة)

---

## 👁️ تحت المراقبة (مكتملة)

### [6] ~~Dead Code في executor.py Limit Order~~ — ✅ طُبّق 2026-05-18
### [7] ~~import مكرر داخل Main Loop~~ — ✅ طُبّق 2026-05-19
### [8] ~~print() في order validation (executor.py)~~ — ✅ طُبّق 2026-05-18
### [9] ~~print() في close_position/modify_position (executor.py)~~ — ✅ طُبّق 2026-05-19

---

## ✅ مكتملة (للمرجع)

| # | المشكلة | التاريخ |
|---|---------|---------|
| E1 | datetime index vs column — EURUSD/GBPUSD | 2026-05-12 |
| E2 | Break-Even SELL — منطق معكوس | v2.1.0 (2026-05-01) |
| E3 | قسمة على صفر في Position Sizing | v2.1.0 (2026-05-01) |
| E4 | ATR Defaults خاطئة | v2.1.0 (2026-05-01) |
| E5 | signal['asia_high'] KeyError | 2026-05-12 |
| E6 | LondonSignalGenerator غير مستوردة | 2026-05-12 |
| E7 | print() في trade_monitor | 2026-05-12 |
| E8 | datetime.now() Local Time بدل UTC | 2026-05-15 |
| E9 | partial lots round → math.floor | 2026-05-17 |
| E10 | MT5 أخطاء الاتصال تُسجَّل في logs | 2026-05-17 |
