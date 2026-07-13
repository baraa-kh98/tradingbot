# اقتراحات مفتوحة — قيد الدراسة

> آخر تحديث: 2026-07-13 (روتين صباحي — الأحد | يوم 57 نظيف | 🔬 Month-End Filter ❌ REJECTED | 🔴 June CPI غداً 14 يوليو @ 12:30 UTC | [A][B] 58 يوم | [C] 62 يوم ← الأقدم | يوم 8 حي [G] | يوم 9 حي [F])

---

## 🟡 متوسطة الأولوية

### [4] XAUUSD — `_in_trade` check قبل `_regime_check()` *(2026-05-20، 52 يوم)* ⚡⚡⚡ ESCALATED CRITICAL — **ينتظر موافقتك منذ 52 يوم**
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
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**52 يوم**)

### [4b] XAUUSD Regime Check — Cache مفقود *(منذ 2026-05-16، 52 يوم)* 🚨🚨🚨 CRITICAL — **ينتظر موافقتك منذ 52 يوم**
- **الملف:** `strategy/xauusd_signal.py:129`
- **المشكلة:** `_regime_check()` تستدعي yfinance API في كل دورة (كل 15 دقيقة) بدون Cache
  - 24-96 طلب HTTP يومياً بدون داعٍ
  - عند فشل API → fail-open (كل الصفقات مسموحة بدون فلتر)
  - Dead Import: `from datetime import timedelta` داخل الدالة لا يُستخدم (L133)
- **الإصلاح المقترح:** إضافة `_regime_cache` مع TTL = 3600 ثانية + نقل المنطق لـ `_fetch_regime_live()`
- **تاريخ الاكتشاف:** 2026-05-16
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**52 يوم**)

---

## 🔵 منخفضة الأولوية

### [3] إضافة "strategy" key لكل Signal Generator *(منذ 2026-05-12، 56 يوم)* ← الأقدم في تاريخ البوت كله
- **الملفات:** `strategy/eurusd_signal.py`, `gbpusd_signal.py`, `xauusd_signal.py`, `london_signal.py`
- **المشكلة:** إشعار Telegram يعرض "Breakout" لكل الأزواج بدل الاسم الفعلي
- **الإصلاح:** إضافة `"strategy": "EURUSD NY Breakout"` إلخ. في كل dict إشارة
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**56 يوم** ← **الأقدم في تاريخ البوت كله**)

---

## 🔵 منخفضة الأولوية — اقتراحات جديدة

### [Month-End Filter] EURUSD/GBPUSD — تصفية آخر 2-3 أيام الشهر *(2026-06-30، 1 يوم)*
- **الملفات:** `strategy/eurusd_signal.py`, `strategy/gbpusd_signal.py`
- **الفرضية:** آخر يومين تداول في الشهر يُولّدان False Breakouts بنسبة أعلى بسبب Rebalancing المؤسسي
- **الإصلاح المقترح:**
  ```python
  from datetime import datetime, timezone
  if datetime.now(timezone.utc).day >= 28:
      return None  # skip last 3 trading days of month
  ```
- **Backtest:** ❌ REJECTED — 2026-07-13
  - EURUSD: Sharpe 1.602 → 1.447 (-0.155) | GBPUSD: Sharpe 1.088 → 1.026 (-0.062)
  - الفلتر يُخفّض الأداء — أيام نهاية الشهر تُولّد صفقات جيدة في هذا النظام
- **الحالة:** ❌ مرفوض نهائياً — لا تعديل

---

## ✅ مكتملة حديثاً

### [F] ✅ USDJPY — BOJ Zone Filter *(مطبَّق 2026-07-04)*
- **النتيجة:** Sharpe 0.97 → **1.58** (+0.61) | WR 36.2% → 50.0% | DD -5.68% → -3.25%
- **الملف:** `strategy/london_signal.py` — BOJ_UPPER=151.0, BOJ_LOWER=149.0
- **الحالة:** ✅ طُبّق تلقائياً 2026-07-04

---

## 🔴 أولوية عالية — Backtests مجدولة

### [G] ✅ GBPUSD — H4 RSI Filter *(مطبَّق 2026-07-05)*
- **النتيجة:** Sharpe 1.273 → **1.664** (+0.391) | WR 34.2%→40.6% | DD -7.14%→-6.14% | Return +31.62% | PF 2.222
- **الملف:** `strategy/gbpusd_signal.py` — RSI_HI=75, RSI_LO=25, RSI_PERIOD=14
- **الحالة:** ✅ طُبّق تلقائياً 2026-07-05
- **الإنجاز:** لأول مرة: جميع الأزواج الـ 4 ≥ Sharpe 1.5 في آنٍ واحد 🏆

---

## 👁️ تحت المراقبة

### [21] FOMC Day Filter لـ EURUSD/GBPUSD *(2026-06-14، 15 يوم)*
- **الفرضية:** تصفية الدخول بين 17:50-18:30 UTC في أيام FOMC يُحسّن Win Rate
- **FOMC التالي:** يوليو/أغسطس 2026
- **الحالة:** 💡 فكرة قيد الدراسة — تحتاج backtest

### [5] CPI مُثبَّت يدوياً في XAUUSD *(تحديث دوري)*
- **الملف:** `strategy/xauusd_signal.py:153`
- **القيمة الحالية:** `estimated_cpi = 4.2` — آخر تحديث: 2026-07-09 (May 2026 CPI = 4.17% YoY)
- **التحديث القادم:** June 2026 CPI يصدر **14 يوليو 2026 @ 12:30 UTC** — تحديث فوري بعد الإعلان
- **الحالة:** 🔴 **مجدول غداً الاثنين 14 يوليو @ 12:30 UTC**

### [H] EURUSD — H4 MACD Filter *(جديد 2026-07-13)*
- **الملف:** `strategy/eurusd_signal.py`
- **الفرضية:** مشابه لـ H4 RSI Filter الناجح في GBPUSD — لا BUY عند MACD H4 Bearish | لا SELL عند MACD H4 Bullish
- **المنطق:** MACD(12,26,9) على H4 → إذا MACD Line < Signal Line → Bearish H4 → لا BUY
- **الهدف:** EURUSD Sharpe 1.61 → 1.75+ (تحسين مماثل لـ GBPUSD RSI)
- **تاريخ الاكتشاف:** 2026-07-13
- **الحالة:** 💡 فكرة جديدة — تحتاج Backtest الأسبوع القادم

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
| **F** | **USDJPY BOJ Zone Filter: Sharpe 0.97→1.58, BOJ_UPPER=151, BOJ_LOWER=149** | **2026-07-04** |
| **G** | **GBPUSD H4 RSI Filter: Sharpe 1.273→1.664, RSI_HI=75, RSI_LO=25** | **2026-07-05** |
