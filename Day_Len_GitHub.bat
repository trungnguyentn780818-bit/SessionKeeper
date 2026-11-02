@echo off
chcp 65001 >nul
title Day Ma Nguon Len GitHub - trungnguyentn780818-bit
echo ========================================================
echo         ĐẨY CẬP NHẬT SESSIONKEEPER LÊN GITHUB
echo ========================================================
echo.

set "GIT_EXE=D:\PhanMem\MinGit\cmd\git.exe"
if not exist "%GIT_EXE%" (
    where git >nul 2>&1
    if %errorlevel% equ 0 (
        set "GIT_EXE=git"
    ) else (
        echo [LỖI] Không tìm thấy git.exe!
        pause
        exit /b
    )
)

echo [1/4] Đang thêm file cập nhật...
"%GIT_EXE%" add .

set /p MSG="Nhập ghi chú cập nhật (hoặc nhấn Enter để dùng mặc định): "
if "%MSG%"=="" set "MSG=Cập nhật phiên bản mới SessionKeeper Pro"

echo [2/4] Đang tạo commit: "%MSG%"...
"%GIT_EXE%" commit -m "%MSG%"

echo.
echo [3/4] Kiểm tra liên kết GitHub...
"%GIT_EXE%" remote -v >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Chưa có liên kết tới kho GitHub của bạn.
    set /p REPO_URL="Nhập link repository GitHub (ví dụ: https://github.com/trungnguyentn780818-bit/SessionKeeper.git): "
    if not "%REPO_URL%"=="" (
        "%GIT_EXE%" remote add origin %REPO_URL%
        "%GIT_EXE%" branch -M main
    )
)

echo.
echo [4/4] Đang đẩy code lên GitHub (git push origin main)...
"%GIT_EXE%" push -u origin main

echo.
if %errorlevel% equ 0 (
    echo ========================================================
    echo  [THÀNH CÔNG] Đã đẩy cập nhật lên GitHub thành công!
    echo ========================================================
) else (
    echo [LƯU Ý] Nếu GitHub hỏi đăng nhập, vui lòng nhập Personal Access Token hoặc xác thực trình duyệt.
)

echo.
pause
