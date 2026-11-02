@echo off
title Day Ma Nguon Len GitHub - SessionKeeper Pro
color 0A
echo ========================================================
echo         DONG BO SESSIONKEEPER LEN GITHUB
echo ========================================================
echo.

set "GIT_EXE=D:\PhanMem\MinGit\cmd\git.exe"
if not exist "%GIT_EXE%" set "GIT_EXE=git"

echo [1/3] Kiem tra va them cac file moi...
"%GIT_EXE%" add .

set /p MSG="Nhap ghi chu cap nhat (hoac Enter de dung mac dinh): "
if "%MSG%"=="" set "MSG=Cap nhat phien ban SessionKeeper Pro"

"%GIT_EXE%" commit -m "%MSG%" >nul 2>&1

echo.
echo [2/3] Kiem tra ket noi GitHub...
"%GIT_EXE%" remote set-url origin https://github.com/trungnguyentn780818-bit/SessionKeeper.git

echo.
echo [3/3] Dang day ma nguon len GitHub...
echo.
"%GIT_EXE%" push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo  [THANH CONG] Da dong bo ma nguon len GitHub!
    echo  Xem tai: https://github.com/trungnguyentn780818-bit/SessionKeeper
    echo ========================================================
) else (
    echo.
    echo ========================================================
    echo  [HUONG DAN DANG NHAP GITHUB]
    echo  Khi Git hoi:
    echo    Username: trungnguyentn780818-bit
    echo    Password: Dan ma Token (ghp_...) tao tai:
    echo              https://github.com/settings/tokens
    echo ========================================================
)

echo.
pause
