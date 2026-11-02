@echo off
chcp 65001 >nul
title Cai Dat Khoi Dong SessionKeeper
echo Đang thiết lập SessionKeeper tự khởi động cùng Windows...

set "TARGET_DIR=%~dp0"
set "EXE_PATH=%TARGET_DIR%SessionKeeper.exe"

if not exist "%EXE_PATH%" (
    echo [LỖI] Không tìm thấy file SessionKeeper.exe!
    pause
    exit /b
)

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "SessionKeeperPro" /t REG_SZ /d "\"%EXE_PATH%\" --auto-restore" /f >nul

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo  [THÀNH CÔNG] Đã bật tự khởi động cùng Windows!
    echo  Mỗi khi bật máy, phiên làm việc sẽ tự động mở lại.
    echo ========================================================
) else (
    echo [LỖI] Không thể ghi registry. Vui lòng chạy lại với quyền Administrator.
)

echo.
pause
