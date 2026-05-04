# Trading Bot — PRD (Product Requirements Document)

> **آخر تحديث:** 2026-05-04
> **الإصدار:** 2.3.0
> **الحالة:** تحت التطوير — متوقف مؤقتاً للإصلاح

---

## 1. نظرة عامة

بوت تداول آلي متعدد الأزواج يعمل على منصة MetaTrader 5. يستخدم استراتيجيات breakout موثقة بـ backtest على مدى سنتين. يدعم مراقبة live عبر Telegram ويدمج Claude AI للتحليل الماكرو.

**الهدف:** تنفيذ صفقات عالية الجودة بأقل تدخل يدوي مع إدارة صارمة للمخاطر.

---

## 2. المكونات الرئيسية

```
tradingbot/
├── main.py                  ← نقطة الدخول، الحلقة الرئيسية
├── config.py                ← جميع الإعدادات المركزية
├── notifier.py              ← Telegram: send/send_error/send_crash/send_startup
├── run_bot.bat              ← Windows auto-restart ← شغّل هذا على VPS
├── PRD.md                   ← هذا الملف
├── strategy/                ← توليد الإشارات (19 ملف)
├── data/                    ← جلب البيانات والتحليل (8 ملفات)
├── execution/               ← الاتصال بـ MT5 وتنفيذ الأوامر
├── risk/                    ← إدارة المخاطر ومراقبة الصفقات
├── backtest/                ← البحث وتحسين المعاملات (16 ملف)
├── utils/
│   ├── logger.py            ← نظام logging مركزي (الجديد)
│   └── email_sender.py
├── logs/                    ← يُنشأ تلقائياً عند أول تشغيل
│   ├── bot_YYYY-MM-DD.log   ← كل شي
│   ├── errors_YYYY-MM-DD.log← الأخطاء فقط
│   └── trades_YYYY-MM-DD.log← الصفقات فقط
├── journal/                 ← نتائج الصفقات والإحصائيات
└── backtest_data/           ← بيانات OHLCV مخزنة مؤقتاً
```

---

## 3. الاستراتيجيات النشطة

| الزوج | الاستراتيجية | ملف الإشارة | Sharpe | العائد | Max DD | الحالة |
|-------|-------------|------------|--------|--------|--------|--------|
| USDJPY | London Breakout | `strategy/london_signal.py` | 0.97 | +17.81% | -5.68% | ✅ نشط — 07:00-10:00 UTC |
| XAUUSD | ATR Channel Breakout | `strategy/xauusd_signal.py` | 1.20 | +35.97% | -7.33% | ✅ نشط — 07:00-10:00 + 13:30-16:00 UTC |
| GBPUSD | NY Breakout | `strategy/gbpusd_signal.py` | 1.22 | +19% | — | ⚠️ مراجعة — 13:30-16:00 UTC |
| EURUSD | NY Breakout | `strategy/eurusd_signal.py` | -0.02 | -0.25% | -5.62% | ❌ خاسرة — معطّل مؤقتاً |

### London Breakout (USDJPY) — المنطق
```
1. احسب Asia Range (00:00–06:59 UTC)
2. عند London Open (07:00–09:59 UTC):
   - BUY: كسر فوق Asia High + 3 pips buffer
   - SELL: كسر تحت Asia Low - 3 pips buffer
3. فلتر H4 EMA: لا تتداول ضد EMA20 vs EMA50
4. SL: الطرف الآخر من Asia Range
5. TP: RR = 3:1
6. Trailing: عند 1R → Breakeven، عند 2R → +1R
```

### Gold ATR Breakout (XAUUSD) — المنطق
```
1. ADX > 25 (تأكيد الاتجاه)
2. كسر N-bar High/Low (35 شمعة)
3. SL = 1.5× ATR
4. TP = 3× ATR
```

---

## 4. إدارة المخاطر

**الملف:** `risk/risk_manager.py`

| المعامل | القيمة |
|---------|--------|
| الرصيد الافتراضي | $10,000 |
| المخاطرة لكل صفقة | 1% |
| أقل RR مقبول | 2.0 |
| أقل confluence | 70 نقطة |
| أقصى صفقات يومية | 3 |
| أقصى خسارة يومية | 3% |
| Partial TP | 50% عند 1.5R |
| Break-Even | عند 1R |
| Trailing Stop | 1.5× ATR |

**ATR Defaults (عند فشل البيانات):**
```python
USDJPY: 0.15
EURUSD: 0.0008
GBPUSD: 0.0010
XAUUSD: 3.0
```

---

## 5. تدفق التنفيذ (main.py)

```
بدء الدورة (كل 15 دقيقة)
  ↓
اتصال MT5 + جلب بيانات H1/H4
  ↓
لكل زوج → strategy_router → إشارة
  ↓
MarketViewBuilder → فلتر ماكرو (وزن 25-20%)
  ↓
RiskManager.validate() → حجم اللوت
  ↓
Executor.place_order() → MT5
  ↓
TradeMonitor.check_and_manage() → trailing/BE/partial
  ↓
Telegram notification
```

---

## 6. الاتصالات والـ APIs

| الخدمة | الاستخدام | الملف |
|--------|---------|-------|
| MetaTrader 5 | تنفيذ الصفقات | `execution/executor.py` |
| Twelve Data API | بيانات OHLCV | `data/data_feed.py` |
| Claude API | تحليل ماكرو + self-optimizer | `strategy/ai_vision.py` |
| Telegram Bot | مراقبة + تحكم | `telegram_dashboard.py` |
| FRED API | بيانات اقتصادية | `data/macro_data.py` |
| FinnHub API | أخبار وأحداث | `data/news_calendar.py` |
| SMTP Email | تقارير يومية | `utils/email_sender.py` |

---

## 7. أوامر التشغيل

```bash
# تشغيل عادي
python main.py

# تشغيل مع auto-restart (Windows VPS) ← الموصى به
run_bot.bat

# تشغيل دورة واحدة فقط
python main.py --once

# backtest لندن
python backtest/london_final.py

# backtest الذهب
python backtest/xauusd_backtest.py

# بحث EURUSD
python backtest/eurusd_research.py

# تشخيص اتصال
python diagnose.py
```

---

## 8. Telegram Dashboard — الأوامر

| الأمر | الوظيفة |
|-------|---------|
| `/status` | حالة الصفقات المفتوحة |
| `/positions` | تفاصيل كل صفقة |
| `/pnl` | ربح/خسارة اليوم |
| `/close_all` | إغلاق كل الصفقات |
| `/pause` | إيقاف مؤقت |
| `/resume` | استئناف التداول |
| `/help` | قائمة الأوامر |

---

## 9. هيكل البيانات — Positions Dict

```python
{
    "ticket": int,
    "symbol": str,          # ← أضيف 2026-05-01
    "type": "BUY"|"SELL",
    "volume": float,
    "open_price": float,
    "current_price": float,
    "sl": float,
    "tp": float,
    "profit": float,
    "time": int,
}
```

---

## 10. سجل التعديلات

### v2.3.0 — 2026-05-04 (Kill Zones للذهب + Global Gate)
- **[FIX]** `main.py` — إصلاح Global Time Gate: كان يسمح فقط لندن (07-10 UTC)، الآن يشمل NY AM (13:30-16) وNY PM (19-21 UTC)
- **[FIX]** `strategy/xauusd_signal.py` — إضافة Kill Zone فلتر: الذهب الآن يتداول فقط في لندن (07-10) أو NY AM (13:30-16) وليس في Dead Zone
- **[FIX]** `data/economic_tracker.py` — حذف `^JGB` غير الموجود على yfinance، استبدال بقيمة محسوبة
- **[FIX]** `data/macro_data.py` — تحذير FRED API Key يظهر مرة واحدة بدل 10+ مرات

### v2.2.0 — 2026-05-04 (Logging + Auto-restart)
- **[NEW]** `utils/logger.py` — نظام logging مركزي مع 3 ملفات يومية (bot / errors / trades)
- **[NEW]** `logs/` — مجلد يُنشأ تلقائياً لحفظ الـ logs مع rotation 30 يوم
- **[UPD]** `main.py` — استبدال جميع `print()` الحرجة بـ `logger.info/warning/error`
- **[UPD]** `main.py` — إشعار Telegram مفصّل عند أي خطأ غير متوقع مع اسم ملف الـ log
- **[UPD]** `notifier.py` — إعادة كتابة كاملة: `send_error()`, `send_crash()`, `send_startup()`, `send_daily_summary()`
- **[NEW]** `run_bot.bat` — ملف Windows يعيد تشغيل البوت تلقائياً إذا انهار

### v2.1.0 — 2026-05-01 (إصلاحات حرجة)
- **[FIX]** `risk/risk_manager.py:161` — Break-Even SELL كان معكوساً (`entry - offset` → `entry + offset`)
- **[FIX]** `risk/risk_manager.py:73` — حماية من القسمة على صفر في حساب pip_value لأزواج JPY
- **[FIX]** `risk/trade_monitor.py` — ATR defaults مختلفة لكل زوج (كان 0.15 لكل الأزواج = خطأ لـ EURUSD/GBPUSD/XAUUSD)
- **[FIX]** `execution/executor.py:453` — إضافة `"symbol"` لـ dict الصفقات المرجعة من `get_open_positions()`
- **[FIX]** `risk/trade_monitor.py:84` — `get_current_atr()` يأخذ symbol ويرجع ATR صح لكل زوج
- **[FIX]** `risk/trade_monitor.py:45` — استبدال `except: pass` بـ logging فعلي
- **[FIX]** `risk/trade_journal.py:41` — استبدال `except: pass` بـ logging فعلي
- **[PENDING]** استراتيجية EURUSD نتائجها سلبية (-0.25%, Win Rate 25%) — تحتاج إعادة backtest

### v2.0.0 — 2026-04-07
- **[NEW]** استبدال ICT strategy بـ London Breakout (`strategy/london_signal.py`)
- **[NEW]** إضافة London Optimizer (`backtest/london_optimizer.py`) — 108 combination grid search
- **[FIX]** `data/data_feed.py` — تصحيح `get_historical_range` → `get_candles`
- **[NEW]** نظام أرشفة مزدوج JSON/MD للصفقات (`backtest/archive_manager.py`)

### v1.5.0 — 2026-03-xx
- **[NEW]** Sequential Backtest Campaign مع Claude AI
- **[NEW]** `strategy/market_view_builder.py` — تحليل ماكرو مركب
- **[NEW]** `data/market_regime.py` — كشف نظام السوق (trending/ranging)
- **[NEW]** Self-optimizer (`strategy/self_optimizer.py`)

### v1.0.0 — الإصدار الأول
- ICT strategy (Order Blocks, FVG, Liquidity)
- Multi-pair support: USDJPY, EURUSD, GBPUSD, XAUUSD
- Risk Manager + Trade Monitor + Trade Journal
- Telegram Dashboard

---

## 11. المشاكل المعروفة (Open Issues)

| الأولوية | المشكلة | الملف | الحالة |
|---------|---------|-------|--------|
| 🔴 عالية | EURUSD استراتيجيتها خاسرة | `strategy/eurusd_signal.py` | ❌ مفتوح |
| 🟡 متوسطة | GBPUSD نتائجها تحتاج مراجعة | `strategy/gbpusd_signal.py` | ⚠️ مفتوح |
| 🟡 متوسطة | حجم الإغلاق الجزئي غير دقيق لـ lots صغيرة | `risk/risk_manager.py:245` | ⚠️ مفتوح |
| 🔵 منخفضة | MT5 connection error handling ضعيف | `execution/executor.py:46` | ⚠️ مفتوح |

---

## 12. ملاحظات تقنية

- **اللغة:** Python 3.14
- **نظام التشغيل:** Windows (بسبب MT5) أو macOS للـ backtest فقط
- **MT5:** يحتاج Windows لتنفيذ الصفقات الحقيقية
- **PIP_VALUE:** يُحدَّد في `config.py` ويؤثر على حسابات كل الأزواج — تأكد من تطابقه مع الزوج النشط
- **Kill Zones:** London 07:00–10:00 UTC، NY 13:30–16:00 و19:00–21:00 UTC
- **Magic Number:** يُميز صفقات البوت عن الصفقات اليدوية في MT5
