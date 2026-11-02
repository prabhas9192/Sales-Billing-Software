"""
The shop's own time. Bills are stamped, and "today" is worked out, in the time
zone chosen in setup rather than the computer's, so a shop's day starts and ends
when the shop's does.
"""
import datetime
import functools
import os
from zoneinfo import ZoneInfo, available_timezones

from billflow.config import APP_SETTINGS


@functools.lru_cache(maxsize=16)
def _zone(name: str):
    try:
        return ZoneInfo(name)
    except Exception:  # unknown name, empty name, or no time zone data on this computer
        return None


def now() -> datetime.datetime:
    """The current date and time in the shop's time zone, without zone information (as stored in the database)."""
    zone = _zone(APP_SETTINGS.get("timezone") or "")
    return datetime.datetime.now(zone).replace(tzinfo=None) if zone else datetime.datetime.now()


def today() -> datetime.date:
    return now().date()


def valid_zone(name: str) -> bool:
    """An IANA zone name, or '' for this computer's own time zone."""
    return name == "" or _zone(name) is not None


@functools.lru_cache(maxsize=1)
def timezone_names() -> list:
    """The zones to offer: regional names such as Asia/Kolkata, plus UTC."""
    return sorted(n for n in available_timezones() if "/" in n and not n.startswith(("Etc/", "posix/", "right/"))) + ["UTC"]


def system_timezone() -> str:
    """This computer's own time zone as an IANA name, or '' if it cannot be told."""
    name = os.environ.get("TZ", "").lstrip(":")
    if name in timezone_names():
        return name
    try:
        target = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in target:
            name = target.split("zoneinfo/", 1)[1]
            if name in timezone_names():
                return name
    except OSError:
        pass
    try:
        with open("/etc/timezone", "r", encoding="utf-8") as f:
            name = f.read().strip()
        return name if name in timezone_names() else ""
    except OSError:
        return ""
