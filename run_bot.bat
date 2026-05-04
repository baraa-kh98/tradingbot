@echo off
title Trading Bot — Auto Restart
color 0A

echo ============================================
echo   Trading Bot — Auto Restart Mode
echo   اضغط Ctrl+C لوقف البوت نهائياً
echo ============================================
echo.

:loop
echo [%date% %time%] تشغيل البوت...
python main.py

echo.
echo [%date% %time%] البوت توقف — إعادة تشغيل بعد 15 ثانية...
echo اضغط Ctrl+C الآن لو تريد تلغي الإعادة
echo.
timeout /t 15 /nobreak

echo.
goto loop
