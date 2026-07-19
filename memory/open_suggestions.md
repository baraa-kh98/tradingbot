# اقتراحات مفتوحة — قيد الدراسة

> آخر تحديث: 2026-07-19 (روتين صباحي — الأحد | يوم 63 نظيف | السوق مغلق | [A][B] 64 يوم ← رقم قياسي | [C] 68 يوم ← الأقدم | يوم 15 حي [G] 🎯 | يوم 16 حي [F] | يوم 4 حي [I] | BOJ 31 يوليو: 12 يوماً)

---

## 🟡 متوسطة الأولوية

### [4] XAUUSD — `_in_trade` check قبل `_regime_check()` *(2026-05-20)* ⚡⚡⚡ ESCALATED CRITICAL — **ينتظر موافقتك منذ 63 يوم**
- **الملف:** `strategy/xauusd_signal.py:182-185`
- **المشكلة:** `_regime_check()` تُستدعى قبل فحص `self._in_trade` → طلبان HTTP في كل دورة حتى عند وجود صفقة مفتوحة
- **الإصلاح المقترح:**
  ```python
  if self._in_trade:
      return None
  if not self._regime_check():
      return None
  ```
- **تاريخ الاكتشاف:** 2026-05-20
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**64 يوم**)

### [4b] XAUUSD Regime Check — Cache مفقود *(منذ 2026-05-16)* 🚨🚨🚨 CRITICAL — **ينتظر موافقتك منذ 63 يوم**
- **الملف:** `strategy/xauusd_signal.py:129`
- **المشكلة:** `_regime_check()` تستدعي yfinance API في كل دورة (كل 15 دقيقة) بدون Cache
  - 24-96 طلب HTTP يومياً بدون داعٍ
  - عند فشل API → fail-open (كل الصفقات مسموحة بدون فلتر)
  - Dead Import: `from datetime import timedelta` داخل الدالة لا يُستخدم (L133)
- **الإصلاح المقترح:** إضافة `_regime_cache` مع TTL = 3600 ثانية + نقل المنطق لـ `_fetch_regime_live()`
- **تاريخ الاكتشاف:** 2026-05-16
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**64 يوم**)

---

## 🔵 منخفضة الأولوية

### [3] إضافة "strategy" key لكل Signal Generator *(منذ 2026-05-12)* ← الأقدم في تاريخ البوت كله
- **الملفات:** `strategy/eurusd_signal.py`, `gbpusd_signal.py`, `xauusd_signal.py`, `london_signal.py`
- **المشكلة:** إشعار Telegram يعرض "Breakout" لكل الأزواج بدل الاسم الفعلي
- **الإصلاح:** إضافة `"strategy": "EURUSD NY Breakout"` إلخ. في كل dict إشارة
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**68 يوم** ← **الأقدم في تاريخ البوت كله**)

---

## 👁️ تحت المراقبة

### [5] CPI مُثبَّت يدوياً في XAUUSD *(تحديث متأخر)*
- **الملف:** `strategy/xauusd_signal.py:153`
- **القيمة الحالية:** `estimated_cpi = 4.2` — May 2026 CPI (قديمة)
- **June 2026 CPI:** صدر 2026-07-14 @ 12:30 UTC — **لم يُطبَّق بعد**
  - بيئة الكلاود لا تستطيع الوصول لـ BLS/yfinance (HTTP 403)
  - التحديث يجب يدوياً على VPS: `estimated_cpi = X.X  # June 2026 CPI`
- **الحالة:** 🔴 **متأخر 5 أيام — يحتاج تدخل يدوي على VPS**

### [G] ✅ GBPUSD — H4 RSI Filter *(مطبَّق 2026-07-05)* — يوم 15 حي 🎯
- **النتيجة (backtest):** Sharpe 1.273 → 1.664 (+0.391)
- **الحالة:** مراقبة مستمرة — **مرحلة التأكيد الحرجة (15 صفقة لايف)**

### [F] ✅ USDJPY BOJ Filter *(مطبَّق 2026-07-04)* — يوم 16 حي
- **النتيجة (backtest):** Sharpe 0.97 → 1.58 (+0.61)
- **تنبيه:** BOJ اجتماع 31 يوليو — ✅ مُختبَر 2026-07-18 — BOJ_LOWER=149 يبقى (لا تغيير)

### [21] FOMC Day Filter لـ EURUSD/GBPUSD *(2026-06-14)*
- **الفرضية:** تصفية الدخول قرب وقت FOMC (17:50-18:30 UTC)
- **FOMC التالي:** أغسطس 2026
- **الحالة:** 💡 فكرة قيد الدراسة — تحتاج backtest (بعد تقييم [G] و [F])

### [BOJ Prep] USDJPY BOJ_LOWER طوارئ *(2026-07-31)* — ✅ مُختبَر 2026-07-18
- **الخطر:** BOJ اجتماع 31 يوليو — إذا رُفعت الفائدة → USDJPY قد يكسر 149
- **الملف:** `strategy/london_signal.py` — BOJ_LOWER=149 حالياً
- **Engine:** `backtest/usdjpy_boj_lower_test.py` (مُنشأ 2026-07-18)
- **النتيجة:** BOJ_LOWER=149 هو الأفضل — 148/149 متطابقان — لا تغيير لازم
- **الحالة:** ✅ مُختبَر — الجاهزية تامة لكل سيناريوهات BOJ 31 يوليو

---

## ✅ مكتملة حديثاً

### [I] ✅ EURUSD ADX_MIN=18 Filter *(مطبَّق 2026-07-16)* — يراقب (يوم 4)
- **الـ Backtest (finetune engine):** Sharpe 1.706 → **1.885** (+0.179)
- **Return:** +55.06% → +58.66% | **MaxDD:** -11.79% → -9.91% | **WR:** 33.3% → 35.3%
- **الملف:** `strategy/eurusd_signal.py` — ADX_MIN=18 + `_adx()` method
- **الحالة:** ✅ طُبّق تلقائياً 2026-07-16

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
