# Trading Bot — Claude Code Autonomous Development

> هذا الملف يُقرأ تلقائياً في كل Claude Code session.
> الغرض: تطوير مستقل للاستراتيجيات، backtest، وتحسين الأداء.

---

## Current Strategy Performance (Backtest Baseline)

| Pair   | Strategy        | Sharpe | Return   | Max DD   | Status |
|--------|-----------------|--------|----------|----------|--------|
| USDJPY | London Breakout | 0.97   | +17.81%  | -5.68%   | ✅ Live |
| EURUSD | NY Breakout     | 1.71   | +55.1%   | -11.79%  | ✅ Live |
| GBPUSD | NY Breakout     | 1.22   | +19.1%   | -7.1%    | ✅ Live |
| XAUUSD | ATR Channel     | 1.20   | +35.97%  | -7.33%   | ✅ Live |

---

## Success Criteria (أهداف التحسين)

- Sharpe ratio ≥ 1.5 لكل الأزواج
- Win rate ≥ 52%
- Max drawdown ≤ 15%
- Annual ROI ≥ 15%

---

## Backtest Commands

```bash
# كل الأزواج دفعة واحدة
python3 backtest/multi_pair_backtest.py

# كل زوج منفرد
python3 backtest/london_final.py        # USDJPY
python3 backtest/eurusd_research.py     # EURUSD
python3 backtest/gbpusd_research.py     # GBPUSD
python3 backtest/xauusd_backtest.py     # XAUUSD

# Grid search (parameter sweep)
python3 backtest/london_optimizer.py    # USDJPY grid search

# Finetune
python3 backtest/eurusd_finetune.py
python3 backtest/gbpusd_finetune.py
python3 backtest/gold_finetune.py
```

---

## Historical Data Location

**مجلد:** `backtest_data/`

| File | Timeframe | Period |
|------|-----------|--------|
| `EURUSD_H1_2years.csv` | H1 | 2 years |
| `GBPUSD_H1_2years.csv` | H1 | 2 years |
| `USDJPY_H1_2years.csv` | H1 | 2 years |
| `USDJPY_H4_3years.csv` | H4 | 3 years |
| `XAUUSD_H1_2years.csv` | H1 | 2 years |
| `XAUUSD_M15_2years.csv` | M15 | 2 years |

**Columns:** `datetime, Open, High, Low, Close, Volume, ATR, EMA_20, EMA_50`

**Fetch fresh data:**
```python
from data.data_feed import DataFeed
feed = DataFeed(pair="EURUSD")
df = feed.get_backtest_data()  # H1, 2 years via Twelvedata
```

---

## Strategy Files (Live — Handle With Care)

```
strategy/eurusd_signal.py    → NY Breakout (13:30-16:00 UTC)
strategy/gbpusd_signal.py    → NY Breakout (13:30-16:00 UTC)
strategy/london_signal.py    → London Breakout (07:00-10:00 UTC)
strategy/xauusd_signal.py    → ATR Channel (London + NY)
```

**قواعد تعديل الاستراتيجية:**
1. شغّل الـ backtest أولاً، قارن النتائج
2. إذا Sharpe الجديد ≥ القديم → طبّق التعديل على ملف `strategy/`
3. سجّل التغيير في `memory/development_log.md`
4. لا تغيّر risk params (1% per trade، 2.0 min RR) بدون موافقة صريحة

---

## Risk Parameters (ثابتة — لا تعدّلها)

- Risk per trade: 1%
- Min Risk/Reward: 2.0
- Daily max loss: 3%
- Partial close at: 1.5R
- Max trades/day: 3

---

## Memory & Tracking Files

```
memory/development_log.md    → سجل كل التعديلات والنتائج
memory/strategy_results.md   → أداء أسبوعي مقارنة بالـ backtest
memory/open_suggestions.md   → اقتراحات معلّقة
reports/fix_plan_YYYY-MM-DD.md → تقرير يومي من الروتين
```

**بعد كل backtest ناجح، أضف النتائج في `memory/development_log.md`:**
```markdown
### Backtest Run — YYYY-MM-DD
- Pair: EURUSD | Strategy: NY Breakout
- Params changed: breakout_threshold 0.0005 → 0.0004
- Old Sharpe: 1.71 | New Sharpe: 1.85
- Old Return: +55.1% | New Return: +61.2%
- Decision: ✅ Applied to strategy/eurusd_signal.py
```

---

## Data APIs Available

| API | Purpose | Config Key |
|-----|---------|-----------|
| Twelvedata | OHLCV candles (primary) | `TWELVE_DATA_API_KEY` |
| yfinance | OHLCV fallback | No key needed |
| FinnHub | News + Sentiment | `FINNHUB_API_KEY` |
| FRED | Economic indicators | `FRED_API_KEY` |
| MT5 | Live trading + history | MT5 credentials |

---

## Workflow for Autonomous Improvement

```
1. python3 backtest/multi_pair_backtest.py  → get baseline
2. For each pair with Sharpe < target:
   a. Read its research script (eurusd_research.py etc.)
   b. Identify parameter ranges to test
   c. Run grid search or finetune script
   d. If improved → update strategy/ file
   e. Log to memory/development_log.md
3. Re-run multi_pair_backtest.py to confirm
4. Commit if all Sharpe ≥ targets
```
