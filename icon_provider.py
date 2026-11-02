import os
import ctypes
from ctypes import wintypes
import win32gui
from PIL import Image
import customtkinter as ctk

_icon_cache = {}

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', wintypes.LONG),
        ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', wintypes.LONG),
        ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD),
    ]

def extract_smooth_icon(exe_path):
    """Extract true 32-bit RGBA icon with crystal-clear alpha transparency (No black halos)"""
    if not exe_path or not os.path.exists(exe_path):
        return None
    try:
        large, small = win32gui.ExtractIconEx(exe_path, 0)
        hicon = large[0] if large else (small[0] if small else None)
        if not hicon:
            return None

        icon_info = win32gui.GetIconInfo(hicon)
        hbmColor = int(icon_info[4])
        bmp = win32gui.GetObject(hbmColor)
        w, h = bmp.bmWidth, bmp.bmHeight

        hdc = win32gui.GetDC(0)
        memdc = win32gui.CreateCompatibleDC(hdc)

        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = w
        bi.biHeight = -h # top-down
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0

        buf = ctypes.create_string_buffer(w * h * 4)
        ctypes.windll.gdi32.GetDIBits(int(memdc), hbmColor, 0, h, buf, ctypes.byref(bi), 0)

        raw_img = Image.frombuffer('RGBA', (w, h), buf.raw, 'raw', 'BGRA', 0, 1)

        # Cleanup GDI handles
        for h_ic in (large or []) + (small or []):
            win32gui.DestroyIcon(h_ic)
        win32gui.DeleteObject(hbmColor)
        win32gui.DeleteObject(int(icon_info[3]))
        win32gui.DeleteDC(memdc)
        win32gui.ReleaseDC(0, hdc)

        return raw_img
    except Exception:
        return None

def get_item_icon(item_data, size=24):
    """Get razor-sharp application icon for session item"""
    exe = item_data.get("exe")
    itype = item_data.get("type", "")
    cat = item_data.get("category", "")
    target = item_data.get("target", "")

    cache_key = f"{str(exe).lower()}_{cat}_{itype}_{size}"
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    # Try smooth extraction from EXE
    if exe and os.path.exists(exe):
        pil_img = extract_smooth_icon(exe)
        if pil_img:
            # Resize with Lanczos anti-aliasing for retina-quality sharpness
            resized = pil_img.resize((size, size), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=resized, dark_image=resized, size=(size, size))
            _icon_cache[cache_key] = ctk_img
            return ctk_img

    # Fallback to Explorer / Folder icon
    if itype == "folder":
        folder_exe = r"C:\Windows\explorer.exe"
        pil_img = extract_smooth_icon(folder_exe)
        if pil_img:
            resized = pil_img.resize((size, size), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=resized, dark_image=resized, size=(size, size))
            _icon_cache[cache_key] = ctk_img
            return ctk_img

    # Generic high-contrast fallback
    from PIL import ImageDraw
    fallback_pil = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(fallback_pil)
    d.rounded_rectangle([1, 1, size-2, size-2], radius=4, fill=(51, 65, 85, 255))
    d.text((size//3, size//4), "•", fill=(255, 255, 255, 255))
    ctk_img = ctk.CTkImage(light_image=fallback_pil, dark_image=fallback_pil, size=(size, size))
    _icon_cache[cache_key] = ctk_img
    return ctk_img
