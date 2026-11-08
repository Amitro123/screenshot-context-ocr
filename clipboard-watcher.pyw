"""
clipboard-watcher.pyw - Screenshot-to-Claude OCR watcher.

Runs silently in the background (no console window on Windows).
When a new screenshot lands on the clipboard (Win+Shift+S / Snipping Tool),
shows a small popup asking whether to extract its text for Claude.
If the user confirms, runs scripts/ocr.py --clipboard --copy --engine auto, which
replaces the clipboard image with the extracted text (Ctrl+V into Claude).

Start: start-watcher.cmd      Stop: stop-watcher.cmd
UI language: settings.json {"language": "en" | "he"}, or env SCREENSHOT_CONTEXT_LANG.
Everything is local. Extracted text is never written to the log file.
"""

import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk

# -- Paths -------------------------------------------------------------------

PLUGIN_DIR = Path(__file__).resolve().parent
PYTHON = PLUGIN_DIR / ".venv" / "Scripts" / "python.exe"  # python.exe, not pythonw: ocr.py needs stdout
OCR_SCRIPT = PLUGIN_DIR / "scripts" / "ocr.py"
LOG_FILE = PLUGIN_DIR / "watcher.log"
CREATE_NO_WINDOW = 0x08000000

# -- Settings ----------------------------------------------------------------

POLL_MS = 500      # clipboard poll interval
TOAST_MS = 9000    # auto-dismiss the question popup
DEBOUNCE_S = 3.0   # min seconds between popups

# -- Logging (never logs extracted text) --------------------------------------

def _log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
        if LOG_FILE.stat().st_size > 200_000:
            LOG_FILE.write_text("", encoding="utf-8")
    except Exception:
        pass

# -- Localisation ----------------------------------------------------------------

def _load_locale():
    lang = os.environ.get("SCREENSHOT_CONTEXT_LANG")
    if not lang:
        try:
            lang = json.loads((PLUGIN_DIR / "settings.json").read_text(encoding="utf-8")).get("language")
        except Exception:
            lang = None
    for code in (lang, "en"):
        if not code:
            continue
        try:
            return json.loads((PLUGIN_DIR / "locales" / f"{code}.json").read_text(encoding="utf-8"))
        except Exception as e:
            _log(f"locale {code!r} not loaded: {e!r}")
    raise SystemExit("No usable locale found in locales/")

T = _load_locale()
RTL = bool(T.get("rtl"))
SIDE = tk.RIGHT if RTL else tk.LEFT      # pack direction
ANCHOR = "e" if RTL else "w"             # text/row alignment
JUSTIFY = "right" if RTL else "left"

# -- Shared state ------------------------------------------------------------

_actions = queue.Queue()   # watcher thread -> UI
_results = queue.Queue()   # OCR thread -> UI: dict
_last_toast_time = 0.0
_busy = False
_get_seq = ctypes.windll.user32.GetClipboardSequenceNumber

# -- OCR (background thread) ----------------------------------------------------

def _run_ocr_bg():
    result = {"ok": False, "msg": "", "warnings": [], "engine": ""}
    if not PYTHON.exists() or not OCR_SCRIPT.exists():
        result["msg"] = T["install_incomplete"]
        _results.put(result)
        return
    try:
        r = subprocess.run(
            [str(PYTHON), str(OCR_SCRIPT), "--clipboard", "--copy", "--engine", "auto"],
            capture_output=True, timeout=120, creationflags=CREATE_NO_WINDOW)
        err = r.stderr.decode("utf-8", errors="replace")
        result["ok"] = r.returncode == 0
        if result["ok"]:
            for line in err.splitlines():
                if line.startswith("WARN:"):
                    result["warnings"].append(line[5:].strip())
                elif line.startswith("ENGINE:"):
                    result["engine"] = line[7:].strip()
            _log(f"ocr ok engine={result['engine']} chars={len(r.stdout)} warnings={result['warnings']}")
        else:
            result["msg"] = err.strip().splitlines()[-1] if err.strip() else "unknown error"
            _log(f"ocr failed: {result['msg'][:500]}")
    except subprocess.TimeoutExpired:
        result["msg"] = T["timeout"]
        _log("ocr timeout")
    except Exception as e:
        result["msg"] = str(e)
        _log(f"ocr exception: {e!r}")
    _results.put(result)

# -- Clipboard watcher (background thread) ------------------------------------------

def _watch():
    global _last_toast_time
    from PIL import Image, ImageGrab
    last_seq = _get_seq()
    _log("watcher started")
    while True:
        time.sleep(POLL_MS / 1000)
        try:
            seq = _get_seq()
            if seq == last_seq:
                continue
            last_seq = seq
            now = time.time()
            if _busy or (now - _last_toast_time) < DEBOUNCE_S:
                continue
            img = None
            for _ in range(8):  # Snipping Tool may hold the clipboard briefly
                try:
                    img = ImageGrab.grabclipboard()
                except Exception:
                    img = None
                if isinstance(img, Image.Image):
                    break
                time.sleep(0.25)
            if isinstance(img, Image.Image):
                _last_toast_time = time.time()
                _actions.put("toast")
        except Exception as e:
            _log(f"watcher error: {e!r}")

# -- UI -----------------------------------------------------------------------------

DARK, TEXT, SUBTLE = "#1e1e2e", "#cdd6f4", "#a6adc8"
BLUE, GREEN, RED, AMBER = "#89b4fa", "#a6e3a1", "#f38ba8", "#f9e2af"
GRAY, BORDER = "#313244", "#45475a"
ICON_FONT = ("Segoe UI Symbol", 13)


def _corner(root_win, w, h, margin=20, taskbar=60):
    return root_win.winfo_screenwidth() - w - margin, root_win.winfo_screenheight() - h - taskbar


def _popup(root_win, w, h):
    win = tk.Toplevel(root_win)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(bg=BORDER)
    x, y = _corner(root_win, w, h)
    win.geometry(f"{w}x{h}+{x}+{y}")
    inner = tk.Frame(win, bg=DARK, padx=16, pady=12)
    inner.place(x=1, y=1, width=w - 2, height=h - 2)
    return win, inner


def _make_toast(root_win):
    global _busy
    _busy = True
    win, inner = _popup(root_win, 380, 128)

    hdr = tk.Frame(inner, bg=DARK)
    hdr.pack(fill=tk.X, pady=(0, 4))
    tk.Label(hdr, text="✂", bg=DARK, fg=BLUE, font=ICON_FONT).pack(side=SIDE, padx=(0, 8) if not RTL else (8, 0))
    tk.Label(hdr, text=T["toast_title"], bg=DARK, fg=TEXT,
             font=("Segoe UI", 11, "bold"), anchor=ANCHOR).pack(side=SIDE)
    tk.Label(inner, text=T["toast_body"], bg=DARK, fg=SUBTLE,
             font=("Segoe UI", 9), anchor=ANCHOR, justify=JUSTIFY).pack(fill=tk.X, pady=(0, 10))

    row = tk.Frame(inner, bg=DARK)
    row.pack(anchor=ANCHOR)
    timer = [None]

    def close(yes):
        global _busy
        try:
            win.after_cancel(timer[0])
        except Exception:
            pass
        win.destroy()
        if yes:
            threading.Thread(target=_run_ocr_bg, daemon=True).start()
            root_win.after(50, lambda: _show_working(root_win))
        else:
            _busy = False

    tk.Button(row, text=T["yes"], bg=BLUE, fg=DARK, activebackground="#74c7ec", activeforeground=DARK,
              relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2", padx=10,
              command=lambda: close(True)).pack(side=SIDE)
    tk.Button(row, text=T["no"], width=7, bg=GRAY, fg=TEXT, activebackground=BORDER, activeforeground=TEXT,
              relief="flat", font=("Segoe UI", 9), cursor="hand2",
              command=lambda: close(False)).pack(side=SIDE, padx=8)
    timer[0] = win.after(TOAST_MS, lambda: close(False))


def _show_working(root_win):
    win, inner = _popup(root_win, 380, 56)
    row = tk.Frame(inner, bg=DARK)
    row.pack(fill=tk.BOTH, expand=True)
    tk.Label(row, text="⟳", bg=DARK, fg=SUBTLE, font=ICON_FONT).pack(side=SIDE, padx=(0, 8) if not RTL else (8, 0))
    tk.Label(row, text=T["working"], bg=DARK, fg=SUBTLE, font=("Segoe UI", 9), anchor=ANCHOR).pack(side=SIDE)
    root_win._working_win = win


def _show_result(root_win, res):
    global _busy
    try:
        root_win._working_win.destroy()
    except Exception:
        pass

    if res.get("started"):
        icon, color, body, ms, h = "●", BLUE, T["started"], 4000, 80
    else:
        _busy = False
        if not res["ok"]:
            icon, color, ms, h = "✖", RED, 6000, 90
            body = T["error"].format(detail=res["msg"][:140])
        elif res["warnings"]:
            reasons = "; ".join(T["reasons"].get(w.split(":")[0], w.split(":")[0]) for w in res["warnings"])
            icon, color, ms, h = "⚠", AMBER, 10000, 110
            body = T["warning"].format(reasons=reasons)
        else:
            engine = T["engine_windows"] if res["engine"] == "windows" else ""
            icon, color, ms, h = "✔", GREEN, 5000, 80
            body = T["copied"].format(engine=engine)

    win, inner = _popup(root_win, 380, h)
    row = tk.Frame(inner, bg=DARK)
    row.pack(fill=tk.BOTH, expand=True)
    tk.Label(row, text=icon, bg=DARK, fg=color, font=ICON_FONT).pack(side=SIDE, padx=(0, 10) if not RTL else (10, 0))
    tk.Label(row, text=body, bg=DARK, fg=color, font=("Segoe UI", 9), anchor=ANCHOR,
             justify=JUSTIFY, wraplength=310).pack(side=SIDE)
    win.after(ms, win.destroy)


def _pump(root_win):
    try:
        while True:
            if _actions.get_nowait() == "toast":
                _make_toast(root_win)
    except queue.Empty:
        pass
    try:
        while True:
            _show_result(root_win, _results.get_nowait())
    except queue.Empty:
        pass
    root_win.after(POLL_MS, lambda: _pump(root_win))


def main():
    # Single instance: a second launch exits quietly.
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\ScreenshotContextWatcher")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)

    root = tk.Tk()
    root.withdraw()
    root.title("Screenshot Context Watcher")
    threading.Thread(target=_watch, daemon=True).start()
    _results.put({"started": True})
    root.after(POLL_MS, lambda: _pump(root))
    root.mainloop()
    del mutex


if __name__ == "__main__":
    main()
