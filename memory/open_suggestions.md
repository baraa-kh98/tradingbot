# اقتراحات مفتوحة — قيد الدراسة

> آخر تحديث: 2026-06-28 (روتين صباحي — الأحد | يوم 43 نظيف ← رقم قياسي مطلق جديد | أسواق مغلقة — Q3 يبدأ الليلة 22:00 UTC | [A][B][C][D][E] تنتظر الموافقة | [18] USDJPY Asia MR — ❌ REJECTED أمس | [F] USDJPY BOJ Zone مجدول 7-11 يوليو)

---

## 🟡 متوسطة الأولوية

### [4] XAUUSD — `_in_trade` check قبل `_regime_check()` *(2026-05-20، 43 يوم)* ⚡⚡⚡ ESCALATED CRITICAL — **ينتظر موافقتك منذ 43 يوم**
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
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**43 يوم**)

### [4b] XAUUSD Regime Check — Cache مفقود *(منذ 2026-05-16، 43 يوم)* 🚨🚨🚨 CRITICAL — **ينتظر موافقتك منذ 43 يوم**
- **الملف:** `strategy/xauusd_signal.py:129`
- **المشكلة:** `_regime_check()` تستدعي yfinance API في كل دورة (كل 15 دقيقة) بدون Cache
  - 24-96 طلب HTTP يومياً بدون داعٍ
  - عند فشل API → fail-open (كل الصفقات مسموحة بدون فلتر)
  - Dead Import: `from datetime import timedelta` داخل الدالة لا يُستخدم (L133)
- **الإصلاح المقترح:** إضافة `_regime_cache` مع TTL = 3600 ثانية + نقل المنطق لـ `_fetch_regime_live()`
- **تاريخ الاكتشاف:** 2026-05-16
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**43 يوم**)

---

## 🔵 منخفضة الأولوية

### [1] ~~دقة الإغلاق الجزئي~~ — ✅ طُبّق 2026-05-17
### [2] ~~MT5 Connection Error Handling~~ — ✅ طُبّق 2026-05-17
### [10] ~~SELL Break-Even Offset~~ — ✅ **طُبّق 2026-05-22**
- **الملف:** `risk/risk_manager.py:163`
- **الإصلاح:** `entry + offset` → `entry - offset` (SL تحت entry = ربح 2 pip عند الضرب)

### [NEW-minor] ICT Comment في trade_monitor.py *(2026-06-23، 6 أيام)*
- **الملف:** `risk/trade_monitor.py:203`
- **المشكلة:** `"comment": "ICT Partial TP"` — بقايا من v1.0 ICT strategy — ظاهر في logs MT5 كـ "ICT"
- **الإصلاح:** تغيير إلى `"comment": "Bot Partial TP"` — دقيقة واحدة
- **التأثير:** لا تأثير وظيفي — مضلّل في logs MT5 فقط
- **الحالة:** 🔵 منخفضة — ينتظر موافقتك (6 أيام)

### [D] GBPUSD Docstring قديم *(2026-06-09، 20 يوم)*
- **الملف:** `strategy/gbpusd_signal.py:5-17`
- **المشكلة:** الـ docstring يقول:
  - `Sharpe=1.224` — الصح بعد finetune: **1.270**
  - `min_rr=3.0 | TP = 3.0 × risk` — القيمة الفعلية `MIN_RR=4.0`
- **التأثير:** لا تأثير وظيفي — مجرد توثيق مضلّل للقراءة
- **الإصلاح:** تحديث السطور 5,9,16 في الـ docstring (2 دقيقة)
- **الحالة:** 📝 منخفضة الأولوية — **ينتظر موافقتك (20 يوم)**

### [3] إضافة "strategy" key لكل Signal Generator *(منذ 2026-05-12، 47 يوم)* ← الأقدم في تاريخ البوت كله
- **الملفات:** `strategy/eurusd_signal.py`, `gbpusd_signal.py`, `xauusd_signal.py`, `london_signal.py`
- **المشكلة:** إشعار Telegram يعرض "Breakout" لكل الأزواج بدل الاسم الفعلي
- **الإصلاح:** إضافة `"strategy": "EURUSD NY Breakout"` إلخ. في كل dict إشارة
- **الحالة:** ⏳ ينتظر موافقة المستخدم (**47 يوم** ← **الأقدم في تاريخ البوت كله**)

### [E] XAUUSD Docstring — Sharpe قديم *(2026-06-27، 2 يوم)* 🔵 منخفضة
- **الملف:** `strategy/xauusd_signal.py:10`
- **المشكلة:** `Sharpe=1.31` — الصح بعد June 21 re-run: **Sharpe=1.621**
- **الإصلاح:** تغيير L10 من `Sharpe=1.31` إلى `Sharpe=1.62 (2026-06-21 re-run)` — دقيقة واحدة
- **الحالة:** 🔵 منخفضة — توثيق فقط — **ينتظر موافقتك (2 يوم)**

---

## 🔴 أولوية عالية — Backtests مجدولة

### [F] USDJPY — استراتيجيات بديلة *(2026-06-27، 2 يوم)* 🔴 أولوية الأسبوع 7-11 يوليو
- **الخلفية:** [18] USDJPY Asia MR مُغلَق (❌ REJECTED 2026-06-27) — USDJPY أكبر فجوة (Sharpe 0.98 vs هدف 1.5)
- **3 مقترحات للـ backtest بالترتيب:**
  1. **🥇 BOJ Zone Filter:** SELL فقط عند price > 155 + failed breakout London | BUY عند price < 147
  2. **🥈 Carry Trade Reversal:** VIX > 20 + USDJPY فوق EMA50 H4 → SELL (risk-off reversal)
  3. **🥉 Session Overlap NY (13:00-15:00 UTC):** نفس نافذة EURUSD/GBPUSD لكن بمنطق breakout مختلف لـ USDJPY
- **الأولوية:** 🔴 عالية — أكبر فجوة Sharpe في البوت (-0.52)
- **الجدول:** أسبوع 7-11 يوليو 2026 (بعد عطلة Independence Day)
- **الحالة:** 💡 مجدولة

---

## 👁️ تحت المراقبة

### [21] FOMC Day Filter لـ EURUSD/GBPUSD *(2026-06-14، 14 يوم)*
- **الخلفية:** FOMC يحدث 8 مرات/سنة — إعلانات الفيدرالي عادةً 18:00 UTC الأربعاء
- **الفرضية:** تصفية الدخول بين 17:50-18:30 UTC في أيام FOMC يُحسّن Win Rate
- **الأولوية:** متوسطة — FOMC التالي في يوليو/أغسطس 2026
- **الحالة:** 💡 فكرة قيد الدراسة — تحتاج backtest

### [5] CPI مُثبَّت يدوياً في XAUUSD *(مستمر)*
- **الملف:** `strategy/xauusd_signal.py:153`
- **القيمة الحالية:** `estimated_cpi = 2.8` — آخر تحديث: مايو 2026
- **الإصلاح المقترح:** تحديث بعد صدور CPI يوليو (حوالي 8 يوليو 2026)
- **الحالة:** 🔍 تحت المراقبة — أولوية منخفضة

### [12] Weekend Gap *(مراقبة دورية — Q3-Open الليلة)*
- **الموضوع:** Q2-End + Q3-Start = Weekend Gap محتمل عالياً في الأسواق الليلة 22:00 UTC
- **الأزواج الأكثر تأثراً:** XAUUSD > EURUSD/GBPUSD
- **التوصية:** لا إشارات في أول 30 دقيقة London Open الاثنين 30 يونيو
- **الحالة:** 🔍 مراقبة أسبوعية

### [14] تأثير الأعياد الأمريكية — Independence Day 4 يوليو *(جديد)*
- **الموضوع:** الجمعة 4 يوليو 2026 = US Independence Day — سيولة صفر في NY
- **الأزواج المتأثرة:** EURUSD/GBPUSD (NY Breakout) + XAUUSD
- **التوصية:** إيقاف البوت أو تصفية اليوم يدوياً
- **الحالة:** 🔍 تحذير مسبق

### [11] XAUUSD — datetime.now() vs candle index للـ session filter *(2026-05-21)*
- **الملف:** `strategy/xauusd_signal.py:176-180`
- **خطورة:** منخفضة (live OK، backtest script على الأرجح يمتلك فلترة خاصة)
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
| **E16** | **Exception logging في _regime_check() — xauusd_signal.py** | **2026-05-28** |
| **E17** | **GBPUSD MIN_RR: 3.0 → 4.0 (Sharpe 1.224→1.270, finetune 2026-06-06)** | **2026-06-06** |
| **B20** | **[20] XAUUSD n=20/adx=20 — TESTED ❌ REJECTED (Sharpe 0.907 << 1.621)** | **2026-06-21** |
| **B22** | **[22] GBPUSD Session Narrowing — TESTED ❌ REJECTED (Full 13-15 is optimal)** | **2026-06-21** |
| **B18** | **[18] USDJPY Asia Mean Reversion — TESTED ❌ REJECTED (Best Sharpe=1.027, T=23)** | **2026-06-27** |
