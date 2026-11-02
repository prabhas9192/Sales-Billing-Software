import tkinter as tk
from tkinter import ttk
from .theme import theme, shade, init_ttk_style
from ..config import F_TITLE, F_HEAD, F_BODY, F_SMALL, F_MONO

LABEL_STYLES = {
    "title":   lambda: {"fg": theme.text,    "font": F_TITLE},
    "heading": lambda: {"fg": theme.text,    "font": F_HEAD},
    "body":    lambda: {"fg": theme.text,    "font": F_BODY},
    "muted":   lambda: {"fg": theme.muted,   "font": F_SMALL},
    "accent":  lambda: {"fg": theme.accent,  "font": F_BODY},
    "success": lambda: {"fg": theme.success, "font": F_BODY},
    "warn":    lambda: {"fg": theme.warning, "font": F_BODY},
    "danger":  lambda: {"fg": theme.danger,  "font": F_BODY},
    "mono":    lambda: {"fg": theme.text,    "font": F_MONO},
}

def make_card(parent, **kw):
    kw.setdefault("bg", theme.card_bg)
    kw.setdefault("highlightbackground", theme.border)
    kw.setdefault("highlightthickness", 1)
    kw.setdefault("relief", "flat")
    return tk.Frame(parent, **kw)

def make_label(parent, text, style="body", bg=None, **kw):
    style_fn = LABEL_STYLES.get(style, LABEL_STYLES["body"])
    cfg = style_fn()
    cfg["bg"] = bg or theme.card_bg
    cfg.update(kw)
    return tk.Label(parent, text=text, **cfg)

def make_entry(parent, width=20, **kw):
    kw.setdefault("bg", theme.input_bg)
    kw.setdefault("fg", theme.text)
    kw.setdefault("insertbackground", theme.accent)
    kw.setdefault("relief", "flat")
    kw.setdefault("font", F_BODY)
    kw.setdefault("bd", 5)
    return tk.Entry(parent, width=width, **kw)

def make_button(parent, text, command, color=None, **kw):
    btn_color = color or theme.accent
    btn = tk.Button(
        parent, text=text, command=command,
        bg=btn_color, fg="white", font=F_BODY,
        relief="flat", bd=0, padx=10, pady=5,
        activebackground=btn_color, activeforeground="white",
        cursor="hand2", **kw
    )
    def _enter(e): btn.config(bg=shade(btn_color, -20))
    def _leave(e): btn.config(bg=btn_color)
    btn.bind("<Enter>", _enter)
    btn.bind("<Leave>", _leave)
    return btn

def make_combo(parent, values=(), width=20, **kw):
    init_ttk_style()
    return ttk.Combobox(parent, values=list(values), width=width,
                        state="readonly", style="App.TCombobox", **kw)

def make_listbox(container, **kw):
    kw.setdefault("bg", theme.input_bg)
    kw.setdefault("fg", theme.text)
    kw.setdefault("selectbackground", theme.accent)
    kw.setdefault("selectforeground", "white")
    kw.setdefault("font", F_MONO)
    kw.setdefault("relief", "flat")
    kw.setdefault("bd", 0)
    kw.setdefault("activestyle", "none")
    kw.setdefault("highlightbackground", theme.border)
    kw.setdefault("highlightthickness", 1)
    lb = tk.Listbox(container, **kw)
    sb = ttk.Scrollbar(container, orient="vertical", command=lb.yview)
    lb.configure(yscrollcommand=sb.set)
    return lb, sb

def sep(parent, bg=None, pady=6):
    tk.Frame(parent, bg=bg or theme.border, height=1).pack(fill="x", pady=pady)

def field_group(parent, label_text, bg=None):
    make_label(parent, label_text, style="muted", bg=bg or theme.card_bg).pack(anchor="w", pady=(5, 1))
    e = make_entry(parent, width=24)
    e.pack(anchor="w")
    return e

def stat_tile(parent, title, var, color=None):
    tile_color = color or theme.accent
    c = make_card(parent, padx=14, pady=10)
    c.pack(side="left", fill="both", expand=True, padx=5)
    make_label(c, title, style="muted").pack(anchor="w")
    tk.Label(c, textvariable=var, bg=theme.card_bg, fg=tile_color,
             font=("Segoe UI", 18, "bold")).pack(anchor="w")
    return c
