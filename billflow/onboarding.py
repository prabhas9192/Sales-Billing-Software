"""
First-run setup: what the setup screen offers, and applying what the owner chose.

Nothing is saved until the chosen database has been reached and its tables
created, so a typing mistake cannot leave BillFlow pointing at a database that
does not work.
"""
import json
import os

from billflow import clock, config, database, dbconfig, dbsetup
from billflow.config import APP_SETTINGS, CURRENCIES
from billflow.dbconfig import ENGINES, DatabaseConfigError, DatabaseTarget
from billflow.sample_data import load_sample_data
from billflow.web.access import PIN_PATTERN, AccessControl

SETUP_FILE = os.path.join(config.DATA_DIR, "billflow_setup.json")

_TEXT_FIELDS = {  # setting -> (what to call it, longest allowed)
    "shop_name": ("shop name", 120),
    "shop_phone": ("phone number", 40),
    "shop_address": ("address", 250),
    "shop_gstin": ("GSTIN", 20),
}
_DEFAULT_USER = {"postgresql": "postgres", "mysql": "root"}


class SetupError(ValueError):
    """The owner's choices cannot be used; the message says what to change."""


def is_complete() -> bool:
    """Has anything chosen a database yet? If not, this is a first run."""
    return os.path.exists(SETUP_FILE) or bool(os.environ.get("BILLFLOW_DB")) or dbconfig.load_saved() is not None


def share_on_network() -> bool:
    """Did the owner ask, in setup, for phones on the network to be allowed in?"""
    try:
        with open(SETUP_FILE, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("share_on_network"))
    except (OSError, ValueError, AttributeError):
        return False


def clean_settings(data: dict, require_name: bool = False) -> dict:
    """The shop settings in data that are valid, tidied up. Raises SetupError for any that are not."""
    cleaned = {}
    for key, (label, limit) in _TEXT_FIELDS.items():
        if key in data:
            value = str(data[key] or "").strip()
            if len(value) > limit:
                raise SetupError(f"Keep the {label} under {limit} characters.")
            cleaned[key] = value
    if ("shop_name" in cleaned or require_name) and not cleaned.get("shop_name"):
        raise SetupError("Enter your shop's name.")
    if "currency" in data:
        code = str(data["currency"] or "").strip().upper()
        if code not in CURRENCIES:
            raise SetupError("Choose a currency from the list.")
        cleaned["currency"] = code
    if "timezone" in data:
        name = str(data["timezone"] or "").strip()
        if not clock.valid_zone(name):
            raise SetupError("That time zone is not in the list. Pick one such as Asia/Kolkata, or leave it empty to use this computer's.")
        cleaned["timezone"] = name
    return cleaned


def build_target(spec: dict) -> DatabaseTarget:
    """The database described by the setup form's fields."""
    engine = ENGINES.get(str(spec.get("engine") or ""))
    if engine is None:
        raise SetupError("Choose a database type.")
    if engine.dialect == "sqlite":
        return dbconfig.parse_url(dbconfig.sqlite_url(str(spec.get("path") or "data/billflow.db").strip()))
    try:
        port = int(spec.get("port") or engine.port)
    except (TypeError, ValueError):
        raise SetupError("The port must be a number.") from None
    name = str(spec.get("name") or "").strip()
    if not name:
        raise SetupError("Enter the name of the database.")
    return DatabaseTarget(engine, host=str(spec.get("host") or "localhost").strip(), port=port,
                          user=str(spec.get("user") or _DEFAULT_USER[engine.dialect]).strip(),
                          password=str(spec.get("password") or ""), name=name)


def state() -> dict:
    """Everything the setup screen needs to draw itself. Never includes a password."""
    current = None
    if is_complete():
        target = database.current()
        current = {"engine": target.engine.key, "display": target.display, "path": target.path,
                   "host": target.host, "port": target.port, "name": target.name, "user": target.user}
    return {
        "complete": is_complete(),
        "database": current,
        "engines": [{"key": e.key, "label": e.label, "about": e.about, "port": e.port, "server": e.dialect != "sqlite",
                     "ready": dbconfig.driver_ready(e), "pip": e.pip, "default_user": _DEFAULT_USER.get(e.dialect, "")}
                    for e in ENGINES.values()],
        "settings": {key: APP_SETTINGS.get(key, "") for key in (*_TEXT_FIELDS, "currency", "timezone")},
        "currencies": [{"code": c, "name": v["name"], "symbol": v["symbol"]} for c, v in CURRENCIES.items()],
        "timezones": clock.timezone_names(),
        "system_timezone": clock.system_timezone(),
        "share": {"enabled": share_on_network()},
    }


def test_database(spec: dict) -> dict:
    """Can BillFlow use this database? Used by the setup screen's Test button."""
    target = build_target(spec)
    if target.engine.dialect == "sqlite":
        if os.path.isdir(target.path):
            return {"ok": False, "missing": False, "message": f"{target.path} is a folder. Give a file name, such as billflow.db."}
        probe = os.path.dirname(target.path)
        while probe and not os.path.isdir(probe):
            probe = os.path.dirname(probe)
        if not probe or not os.access(probe, os.W_OK):
            return {"ok": False, "missing": False, "message": f"BillFlow cannot write to {probe or target.path}."}
        kind = "the existing file" if os.path.exists(target.path) else "a new file"
        return {"ok": True, "missing": False, "message": f"BillFlow will use {kind}: {target.path}"}
    ok, message = dbsetup.test_connection(target)
    return {"ok": ok, "message": message, "missing": (not ok) and dbsetup.database_missing(message)}


def apply(payload: dict, sharing_active: bool = False) -> dict:
    """Carry out the owner's choices. sharing_active: BillFlow is already letting other devices in."""
    settings = clean_settings(payload.get("settings") or {}, require_name=True)
    target = build_target(payload.get("database") or {})
    share = payload.get("share") or {}
    share_on = bool(share.get("enabled"))
    pin = str(share.get("pin") or "").strip()
    if share_on and pin and not PIN_PATTERN.fullmatch(pin):
        raise SetupError("The phone PIN must be 4 to 12 digits, or leave it empty for a random one.")

    # The database must work before anything at all is saved.
    if target.engine.dialect != "sqlite":
        if not dbconfig.driver_ready(target.engine):
            raise SetupError(f"{target.engine.label} needs a driver first. Install it with:  pip install {target.engine.pip}")
        ok, message = dbsetup.test_connection(target)
        if not ok and dbsetup.database_missing(message) and payload.get("create_database"):
            try:
                dbsetup.create_database(target)
            except Exception as exc:
                raise SetupError(f"Could not create the database: {exc}") from exc
            ok, message = dbsetup.test_connection(target)
        if not ok:
            raise SetupError(f"Cannot connect to the database: {message}")

    messages = []
    try:
        database.configure(target.url)
        database.init_db()
        if payload.get("sample_data"):
            load_sample_data(say=messages.append)
    except Exception as exc:
        database.configure()  # back to whatever was chosen before
        raise SetupError(f"Could not prepare the database: {exc}") from exc

    dbconfig.save(target.url)
    APP_SETTINGS.update(settings)
    config.save_settings(APP_SETTINGS)
    shown_pin = AccessControl(pin=pin or None).pin if share_on else None
    with open(SETUP_FILE, "w", encoding="utf-8") as f:
        json.dump({"completed": True, "share_on_network": share_on}, f)
    return {"success": True, "database": target.display, "messages": messages, "share": share_on,
            "pin": shown_pin, "restart_needed": share_on != sharing_active}
