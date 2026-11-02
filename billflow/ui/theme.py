from tkinter import ttk
from ..config import APP_SETTINGS

THEMES = {
    "Shadcn Dark": {
        "BG": "#09090b", "SIDEBAR_BG": "#121215", "CARD_BG": "#18181b",
        "ACCENT": "#10b981", "DANGER": "#ef4444", "SUCCESS": "#10b981",
        "WARNING": "#f59e0b", "TEXT": "#fafafa", "MUTED": "#a1a1aa",
        "INPUT_BG": "#141417", "BORDER": "#27272a",
        "CAL_HIGH": "#10b981", "CAL_MED": "#f59e0b",
        "CAL_LOW": "#ef4444", "CAL_EMPTY": "#141417",
    },
    "Shadcn Light": {
        "BG": "#f8fafc", "SIDEBAR_BG": "#f1f5f9", "CARD_BG": "#ffffff",
        "ACCENT": "#2563eb", "DANGER": "#dc2626", "SUCCESS": "#16a34a",
        "WARNING": "#d97706", "TEXT": "#09090b", "MUTED": "#64748b",
        "INPUT_BG": "#f8fafc", "BORDER": "#e2e8f0",
        "CAL_HIGH": "#16a34a", "CAL_MED": "#d97706",
        "CAL_LOW": "#dc2626", "CAL_EMPTY": "#f1f5f9",
    },
    "Dark Violet": {
        "BG": "#1a1a28", "SIDEBAR_BG": "#111120", "CARD_BG": "#22223a",
        "ACCENT": "#5b54f0", "DANGER": "#e05050", "SUCCESS": "#38d47a",
        "WARNING": "#f0b429", "TEXT": "#dcdcf0", "MUTED": "#6868a0",
        "INPUT_BG": "#2c2c46", "BORDER": "#30305a",
        "CAL_HIGH": "#38d47a", "CAL_MED": "#f0b429",
        "CAL_LOW": "#e05050", "CAL_EMPTY": "#2c2c46",
    },
    "Midnight Blue": {
        "BG": "#0d1117", "SIDEBAR_BG": "#090d12", "CARD_BG": "#161b22",
        "ACCENT": "#58a6ff", "DANGER": "#f85149", "SUCCESS": "#3fb950",
        "WARNING": "#d29922", "TEXT": "#c9d1d9", "MUTED": "#484f58",
        "INPUT_BG": "#21262d", "BORDER": "#30363d",
        "CAL_HIGH": "#3fb950", "CAL_MED": "#d29922",
        "CAL_LOW": "#f85149", "CAL_EMPTY": "#21262d",
    },
    "Solarized Dark": {
        "BG": "#002b36", "SIDEBAR_BG": "#001e26", "CARD_BG": "#073642",
        "ACCENT": "#268bd2", "DANGER": "#dc322f", "SUCCESS": "#859900",
        "WARNING": "#b58900", "TEXT": "#839496", "MUTED": "#586e75",
        "INPUT_BG": "#073642", "BORDER": "#094656",
        "CAL_HIGH": "#859900", "CAL_MED": "#b58900",
        "CAL_LOW": "#dc322f", "CAL_EMPTY": "#073642",
    },
    "Light": {
        "BG": "#f0f2f5", "SIDEBAR_BG": "#e2e6ea", "CARD_BG": "#ffffff",
        "ACCENT": "#4361ee", "DANGER": "#e63946", "SUCCESS": "#2a9d5c",
        "WARNING": "#e07c00", "TEXT": "#1d2333", "MUTED": "#6b7280",
        "INPUT_BG": "#f8f9fa", "BORDER": "#d1d5db",
        "CAL_HIGH": "#2a9d5c", "CAL_MED": "#e07c00",
        "CAL_LOW": "#e63946", "CAL_EMPTY": "#e9ecef",
    },
}

class ThemeManager:
    def __init__(self):
        self.name = APP_SETTINGS.get("theme", "Shadcn Dark")
        self.apply(self.name)

    def apply(self, theme_name: str):
        self.name = theme_name
        t = THEMES.get(theme_name, THEMES["Shadcn Dark"])
        self.bg         = t["BG"]
        self.sidebar_bg = t["SIDEBAR_BG"]
        self.card_bg    = t["CARD_BG"]
        self.accent     = t["ACCENT"]
        self.danger     = t["DANGER"]
        self.success    = t["SUCCESS"]
        self.warning    = t["WARNING"]
        self.text       = t["TEXT"]
        self.muted      = t["MUTED"]
        self.input_bg   = t["INPUT_BG"]
        self.border     = t["BORDER"]
        self.cal_high   = t["CAL_HIGH"]
        self.cal_med    = t["CAL_MED"]
        self.cal_low    = t["CAL_LOW"]
        self.cal_empty  = t["CAL_EMPTY"]

theme = ThemeManager()

def shade(hex_color: str, delta: int) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r, g, b = (max(0, min(255, v + delta)) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"

_ttk_style_done = False
def init_ttk_style():
    global _ttk_style_done
    s = ttk.Style()
    try:
        s.theme_use("clam")
    except Exception:
        pass

    # Combobox Styling
    s.configure("App.TCombobox",
        fieldbackground=theme.input_bg, background=theme.input_bg,
        foreground=theme.text, selectbackground=theme.accent,
        selectforeground="white", bordercolor=theme.border, arrowcolor=theme.accent)
    s.map("App.TCombobox",
        fieldbackground=[("readonly", theme.input_bg)],
        foreground=[("readonly", theme.text)])

    # Scrollbar Styling
    s.configure("Vertical.TScrollbar",
        troughcolor=theme.sidebar_bg, background=theme.border,
        arrowcolor=theme.muted, bordercolor=theme.sidebar_bg)
    s.map("Vertical.TScrollbar", background=[("active", theme.accent)])

    # Treeview (Data tables) Modern Styling
    s.configure("Treeview",
        background=theme.card_bg,
        foreground=theme.text,
        fieldbackground=theme.card_bg,
        borderwidth=0,
        rowheight=26,
        font=("Segoe UI", 9)
    )
    s.configure("Treeview.Heading",
        background=theme.sidebar_bg,
        foreground=theme.muted,
        relief="flat",
        borderwidth=1,
        font=("Segoe UI", 9, "bold")
    )
    s.map("Treeview",
        background=[("selected", theme.accent)],
        foreground=[("selected", "#ffffff" if theme.name != "Shadcn Light" else "#ffffff")]
    )

    _ttk_style_done = True
