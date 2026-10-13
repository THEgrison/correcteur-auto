"""Petite notification discrète (sans voler le focus)."""

from __future__ import annotations

import tkinter as tk


def show_toast(root: tk.Tk, message: str, kind: str = "info", ms: int = 2200) -> None:
    colors = {
        "info": ("#1565C0", "#E3F2FD"),
        "ok": ("#2E7D32", "#E8F5E9"),
        "err": ("#C62828", "#FFEBEE"),
        "busy": ("#F9A825", "#FFF8E1"),
    }
    fg, bg = colors.get(kind, colors["info"])

    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    try:
        win.attributes("-type", "notification")
    except tk.TclError:
        pass

    frame = tk.Frame(win, bg=bg, padx=14, pady=10, highlightthickness=2, highlightbackground=fg)
    frame.pack(fill="both", expand=True)
    tk.Label(
        frame,
        text="Correcteur Auto",
        bg=bg,
        fg=fg,
        font=("DejaVu Sans", 9, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        frame,
        text=message,
        bg=bg,
        fg="#222",
        font=("DejaVu Sans", 10),
        wraplength=320,
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(2, 0))

    win.update_idletasks()
    sw = win.winfo_screenwidth()
    w = win.winfo_reqwidth()
    h = win.winfo_reqheight()
    x = max(12, sw - w - 24)
    y = 48
    win.geometry(f"+{x}+{y}")

    # Ne pas voler le focus
    try:
        win.transient(root)
    except tk.TclError:
        pass

    def close() -> None:
        try:
            win.destroy()
        except tk.TclError:
            pass

    win.after(ms, close)
