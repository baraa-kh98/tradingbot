# اقتراحات مفتوحة — قيد الدراسة

> آخر تحديث: 2026-08-03 (روتين صباحي — الاثنين | يوم 78 نظيف ← رقم قياسي مستمر 🎉 | [A][B] 79 يوم ← رقم قياسي | [C] 83 يوم ← الأقدم | يوم 29 حي [G] 🎯 — **القرار غداً 2026-08-04** | يوم 30 حي [F] — ما بعد BOJ | يوم 18 حي [I] | CPI متأخر **20 يوم** 🔴🔴🔴)

---

## 🟡 متوسطة الأولوية

### [4] XAUUSD — `_in_trade` check قبل `_regime_check()` *(2026-05-20)* ⚡⚡⚡ ESCALATED CRITICAL — ينتظر موافقتك منذ **79 يوم**
- **الملف:** `strategy/xauusd_signal.py:187-190`
- **المشكلة:** `_regime_check()` تُستدعى قبل فحص `self._in_trade` → طلبان HTTP في كل دورة حتى عند وجود صفقة مفتوحة
- **الإصلاح المقترح:**
  ```python
  if self._in_trade:
      return None
  if not self._regime_check():
      return None
  ```
- **تاريخ الاكتشاف:** 2026-05-20
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**79 يوم**)

### [4b] XAUUSD Regime Check — Cache مفقود *(منذ 2026-05-16)* 🚨🚨🚨 CRITICAL — ينتظر موافقتك منذ **79 يوم**
- **الملف:** `strategy/xauusd_signal.py:129`
- **المشكلة:** `_regime_check()` تستدعي yfinance API في كل دورة (كل 15 دقيقة) بدون Cache
  - 24-96 طلب HTTP يومياً بدون داعٍ
  - عند فشل API → fail-open (كل الصفقات مسموحة بدون فلتر)
  - Dead Import: `from datetime import timedelta` داخل الدالة لا يُستخدم (L136) — مُؤكَّد اليوم
- **الإصلاح المقترح:** إضافة `_regime_cache` مع TTL = 3600 ثانية + نقل المنطق لـ `_fetch_regime_live()`
- **تاريخ الاكتشاف:** 2026-05-16
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**79 يوم**)

---

## 🔵 منخفضة الأولوية

### [3] إضافة "strategy" key لكل Signal Generator *(منذ 2026-05-12)* ← الأقدم في تاريخ البوت كله — **83 يوم**
- **الملفات:** `strategy/eurusd_signal.py`, `gbpusd_signal.py`, `xauusd_signal.py`, `london_signal.py`
- **المشكلة:** إشعار Telegram يعرض "Breakout" لكل الأزواج بدل الاسم الفعلي
- **الإصلاح:** إضافة `"strategy": "EURUSD NY Breakout"` إلخ. في كل dict إشارة
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**83 يوم** ← **الأقدم في تاريخ البوت كله**)

---

## 👁️ تحت المراقبة

### [5] CPI مُثبَّت يدوياً في XAUUSD *(تحديث متأخر)*
- **الملف:** `strategy/xauusd_signal.py:153`
- **القيمة الحالية:** `estimated_cpi = 4.2` — May 2026 CPI (قديمة)
- **June 2026 CPI:** صدر 2026-07-14 @ 12:30 UTC — **لم يُطبَّق بعد**
  - بيئة الكلاود لا تستطيع الوصول لـ BLS/yfinance (HTTP 403)
  - التحديث يجب يدوياً على VPS: `estimated_cpi = X.X  # June 2026 CPI`
- **الحالة:** 🔴🔴🔴 **متأخر 20 يوماً — الأعلى في تاريخ البوت — السوق مفتوح الآن (الاثنين) — يحتاج تحديثاً فورياً على VPS**

### [G] ✅ GBPUSD — H4 RSI Filter *(مطبَّق 2026-07-05)* — يوم 29 حي 🎯
- **النتيجة (backtest):** Sharpe 1.273 → 1.664 (+0.391)
- **الحالة:** مراقبة مستمرة — مرحلة التأكيد الحرجة (15 صفقة لايف)
- **القرار المتوقع:** ~2026-08-04 (**غداً** — راجع صفقات GBPUSD على VPS اليوم)

### [F] ✅ USDJPY BOJ Filter *(مطبَّق 2026-07-04)* — يوم 30 حي — ما بعد BOJ
- **النتيجة (backtest):** Sharpe 0.97 → 1.58 (+0.61)
- **BOJ 31 يوليو:** مرّ أمس — الإعلان صدر 01:00-04:00 UTC — لا بيانات VPS متاحة
- **BOJ_LOWER=149:** مُختبَر ومؤكَّد — جاهز لكل السيناريوهات ✅
- **الحالة:** انتظار نتائج VPS — القرار النهائي ~2026-08-07

### [I] ✅ EURUSD ADX_MIN=18 Filter *(مطبَّق 2026-07-16)* — يوم 18 حي (مراقبة مبكرة)
- **النتيجة (backtest):** Sharpe 1.706 → 1.885 (+0.179)
- **الحالة:** مراقبة مبكرة — 15 يوم إضافي أو 15 صفقة لايف

### [21] FOMC September 2026 Filter لـ EURUSD/GBPUSD *(2026-06-14)* — تصحيح: ليس أغسطس
- **الفرضية:** تصفية الدخول قرب وقت FOMC (17:50-18:30 UTC)
- **FOMC التالي:** **سبتمبر 2026** (~15-16 سبتمبر) — FOMC لا يجتمع في أغسطس
- **الحالة:** 💡 Backtest مناسب في أغسطس 2026 (قبل 4-6 أسابيع من الاجتماع)

### [22] XAUUSD BOJ/FOMC Event ± 24h ATR Threshold *(2026-07-26)*
- **الفرضية:** في أيام الأحداث الكبرى (BOJ/FOMC) ± 24 ساعة → رفع ATR threshold لـ XAUUSD
- **الهدف:** تجنب دخولات ضعيفة قبل الأحداث، الاستفادة من الزخم بعدها
- **ملاحظة:** BOJ أمس (31 يوليو) أعطى بيانات حقيقية — راجع ATR XAUUSD أمس على VPS
- **الحالة:** 💡 backtest `python3 backtest/xauusd_backtest.py` على VPS (بيئة الكلاود بطيئة جداً)

### [BOJ Prep] USDJPY BOJ_LOWER طوارئ *(2026-07-31)* — ✅ مُختبَر 2026-07-18 — الإعلان مرّ أمس
- **الوضع:** BOJ أعلن أمس 31 يوليو (01:00-04:00 UTC) — السوق مغلق اليوم (السبت)
- **الملف:** `strategy/london_signal.py` — BOJ_LOWER=149 حالياً
- **النتيجة:** BOJ_LOWER=149 هو الأفضل — مُختبَر ومؤكَّد — لا تغيير لازم
- **الحالة:** ✅ راجع نتائج VPS لمعرفة ما إذا كان الفلتر اُستخدم أمس

### [23] USDJPY Post-BOJ Momentum Strategy *(2026-07-30)*
- **الفرضية:** بعد قرار رفع BOJ، USDJPY ينتج اتجاهاً هبوطياً قوياً يستمر 3-5 أيام
- **المقترح:** تخفيف مؤقت لفلتر BOJ_LOWER بعد قرار الرفع الموثّق — استغلال الاتجاه الواضح
- **الشرط:** فقط بعد تأكيد رفع الفائدة (ليس تثبيت) — راجع قرار BOJ أمس على VPS/Bloomberg
- **الحالة:** 💡 backtest `python3 backtest/london_optimizer.py` على VPS إذا تأكد رفع BOJ

---

## ✅ مكتملة (للمرجع)

| # | المشكلة | التاريخ |
|---|---------|---------|
| E1 | datetime index vs column — EURUSD/GBPUSD | 2026-05-12 |
| E2 | Break-Even SELL — منطق معكوس (v1) | v2.1.0 |
| E3 | قسمة على صفر في Position Sizing | v2.1.0 |
| E4 | ATR Defaults خاطئة | v2.1.0 |
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
| E15 | SELL Break-Even: entry+offset → entry-offset | 2026-05-22 |
| E16 | Exception logging في _regime_check() | 2026-05-28 |
| E17 | GBPUSD MIN_RR: 3.0 → 4.0 | 2026-06-06 |
| B20 | XAUUSD n=20/adx=20 — ❌ REJECTED | 2026-06-21 |
| B22 | GBPUSD Session Narrowing — ❌ REJECTED | 2026-06-21 |
| B18 | USDJPY Asia MR — ❌ REJECTED | 2026-06-27 |
| D | GBPUSD Docstring: Sharpe=1.224→1.270, min_rr=3.0→4.0 | 2026-06-29 |
| E | XAUUSD Docstring: Sharpe=1.31→1.62 | 2026-06-29 |
| NEW-minor | trade_monitor.py:203 "ICT Partial TP" → "Bot Partial TP" | 2026-06-29 |
| Month-End | EURUSD/GBPUSD Month-End Filter — ❌ REJECTED | 2026-07-13 |
| H | EURUSD H4 MACD Filter — ❌ REJECTED | 2026-07-14 |
| F | USDJPY BOJ Zone Filter: Sharpe 0.97→1.58 | 2026-07-04 |
| G | GBPUSD H4 RSI Filter: Sharpe 1.27→1.664 | 2026-07-05 |
| **I** | **EURUSD ADX_MIN=18: Sharpe 1.706→1.885** | **2026-07-16** |
| **J** | **GBPUSD ADX_MIN=18 — ❌ REJECTED (20 صفقة فقط)** | **2026-07-18** |
| **BOJ Prep** | **USDJPY BOJ_LOWER Test: 149 الأفضل — جاهز** | **2026-07-18** |
