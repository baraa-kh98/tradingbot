@echo off
chcp 65001 > nul
title إعداد التشغيل التلقائي للبوت
color 0B

echo ============================================
echo   إعداد التشغيل التلقائي عند بدء Windows
echo ============================================
echo.

REM الحصول على المسار الحالي
set BOT_DIR=%~dp0
set BAT_FILE=%BOT_DIR%run_bot.bat

echo مسار البوت: %BOT_DIR%
echo ملف التشغيل: %BAT_FILE%
echo.

REM إضافة Task Scheduler يشتغل عند تسجيل الدخول
echo جاري إضافة المهمة التلقائية...
schtasks /create /tn "TradingBot" /tr "%BAT_FILE%" /sc ONLOGON /rl HIGHEST /f

if %errorlevel% == 0 (
    echo.
    echo ============================================
    echo  تم بنجاح! البوت سيشتغل تلقائياً عند:
    echo  - بدء تشغيل Windows
    echo  - تسجيل الدخول
    echo ============================================
    echo.
    echo للتحقق: افتح Task Scheduler وابحث عن "TradingBot"
    echo لإلغاء التلقائي: schtasks /delete /tn "TradingBot" /f
) else (
    echo.
    echo ============================================
    echo  فشل! جرّب تشغيل هذا الملف كـ Administrator
    echo  كليك يمين على الملف ثم "Run as administrator"
    echo ============================================
)

echo.
pause
