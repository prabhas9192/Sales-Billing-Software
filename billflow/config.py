import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "billflow.db")
SETTINGS_FILE = os.path.join(DATA_DIR, "billflow_settings.json")

# Fallback: if old DB exists in PROTOTYPE/billflow.db, migrate or allow usage
OLD_DB_PATH = os.path.join(BASE_DIR, "PROTOTYPE", "billflow.db")
if os.path.exists(OLD_DB_PATH) and not os.path.exists(DB_PATH):
    import shutil
    try:
        shutil.copy2(OLD_DB_PATH, DB_PATH)
    except Exception:
        pass

# Supported Currencies
CURRENCIES = {
    "INR — ₹  India":        {"symbol": "₹",  "code": "INR"},
    "USD — $  United States":{"symbol": "$",  "code": "USD"},
    "EUR — €  Euro Zone":    {"symbol": "€",  "code": "EUR"},
    "GBP — £  UK":           {"symbol": "£",  "code": "GBP"},
    "JPY — ¥  Japan":        {"symbol": "¥",  "code": "JPY"},
    "CNY — ¥  China":        {"symbol": "¥",  "code": "CNY"},
    "AED — د.إ  UAE":        {"symbol": "د.إ","code": "AED"},
    "SGD — S$  Singapore":   {"symbol": "S$", "code": "SGD"},
    "AUD — A$  Australia":   {"symbol": "A$", "code": "AUD"},
    "CAD — C$  Canada":      {"symbol": "C$", "code": "CAD"},
    "BRL — R$  Brazil":      {"symbol": "R$", "code": "BRL"},
    "ZAR — R   South Africa":{"symbol": "R",  "code": "ZAR"},
    "NGN — ₦  Nigeria":      {"symbol": "₦",  "code": "NGN"},
    "KES — Ksh Kenya":       {"symbol": "Ksh","code": "KES"},
    "PKR — ₨  Pakistan":     {"symbol": "₨",  "code": "PKR"},
    "BDT — ৳  Bangladesh":   {"symbol": "৳",  "code": "BDT"},
}

DEFAULT_SETTINGS = {
    "theme": "Shadcn Dark",
    "currency": "INR — ₹  India",
    "shop_name": "BillFlow Store",
    "shop_phone": "+91 98765 43210",
    "shop_address": "Tech District, Innovation Hub",
}

def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings.update(json.load(f))
    except Exception:
        pass
    return settings

def save_settings(settings_dict: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings_dict, f, indent=2)
    except Exception:
        pass

APP_SETTINGS = load_settings()

def curr_sym() -> str:
    """Return the active currency symbol, e.g. '₹' or '$'."""
    return CURRENCIES.get(APP_SETTINGS.get("currency", "INR — ₹  India"), {"symbol": "₹"})["symbol"]

# Typography
F_TITLE = ("Segoe UI", 16, "bold")
F_HEAD  = ("Segoe UI", 11, "bold")
F_BODY  = ("Segoe UI", 10)
F_SMALL = ("Segoe UI",  9)
F_MONO  = ("Consolas", 10)
