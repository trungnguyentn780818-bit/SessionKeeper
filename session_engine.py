import os
import sys
import json
import re
import time
import subprocess
import threading
import winreg
from pathlib import Path

try:
    import win32gui
    import win32process
    import win32con
    import win32api
    import win32service
    import win32com.client
    import pythoncom
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "sessions.json"
CONFIG_FILE = BASE_DIR / "config.json"

STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_NAME = "SessionKeeperPro"

IGNORE_NAMES = {
    "svchost.exe", "conhost.exe", "runtimebroker.exe", "csrss.exe", "dwm.exe",
    "shellexperiencehost.exe", "searchhost.exe", "startmenuexperiencehost.exe",
    "taskhostw.exe", "sihost.exe", "ctfmon.exe", "fontdrvhost.exe", "smartscreen.exe",
    "widgetboard.exe", "widgetservice.exe", "textinputhost.exe", "securityhealthsystray.exe",
    "adskaccesscore.exe", "adskaccessservicehost.exe", "adskaccessuihost.exe", "adsklicensingagent.exe",
    "adskidentitymanager.exe", "adpclientservice.exe", "msedgewebview2.exe", "python.exe", "python3.13.exe",
    "pythonw.exe", "powershell.exe", "cmd.exe", "prevhost.exe", "splwow64.exe", "useroobebroker.exe",
    "wmiapsrv.exe", "dell.techhub.instrumentation.userprocess.exe", "rtkauduservice64.exe", "sessionkeeper.exe"
}

def load_config():
    default_cfg = {
        "auto_restore_on_startup": False,
        "auto_snapshot_enabled": True,
        "auto_snapshot_interval_mins": 10,
        "restore_window_layout": True,
        "global_hotkeys_enabled": True,
        "minimize_to_tray": True,
        "restore_delay_seconds": 0.4,
        "last_saved_time": ""
    }
    if not CONFIG_FILE.exists():
        save_config(default_cfg)
        return default_cfg
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            for k, v in default_cfg.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception:
        return default_cfg

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")

def is_windows_startup():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, STARTUP_NAME)
            return bool(val)
    except Exception:
        return False

def set_windows_startup(enable=True):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                exe_file = BASE_DIR / "SessionKeeper.exe"
                if exe_file.exists():
                    cmd = f'"{exe_file}" --auto-restore'
                else:
                    pythonw = Path(sys.executable).parent / "pythonw.exe"
                    if not pythonw.exists():
                        pythonw = Path(sys.executable)
                    cmd = f'"{pythonw}" "{BASE_DIR / "app.py"}" --auto-restore'
                winreg.SetValueEx(key, STARTUP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, STARTUP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print(f"Error configuring startup: {e}")
        return False

def scan_desktop_windows():
    """Ultra-fast, non-blocking single pass for open CAD tabs, MicroStation docs, and window layouts"""
    drawings = set()
    micro_docs = set()
    layouts = {}

    def runner():
        try:
            h_winsta = win32service.OpenWindowStation('WinSta0', False, win32con.GENERIC_ALL)
            h_winsta.SetProcessWindowStation()
            h_desk = win32service.OpenDesktop('Default', 0, False, win32con.GENERIC_ALL)
            h_desk.SetThreadDesktop()
        except Exception:
            pass

        def enum_cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            c = win32gui.GetClassName(hwnd)
            t = win32gui.GetWindowText(hwnd).strip()

            # 1. AutoCAD open drawing tabs (AcTaskBarWin has 100% 1-to-1 tabs in AutoCAD)
            if c == 'AcTaskBarWin' and t.lower().endswith(('.dwg', '.dxf')):
                drawings.add(t)
            elif ('autocad' in t.lower() or 'acad' in c.lower() or 'afxmdiframe' in c.lower()) and '[' in t:
                if '.dwg' in t.lower() or '.dxf' in t.lower():
                    s = t.find('[')
                    e = t.find(']', s)
                    if s != -1 and e != -1:
                        dname = t[s+1:e].strip()
                        if dname:
                            drawings.add(dname)

            # 2. MicroStation open documents
            if '.dgn' in t.lower() and ('microstation' in t.lower() or 'mstn' in c.lower()):
                for part in t.split():
                    if part.lower().endswith('.dgn'):
                        micro_docs.add(part)

            # 3. Window layouts by Process ID
            if not win32gui.GetParent(hwnd):
                try:
                    _, wpid = win32process.GetWindowThreadProcessId(hwnd)
                    if wpid and wpid not in layouts:
                        rect = win32gui.GetWindowRect(hwnd)
                        w = rect[2] - rect[0]
                        h = rect[3] - rect[1]
                        if w > 100 and h > 100:
                            placement = win32gui.GetWindowPlacement(hwnd)
                            layouts[wpid] = {
                                'rect': [rect[0], rect[1], w, h],
                                'state': placement[1]
                            }
                except Exception:
                    pass

        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception:
            pass

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout=1.5)
    return list(drawings), list(micro_docs), layouts

def get_window_layout(pid):
    _, _, layouts = scan_desktop_windows()
    return layouts.get(pid)

def apply_window_layout(hwnd, layout):
    if not HAS_WIN32 or not layout:
        return
    try:
        state = layout.get("state", 1)
        rect = layout.get("rect")
        if state == 3:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        elif rect and len(rect) == 4:
            x, y, w, h = rect
            win32gui.ShowWindow(hwnd, win32con.SW_SHOWNORMAL)
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_NOTOPMOST,
                x, y, w, h,
                win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
            )
    except Exception:
        pass

def get_running_processes_wmi():
    """Query processes in-process via COM (Zero subprocess, zero CMD popup)"""
    procs = []
    try:
        pythoncom.CoInitialize()
        wmi = win32com.client.GetObject("winmgmts:")
        query_res = wmi.ExecQuery("SELECT ProcessId, Name, ExecutablePath, CommandLine FROM Win32_Process WHERE SessionId != 0")
        for p in query_res:
            exe = p.ExecutablePath
            if exe:
                procs.append({
                    "ProcessId": int(p.ProcessId),
                    "Name": str(p.Name or ""),
                    "ExecutablePath": str(exe),
                    "CommandLine": str(p.CommandLine or "")
                })
    except Exception:
        pass
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return procs

def get_open_explorer_folders():
    folders = []
    try:
        pythoncom.CoInitialize()
        shell = win32com.client.Dispatch("Shell.Application")
        for w in shell.Windows():
            try:
                p = w.Document.Folder.Self.Path
                if p and os.path.isdir(p) and not p.startswith("::{"):
                    if p not in folders:
                        folders.append(p)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return folders

def resolve_drawing_full_path(dwg_name, explorer_folders):
    """Resolve absolute path for an actively open drawing without freezing"""
    # 1. Search in open explorer folders
    for fold in explorer_folders:
        cand = os.path.join(fold, dwg_name)
        if os.path.exists(cand):
            return cand

    # 2. Check AutoCAD Recent File List from registry
    try:
        base_key = r"Software\Autodesk\AutoCAD"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base_key) as k1:
            for i in range(winreg.QueryInfoKey(k1)[0]):
                ver = winreg.EnumKey(k1, i)
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{base_key}\\{ver}") as k2:
                        for j in range(winreg.QueryInfoKey(k2)[0]):
                            sub = winreg.EnumKey(k2, j)
                            recent_key = f"{base_key}\\{ver}\\{sub}\\Recent File List"
                            try:
                                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, recent_key) as rk:
                                    for idx in range(1, 100):
                                        try:
                                            val, _ = winreg.QueryValueEx(rk, f"File{idx}")
                                            if val and os.path.basename(val).lower() == dwg_name.lower() and os.path.exists(val):
                                                return val
                                        except Exception:
                                            break
                            except Exception:
                                pass
                except Exception:
                    pass
    except Exception:
        pass

    # 3. Fast scan in project roots (shallow, max 1 level)
    for sdir in [r"D:\!!!CHUYEN TRACH CSDL KH 483\LONGBINH", r"D:\4.90 NGAY DEM\CATLAI", r"D:\Downloads"]:
        if os.path.isdir(sdir):
            cand = os.path.join(sdir, dwg_name)
            if os.path.exists(cand):
                return cand
            try:
                for entry in os.scandir(sdir):
                    if entry.is_dir():
                        sub_cand = os.path.join(entry.path, dwg_name)
                        if os.path.exists(sub_cand):
                            return sub_cand
            except Exception:
                pass

    return dwg_name

def get_truly_open_autocad_drawings():
    dwgs, _, _ = scan_desktop_windows()
    return dwgs

def get_truly_open_microstation_docs():
    _, micros, _ = scan_desktop_windows()
    return micros

def scan_session():
    """Precise session scanner: Exact active files, ZERO ghost files, ZERO duplicate apps"""
    truly_open_cad, truly_open_micro, layouts_map = scan_desktop_windows()
    procs = get_running_processes_wmi()
    items = []
    seen = set()

    explorer_folders = get_open_explorer_folders()

    has_autocad_proc = False
    acad_exe = r"C:\Program Files\Autodesk\AutoCAD 2023\acad.exe"

    has_micro_proc = False
    micro_exe = r"C:\Program Files (x86)\Bentley\MicroStation V8i (SELECTseries)\MicroStation\ustation.exe"

    has_excel_file = False
    excel_exe = r"C:\Program Files\Microsoft Office\Root\Office16\EXCEL.EXE"
    excel_files_found = []

    # 1. Process scan for Browsers, Zalo, Excel, Word, etc.
    for p in procs:
        pid = p.get("ProcessId")
        name = (p.get("Name") or "").lower()
        exe = p.get("ExecutablePath") or ""
        cli = p.get("CommandLine") or ""

        if not exe or name in IGNORE_NAMES:
            continue

        layout = layouts_map.get(pid)

        # Chrome
        if name == "chrome.exe":
            if "--type=" in cli:
                continue
            key = "browser_chrome"
            if key not in seen:
                seen.add(key)
                items.append({
                    "id": key, "type": "browser", "category": "Trình duyệt",
                    "name": "Google Chrome", "detail": "Khôi phục toàn bộ Tabs",
                    "exe": exe, "args": ["--restore-last-session"], "layout": layout, "enabled": True
                })
            continue

        # Edge
        if name == "msedge.exe":
            if "--type=" in cli:
                continue
            key = "browser_edge"
            if key not in seen:
                seen.add(key)
                items.append({
                    "id": key, "type": "browser", "category": "Trình duyệt",
                    "name": "Microsoft Edge", "detail": "Khôi phục toàn bộ Tabs",
                    "exe": exe, "args": ["--restore-last-session"], "layout": layout, "enabled": True
                })
            continue

        # Zalo
        if "zalo" in name:
            if "--type=" in cli:
                continue
            key = "app_zalo"
            if key not in seen:
                seen.add(key)
                items.append({
                    "id": key, "type": "app", "category": "Liên lạc",
                    "name": "Zalo PC", "detail": exe,
                    "exe": exe, "args": [], "layout": layout, "enabled": True
                })
            continue

        # AutoCAD process check
        if name == "acad.exe":
            has_autocad_proc = True
            acad_exe = exe
            continue

        # MicroStation process check
        if name == "ustation.exe":
            has_micro_proc = True
            micro_exe = exe
            continue

        # Excel
        if name == "excel.exe":
            excel_exe = exe
            m = re.search(r'"([A-Za-z]:\\[^"]+\.(?:xlsx|xls|csv))"', cli, re.IGNORECASE)
            if not m:
                m = re.search(r'([A-Za-z]:\\[^\s"]+\.(?:xlsx|xls|csv))', cli, re.IGNORECASE)
            if m and os.path.exists(m.group(1)):
                fpath = m.group(1)
                fname = os.path.basename(fpath)
                k = f"excel_file_{fpath.lower()}"
                if k not in seen:
                    seen.add(k)
                    has_excel_file = True
                    excel_files_found.append({
                        "id": k, "type": "file", "category": "Bảng tính",
                        "name": fname, "detail": fpath,
                        "exe": exe, "target": fpath, "layout": layout, "enabled": True
                    })
            continue

        # Word
        if name == "winword.exe":
            m = re.search(r'"([A-Za-z]:\\[^"]+\.(?:docx|doc))"', cli, re.IGNORECASE)
            if not m:
                m = re.search(r'([A-Za-z]:\\[^\s"]+\.(?:docx|doc))', cli, re.IGNORECASE)
            if m and os.path.exists(m.group(1)):
                fpath = m.group(1)
                fname = os.path.basename(fpath)
                k = f"word_file_{fpath.lower()}"
                if k not in seen:
                    seen.add(k)
                    items.append({
                        "id": k, "type": "file", "category": "Văn bản",
                        "name": fname, "detail": fpath,
                        "exe": exe, "target": fpath, "layout": layout, "enabled": True
                    })
            continue

    # 2. Add Excel: ONLY add the open file(s)! NEVER add duplicate generic "Microsoft Excel"!
    if excel_files_found:
        items.extend(excel_files_found)
    elif any(p.get("Name", "").lower() == "excel.exe" for p in procs):
        # Excel is running with NO file open at all
        items.append({
            "id": "app_excel", "type": "app", "category": "Bảng tính",
            "name": "Microsoft Excel", "detail": excel_exe,
            "exe": excel_exe, "args": [], "enabled": True
        })

    # 3. Add AutoCAD: ONLY add drawings that are ACTUALLY OPEN right now!
    if truly_open_cad:
        for dwg in truly_open_cad:
            full_path = resolve_drawing_full_path(dwg, explorer_folders)
            k = f"cad_{dwg.lower()}"
            if k not in seen:
                seen.add(k)
                items.append({
                    "id": k, "type": "file", "category": "Bản vẽ CAD",
                    "name": dwg, "detail": full_path,
                    "exe": acad_exe, "target": full_path, "enabled": True
                })
    elif has_autocad_proc:
        # AutoCAD is open with NO drawing
        items.append({
            "id": "app_acad", "type": "app", "category": "Bản vẽ CAD",
            "name": "AutoCAD 2023", "detail": acad_exe,
            "exe": acad_exe, "args": [], "enabled": True
        })

    # 4. Add MicroStation: ONLY add open .dgn or generic app (No duplicate)
    if truly_open_micro:
        for dgn in truly_open_micro:
            dgn_path = dgn
            for fold in explorer_folders:
                cand = os.path.join(fold, dgn)
                if os.path.exists(cand):
                    dgn_path = cand
                    break
            if not os.path.exists(dgn_path):
                for sdir in [r"D:\!!!CHUYEN TRACH CSDL KH 483\LONGBINH", r"D:\4.90 NGAY DEM\CATLAI"]:
                    if os.path.isdir(sdir):
                        for root, _, files in os.walk(sdir):
                            for f in files:
                                if f.lower() == dgn.lower():
                                    dgn_path = os.path.join(root, f)
                                    break
                            if os.path.exists(dgn_path):
                                break
                    if os.path.exists(dgn_path):
                        break
            k = f"micro_{dgn.lower()}"
            if k not in seen:
                seen.add(k)
                items.append({
                    "id": k, "type": "file", "category": "MicroStation",
                    "name": dgn, "detail": dgn_path,
                    "exe": micro_exe, "target": dgn_path, "enabled": True
                })
    elif has_micro_proc:
        items.append({
            "id": "app_micro", "type": "app", "category": "MicroStation",
            "name": "MicroStation V8i", "detail": micro_exe,
            "exe": micro_exe, "args": [], "enabled": True
        })

    # 5. Open Explorer folders
    for fold in explorer_folders:
        f_key = f"folder_{fold.lower()}"
        if f_key not in seen:
            seen.add(f_key)
            items.append({
                "id": f_key, "type": "folder", "category": "Thư mục",
                "name": os.path.basename(fold) or fold, "detail": fold,
                "target": fold, "enabled": True
            })

    return items

def load_all_sessions():
    if not DATA_FILE.exists():
        return {"latest": [], "profiles": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return {"latest": data, "profiles": {}}
            return data
    except Exception as e:
        print(f"Error loading sessions: {e}")
        return {"latest": [], "profiles": {}}

def save_all_sessions(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving sessions: {e}")
        return False

def save_session(items, profile_name="latest"):
    data = load_all_sessions()
    if profile_name == "latest":
        data["latest"] = items
    else:
        if "profiles" not in data:
            data["profiles"] = {}
        data["profiles"][profile_name] = {
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "items": items
        }
    return save_all_sessions(data)

def get_session(profile_name="latest"):
    data = load_all_sessions()
    if profile_name == "latest":
        return data.get("latest", [])
    return data.get("profiles", {}).get(profile_name, {}).get("items", [])

def restore_session(profile_name="latest", delay=0.4, restore_layout=True, progress_callback=None):
    items = get_session(profile_name)
    launched = []
    errors = []

    for idx, item in enumerate(items):
        if not item.get("enabled", True):
            continue

        itype = item.get("type")
        name = item.get("name", "Unknown")
        layout = item.get("layout")

        if progress_callback:
            progress_callback(name, idx + 1, len(items))

        try:
            proc = None
            if itype == "browser":
                exe = item.get("exe")
                args = item.get("args", ["--restore-last-session"])
                if exe and os.path.exists(exe):
                    proc = subprocess.Popen([exe] + args, creationflags=subprocess.CREATE_NO_WINDOW)
                    launched.append(name)
                else:
                    errors.append(f"{name}: Không tìm thấy")

            elif itype == "file":
                target = item.get("target")
                exe = item.get("exe")
                if target and os.path.exists(target):
                    if exe and os.path.exists(exe):
                        proc = subprocess.Popen([exe, target], creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        os.startfile(target)
                    launched.append(name)
                else:
                    # If target is just filename, try to launch with exe
                    if exe and os.path.exists(exe) and target:
                        proc = subprocess.Popen([exe, target], creationflags=subprocess.CREATE_NO_WINDOW)
                        launched.append(name)
                    else:
                        errors.append(f"{name}: Không tồn tại")

            elif itype == "folder":
                target = item.get("target")
                if target and os.path.exists(target):
                    os.startfile(target)
                    launched.append(name)
                else:
                    errors.append(f"{name}: Thư mục không tồn tại")

            elif itype == "app":
                exe = item.get("exe")
                args = item.get("args", [])
                if exe and os.path.exists(exe):
                    if args:
                        proc = subprocess.Popen([exe] + args, creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        os.startfile(exe)
                    launched.append(name)
                else:
                    errors.append(f"{name}: Không tìm thấy")

            # Restore layout
            if restore_layout and layout and proc and HAS_WIN32:
                def delayed_layout(p_id, l_out):
                    time.sleep(2.0)
                    def find_enum(h, _):
                        if win32gui.IsWindowVisible(h):
                            try:
                                _, w_id = win32process.GetWindowThreadProcessId(h)
                                if w_id == p_id:
                                    apply_window_layout(h, l_out)
                            except Exception:
                                pass
                    try:
                        win32gui.EnumWindows(find_enum, None)
                    except Exception:
                        pass
                threading.Thread(target=delayed_layout, args=(proc.pid, layout), daemon=True).start()

            if delay > 0:
                time.sleep(delay)

        except Exception as e:
            errors.append(f"{name}: {str(e)}")

    return launched, errors

def shutdown_system(delay=5, comment="SessionKeeper tat may"):
    subprocess.run(["shutdown", "/s", "/t", str(delay), "/c", comment], creationflags=subprocess.CREATE_NO_WINDOW)

def hibernate_system():
    try:
        import ctypes
        ctypes.windll.PowrProf.SetSuspendState(1, 1, 0)
    except Exception:
        subprocess.run(["shutdown", "/h"], creationflags=subprocess.CREATE_NO_WINDOW)

def cancel_shutdown():
    subprocess.run(["shutdown", "/a"], creationflags=subprocess.CREATE_NO_WINDOW)

# Background auto-snapshot thread (100% in-process, zero subprocess)
_snapshot_thread = None
_stop_snapshot = threading.Event()

def _auto_snapshot_worker(interval_mins, callback=None):
    # 1. Take initial auto-snapshot 20 seconds after app starts
    if not _stop_snapshot.wait(timeout=20):
        try:
            items = scan_session()
            if items:
                save_session(items, profile_name="auto_snapshot")
                if callback:
                    callback(time.strftime("%Y-%m-%d %H:%M:%S"), len(items))
        except Exception as e:
            print(f"Auto snapshot error: {e}")

    # 2. Recurring auto-snapshots every interval_mins
    while not _stop_snapshot.is_set():
        if _stop_snapshot.wait(timeout=interval_mins * 60):
            break
        try:
            items = scan_session()
            if items:
                save_session(items, profile_name="auto_snapshot")
                if callback:
                    callback(time.strftime("%Y-%m-%d %H:%M:%S"), len(items))
        except Exception as e:
            print(f"Auto snapshot error: {e}")

def start_auto_snapshot(interval_mins=10, callback=None):
    global _snapshot_thread, _stop_snapshot
    stop_auto_snapshot()
    _stop_snapshot.clear()
    _snapshot_thread = threading.Thread(target=_auto_snapshot_worker, args=(interval_mins, callback), daemon=True)
    _snapshot_thread.start()

def stop_auto_snapshot():
    global _stop_snapshot
    _stop_snapshot.set()

# Global Hotkeys Listener (0% CPU event-driven)
_hotkey_thread = None
_stop_hotkeys = False

def start_global_hotkeys(on_save, on_restore, on_hibernate):
    global _hotkey_thread, _stop_hotkeys
    if not HAS_WIN32:
        return
    _stop_hotkeys = False

    def hotkey_worker():
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        HOTKEY_SAVE = 101
        HOTKEY_RESTORE = 102
        HOTKEY_HIBERNATE = 103

        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        MOD_NOREPEAT = 0x4000

        user32.RegisterHotKey(None, HOTKEY_SAVE, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord('S'))
        user32.RegisterHotKey(None, HOTKEY_RESTORE, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord('R'))
        user32.RegisterHotKey(None, HOTKEY_HIBERNATE, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord('H'))

        msg = wintypes.MSG()
        while not _stop_hotkeys:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                break
            if msg.message == 0x0312:
                hid = msg.wParam
                if hid == HOTKEY_SAVE and on_save:
                    on_save()
                elif hid == HOTKEY_RESTORE and on_restore:
                    on_restore()
                elif hid == HOTKEY_HIBERNATE and on_hibernate:
                    on_hibernate()
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnregisterHotKey(None, HOTKEY_SAVE)
        user32.UnregisterHotKey(None, HOTKEY_RESTORE)
        user32.UnregisterHotKey(None, HOTKEY_HIBERNATE)

    _hotkey_thread = threading.Thread(target=hotkey_worker, daemon=True)
    _hotkey_thread.start()

def stop_global_hotkeys():
    global _stop_hotkeys, _hotkey_thread
    _stop_hotkeys = True
    if _hotkey_thread and _hotkey_thread.ident:
        try:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(_hotkey_thread.ident, 0x0012, 0, 0)
        except Exception:
            pass
