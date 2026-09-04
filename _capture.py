"""Captura PrintWindow de la ventana 'SMA 2.0' (ctypes puro, sin pywin32)."""
import ctypes
import sys
import time
from ctypes import wintypes

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()

W = int(sys.argv[1]) if len(sys.argv) > 1 else 1920
H = int(sys.argv[2]) if len(sys.argv) > 2 else 2400
OUT = sys.argv[3] if len(sys.argv) > 3 else "_shot.png"

target = []

@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def enum_cb(hwnd, lparam):
    if user32.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if buf.value.startswith("SMA 2.0"):
            target.append(hwnd)
    return True

user32.EnumWindows(enum_cb, 0)
if not target:
    print("NO_WINDOW")
    sys.exit(1)
hwnd = target[0]

user32.MoveWindow(hwnd, 0, 0, W, H, True)
time.sleep(3.5)

rect = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
w, h = rect.right - rect.left, rect.bottom - rect.top

hdc_win = user32.GetWindowDC(hwnd)
hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
hbmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
gdi32.SelectObject(hdc_mem, hbmp)
ok = user32.PrintWindow(hwnd, hdc_mem, 2)  # PW_RENDERFULLCONTENT

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]

bmi = BITMAPINFOHEADER()
bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
bmi.biWidth, bmi.biHeight = w, -h
bmi.biPlanes, bmi.biBitCount, bmi.biCompression = 1, 32, 0
buf = ctypes.create_string_buffer(w * h * 4)
gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
img.save(OUT)
print(f"SAVED {OUT} {w}x{h} printwindow_ok={ok}")

gdi32.DeleteObject(hbmp)
gdi32.DeleteDC(hdc_mem)
user32.ReleaseDC(hwnd, hdc_win)
