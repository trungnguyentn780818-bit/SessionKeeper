import os
import sys
import re
import json
import time
import subprocess
import urllib.request
import webbrowser
from pathlib import Path

CURRENT_VERSION = "2.3.0"
VERSION_URL = "https://raw.githubusercontent.com/trungnguyentn780818-bit/SessionKeeper/main/version.json"
GITHUB_REPO_URL = "https://github.com/trungnguyentn780818-bit/SessionKeeper"

if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).resolve().parent
    EXE_PATH = Path(sys.executable).resolve()
else:
    APP_DIR = Path(__file__).resolve().parent
    EXE_PATH = APP_DIR / "SessionKeeper.exe"

def parse_version(v_str):
    nums = re.findall(r'\d+', str(v_str))
    return tuple(map(int, nums)) if nums else (0, 0, 0)

def check_for_updates(timeout=4):
    """
    Checks GitHub for a newer version of SessionKeeper.
    Returns: (has_update: bool, info: dict or None)
    """
    try:
        cache_bust_url = f"{VERSION_URL}?t={int(time.time())}"
        req = urllib.request.Request(
            cache_bust_url,
            headers={"User-Agent": f"SessionKeeper-Updater/{CURRENT_VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        remote_ver_str = data.get("version", "0.0.0")
        if parse_version(remote_ver_str) > parse_version(CURRENT_VERSION):
            return True, data
        return False, data
    except Exception as e:
        print(f"Update check error: {e}")
        return False, None

def download_and_apply_update(download_url, progress_callback=None):
    """
    Downloads new SessionKeeper.exe and applies it via a detached batch script.
    """
    try:
        temp_exe = APP_DIR / "SessionKeeper_new.tmp"
        if temp_exe.exists():
            temp_exe.unlink()

        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": f"SessionKeeper-Updater/{CURRENT_VERSION}"}
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 64 * 1024

            with open(temp_exe, "wb") as out_file:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        pct = int((downloaded / total_size) * 100)
                        progress_callback(pct, downloaded, total_size)

        # Kiểm tra file tải về hợp lệ (> 5MB)
        if temp_exe.stat().st_size < 5 * 1024 * 1024:
            if temp_exe.exists():
                temp_exe.unlink()
            return False, "File tải về không hoàn chỉnh (quá nhỏ)."

        # Tạo file batch để thay thế file exe hiện tại và khởi động lại
        bat_file = APP_DIR / "_apply_update.bat"
        target_exe = EXE_PATH.name

        bat_script = f"""@echo off
timeout /t 1 /nobreak >nul
taskkill /f /im "{target_exe}" >nul 2>&1
timeout /t 1 /nobreak >nul
move /y "SessionKeeper_new.tmp" "{target_exe}" >nul
start "" "{target_exe}"
del "%~f0"
"""
        with open(bat_file, "w", encoding="ascii") as f:
            f.write(bat_script)

        # Chạy batch script độc lập và thoát ứng dụng
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat_file)],
            cwd=str(APP_DIR),
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        )
        return True, "Success"

    except Exception as e:
        return False, str(e)

def open_download_page():
    try:
        webbrowser.open(GITHUB_REPO_URL)
    except Exception:
        pass
