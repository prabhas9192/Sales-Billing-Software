import tkinter as tk
from tkinter import messagebox
from ..theme import theme, THEMES
from ..widgets import make_card, make_label, make_entry, make_button, make_combo
from ...config import APP_SETTINGS, CURRENCIES, save_settings, F_BODY

class SettingsView:
    def __init__(self, parent: tk.Widget, app):
        self.app = app
        self.frame = tk.Frame(parent, bg=theme.bg)

        make_label(self.frame, "Settings", style="title", bg=theme.bg).pack(anchor="w", pady=(0, 12))

        # Shop Info
        shop_card = make_card(self.frame, padx=20, pady=14)
        shop_card.pack(fill="x", pady=(0, 10))
        make_label(shop_card, "Shop / Business Info", style="heading").pack(anchor="w", pady=(0, 8))
        row_si = tk.Frame(shop_card, bg=theme.card_bg)
        row_si.pack(fill="x")

        make_label(row_si, "Shop Name", style="muted").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=3)
        self.e_sname = make_entry(row_si, width=30)
        self.e_sname.insert(0, APP_SETTINGS.get("shop_name", "My Shop"))
        self.e_sname.grid(row=0, column=1, sticky="w")

        make_label(row_si, "Phone", style="muted").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=3)
        self.e_sphone = make_entry(row_si, width=30)
        self.e_sphone.insert(0, APP_SETTINGS.get("shop_phone", ""))
        self.e_sphone.grid(row=1, column=1, sticky="w")

        make_label(row_si, "Address", style="muted").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=3)
        self.e_saddr = make_entry(row_si, width=30)
        self.e_saddr.insert(0, APP_SETTINGS.get("shop_address", ""))
        self.e_saddr.grid(row=2, column=1, sticky="w")

        # Currency
        curr_card = make_card(self.frame, padx=20, pady=14)
        curr_card.pack(fill="x", pady=(0, 10))
        make_label(curr_card, "Currency", style="heading").pack(anchor="w", pady=(0, 8))
        curr_row = tk.Frame(curr_card, bg=theme.card_bg)
        curr_row.pack(fill="x")
        make_label(curr_row, "Select currency:", style="muted").pack(side="left", padx=(0, 10))
        self.cb_curr = make_combo(curr_row, list(CURRENCIES.keys()), width=36)
        self.cb_curr.set(APP_SETTINGS.get("currency", "INR — ₹  India"))
        self.cb_curr.pack(side="left")
        self.curr_flag_lbl = tk.Label(curr_card, text="", bg=theme.card_bg, fg=theme.text, font=("Segoe UI", 22))
        self.curr_flag_lbl.pack(anchor="w", pady=(6, 0))

        def _update_flag(*_):
            key = self.cb_curr.get()
            info = CURRENCIES.get(key, {})
            self.curr_flag_lbl.config(text=f"{info.get('flag','')}  {info.get('code','')}  {info.get('symbol','')}")

        self.cb_curr.bind("<<ComboboxSelected>>", _update_flag)
        _update_flag()

        # Theme
        theme_card = make_card(self.frame, padx=20, pady=14)
        theme_card.pack(fill="x", pady=(0, 10))
        make_label(theme_card, "Appearance — Theme", style="heading").pack(anchor="w", pady=(0, 8))

        theme_btn_row = tk.Frame(theme_card, bg=theme.card_bg)
        theme_btn_row.pack(fill="x", pady=(0, 6))
        self.theme_btns = {}
        self.swatch_frame = tk.Frame(theme_card, bg=theme.card_bg, height=28)
        self.swatch_frame.pack(fill="x", pady=(4, 0))

        def _preview_theme(name):
            t = THEMES[name]
            for child in self.swatch_frame.winfo_children():
                child.destroy()
            for key, hex_c in list(t.items())[:8]:
                col_f = tk.Frame(self.swatch_frame, bg=hex_c, width=28, height=28)
                col_f.pack(side="left", padx=2)
                col_f.pack_propagate(False)
                tk.Label(col_f, bg=hex_c).pack(fill="both", expand=True)

        def _select_theme(name):
            for n, btn in self.theme_btns.items():
                btn.config(
                    relief="sunken" if n == name else "flat",
                    bg=THEMES[name]["ACCENT"] if n == name else theme.card_bg,
                    fg="white" if n == name else theme.muted
                )
            _preview_theme(name)

        self._select_theme_fn = _select_theme

        for tname in THEMES:
            t = THEMES[tname]
            btn = tk.Button(
                theme_btn_row, text=tname, bg=theme.card_bg, fg=theme.muted,
                font=F_BODY, relief="flat", bd=1, padx=12, pady=6,
                highlightbackground=t["ACCENT"], highlightthickness=2,
                cursor="hand2", command=lambda n=tname: _select_theme(n)
            )
            btn.pack(side="left", padx=4)
            self.theme_btns[tname] = btn

        _select_theme(APP_SETTINGS.get("theme", "Dark Violet"))

        # Save Button
        save_row = tk.Frame(self.frame, bg=theme.bg)
        save_row.pack(anchor="w", pady=8)
        make_button(save_row, "Save Settings", self.do_save, color=theme.success).pack(side="left", padx=(0, 8))
        make_label(save_row, "Theme takes full effect on next restart.", style="muted", bg=theme.bg).pack(side="left")

    def do_save(self):
        chosen_theme = next(
            (n for n, btn in self.theme_btns.items() if btn.cget("relief") == "sunken"),
            APP_SETTINGS["theme"]
        )
        APP_SETTINGS["shop_name"]    = self.e_sname.get().strip() or "My Shop"
        APP_SETTINGS["shop_phone"]   = self.e_sphone.get().strip()
        APP_SETTINGS["shop_address"] = self.e_saddr.get().strip()
        APP_SETTINGS["currency"]     = self.cb_curr.get()
        APP_SETTINGS["theme"]        = chosen_theme
        save_settings(APP_SETTINGS)
        theme.apply(chosen_theme)
        messagebox.showinfo("Saved",
            f"Settings saved!\n\nTheme: {chosen_theme}\n"
            f"Currency: {CURRENCIES.get(self.cb_curr.get(),{}).get('symbol','')}\n\n"
            "Restart the app for the theme to apply everywhere,\n"
            "or navigate away and back to see partial updates.")

    def refresh(self):
        self.e_sname.delete(0, "end")
        self.e_sname.insert(0, APP_SETTINGS.get("shop_name", "My Shop"))
        self.e_sphone.delete(0, "end")
        self.e_sphone.insert(0, APP_SETTINGS.get("shop_phone", ""))
        self.e_saddr.delete(0, "end")
        self.e_saddr.insert(0, APP_SETTINGS.get("shop_address", ""))
        self.cb_curr.set(APP_SETTINGS.get("currency", "INR — ₹  India"))
        self._select_theme_fn(APP_SETTINGS.get("theme", "Dark Violet"))
