"""
Signed staff-session cookies: how the till remembers who signed in with their own PIN.

The cookie holds the staff id and an expiry, signed with a secret kept in the database. The
signature also covers the staff member's current PIN, so changing or removing a PIN signs that
person out everywhere. This says who is at the till for the audit log; the shop's access PIN is
what protects the data.
"""
import hashlib
import hmac
import secrets
import threading
import time

from billflow.database import db_one, db_run

COOKIE_NAME = "bf_staff"
SESSION_SECONDS = 30 * 24 * 3600
MAX_FAILURES = 5
LOCKOUT_SECONDS = 300
_SECRET_NAME = "staff_cookie"

_lock = threading.Lock()
_failures: dict[str, tuple[int, float]] = {}


def _secret() -> bytes:
    lookup = "SELECT value FROM app_secrets WHERE name = ?"
    row = db_one(lookup, (_SECRET_NAME,))
    failure = None
    if row is None:
        try:
            db_run("INSERT INTO app_secrets (name, value) VALUES (?, ?)", (_SECRET_NAME, secrets.token_hex(32)))
        except Exception as err:  # a parallel request may have created it first; the name is UNIQUE
            failure = err
        row = db_one(lookup, (_SECRET_NAME,))
    if row is None:
        raise RuntimeError("Could not create the staff cookie secret") from failure
    return row["value"].encode()


def _sign(staff_id: int, expires: int, pin: str) -> str:
    return hmac.new(_secret(), f"{staff_id}.{expires}.{pin}".encode(), hashlib.sha256).hexdigest()


def make_cookie_value(staff_id: int, pin: str) -> str:
    expires = int(time.time()) + SESSION_SECONDS
    return f"{staff_id}.{expires}.{_sign(staff_id, expires, pin)}"


def staff_from_cookie(value: str) -> dict | None:
    """The active staff member this cookie value proves, or None for anything forged, expired or stale."""
    parts = str(value).split(".")
    if len(parts) != 3 or not all(p.isascii() and p.isdigit() for p in parts[:2]):
        return None
    staff_id, expires = int(parts[0]), int(parts[1])
    if expires < time.time():
        return None
    row = db_one("SELECT id, name, role, permissions, pin FROM staff WHERE id = ? AND active = 1", (staff_id,))
    if row is None or not row["pin"]:
        return None
    if not hmac.compare_digest(parts[2], _sign(staff_id, expires, row["pin"])):
        return None
    row.pop("pin")
    return row


def seconds_locked_out(client: str) -> int:
    """How long this client must wait before trying a PIN again; 0 when it may try."""
    now = time.time()
    with _lock:
        count, since = _failures.get(client, (0, now))
        if count >= MAX_FAILURES and now - since < LOCKOUT_SECONDS:
            return int(since + LOCKOUT_SECONDS - now) + 1
        return 0


def record_failure(client: str):
    now = time.time()
    with _lock:
        if len(_failures) > 1000:
            for stale in [c for c, f in _failures.items() if now - f[1] >= LOCKOUT_SECONDS]:
                del _failures[stale]
        count, since = _failures.get(client, (0, now))
        if now - since >= LOCKOUT_SECONDS:
            count, since = 0, now
        _failures[client] = (count + 1, since)


def clear_failures(client: str):
    with _lock:
        _failures.pop(client, None)
