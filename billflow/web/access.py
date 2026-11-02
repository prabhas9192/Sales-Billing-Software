"""
Access control for BillFlow's LAN mode.

The computer running BillFlow is always trusted. Any other device must enter
the access PIN once and then holds a signed session cookie. Requests that
arrive through a proxy or tunnel are never treated as local.
"""
import hmac
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import threading
import time
import urllib.parse

from billflow.config import DATA_DIR

ACCESS_FILE = os.path.join(DATA_DIR, "billflow_access.json")
COOKIE_NAME = "bf_session"
SESSION_SECONDS = 30 * 24 * 3600
MAX_FAILURES = 5
LOCKOUT_SECONDS = 300
PIN_PATTERN = re.compile(r"\d{4,12}")
PROXY_HEADERS = ("X-Forwarded-For", "Forwarded", "X-Real-IP")


def is_loopback(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(str(addr).split("%")[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback


def host_allowed(host_header: str) -> bool:
    """Accept only IP addresses, localhost and this computer's own name in the
    Host header. A DNS-rebinding attack arrives under the attacker's domain, so
    it is refused here before the local-computer exemption can apply."""
    try:
        name = urllib.parse.urlsplit("//" + host_header).hostname
    except ValueError:
        return False
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    me = socket.gethostname().lower()
    return name in ("localhost", me, me + ".local") or name.endswith(".localhost")


def lan_addresses() -> list:
    """This computer's IPv4 addresses on the local network, main one first."""
    found = []
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))  # sends nothing; just picks the outgoing interface
        found.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    try:
        found += [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    unique = []
    for addr in found:
        ip = ipaddress.ip_address(addr)
        if not (ip.is_loopback or ip.is_link_local or ip.is_unspecified) and addr not in unique:
            unique.append(addr)
    return unique


class AccessControl:
    """The access PIN, the secret that signs session cookies, and a brute-force limiter."""

    def __init__(self, path: str | None = None, pin: str | None = None):
        self.path = path or ACCESS_FILE
        self.pin = ""
        self._secret = ""
        self._lock = threading.Lock()
        self._failures: dict[str, tuple[int, float]] = {}
        self._load()
        if pin is not None:
            self.set_pin(pin)
        elif not self.pin:
            self.set_pin(f"{secrets.randbelow(10 ** 6):06d}")

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if PIN_PATTERN.fullmatch(saved["pin"]) and saved["secret"]:
                self.pin, self._secret = saved["pin"], saved["secret"]
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def set_pin(self, pin: str):
        """Change the PIN. A new PIN also replaces the signing secret, which signs out every device."""
        if not PIN_PATTERN.fullmatch(str(pin)):
            raise ValueError("The access PIN must be 4 to 12 digits.")
        if pin == self.pin and self._secret:
            return
        self.pin, self._secret = str(pin), secrets.token_hex(32)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pin": self.pin, "secret": self._secret}, f)
        try:
            os.chmod(self.path, 0o600)  # the mode above only applies when the file is first created
        except OSError:
            pass

    def make_token(self) -> str:
        expires = str(int(time.time()) + SESSION_SECONDS)
        return f"{expires}.{self._sign(expires)}"

    def valid_token(self, token: str) -> bool:
        expires, _, signature = str(token).partition(".")
        if not expires.isdigit() or int(expires) < time.time():
            return False
        return hmac.compare_digest(signature, self._sign(expires))

    def _sign(self, value: str) -> str:
        return hmac.new(self._secret.encode(), value.encode(), hashlib.sha256).hexdigest()

    def check_pin(self, client: str, attempt: str) -> tuple[bool, int]:
        """Returns (accepted, seconds_to_wait). After MAX_FAILURES wrong PINs a
        client is locked out, and stays locked out even if it then sends the right one."""
        now = time.time()
        with self._lock:
            if len(self._failures) > 1000:
                self._failures = {c: f for c, f in self._failures.items() if now - f[1] < LOCKOUT_SECONDS}
            count, since = self._failures.get(client, (0, now))
            if now - since >= LOCKOUT_SECONDS:
                count, since = 0, now
            if count >= MAX_FAILURES:
                return False, int(since + LOCKOUT_SECONDS - now) + 1
            if hmac.compare_digest(attempt.encode(), self.pin.encode()):
                self._failures.pop(client, None)
                return True, 0
            count += 1
            self._failures[client] = (count, since)
            return False, (int(since + LOCKOUT_SECONDS - now) + 1 if count >= MAX_FAILURES else 0)
