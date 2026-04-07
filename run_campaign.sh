#!/bin/zsh
# run_campaign.sh — تشغيل باكتست London Breakout لجميع الأزواج بالتسلسل
# Usage: bash run_campaign.sh
# التوقيت المتوقع: 1-2 ساعة

set -e
cd "$(dirname "$0")"

PAIRS=(EURUSD GBPUSD XAUUSD USDJPY)
LOG_FILE="journal/campaign.log"

mkdir -p journal

echo "" | tee -a "$LOG_FILE"
echo "=========================================="  | tee -a "$LOG_FILE"
echo "  London Breakout Campaign بدأت"            | tee -a "$LOG_FILE"
echo "  $(date)"                                   | tee -a "$LOG_FILE"
echo "  الأزواج: ${PAIRS[*]}"                     | tee -a "$LOG_FILE"
echo "==========================================" | tee -a "$LOG_FILE"

COMPLETED=0
FAILED=0
TOTAL=${#PAIRS[@]}
COUNT=0

for PAIR in "${PAIRS[@]}"; do
    COUNT=$((COUNT + 1))
    echo ""                                                              | tee -a "$LOG_FILE"
    echo "------------------------------------------"                   | tee -a "$LOG_FILE"
    echo "  [$(date +%H:%M:%S)] بدء معالجة: $PAIR"                    | tee -a "$LOG_FILE"
    echo "------------------------------------------"                   | tee -a "$LOG_FILE"

    # Step 1: جلب البيانات
    if python3 fetch_pair_data.py "$PAIR" 2>&1 | tee -a "$LOG_FILE"; then
        echo "  ✅ البيانات جاهزة لـ $PAIR" | tee -a "$LOG_FILE"
    else
        echo "  ❌ فشل جلب بيانات $PAIR — تخطي" | tee -a "$LOG_FILE"
        FAILED=$((FAILED + 1))
        continue
    fi

    # Step 2: تشغيل الباكتست
    if python3 multi_pair_backtest.py "$PAIR" 2>&1 | tee -a "$LOG_FILE"; then
        echo "  ✅ باكتست $PAIR اكتمل" | tee -a "$LOG_FILE"
        COMPLETED=$((COMPLETED + 1))
    else
        echo "  ❌ فشل باكتست $PAIR" | tee -a "$LOG_FILE"
        FAILED=$((FAILED + 1))
    fi

    # استراحة بين الأزواج لتجنب API rate limiting
    if [ "$COUNT" -lt "$TOTAL" ]; then
        echo "  ⏳ استراحة 30 ثانية..." | tee -a "$LOG_FILE"
        sleep 30
    fi
done

echo ""                                                         | tee -a "$LOG_FILE"
echo "=========================================="               | tee -a "$LOG_FILE"
echo "  الحملة انتهت: $COMPLETED نجح، $FAILED فشل"           | tee -a "$LOG_FILE"
echo "  $(date)"                                               | tee -a "$LOG_FILE"
echo "==========================================" | tee -a "$LOG_FILE"

# الملخص النهائي
if [ "$COMPLETED" -gt 0 ]; then
    echo ""                                       | tee -a "$LOG_FILE"
    echo "  --- النتائج النهائية ---"             | tee -a "$LOG_FILE"
    python3 aggregate_results.py 2>&1 | tee -a "$LOG_FILE"
fi

echo ""
echo "📋 يمكنك متابعة الـ log: tail -f $LOG_FILE"
echo "📊 النتائج: cat journal/campaign_summary.md"
