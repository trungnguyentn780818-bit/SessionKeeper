@echo off
title Cai Dat Khoi Dong Cung Windows - SessionKeeper Pro
color 0B
echo ========================================================
echo   THIET LAP SESSIONKEEPER TU DONG KHOI DONG CUNG MAY
echo ========================================================
echo.

set "TARGET_DIR=%~dp0"
set "EXE_PATH=%TARGET_DIR%SessionKeeper.exe"

if not exist "%EXE_PATH%" (
    echo [LOI] Khong tim thay file SessionKeeper.exe trong thu muc nay!
    pause
    exit /b
)

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "SessionKeeperPro" /t REG_SZ /d "\"%EXE_PATH%\" --auto-restore" /f >nul

if %errorlevel% equ 0 (
    echo [THANH CONG] Da bat tu khoi dong cung Windows!
    echo Moi khi bat may tinh, cac file lam viec se tu dong duoc mo lai.
) else (
    echo [LOI] Khong the ghi Registry. Vui long chay lai bang cach chuot phai chon "Run as administrator".
)

echo.
pause
