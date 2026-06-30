# اقتراحات مفتوحة — قيد الدراسة

> آخر تحديث: 2026-06-30 (روتين صباحي — الثلاثاء | يوم 45 نظيف ← رقم قياسي مطلق | آخر يوم H1 2026 | ⚠️ Month-End Rebalancing Risk | [A][B][C] تنتظر الموافقة 45+ يوم | [F] BOJ Zone مجدول 7-11 يوليو | [Month-End Filter] اقتراح جديد)

---

## 🟡 متوسطة الأولوية

### [4] XAUUSD — `_in_trade` check قبل `_regime_check()` *(2026-05-20، 44 يوم)* ⚡⚡⚡ ESCALATED CRITICAL — **ينتظر موافقتك منذ 44 يوم**
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
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**44 يوم**)

### [4b] XAUUSD Regime Check — Cache مفقود *(منذ 2026-05-16، 44 يوم)* 🚨🚨🚨 CRITICAL — **ينتظر موافقتك منذ 44 يوم**
- **الملف:** `strategy/xauusd_signal.py:129`
- **المشكلة:** `_regime_check()` تستدعي yfinance API في كل دورة (كل 15 دقيقة) بدون Cache
  - 24-96 طلب HTTP يومياً بدون داعٍ
  - عند فشل API → fail-open (كل الصفقات مسموحة بدون فلتر)
  - Dead Import: `from datetime import timedelta` داخل الدالة لا يُستخدم (L133)
- **الإصلاح المقترح:** إضافة `_regime_cache` مع TTL = 3600 ثانية + نقل المنطق لـ `_fetch_regime_live()`
- **تاريخ الاكتشاف:** 2026-05-16
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**44 يوم**)

---

## 🔵 منخفضة الأولوية

### [3] إضافة "strategy" key لكل Signal Generator *(منذ 2026-05-12، 48 يوم)* ← الأقدم في تاريخ البوت كله
- **الملفات:** `strategy/eurusd_signal.py`, `gbpusd_signal.py`, `xauusd_signal.py`, `london_signal.py`
- **المشكلة:** إشعار Telegram يعرض "Breakout" لكل الأزواج بدل الاسم الفعلي
- **الإصلاح:** إضافة `"strategy": "EURUSD NY Breakout"` إلخ. في كل dict إشارة
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**48 يوم** ← **الأقدم في تاريخ البوت كله**)

---

## 🔵 منخفضة الأولوية — اقتراحات جديدة

### [Month-End Filter] EURUSD/GBPUSD — تصفية آخر 2-3 أيام الشهر *(2026-06-30، جديد)*
- **الملفات:** `strategy/eurusd_signal.py`, `strategy/gbpusd_signal.py`
- **الفرضية:** آخر يومين تداول في الشهر يُولّدان False Breakouts بنسبة أعلى بسبب Rebalancing المؤسسي
- **الإصلاح المقترح:**
  ```python
  from datetime import datetime, timezone
  if datetime.now(timezone.utc).day >= 28:
      return None  # skip last 3 trading days of month
  ```
- **يحتاج backtest** على `backtest_data/EURUSD_H1_2years.csv` و `GBPUSD_H1_2years.csv`
- **الحالة:** 💡 فكرة — تحتاج backtest لتأكيد

---

## 🔴 أولوية عالية — Backtests مجدولة

### [F] USDJPY — BOJ Zone Filter *(2026-06-27، 2 يوم)* 🔴 أولوية الأسبوع 7-11 يوليو
- **الخلفية:** [18] USDJPY Asia MR مُغلَق (❌ REJECTED 2026-06-27) — USDJPY أكبر فجوة (Sharpe 0.97 vs هدف 1.5)
- **المقترح الأول (مُفضَّل):** SELL فقط عند price > 155 + failed London breakout | BUY عند price < 147
- **الجدول:** أسبوع 7-11 يوليو 2026 (بعد Independence Day)
- **الأولوية:** 🔴 عالية — أكبر فجوة Sharpe في البوت (-0.53)
- **الحالة:** 💡 مجدولة

---

## 👁️ تحت المراقبة

### [21] FOMC Day Filter لـ EURUSD/GBPUSD *(2026-06-14، 15 يوم)*
- **الفرضية:** تصفية الدخول بين 17:50-18:30 UTC في أيام FOMC يُحسّن Win Rate
- **FOMC التالي:** يوليو/أغسطس 2026
- **الحالة:** 💡 فكرة قيد الدراسة — تحتاج backtest

### [5] CPI مُثبَّت يدوياً في XAUUSD *(مستمر)*
- **الملف:** `strategy/xauusd_signal.py:153`
- **القيمة الحالية:** `estimated_cpi = 2.8` — آخر تحديث: مايو 2026
- **تحديث مطلوب:** بعد صدور CPI يوليو (~8 يوليو 2026)
- **الحالة:** 🔍 تحت المراقبة — أولوية منخفضة

### [11] XAUUSD — datetime.now() vs candle index للـ session filter *(2026-05-21)*
- **الملف:** `strategy/xauusd_signal.py:176-180`
- **خطورة:** منخفضة — مراقبة فقط

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
| E15 | SELL Break-Even: entry+offset → entry-offset | 2026-05-22 |
| E16 | Exception logging في _regime_check() | 2026-05-28 |
| E17 | GBPUSD MIN_RR: 3.0 → 4.0 | 2026-06-06 |
| B20 | XAUUSD n=20/adx=20 — ❌ REJECTED | 2026-06-21 |
| B22 | GBPUSD Session Narrowing — ❌ REJECTED | 2026-06-21 |
| B18 | USDJPY Asia MR — ❌ REJECTED | 2026-06-27 |
| **D** | **GBPUSD Docstring: Sharpe=1.224→1.270, min_rr=3.0→4.0** | **2026-06-29** |
| **E** | **XAUUSD Docstring: Sharpe=1.31→1.62 (re-run 2026-06-21)** | **2026-06-29** |
| **NEW-minor** | **trade_monitor.py:203 "ICT Partial TP" → "Bot Partial TP"** | **2026-06-29** |
