import os
import sys
import ctypes
from pathlib import Path

# Fix Windows Taskbar App Icon
try:
    myappid = 'sessionkeeper.pro.workstation.2.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

import time
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime

import customtkinter as ctk
from PIL import Image
import pystray
from pystray import MenuItem as item

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

import session_engine as engine
import icon_provider
import updater

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

ICON_ICO = BASE_DIR / "app_icon.ico"
ICON_PNG = BASE_DIR / "app_icon.png"

class SessionKeeperPro(ctk.CTk):
    def __init__(self, start_minimized=False):
        super().__init__()

        self.title("SessionKeeper Pro")
        self.geometry("940x710")
        self.minsize(860, 620)
        self.configure(fg_color="#0d1117")

        if ICON_ICO.exists():
            self.iconbitmap(str(ICON_ICO))
        try:
            if ICON_PNG.exists():
                icon_img = tk.PhotoImage(file=str(ICON_PNG))
                self.iconphoto(True, icon_img)
        except Exception:
            pass

        self.cfg = engine.load_config()
        self.current_items = []
        self.check_vars = {}
        self.timer_running = False
        self.timer_seconds_left = 0

        self.ui_queue = queue.Queue()
        self.check_ui_queue()

        self.tray_icon = None
        self.init_tray()

        self.setup_ui()
        self.refresh_scan()

        if self.cfg.get("auto_snapshot_enabled", True):
            engine.start_auto_snapshot(
                self.cfg.get("auto_snapshot_interval_mins", 10),
                callback=self.on_snapshot_saved
            )

        if self.cfg.get("global_hotkeys_enabled", True):
            engine.start_global_hotkeys(
                on_save=self.quick_hotkey_save,
                on_restore=self.quick_hotkey_restore,
                on_hibernate=engine.hibernate_system
            )

        self.update_info = None
        threading.Thread(target=self.check_updates_background, daemon=True).start()

        self.protocol("WM_DELETE_WINDOW", self.on_close_window)

    def post_ui(self, func):
        """Thread-safe UI callback dispatcher using queue and main thread polling"""
        self.ui_queue.put(func)

    def check_ui_queue(self):
        while True:
            try:
                fn = self.ui_queue.get_nowait()
                fn()
            except queue.Empty:
                break
            except Exception as e:
                print(f"UI callback error: {e}")
        self.after(35, self.check_ui_queue)

    def init_tray(self):
        try:
            if ICON_PNG.exists():
                tray_img = Image.open(str(ICON_PNG))
            else:
                tray_img = Image.new("RGBA", (64, 64), (16, 185, 129, 255))

            menu = (
                item("Mở SessionKeeper", self.show_from_tray, default=True),
                item("Khôi phục phiên (Ctrl+Alt+R)", lambda: self.quick_hotkey_restore()),
                item("Lưu phiên (Ctrl+Alt+S)", lambda: self.quick_hotkey_save()),
                pystray.Menu.SEPARATOR,
                item("Ngủ đông (Ctrl+Alt+H)", lambda: engine.hibernate_system()),
                item("Khởi động lại", lambda: self.on_restart_clicked()),
                item("Tắt máy an toàn", lambda: self.on_save_shutdown_clicked()),
                pystray.Menu.SEPARATOR,
                item("Thoát", self.quit_app)
            )
            self.tray_icon = pystray.Icon("SessionKeeperPro", tray_img, "SessionKeeper Pro", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print(f"Tray error: {e}")

    def show_from_tray(self):
        self.after(0, self.deiconify)
        self.after(0, self.lift)
        self.after(0, self.focus_force)

    def on_close_window(self):
        if self.cfg.get("minimize_to_tray", True):
            self.withdraw()
        else:
            self.quit_app()

    def quit_app(self):
        if self.tray_icon:
            self.tray_icon.stop()
        engine.stop_auto_snapshot()
        engine.stop_global_hotkeys()
        self.destroy()
        sys.exit(0)

    def setup_ui(self):
        # 1. Header Navigation Bar (Deep Obsidian Theme)
        top_bar = ctk.CTkFrame(self, height=52, fg_color="#161b22", corner_radius=0)
        top_bar.pack(fill="x", side="top")

        left_b = ctk.CTkFrame(top_bar, fg_color="transparent")
        left_b.pack(side="left", padx=16, pady=8)

        logo_title = ctk.CTkLabel(
            left_b, text="SESSIONKEEPER",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#38bdf8"
        )
        logo_title.pack(side="left")

        pro_badge = ctk.CTkLabel(
            left_b, text="PRO",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#21262d", text_color="#8b949e", corner_radius=4, padx=6
        )
        pro_badge.pack(side="left", padx=8)

        right_b = ctk.CTkFrame(top_bar, fg_color="transparent")
        right_b.pack(side="right", padx=16, pady=8)

        self.chip_cad = ctk.CTkLabel(
            right_b, text="0 CAD",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#21262d", text_color="#58a6ff", corner_radius=4, padx=8, pady=2
        )
        self.chip_cad.pack(side="left", padx=3)

        self.chip_micro = ctk.CTkLabel(
            right_b, text="0 Micro",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#21262d", text_color="#38bdf8", corner_radius=4, padx=8, pady=2
        )
        self.chip_micro.pack(side="left", padx=3)

        self.chip_excel = ctk.CTkLabel(
            right_b, text="0 Excel",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#21262d", text_color="#3fb950", corner_radius=4, padx=8, pady=2
        )
        self.chip_excel.pack(side="left", padx=3)

        self.chip_total = ctk.CTkLabel(
            right_b, text="0 Mục",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#21262d", text_color="#c9d1d9", corner_radius=4, padx=8, pady=2
        )
        self.chip_total.pack(side="left", padx=3)

        self.lbl_sync_status = ctk.CTkLabel(
            right_b, text="● Sẵn sàng",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#3fb950", padx=8
        )
        self.lbl_sync_status.pack(side="left", padx=(6, 0))

        self.btn_update_badge = ctk.CTkButton(
            right_b, text="🚀 Có bản mới",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1f6feb", hover_color="#388bfd",
            height=26, corner_radius=13,
            command=self.on_update_badge_clicked
        )

        # 2. Command Ribbon (Clean, balanced 4-action bar)
        ribbon = ctk.CTkFrame(self, fg_color="#161b22", corner_radius=8, border_width=1, border_color="#30363d")
        ribbon.pack(fill="x", padx=14, pady=(10, 6))

        r_inner = ctk.CTkFrame(ribbon, fg_color="transparent")
        r_inner.pack(fill="x", padx=8, pady=8)

        # 1. Khôi Phục (Subtle Emerald)
        self.btn_restore = ctk.CTkButton(
            r_inner, text="Khôi Phục (Ctrl+Alt+R)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0e4429", hover_color="#006d32",
            border_width=1, border_color="#238636", text_color="#3fb950",
            height=36, corner_radius=6,
            command=self.on_restore_clicked
        )
        self.btn_restore.pack(side="left", fill="x", expand=True, padx=4)

        # 2. Lưu Phiên (Deep Blue)
        self.btn_save = ctk.CTkButton(
            r_inner, text="Lưu Phiên (Ctrl+Alt+S)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0c2d6b", hover_color="#1158c7",
            border_width=1, border_color="#1f6feb", text_color="#58a6ff",
            height=36, corner_radius=6,
            command=self.on_save_clicked
        )
        self.btn_save.pack(side="left", fill="x", expand=True, padx=4)

        # 3. Ngủ Đông (Refined Deep Violet)
        self.btn_hibernate = ctk.CTkButton(
            r_inner, text="Ngủ Đông (Ctrl+Alt+H)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#271052", hover_color="#451a8a",
            border_width=1, border_color="#8957e5", text_color="#d2a8ff",
            height=36, corner_radius=6,
            command=self.on_hibernate_clicked
        )
        self.btn_hibernate.pack(side="left", fill="x", expand=True, padx=4)

        # 4. Khởi Động Lại (Warm Amber)
        self.btn_restart = ctk.CTkButton(
            r_inner, text="Khởi Động Lại",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#3d2200", hover_color="#6e3c00",
            border_width=1, border_color="#d29922", text_color="#e3b341",
            height=36, corner_radius=6,
            command=self.on_restart_clicked
        )
        self.btn_restart.pack(side="left", fill="x", expand=True, padx=4)

        # 5. Tắt Máy (Dark Crimson)
        self.btn_shutdown = ctk.CTkButton(
            r_inner, text="Tắt Máy An Toàn",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#490202", hover_color="#780e0e",
            border_width=1, border_color="#b62324", text_color="#ff7b72",
            height=36, corner_radius=6,
            command=self.on_save_shutdown_clicked
        )
        self.btn_shutdown.pack(side="left", fill="x", expand=True, padx=4)

        # 3. Workspace Tabview
        self.tabview = ctk.CTkTabview(
            self,
            fg_color="#161b22",
            segmented_button_fg_color="#21262d",
            segmented_button_selected_color="#1f6feb",
            segmented_button_selected_hover_color="#388bfd",
            command=self.on_tab_changed
        )
        self.tabview.pack(fill="both", expand=True, padx=14, pady=4)

        self.tab_active = self.tabview.add("Phiên Làm Việc")
        self.tab_profiles = self.tabview.add("Hồ Sơ Dự Án")
        self.tab_settings = self.tabview.add("Cài Đặt & Hẹn Giờ")

        self.setup_tab_active()
        self.setup_tab_profiles()
        self.setup_tab_settings()

        # 4. Bottom Clean Status Line (No noisy messages)
        bot_bar = ctk.CTkFrame(self, height=24, fg_color="#0d1117")
        bot_bar.pack(fill="x", side="bottom", padx=16, pady=(0, 4))

        self.lbl_bot_status = ctk.CTkLabel(
            bot_bar, text="Sẵn sàng.",
            font=ctk.CTkFont(size=11), text_color="#8b949e"
        )
        self.lbl_bot_status.pack(side="left")

        self.lbl_last_time = ctk.CTkLabel(
            bot_bar, text="",
            font=ctk.CTkFont(size=11), text_color="#8b949e"
        )
        self.lbl_last_time.pack(side="right")

    def set_status(self, text, color="#8b949e"):
        self.lbl_bot_status.configure(text=text, text_color=color)

    # ================= TAB 1: PHIÊN LÀM VIỆC =================
    def setup_tab_active(self):
        ctrl = ctk.CTkFrame(self.tab_active, fg_color="transparent")
        ctrl.pack(fill="x", padx=4, pady=(2, 6))

        lbl_sec = ctk.CTkLabel(
            ctrl, text="DANH SÁCH ỨNG DỤNG & TÀI LIỆU",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#8b949e"
        )
        lbl_sec.pack(side="left")

        btn_add_f = ctk.CTkButton(
            ctrl, text="+ Tệp...", width=70, height=26,
            fg_color="#21262d", hover_color="#30363d", font=ctk.CTkFont(size=11),
            command=self.add_custom_file
        )
        btn_add_f.pack(side="right", padx=(4, 0))

        btn_add_d = ctk.CTkButton(
            ctrl, text="+ Thư mục...", width=80, height=26,
            fg_color="#21262d", hover_color="#30363d", font=ctk.CTkFont(size=11),
            command=self.add_custom_folder
        )
        btn_add_d.pack(side="right", padx=4)

        self.btn_ref = ctk.CTkButton(
            ctrl, text="Quét lại", width=70, height=26,
            fg_color="#21262d", hover_color="#30363d", font=ctk.CTkFont(size=11),
            command=self.refresh_scan
        )
        self.btn_ref.pack(side="right", padx=4)

        btn_sel = ctk.CTkButton(
            ctrl, text="Chọn hết", width=65, height=26,
            fg_color="#21262d", hover_color="#30363d", font=ctk.CTkFont(size=11),
            command=lambda: self.toggle_all(True)
        )
        btn_sel.pack(side="right", padx=4)

        btn_unsel = ctk.CTkButton(
            ctrl, text="Bỏ chọn", width=65, height=26,
            fg_color="#21262d", hover_color="#30363d", font=ctk.CTkFont(size=11),
            command=lambda: self.toggle_all(False)
        )
        btn_unsel.pack(side="right", padx=4)

        self.scroll_items = ctk.CTkScrollableFrame(
            self.tab_active, corner_radius=6, fg_color="#0d1117"
        )
        self.scroll_items.pack(fill="both", expand=True, padx=4, pady=2)

    def refresh_scan(self):
        self.lbl_sync_status.configure(text="● Đang quét...", text_color="#58a6ff")
        if hasattr(self, 'btn_ref'):
            self.btn_ref.configure(state="disabled")

        def bg_scan():
            try:
                items = engine.scan_session()
            except Exception as e:
                print(f"Scan error: {e}")
                items = []
            self.post_ui(lambda: self._on_scan_finished(items))

        threading.Thread(target=bg_scan, daemon=True).start()

    def _on_scan_finished(self, items):
        if hasattr(self, 'btn_ref'):
            self.btn_ref.configure(state="normal")
        self.current_items = items
        self.render_items_list()

        cad_count = sum(1 for x in self.current_items if x.get("category") == "Bản vẽ CAD")
        micro_count = sum(1 for x in self.current_items if x.get("category") == "MicroStation")
        excel_count = sum(1 for x in self.current_items if x.get("category") == "Bảng tính")

        self.chip_cad.configure(text=f"{cad_count} CAD")
        self.chip_micro.configure(text=f"{micro_count} Micro")
        self.chip_excel.configure(text=f"{excel_count} Excel")
        self.chip_total.configure(text=f"{len(self.current_items)} Mục")

        last_time = self.cfg.get("last_saved_time", "")
        if last_time:
            self.lbl_last_time.configure(text=f"Phiên gần nhất: {last_time}")
            self.lbl_sync_status.configure(text="● Đã đồng bộ", text_color="#3fb950")
        else:
            self.lbl_sync_status.configure(text="● Sẵn sàng", text_color="#3fb950")

        self.set_status(f"Đã phát hiện {len(self.current_items)} mục đang mở.")

    def render_items_list(self):
        for w in self.scroll_items.winfo_children():
            w.destroy()
        self.check_vars.clear()

        if not self.current_items:
            empty = ctk.CTkLabel(
                self.scroll_items, text="Không phát hiện ứng dụng nào đang mở.",
                text_color="#8b949e", pady=40
            )
            empty.pack()
            return

        for item_data in self.current_items:
            # Card row
            row = ctk.CTkFrame(self.scroll_items, fg_color="#161b22", corner_radius=6, border_width=1, border_color="#21262d")
            row.pack(fill="x", padx=2, pady=2)

            var = ctk.BooleanVar(value=item_data.get("enabled", True))
            self.check_vars[item_data["id"]] = var

            chk = ctk.CTkCheckBox(row, text="", variable=var, width=20, corner_radius=4)
            chk.pack(side="left", padx=(10, 6), pady=8)

            # REAL APPLICATION ICON (Image 2 fix)
            app_icon = icon_provider.get_item_icon(item_data, size=24)
            icon_lbl = ctk.CTkLabel(row, text="", image=app_icon, width=28)
            icon_lbl.pack(side="left", padx=(0, 6), pady=6)

            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=4, pady=4)

            name_box = ctk.CTkFrame(info, fg_color="transparent")
            name_box.pack(fill="x")

            name_lbl = ctk.CTkLabel(
                name_box, text=item_data["name"],
                font=ctk.CTkFont(size=12, weight="bold"), text_color="#f0f6fc", anchor="w"
            )
            name_lbl.pack(side="left")

            if item_data.get("unsaved"):
                warn_pill = ctk.CTkLabel(
                    name_box, text=" Chưa lưu (Cần Ctrl+S) ",
                    font=ctk.CTkFont(size=9, weight="bold"),
                    fg_color="#78350f", text_color="#fef3c7", corner_radius=3
                )
                warn_pill.pack(side="left", padx=6)

            det_lbl = ctk.CTkLabel(
                info, text=item_data.get("detail", ""),
                font=ctk.CTkFont(size=10), text_color="#8b949e", anchor="w"
            )
            det_lbl.pack(fill="x")

            # Layout chip if captured
            layout = item_data.get("layout")
            if layout and layout.get("rect"):
                r = layout["rect"]
                chip_txt = f"{r[2]}x{r[3]}" if layout.get("state") != 3 else "Toàn màn hình"
                layout_chip = ctk.CTkLabel(
                    row, text=chip_txt,
                    font=ctk.CTkFont(size=9), fg_color="#21262d", text_color="#8b949e",
                    corner_radius=3, padx=6
                )
                layout_chip.pack(side="right", padx=6)

            btn_del = ctk.CTkButton(
                row, text="✕", width=22, height=22,
                fg_color="transparent", text_color="#8b949e", hover_color="#b62324",
                font=ctk.CTkFont(size=11),
                command=lambda it_id=item_data["id"]: self.remove_item(it_id)
            )
            btn_del.pack(side="right", padx=(0, 8))

    def remove_item(self, item_id):
        self.current_items = [x for x in self.current_items if x["id"] != item_id]
        if item_id in self.check_vars:
            del self.check_vars[item_id]
        self.render_items_list()

    def toggle_all(self, state):
        for v in self.check_vars.values():
            v.set(state)

    def add_custom_file(self):
        f = filedialog.askopenfilename(
            title="Thêm tệp vào phiên",
            filetypes=[("Mọi tệp", "*.*"), ("Bản vẽ CAD", "*.dwg;*.dxf"), ("Excel", "*.xlsx;*.xls"), ("Word", "*.docx;*.doc")]
        )
        if f:
            fid = f"file_{f.lower()}"
            ext = os.path.splitext(f)[1].lower()
            cat = "Bản vẽ CAD" if ext in ['.dwg', '.dxf'] else ("Bảng tính" if ext in ['.xlsx', '.xls'] else "Tài liệu")
            self.current_items.append({
                "id": fid,
                "type": "file",
                "category": cat,
                "name": os.path.basename(f),
                "detail": f,
                "target": f,
                "layout": None,
                "unsaved": False,
                "enabled": True
            })
            self.render_items_list()

    def add_custom_folder(self):
        d = filedialog.askdirectory(title="Thêm thư mục vào phiên")
        if d:
            fid = f"folder_{d.lower()}"
            self.current_items.append({
                "id": fid,
                "type": "folder",
                "category": "Thư mục",
                "name": os.path.basename(d) or d,
                "detail": d,
                "target": d,
                "layout": None,
                "unsaved": False,
                "enabled": True
            })
            self.render_items_list()

    def get_selected_items(self):
        selected = []
        for it in self.current_items:
            v = self.check_vars.get(it["id"])
            if v and v.get():
                it["enabled"] = True
                selected.append(it)
        return selected

    def on_save_clicked(self):
        selected = self.get_selected_items()
        if not selected:
            self.set_status("Chưa chọn mục nào để lưu.", "#f85149")
            return
        if engine.save_session(selected, "latest"):
            now_str = datetime.now().strftime("%H:%M:%S")
            self.cfg["last_saved_time"] = now_str
            engine.save_config(self.cfg)
            self.lbl_last_time.configure(text=f"Đã lưu lúc {now_str}")
            self.lbl_sync_status.configure(text="● Đã đồng bộ", text_color="#3fb950")
            self.set_status(f"Đã lưu {len(selected)} mục thành công.", "#3fb950")

    def on_restore_clicked(self):
        saved = engine.get_session("latest")
        if not saved:
            messagebox.showinfo("SessionKeeper", "Chưa có phiên nào được lưu.")
            return

        self.set_status("Đang khôi phục...", "#58a6ff")
        restore_layout = self.cfg.get("restore_window_layout", True)

        def do_restore():
            launched, errors = engine.restore_session("latest", delay=0.4, restore_layout=restore_layout)
            self.post_ui(lambda: self.set_status(f"Đã khôi phục {len(launched)} mục.", "#3fb950"))

        threading.Thread(target=do_restore, daemon=True).start()

    def quick_hotkey_save(self):
        def do_save():
            items = engine.scan_session()
            engine.save_session(items, "latest")
            now_str = datetime.now().strftime("%H:%M:%S")
            self.cfg["last_saved_time"] = now_str
            engine.save_config(self.cfg)
            self.post_ui(lambda: (
                self.lbl_last_time.configure(text=f"Đã lưu lúc {now_str}"),
                self.lbl_sync_status.configure(text="● Đã đồng bộ", text_color="#3fb950"),
                self.set_status(f"Đã lưu {len(items)} mục lúc {now_str}.", "#3fb950")
            ))
            if self.tray_icon:
                try:
                    self.tray_icon.notify(f"Đã lưu phiên ({len(items)} mục)", "SessionKeeper")
                except Exception:
                    pass
        threading.Thread(target=do_save, daemon=True).start()

    def quick_hotkey_restore(self):
        engine.restore_session("latest", delay=0.4, restore_layout=self.cfg.get("restore_window_layout", True))
        if self.tray_icon:
            self.tray_icon.notify("Đang khôi phục phiên...", "SessionKeeper")

    def on_save_shutdown_clicked(self):
        selected = self.get_selected_items()
        if not selected:
            selected = self.current_items

        unsaved = [x for x in selected if x.get("unsaved")]
        if unsaved:
            fnames = "\n".join([f"• {x['name']}" for x in unsaved[:3]])
            ans = messagebox.askyesno(
                "Cảnh báo chưa lưu file",
                f"Phát hiện tài liệu chưa lưu thay đổi:\n{fnames}\n\nBạn có muốn tiếp tục tắt máy không?"
            )
            if not ans:
                return

        engine.save_session(selected, "latest")
        now_str = datetime.now().strftime("%H:%M:%S")
        self.cfg["last_saved_time"] = now_str
        engine.save_config(self.cfg)

        self.show_shutdown_countdown_dialog(len(selected))

    def show_shutdown_countdown_dialog(self, item_count):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Tắt máy")
        dialog.geometry("380x180")
        dialog.configure(fg_color="#0d1117")
        dialog.transient(self)
        dialog.grab_set()

        lbl = ctk.CTkLabel(
            dialog, text=f"Đã lưu {item_count} mục. Tắt máy sau:",
            font=ctk.CTkFont(size=13), text_color="#c9d1d9"
        )
        lbl.pack(pady=(20, 4))

        seconds = 10
        lbl_sec = ctk.CTkLabel(
            dialog, text=f"{seconds}s",
            font=ctk.CTkFont(size=26, weight="bold"), text_color="#f85149"
        )
        lbl_sec.pack(pady=4)

        cancelled = [False]

        def loop_count():
            nonlocal seconds
            if cancelled[0]:
                return
            seconds -= 1
            if seconds <= 0:
                dialog.destroy()
                engine.shutdown_system(delay=1)
            else:
                lbl_sec.configure(text=f"{seconds}s")
                dialog.after(1000, loop_count)

        dialog.after(1000, loop_count)

        btn_box = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_box.pack(pady=10)

        def do_now():
            cancelled[0] = True
            dialog.destroy()
            engine.shutdown_system(delay=1)

        def do_cancel():
            cancelled[0] = True
            dialog.destroy()
            self.set_status("Đã hủy tắt máy.")

        ctk.CTkButton(btn_box, text="Tắt ngay", width=100, fg_color="#b62324", hover_color="#d1242f", command=do_now).pack(side="left", padx=6)
        ctk.CTkButton(btn_box, text="Hủy", width=100, fg_color="#21262d", hover_color="#30363d", command=do_cancel).pack(side="left", padx=6)

    def on_restart_clicked(self):
        selected = self.get_selected_items()
        if not selected:
            selected = self.current_items

        unsaved = [x for x in selected if x.get("unsaved")]
        if unsaved:
            fnames = "\n".join([f"• {x['name']}" for x in unsaved[:3]])
            ans = messagebox.askyesno(
                "Cảnh báo chưa lưu file",
                f"Phát hiện tài liệu chưa lưu thay đổi:\n{fnames}\n\nBạn có muốn tiếp tục khởi động lại không?"
            )
            if not ans:
                return

        engine.save_session(selected, "latest")
        now_str = datetime.now().strftime("%H:%M:%S")
        self.cfg["last_saved_time"] = now_str
        engine.save_config(self.cfg)

        self.show_restart_countdown_dialog(len(selected))

    def show_restart_countdown_dialog(self, item_count):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Khởi động lại")
        dialog.geometry("380x180")
        dialog.configure(fg_color="#0d1117")
        dialog.transient(self)
        dialog.grab_set()

        lbl = ctk.CTkLabel(
            dialog, text=f"Đã lưu {item_count} mục. Khởi động lại sau:",
            font=ctk.CTkFont(size=13), text_color="#c9d1d9"
        )
        lbl.pack(pady=(20, 4))

        seconds = 10
        lbl_sec = ctk.CTkLabel(
            dialog, text=f"{seconds}s",
            font=ctk.CTkFont(size=26, weight="bold"), text_color="#d29922"
        )
        lbl_sec.pack(pady=4)

        cancelled = [False]

        def loop_count():
            nonlocal seconds
            if cancelled[0]:
                return
            seconds -= 1
            if seconds <= 0:
                dialog.destroy()
                engine.restart_system(delay=1)
            else:
                lbl_sec.configure(text=f"{seconds}s")
                dialog.after(1000, loop_count)

        dialog.after(1000, loop_count)

        btn_box = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_box.pack(pady=10)

        def do_now():
            cancelled[0] = True
            dialog.destroy()
            engine.restart_system(delay=1)

        def do_cancel():
            cancelled[0] = True
            dialog.destroy()
            self.set_status("Đã hủy khởi động lại.")

        ctk.CTkButton(btn_box, text="Khởi động ngay", width=115, fg_color="#9e6a03", hover_color="#b07d0f", text_color="#ffffff", command=do_now).pack(side="left", padx=6)
        ctk.CTkButton(btn_box, text="Hủy", width=90, fg_color="#21262d", hover_color="#30363d", command=do_cancel).pack(side="left", padx=6)

    def on_hibernate_clicked(self):
        ans = messagebox.askyesno(
            "Ngủ Đông",
            "Chế độ Ngủ Đông ngắt điện hoàn toàn nhưng giữ nguyên 100% cửa sổ và bản vẽ.\n\nNgủ đông ngay bây giờ?"
        )
        if ans:
            engine.hibernate_system()

    def on_clean_temp_clicked(self):
        count, mb = engine.scan_and_clean_temp(delete=False)
        ans = messagebox.askyesno(
            "Dọn Rác CAD & File Tạm",
            f"Tìm thấy {count} tệp tạm (.bak, .tmp) chiếm khoảng {mb:.1f} MB.\n\nBạn có muốn xóa để giải phóng dung lượng không?"
        )
        if ans:
            c, m = engine.scan_and_clean_temp(delete=True)
            messagebox.showinfo("SessionKeeper", f"Đã dọn sạch {c} tệp rác ({m:.1f} MB)!")
            self.set_status(f"Đã dọn dẹp {m:.1f} MB tệp rác.", "#3fb950")

    # ================= TAB 2: HỒ SƠ DỰ ÁN =================
    def setup_tab_profiles(self):
        top_p = ctk.CTkFrame(self.tab_profiles, fg_color="transparent")
        top_p.pack(fill="x", padx=4, pady=6)

        lbl = ctk.CTkLabel(top_p, text="DANH SÁCH DỰ ÁN", font=ctk.CTkFont(size=11, weight="bold"), text_color="#8b949e")
        lbl.pack(side="left")

        btn_new_p = ctk.CTkButton(
            top_p, text="+ Lưu thành Dự án...",
            fg_color="#1f6feb", hover_color="#388bfd", font=ctk.CTkFont(size=11),
            command=self.save_as_new_profile
        )
        btn_new_p.pack(side="right")

        self.scroll_profiles = ctk.CTkScrollableFrame(self.tab_profiles, corner_radius=6, fg_color="#0d1117")
        self.scroll_profiles.pack(fill="both", expand=True, padx=4, pady=2)

        self.refresh_profiles_list()

    def on_tab_changed(self):
        if self.tabview.get() == "Hồ Sơ Dự Án":
            self.refresh_profiles_list()

    def on_snapshot_saved(self, saved_time, count):
        self.post_ui(lambda: (
            self.refresh_profiles_list(),
            self.set_status(f"Auto-Snapshot tự động lưu lúc {saved_time[-8:]} ({count} mục).", "#3fb950")
        ))

    def refresh_profiles_list(self):
        for w in self.scroll_profiles.winfo_children():
            w.destroy()

        data = engine.load_all_sessions()
        profiles = data.get("profiles", {})

        auto_snap = profiles.get("auto_snapshot")
        if auto_snap:
            card = ctk.CTkFrame(self.scroll_profiles, fg_color="#161b22", corner_radius=6, border_width=1, border_color="#21262d")
            card.pack(fill="x", padx=2, pady=3)

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=12, pady=6)

            t_lbl = ctk.CTkLabel(info, text="Bản sao lưu ngầm (Auto-Snapshot)", font=ctk.CTkFont(size=12, weight="bold"), text_color="#58a6ff", anchor="w")
            t_lbl.pack(fill="x")

            d_lbl = ctk.CTkLabel(info, text=f"Lưu lúc: {auto_snap.get('saved_at', '')} • {len(auto_snap.get('items', []))} mục", font=ctk.CTkFont(size=10), text_color="#8b949e", anchor="w")
            d_lbl.pack(fill="x")

            btn_open = ctk.CTkButton(
                card, text="Khôi phục", width=85, height=26,
                fg_color="#0e4429", hover_color="#006d32", text_color="#3fb950", font=ctk.CTkFont(size=11),
                command=lambda: self.restore_profile("auto_snapshot")
            )
            btn_open.pack(side="right", padx=10)

        for pname, pdata in profiles.items():
            if pname == "auto_snapshot":
                continue
            card = ctk.CTkFrame(self.scroll_profiles, fg_color="#161b22", corner_radius=6, border_width=1, border_color="#21262d")
            card.pack(fill="x", padx=2, pady=3)

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=12, pady=6)

            t_lbl = ctk.CTkLabel(info, text=pname, font=ctk.CTkFont(size=12, weight="bold"), text_color="#f0f6fc", anchor="w")
            t_lbl.pack(fill="x")

            saved_time = pdata.get("saved_at", "")
            items_cnt = len(pdata.get("items", []))
            d_lbl = ctk.CTkLabel(info, text=f"Lưu lúc: {saved_time} • {items_cnt} mục", font=ctk.CTkFont(size=10), text_color="#8b949e", anchor="w")
            d_lbl.pack(fill="x")

            btn_box = ctk.CTkFrame(card, fg_color="transparent")
            btn_box.pack(side="right", padx=8)

            btn_open = ctk.CTkButton(
                btn_box, text="Mở dự án", width=80, height=26,
                fg_color="#0e4429", hover_color="#006d32", text_color="#3fb950", font=ctk.CTkFont(size=11),
                command=lambda p=pname: self.restore_profile(p)
            )
            btn_open.pack(side="left", padx=3)

            btn_del = ctk.CTkButton(
                btn_box, text="✕", width=24, height=24,
                fg_color="transparent", text_color="#8b949e", hover_color="#b62324", font=ctk.CTkFont(size=11),
                command=lambda p=pname: self.delete_profile(p)
            )
            btn_del.pack(side="left", padx=3)

    def save_as_new_profile(self):
        dialog = ctk.CTkInputDialog(text="Tên dự án:", title="Lưu dự án mới")
        name = dialog.get_input()
        if name and name.strip():
            pname = name.strip()
            selected = self.get_selected_items()
            if not selected:
                selected = self.current_items
            engine.save_session(selected, pname)
            self.refresh_profiles_list()
            self.set_status(f"Đã lưu dự án '{pname}'.", "#3fb950")

    def restore_profile(self, pname):
        self.set_status(f"Đang mở dự án '{pname}'...", "#58a6ff")
        def do_p():
            launched, _ = engine.restore_session(pname, delay=0.4, restore_layout=self.cfg.get("restore_window_layout", True))
            self.post_ui(lambda: self.set_status(f"Đã mở dự án '{pname}' ({len(launched)} mục).", "#3fb950"))
        threading.Thread(target=do_p, daemon=True).start()

    def delete_profile(self, pname):
        if messagebox.askyesno("Xóa", f"Xóa hồ sơ dự án '{pname}'?"):
            data = engine.load_all_sessions()
            if "profiles" in data and pname in data["profiles"]:
                del data["profiles"][pname]
                engine.save_all_sessions(data)
                self.refresh_profiles_list()

    # ================= TAB 3: CÀI ĐẶT & HẸN GIỜ =================
    def setup_tab_settings(self):
        scroll = ctk.CTkScrollableFrame(self.tab_settings, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # 1. Shutdown Timer
        box_timer = ctk.CTkFrame(scroll, corner_radius=6, fg_color="#161b22", border_width=1, border_color="#21262d")
        box_timer.pack(fill="x", pady=4)

        lbl_t = ctk.CTkLabel(box_timer, text="HẸN GIỜ TỰ LƯU & TẮT MÁY", font=ctk.CTkFont(size=11, weight="bold"), text_color="#8b949e")
        lbl_t.pack(anchor="w", padx=14, pady=(10, 6))

        row_t = ctk.CTkFrame(box_timer, fg_color="transparent")
        row_t.pack(fill="x", padx=14, pady=4)

        for m in [15, 30, 45, 60]:
            ctk.CTkButton(
                row_t, text=f"{m}m", width=60, height=28,
                fg_color="#21262d", hover_color="#30363d", font=ctk.CTkFont(size=11),
                command=lambda mins=m: self.start_shutdown_timer(mins)
            ).pack(side="left", padx=3)

        self.btn_timer_toggle = ctk.CTkButton(
            row_t, text="Tùy chỉnh...", width=90, height=28,
            fg_color="#490202", hover_color="#780e0e", text_color="#ff7b72", font=ctk.CTkFont(size=11),
            command=self.toggle_custom_timer
        )
        self.btn_timer_toggle.pack(side="left", padx=8)

        self.lbl_timer_status = ctk.CTkLabel(
            box_timer, text="Chưa bật hẹn giờ.", font=ctk.CTkFont(size=11), text_color="#8b949e"
        )
        self.lbl_timer_status.pack(anchor="w", padx=14, pady=(4, 10))

        # 2. System Settings
        box_cfg = ctk.CTkFrame(scroll, corner_radius=6, fg_color="#161b22", border_width=1, border_color="#21262d")
        box_cfg.pack(fill="x", pady=6)

        lbl_c = ctk.CTkLabel(box_cfg, text="CẤU HÌNH HỆ THỐNG", font=ctk.CTkFont(size=11, weight="bold"), text_color="#8b949e")
        lbl_c.pack(anchor="w", padx=14, pady=(10, 6))

        self.sw_startup = ctk.CTkSwitch(
            box_cfg, text="Tự động khôi phục khi khởi động Windows",
            font=ctk.CTkFont(size=12), command=self.on_switch_startup
        )
        self.sw_startup.pack(anchor="w", padx=14, pady=6)
        if engine.is_windows_startup():
            self.sw_startup.select()

        self.sw_layout = ctk.CTkSwitch(
            box_cfg, text="Ghi nhớ & xếp lại vị trí cửa sổ (Window Layout)",
            font=ctk.CTkFont(size=12), command=self.on_switch_layout
        )
        self.sw_layout.pack(anchor="w", padx=14, pady=6)
        if self.cfg.get("restore_window_layout", True):
            self.sw_layout.select()

        self.sw_hotkeys = ctk.CTkSwitch(
            box_cfg, text="Phím tắt toàn hệ thống (Ctrl+Alt+S / Ctrl+Alt+R / Ctrl+Alt+H)",
            font=ctk.CTkFont(size=12), command=self.on_switch_hotkeys
        )
        self.sw_hotkeys.pack(anchor="w", padx=14, pady=6)
        if self.cfg.get("global_hotkeys_enabled", True):
            self.sw_hotkeys.select()

        self.sw_snapshot = ctk.CTkSwitch(
            box_cfg, text="Tự động sao lưu ngầm mỗi 10 phút (Auto-Snapshot)",
            font=ctk.CTkFont(size=12), command=self.on_switch_snapshot
        )
        self.sw_snapshot.pack(anchor="w", padx=14, pady=6)
        if self.cfg.get("auto_snapshot_enabled", True):
            self.sw_snapshot.select()

        self.sw_tray = ctk.CTkSwitch(
            box_cfg, text="Thu nhỏ xuống khay hệ thống (System Tray) khi đóng",
            font=ctk.CTkFont(size=12), command=self.on_switch_tray
        )
        self.sw_tray.pack(anchor="w", padx=14, pady=6)
        if self.cfg.get("minimize_to_tray", True):
            self.sw_tray.select()

        # 3. Update & Version Info
        box_upd = ctk.CTkFrame(scroll, corner_radius=6, fg_color="#161b22", border_width=1, border_color="#21262d")
        box_upd.pack(fill="x", pady=6)

        lbl_u = ctk.CTkLabel(box_upd, text="CẬP NHẬT PHẦN MỀM & MÃ NGUỒN", font=ctk.CTkFont(size=11, weight="bold"), text_color="#8b949e")
        lbl_u.pack(anchor="w", padx=14, pady=(10, 4))

        lbl_u_info = ctk.CTkLabel(
            box_upd, text=f"Phiên bản hiện tại: v{updater.CURRENT_VERSION} (Portable) • Tự động đồng bộ GitHub",
            font=ctk.CTkFont(size=12), text_color="#c9d1d9"
        )
        lbl_u_info.pack(anchor="w", padx=14, pady=2)

        row_u = ctk.CTkFrame(box_upd, fg_color="transparent")
        row_u.pack(fill="x", padx=14, pady=(6, 12))

        ctk.CTkButton(
            row_u, text="🔄 Kiểm Tra Cập Nhật Ngay", height=30,
            fg_color="#1f6feb", hover_color="#388bfd", font=ctk.CTkFont(size=12, weight="bold"),
            command=self.manual_check_update
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            row_u, text="🌐 Xem Mã Nguồn Trên GitHub", height=30,
            fg_color="#21262d", hover_color="#30363d", font=ctk.CTkFont(size=12),
            command=updater.open_download_page
        ).pack(side="left")

    def start_shutdown_timer(self, mins):
        self.timer_seconds_left = mins * 60
        self.timer_running = True
        self.btn_timer_toggle.configure(text="Hủy hẹn giờ", fg_color="#21262d", hover_color="#30363d", text_color="#c9d1d9")
        self.update_timer_loop()

    def toggle_custom_timer(self):
        if self.timer_running:
            self.timer_running = False
            engine.cancel_shutdown()
            self.lbl_timer_status.configure(text="Đã hủy hẹn giờ.", text_color="#8b949e")
            self.btn_timer_toggle.configure(text="Tùy chỉnh...", fg_color="#490202", hover_color="#780e0e", text_color="#ff7b72")
        else:
            dialog = ctk.CTkInputDialog(text="Số phút:", title="Hẹn giờ tắt máy")
            val = dialog.get_input()
            if val and val.isdigit():
                self.start_shutdown_timer(int(val))

    def update_timer_loop(self):
        if not self.timer_running:
            return
        if self.timer_seconds_left <= 0:
            self.timer_running = False
            self.lbl_timer_status.configure(text="Hết giờ! Đang lưu & tắt máy...", text_color="#ff7b72")
            items = engine.scan_session()
            engine.save_session(items, "latest")
            engine.shutdown_system(delay=5)
            return

        m, s = divmod(self.timer_seconds_left, 60)
        self.lbl_timer_status.configure(text=f"Tự động lưu và tắt máy sau: {m:02d}:{s:02d}", text_color="#d29922")
        self.timer_seconds_left -= 1
        self.after(1000, self.update_timer_loop)

    def on_switch_startup(self):
        val = self.sw_startup.get() == 1
        self.cfg["auto_restore_on_startup"] = val
        engine.save_config(self.cfg)
        engine.set_windows_startup(val)

    def on_switch_layout(self):
        val = self.sw_layout.get() == 1
        self.cfg["restore_window_layout"] = val
        engine.save_config(self.cfg)

    def on_switch_hotkeys(self):
        val = self.sw_hotkeys.get() == 1
        self.cfg["global_hotkeys_enabled"] = val
        engine.save_config(self.cfg)
        if val:
            engine.start_global_hotkeys(
                on_save=self.quick_hotkey_save,
                on_restore=self.quick_hotkey_restore,
                on_hibernate=engine.hibernate_system
            )
        else:
            engine.stop_global_hotkeys()

    def on_switch_snapshot(self):
        val = self.sw_snapshot.get() == 1
        self.cfg["auto_snapshot_enabled"] = val
        engine.save_config(self.cfg)
        if val:
            engine.start_auto_snapshot(
                self.cfg.get("auto_snapshot_interval_mins", 10),
                callback=self.on_snapshot_saved
            )
        else:
            engine.stop_auto_snapshot()

    def on_switch_tray(self):
        val = self.sw_tray.get() == 1
        self.cfg["minimize_to_tray"] = val
        engine.save_config(self.cfg)

    # ================= CẬP NHẬT TỰ ĐỘNG (AUTO-UPDATER) =================
    def check_updates_background(self):
        time.sleep(2.5)
        has_update, info = updater.check_for_updates()
        if has_update and info:
            self.update_info = info
            self.post_ui(lambda: self.show_update_badge(info))

    def show_update_badge(self, info):
        ver = info.get("version", "")
        self.btn_update_badge.configure(text=f"🚀 Bản {ver} mới!")
        self.btn_update_badge.pack(side="left", padx=(0, 6))

    def on_update_badge_clicked(self):
        if self.update_info:
            self.show_update_dialog(self.update_info)
        else:
            self.manual_check_update()

    def manual_check_update(self):
        self.set_status("Đang kiểm tra cập nhật từ GitHub...", "#58a6ff")
        def do_chk():
            has_update, info = updater.check_for_updates(timeout=6)
            if has_update and info:
                self.update_info = info
                self.post_ui(lambda: [
                    self.show_update_badge(info),
                    self.show_update_dialog(info),
                    self.set_status(f"Đã phát hiện bản mới v{info.get('version')}!", "#3fb950")
                ])
            elif info:
                self.post_ui(lambda: messagebox.showinfo("Cập nhật", f"Bạn đang dùng phiên bản mới nhất (v{updater.CURRENT_VERSION})!"))
                self.post_ui(lambda: self.set_status("Đang ở phiên bản mới nhất.", "#3fb950"))
            else:
                self.post_ui(lambda: messagebox.showwarning("Cập nhật", "Không thể kết nối đến GitHub để kiểm tra cập nhật.\nVui lòng kiểm tra kết nối mạng."))
                self.post_ui(lambda: self.set_status("Lỗi kiểm tra cập nhật.", "#f85149"))
        threading.Thread(target=do_chk, daemon=True).start()

    def show_update_dialog(self, info):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Cập Nhật SessionKeeper")
        dialog.geometry("480x420")
        dialog.configure(fg_color="#0d1117")
        dialog.transient(self)
        dialog.grab_set()

        lbl_title = ctk.CTkLabel(
            dialog, text=f"🚀 Đã Có Bản Cập Nhật v{info.get('version', '')}!",
            font=ctk.CTkFont(size=16, weight="bold"), text_color="#58a6ff"
        )
        lbl_title.pack(pady=(16, 4))

        lbl_date = ctk.CTkLabel(
            dialog, text=f"Ngày phát hành: {info.get('release_date', '')}  •  Phiên bản máy: v{updater.CURRENT_VERSION}",
            font=ctk.CTkFont(size=11), text_color="#8b949e"
        )
        lbl_date.pack(pady=(0, 8))

        lbl_log_title = ctk.CTkLabel(dialog, text="NHỮNG ĐIỂM MỚI VỪA CẬP NHẬT:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#8b949e")
        lbl_log_title.pack(anchor="w", padx=16, pady=(4, 2))

        box_log = ctk.CTkScrollableFrame(dialog, height=150, fg_color="#161b22", corner_radius=6, border_width=1, border_color="#30363d")
        box_log.pack(fill="x", padx=16, pady=4)

        changelog = info.get("changelog", [])
        if isinstance(changelog, list):
            for c in changelog:
                ctk.CTkLabel(box_log, text=f"• {c}", font=ctk.CTkFont(size=12), text_color="#c9d1d9", anchor="w", justify="left").pack(fill="x", pady=2)
        else:
            ctk.CTkLabel(box_log, text=str(changelog), font=ctk.CTkFont(size=12), text_color="#c9d1d9", anchor="w", justify="left").pack(fill="x", pady=2)

        prog_bar = ctk.CTkProgressBar(dialog, height=8, corner_radius=4, fg_color="#21262d", progress_color="#1f6feb")
        lbl_prog = ctk.CTkLabel(dialog, text="", font=ctk.CTkFont(size=11), text_color="#8b949e")

        btn_box = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_box.pack(pady=12)

        def do_download():
            btn_auto.configure(state="disabled", text="Đang tải về...")
            btn_gh.configure(state="disabled")
            prog_bar.pack(fill="x", padx=20, pady=(6, 2))
            prog_bar.set(0)
            lbl_prog.pack(pady=(0, 6))

            def worker():
                def p_cb(pct, down, tot):
                    self.post_ui(lambda: [
                        prog_bar.set(pct / 100.0),
                        lbl_prog.configure(text=f"Đang tải: {pct}% ({down // (1024*1024)}MB / {tot // (1024*1024)}MB)")
                    ])

                dl_url = info.get("download_url") or updater.GITHUB_REPO_URL
                ok, msg = updater.download_and_apply_update(dl_url, progress_callback=p_cb)
                if ok:
                    self.post_ui(lambda: [
                        lbl_prog.configure(text="Đã tải xong! Đang khởi động lại ứng dụng...", text_color="#3fb950"),
                        dialog.after(1500, self.quit_app)
                    ])
                else:
                    self.post_ui(lambda: [
                        messagebox.showerror("Lỗi cập nhật", f"Không thể tự động cập nhật: {msg}\nVui lòng tải trực tiếp từ GitHub."),
                        btn_auto.configure(state="normal", text="Thử lại"),
                        btn_gh.configure(state="normal"),
                        prog_bar.pack_forget(),
                        lbl_prog.pack_forget()
                    ])

            threading.Thread(target=worker, daemon=True).start()

        btn_auto = ctk.CTkButton(
            btn_box, text="⚡ Nâng Cấp Tự Động", width=140, height=32,
            fg_color="#1f6feb", hover_color="#388bfd", font=ctk.CTkFont(size=12, weight="bold"),
            command=do_download
        )
        btn_auto.pack(side="left", padx=5)

        btn_gh = ctk.CTkButton(
            btn_box, text="🌐 Tải Từ GitHub", width=120, height=32,
            fg_color="#21262d", hover_color="#30363d", font=ctk.CTkFont(size=12),
            command=lambda: [updater.open_download_page(), dialog.destroy()]
        )
        btn_gh.pack(side="left", padx=5)

        ctk.CTkButton(
            btn_box, text="Để Sau", width=80, height=32,
            fg_color="transparent", hover_color="#21262d", font=ctk.CTkFont(size=12), text_color="#8b949e",
            command=dialog.destroy
        ).pack(side="left", padx=5)

def create_single_desktop_shortcut():
    import win32com.client
    shell = win32com.client.Dispatch("WScript.Shell")
    desktop = shell.SpecialFolders("Desktop")
    
    exe_file = BASE_DIR / "SessionKeeper.exe"
    sc_path = os.path.join(desktop, "SessionKeeper.lnk")
    try:
        s = shell.CreateShortcut(sc_path)
        if exe_file.exists():
            s.TargetPath = str(exe_file)
            s.Arguments = ""
        else:
            pythonw = Path(sys.executable).parent / "pythonw.exe"
            if not pythonw.exists():
                pythonw = Path(sys.executable)
            s.TargetPath = str(pythonw)
            s.Arguments = f'"{BASE_DIR / "app.py"}"'
        s.WorkingDirectory = str(BASE_DIR)
        if ICON_ICO.exists():
            s.IconLocation = str(ICON_ICO)
        s.Description = "SessionKeeper Pro"
        s.Save()
        print(f"Shortcut updated: {sc_path}")
    except Exception as e:
        print(f"Error creating shortcut: {e}")

if __name__ == "__main__":
    if "--auto-restore" in sys.argv:
        engine.restore_session("latest", delay=0.4)
        app = SessionKeeperPro(start_minimized=True)
        app.withdraw()
        app.mainloop()
    elif "--restore-only" in sys.argv:
        engine.restore_session("latest", delay=0.4)
    elif "--save-shutdown" in sys.argv:
        it = engine.scan_session()
        engine.save_session(it, "latest")
        engine.shutdown_system(delay=5)
    elif "--save-restart" in sys.argv:
        it = engine.scan_session()
        engine.save_session(it, "latest")
        engine.restart_system(delay=1)
    else:
        create_single_desktop_shortcut()
        app = SessionKeeperPro()
        app.mainloop()
