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

def is_process_running(proc_name):
    try:
        r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {proc_name}"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return proc_name.lower() in r.stdout.lower()
    except Exception:
        return False

def get_autocad_launcher():
    candidates = [
        r"C:\Program Files\Common Files\Autodesk Shared\AcShellEx\AcLauncher.exe",
        r"C:\Program Files (x86)\Common Files\Autodesk Shared\AcShellEx\AcLauncher.exe"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def restore_folders_in_tabs(folder_items, progress_callback=None, total_count=0, current_idx=0, launched=None, errors=None):
    """
    Khôi phục danh sách thư mục lồng thành các Tab trong cùng 1 cửa sổ File Explorer duy nhất.
    Sử dụng thông điệp hệ thống WM_COMMAND 0xA21B (41499) và COM Navigate của Windows 11.
    """
    if launched is None:
        launched = []
    if errors is None:
        errors = []

    valid_folders = [it for it in folder_items if it.get("target") and os.path.exists(it["target"])]
    if not valid_folders:
        for it in folder_items:
            errors.append(f"{it.get('name')}: Thư mục không tồn tại")
        return current_idx

    # Đảm bảo luồng ngầm liên kết với WinSta0 và Desktop Default
    try:
        h_winsta = win32service.OpenWindowStation('WinSta0', False, win32con.GENERIC_ALL)
        h_winsta.SetProcessWindowStation()
        h_desk = win32service.OpenDesktop('Default', 0, False, win32con.GENERIC_ALL)
        h_desk.SetThreadDesktop()
    except Exception:
        pass

    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    shell = None
    try:
        shell = win32com.client.Dispatch("Shell.Application")
    except Exception:
        pass

    def get_cabinet_hwnd():
        hwnd = None
        def enum_cb(h, _):
            nonlocal hwnd
            if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == 'CabinetWClass':
                hwnd = h
        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception:
            pass
        return hwnd

    hwnd_cabinet = get_cabinet_hwnd()
    start_idx = 0

    # Nếu chưa có cửa sổ File Explorer nào mở, khởi chạy thư mục đầu tiên để tạo cửa sổ
    if not hwnd_cabinet:
        first_it = valid_folders[0]
        current_idx += 1
        name = first_it.get("name", "Folder")
        target = first_it["target"]
        if progress_callback:
            progress_callback(f"Mở Explorer: {name}", current_idx, total_count)
        os.startfile(target)
        launched.append(name)
        start_idx = 1

        # Chờ tối đa 3 giây cho cửa sổ File Explorer hiển thị và nạp xong giao diện
        for _ in range(15):
            time.sleep(0.2)
            hwnd_cabinet = get_cabinet_hwnd()
            if hwnd_cabinet:
                time.sleep(0.5)
                break

    # Nếu không tìm thấy cửa sổ (ví dụ Win 10), mở bình thường các thư mục còn lại
    if not hwnd_cabinet or not shell:
        for it in valid_folders[start_idx:]:
            current_idx += 1
            name = it.get("name", "Folder")
            if progress_callback:
                progress_callback(name, current_idx, total_count)
            try:
                os.startfile(it["target"])
                launched.append(name)
            except Exception as e:
                errors.append(f"{name}: {e}")
            time.sleep(0.3)
        return current_idx

    # Mở tất cả các thư mục còn lại lồng thành các Tab trong cửa sổ File Explorer đó
    for it in valid_folders[start_idx:]:
        current_idx += 1
        name = it.get("name", "Folder")
        target = it["target"]
        if progress_callback:
            progress_callback(f"Tạo Tab: {name}", current_idx, total_count)

        tabs = []
        def enum_tab(h, _):
            if win32gui.GetClassName(h) == 'ShellTabWindowClass':
                tabs.append(h)
        try:
            win32gui.EnumChildWindows(hwnd_cabinet, enum_tab, None)
        except Exception:
            pass

        if not tabs:
            os.startfile(target)
            launched.append(name)
            time.sleep(0.3)
            continue

        try:
            prev_count = shell.Windows().Count
            # Gửi thông điệp hệ thống WM_COMMAND 0xA21B (41499) để tạo Tab mới trong Windows 11
            win32gui.SendMessage(tabs[0], 0x0111, 0xA21B, 0)

            # Chờ Tab mới xuất hiện trong Shell.Windows()
            new_tab = None
            for _ in range(12):
                time.sleep(0.12)
                if shell.Windows().Count > prev_count:
                    new_tab = shell.Windows().Item(shell.Windows().Count - 1)
                    break

            if new_tab:
                new_tab.Navigate(target)
                launched.append(name)
            else:
                os.startfile(target)
                launched.append(name)
        except Exception as e:
            errors.append(f"{name}: {e}")

        time.sleep(0.2)

    for it in folder_items:
        if not it.get("target") or not os.path.exists(it.get("target")):
            errors.append(f"{it.get('name')}: Thư mục không tồn tại")

    return current_idx

def restore_session(profile_name="latest", delay=0.4, restore_layout=True, progress_callback=None):
    items = get_session(profile_name)
    launched = []
    errors = []

    # Lọc các mục được kích hoạt
    enabled_items = [it for it in items if it.get("enabled", True)]
    total_count = len(enabled_items)
    current_idx = 0

    # Phân loại để mở lồng tab trong cùng 1 cửa sổ duy nhất:
    cad_items = []
    excel_items = []
    word_items = []
    browser_items = []
    app_items = []
    folder_items = []
    other_items = []

    for it in enabled_items:
        itype = it.get("type")
        exe = (it.get("exe") or "").lower()
        target = (it.get("target") or "").lower()
        cat = (it.get("category") or "").lower()

        if itype == "browser":
            browser_items.append(it)
        elif itype == "folder":
            folder_items.append(it)
        elif itype == "app":
            app_items.append(it)
        elif itype == "file":
            if "acad.exe" in exe or target.endswith((".dwg", ".dxf")) or "cad" in cat:
                cad_items.append(it)
            elif "excel.exe" in exe or target.endswith((".xlsx", ".xls", ".csv")):
                excel_items.append(it)
            elif "winword.exe" in exe or target.endswith((".docx", ".doc")):
                word_items.append(it)
            else:
                other_items.append(it)
        else:
            other_items.append(it)

    # 1. Khôi phục trình duyệt (mở lại toàn bộ các tab đã lưu trong 1 cửa sổ)
    for it in browser_items:
        current_idx += 1
        name = it.get("name", "Browser")
        if progress_callback:
            progress_callback(name, current_idx, total_count)
        exe = it.get("exe")
        args = it.get("args", ["--restore-last-session"])
        if exe and os.path.exists(exe):
            try:
                subprocess.Popen([exe] + args, creationflags=subprocess.CREATE_NO_WINDOW)
                launched.append(name)
            except Exception as e:
                errors.append(f"{name}: {e}")
        else:
            errors.append(f"{name}: Không tìm thấy trình duyệt")
        if delay > 0:
            time.sleep(delay)

    # 2. Khôi phục bản vẽ CAD (Lồng toàn bộ bản vẽ thành các Tab trong cùng 1 cửa sổ CAD)
    if cad_items:
        ac_launcher = get_autocad_launcher()
        valid_cad = [it for it in cad_items if it.get("target") and os.path.exists(it["target"])]

        if valid_cad:
            cad_targets = [it["target"] for it in valid_cad]
            acad_running = is_process_running("acad.exe")

            # Nếu AutoCAD chưa chạy, khởi chạy bản vẽ đầu tiên và đợi khởi tạo xong listener
            if not acad_running:
                first_it = valid_cad[0]
                first_target = first_it["target"]
                current_idx += 1
                if progress_callback:
                    progress_callback(f"Mở AutoCAD: {first_it.get('name')}", current_idx, total_count)
                try:
                    if ac_launcher:
                        subprocess.Popen([ac_launcher, "/O", first_target], creationflags=subprocess.CREATE_NO_WINDOW)
                    elif first_it.get("exe") and os.path.exists(first_it["exe"]):
                        subprocess.Popen([first_it["exe"], first_target], creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        os.startfile(first_target)
                    launched.append(first_it.get("name"))
                except Exception as e:
                    errors.append(f"{first_it.get('name')}: {e}")

                # Chờ AutoCAD hiển thị giao diện và đăng ký DDE/COM listener (tối đa 4s)
                for _ in range(8):
                    if is_process_running("acad.exe"):
                        time.sleep(1.5)
                        break
                    time.sleep(0.5)

                remaining = valid_cad[1:]
            else:
                remaining = valid_cad

            # Mở tất cả các bản vẽ còn lại lồng vào cửa sổ AutoCAD đang mở thành từng Tab
            for it in remaining:
                current_idx += 1
                name = it.get("name", "CAD Drawing")
                target = it["target"]
                if progress_callback:
                    progress_callback(name, current_idx, total_count)
                try:
                    if ac_launcher:
                        subprocess.Popen([ac_launcher, "/O", target], creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        os.startfile(target)
                    launched.append(name)
                except Exception as e:
                    errors.append(f"{name}: {e}")
                time.sleep(0.3)

        for it in cad_items:
            if not it.get("target") or not os.path.exists(it.get("target")):
                errors.append(f"{it.get('name')}: Tệp bản vẽ không tồn tại")

    # 3. Khôi phục bảng tính Excel (Mở toàn bộ sổ làm việc trong cùng 1 cửa sổ Excel)
    if excel_items:
        valid_excel = [it for it in excel_items if it.get("target") and os.path.exists(it["target"])]
        if valid_excel:
            excel_exe = None
            for it in valid_excel:
                if it.get("exe") and os.path.exists(it["exe"]):
                    excel_exe = it["exe"]
                    break

            excel_targets = [it["target"] for it in valid_excel]
            for it in valid_excel:
                current_idx += 1
                if progress_callback:
                    progress_callback(it.get("name"), current_idx, total_count)
                launched.append(it.get("name"))

            try:
                if excel_exe:
                    # Truyền tất cả các file cùng lúc vào excel.exe để mở lồng trong 1 cửa sổ
                    subprocess.Popen([excel_exe] + excel_targets, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    for t in excel_targets:
                        os.startfile(t)
                        time.sleep(0.3)
            except Exception as e:
                errors.append(f"Excel: {e}")

        for it in excel_items:
            if not it.get("target") or not os.path.exists(it.get("target")):
                errors.append(f"{it.get('name')}: Tệp Excel không tồn tại")

    # 4. Khôi phục tài liệu Word (Mở trong 1 phiên Word)
    if word_items:
        valid_word = [it for it in word_items if it.get("target") and os.path.exists(it["target"])]
        if valid_word:
            word_exe = None
            for it in valid_word:
                if it.get("exe") and os.path.exists(it["exe"]):
                    word_exe = it["exe"]
                    break
            word_targets = [it["target"] for it in valid_word]
            for it in valid_word:
                current_idx += 1
                if progress_callback:
                    progress_callback(it.get("name"), current_idx, total_count)
                launched.append(it.get("name"))
            try:
                if word_exe:
                    subprocess.Popen([word_exe] + word_targets, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    for t in word_targets:
                        os.startfile(t)
                        time.sleep(0.3)
            except Exception as e:
                errors.append(f"Word: {e}")

        for it in word_items:
            if not it.get("target") or not os.path.exists(it.get("target")):
                errors.append(f"{it.get('name')}: Tệp Word không tồn tại")

    # 5. Khôi phục các tệp khác (MicroStation .dgn, PDF...)
    for it in other_items:
        current_idx += 1
        name = it.get("name", "File")
        target = it.get("target")
        exe = it.get("exe")
        layout = it.get("layout")
        if progress_callback:
            progress_callback(name, current_idx, total_count)
        if target and os.path.exists(target):
            try:
                proc = None
                if exe and os.path.exists(exe):
                    proc = subprocess.Popen([exe, target], creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    os.startfile(target)
                launched.append(name)

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

            except Exception as e:
                errors.append(f"{name}: {e}")
        else:
            errors.append(f"{name}: Không tìm thấy tệp")
        if delay > 0:
            time.sleep(delay)

    # 6. Khôi phục thư mục (Lồng thành các Tab trong cùng 1 cửa sổ File Explorer duy nhất)
    if folder_items:
        current_idx = restore_folders_in_tabs(
            folder_items,
            progress_callback=progress_callback,
            total_count=total_count,
            current_idx=current_idx,
            launched=launched,
            errors=errors
        )

    # 7. Khôi phục ứng dụng độc lập (tránh mở trùng 1 app nhiều lần)
    launched_app_exes = set()
    for it in app_items:
        current_idx += 1
        name = it.get("name", "App")
        exe = it.get("exe")
        args = it.get("args", [])
        if progress_callback:
            progress_callback(name, current_idx, total_count)
        if exe and os.path.exists(exe):
            if exe.lower() in launched_app_exes:
                continue
            launched_app_exes.add(exe.lower())
            try:
                if args:
                    subprocess.Popen([exe] + args, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    os.startfile(exe)
                launched.append(name)
            except Exception as e:
                errors.append(f"{name}: {e}")
        else:
            errors.append(f"{name}: Không tìm thấy ứng dụng")
        if delay > 0:
            time.sleep(delay)

    return launched, errors

def shutdown_system(delay=1, comment="SessionKeeper tat may", force=True):
    cmd = ["shutdown", "/s"]
    if force:
        cmd.append("/f")
    cmd.extend(["/t", str(delay), "/c", comment])
    subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW)

def restart_system(delay=1, comment="SessionKeeper khoi dong lai", force=True):
    cmd = ["shutdown", "/r"]
    if force:
        cmd.append("/f")
    cmd.extend(["/t", str(delay), "/c", comment])
    subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW)

def hibernate_system(auto_save=True):
    if auto_save:
        try:
            items = scan_session()
            if items:
                save_session(items, "latest")
        except Exception as e:
            print(f"Error auto-saving before hibernate: {e}")
    # Đảm bảo bật tính năng hibernate của Windows
    try:
        subprocess.run(["powercfg", "-h", "on"], creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass
    # Gọi trực tiếp lệnh shutdown /h để ngắt nguồn 100% (tránh bị S0 Modern Standby chuyển thành Sleep)
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
