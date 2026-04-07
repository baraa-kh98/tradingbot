"""
aggregate_results.py — مقارنة نتائج الباكتست لجميع الأزواج
Usage: python aggregate_results.py
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS_PATH = "journal/multi_pair_results.json"
SUMMARY_PATH = "journal/campaign_summary.md"


def score(r):
    """نقاط المقارنة: Sharpe + Return - Drawdown"""
    if r.get("trades", 0) < 10:
        return -999.0
    return (
        r.get("sharpe", 0) * 4
        + r.get("return_pct", 0) * 0.3
        - abs(r.get("max_dd_pct", 0)) * 0.2
        + (r.get("profit_factor", 1) - 1) * 3
    )


def main():
    if not os.path.exists(RESULTS_PATH):
        print(f"❌ ملف النتائج مش موجود: {RESULTS_PATH}")
        print("   شغّل run_campaign.sh أولاً")
        sys.exit(1)

    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)

    if not results:
        print("❌ لا توجد نتائج بعد")
        sys.exit(1)

    results.sort(key=score, reverse=True)

    # ── طباعة الجدول ────────────────────────────────────────────
    header = (
        f"{'Pair':<8} {'Trades':>7} {'WR%':>6} {'Ret%':>7} "
        f"{'Ann%':>7} {'DD%':>7} {'Sharpe':>7} {'PF':>5} {'Score':>7}"
    )
    sep = "-" * len(header)

    print(f"\n{'='*len(header)}")
    print("  London Breakout — مقارنة الأزواج")
    print(f"{'='*len(header)}")
    print(header)
    print(sep)

    for r in results:
        s = score(r)
        medal = " 🥇" if r == results[0] else ""
        print(
            f"{r['pair']:<8} {r['trades']:>7} {r['win_rate_pct']:>6.1f} "
            f"{r['return_pct']:>7.2f} {r['annual_return']:>7.2f} "
            f"{r['max_dd_pct']:>7.2f} {r['sharpe']:>7.3f} "
            f"{r['profit_factor']:>5.2f} {s:>7.2f}{medal}"
        )

    print(sep)
    best = results[0]
    print(f"\n  الأفضل: {best['pair']} (Score: {score(best):.2f})")
    print(f"  التقييم بتاريخ: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

    # ── كتابة Markdown Summary ───────────────────────────────────
    md_lines = [
        f"# London Breakout — Campaign Summary\n",
        f"**تاريخ التقرير:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n",
        f"**الاستراتيجية:** LondonClean | buffer=3pip | RR=3.0 | min_range=40pip\n",
        f"**الفترة:** سنتين (H1)\n\n",
        f"## النتائج\n",
        f"| Pair | Trades | WR% | Return% | Ann% | Max DD% | Sharpe | PF | Score |",
        f"|------|--------|-----|---------|------|---------|--------|----|-------|",
    ]

    for r in results:
        s = score(r)
        medal = " 🥇" if r == results[0] else ""
        md_lines.append(
            f"| {r['pair']}{medal} | {r['trades']} | {r['win_rate_pct']} | "
            f"{r['return_pct']} | {r['annual_return']} | {r['max_dd_pct']} | "
            f"{r['sharpe']} | {r['profit_factor']} | {s:.2f} |"
        )

    md_lines += [
        f"\n## الخلاصة\n",
        f"**أفضل زوج:** {best['pair']}",
        f"- العائد السنوي: {best['annual_return']}%",
        f"- Sharpe: {best['sharpe']}",
        f"- Win Rate: {best['win_rate_pct']}%",
        f"- Profit Factor: {best['profit_factor']}",
        f"- Max Drawdown: {best['max_dd_pct']}%",
    ]

    os.makedirs("journal", exist_ok=True)
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\n  ✅ التقرير محفوظ في {SUMMARY_PATH}\n")


if __name__ == "__main__":
    main()
