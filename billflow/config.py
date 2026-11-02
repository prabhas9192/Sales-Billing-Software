import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

SETTINGS_FILE = os.path.join(DATA_DIR, "billflow_settings.json")

# Currencies, by ISO code. "locale" decides how digits are grouped (1,00,000 or 100,000).
CURRENCIES = {
    "INR": {"symbol": "₹",   "name": "Indian Rupee",       "locale": "en-IN"},
    "USD": {"symbol": "$",   "name": "US Dollar",          "locale": "en-US"},
    "EUR": {"symbol": "€",   "name": "Euro",               "locale": "en-US"},
    "GBP": {"symbol": "£",   "name": "British Pound",      "locale": "en-GB"},
    "AED": {"symbol": "AED", "name": "UAE Dirham",         "locale": "en-US"},
    "SGD": {"symbol": "S$",  "name": "Singapore Dollar",   "locale": "en-US"},
    "AUD": {"symbol": "A$",  "name": "Australian Dollar",  "locale": "en-US"},
    "CAD": {"symbol": "C$",  "name": "Canadian Dollar",    "locale": "en-US"},
    "JPY": {"symbol": "¥",   "name": "Japanese Yen",       "locale": "en-US"},
    "CNY": {"symbol": "CN¥", "name": "Chinese Yuan",       "locale": "en-US"},
    "BRL": {"symbol": "R$",  "name": "Brazilian Real",     "locale": "en-US"},
    "ZAR": {"symbol": "R",   "name": "South African Rand", "locale": "en-US"},
    "NGN": {"symbol": "₦",   "name": "Nigerian Naira",     "locale": "en-US"},
    "KES": {"symbol": "Ksh", "name": "Kenyan Shilling",    "locale": "en-US"},
    "PKR": {"symbol": "₨",   "name": "Pakistani Rupee",    "locale": "en-IN"},
    "BDT": {"symbol": "৳",   "name": "Bangladeshi Taka",   "locale": "en-IN"},
}

DEFAULT_SETTINGS = {
    "currency": "INR",
    "timezone": "",            # an IANA name such as "Asia/Kolkata"; empty means this computer's own
    "shop_name": "My Shop",
    "shop_phone": "",
    "shop_address": "",
    "shop_gstin": "",
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

def currency_code() -> str:
    """The active currency's ISO code. Settings saved by older versions held a longer label such as 'INR — ₹  India'."""
    value = str(APP_SETTINGS.get("currency", "INR"))
    return value if value in CURRENCIES else (value[:3] if value[:3] in CURRENCIES else "INR")

def curr_sym() -> str:
    """The active currency's symbol, e.g. '₹' or '$'."""
    return CURRENCIES[currency_code()]["symbol"]
