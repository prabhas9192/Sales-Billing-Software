"""
Which database BillFlow uses, and the list of database types it can talk to.

A database is written as a URL:

    sqlite:///data/billflow.db                          (relative to the BillFlow folder)
    sqlite:////home/me/shop.db                          (an absolute path)
    postgresql://user:password@localhost:5432/billflow
    mysql://user:password@localhost:3306/billflow
    mariadb://user:password@localhost:3306/billflow

A bare file name such as shop.db is taken to mean SQLite.
"""
import importlib.util
import json
import os
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

from billflow.config import BASE_DIR, DATA_DIR

SAVED_FILE = os.path.join(DATA_DIR, "billflow_db.json")


class DatabaseConfigError(ValueError):
    """The database choice or its connection details are unusable."""


@dataclass(frozen=True)
class Engine:
    key: str             # the URL scheme
    label: str
    dialect: str         # sqlite | postgresql | mysql: how SQL is written for it
    driver: str | None   # Python module that talks to it
    pip: str             # what to install to get that module
    port: int | None
    example: str
    about: str


ENGINES = {e.key: e for e in (
    Engine("sqlite", "SQLite", "sqlite", None, "", None,
           "sqlite:///data/billflow.db",
           "Built in, nothing to install. One file; best for one shop on one computer."),
    Engine("postgresql", "PostgreSQL", "postgresql", "psycopg", "psycopg[binary]", 5432,
           "postgresql://user:password@localhost:5432/billflow",
           "Popular open-source server database. For several computers, bigger data, proper backups."),
    Engine("mysql", "MySQL", "mysql", "pymysql", "PyMySQL", 3306,
           "mysql://user:password@localhost:3306/billflow",
           "Very widely used server database."),
    Engine("mariadb", "MariaDB", "mysql", "pymysql", "PyMySQL", 3306,
           "mariadb://user:password@localhost:3306/billflow",
           "MySQL-compatible server database; the default on many Linux systems."),
)}
_ALIASES = {"postgres": "postgresql", "sqlite3": "sqlite"}


def sqlite_url(path: str) -> str:
    return "sqlite:///" + path


DEFAULT_URL = sqlite_url(os.path.join(DATA_DIR, "billflow.db"))


def driver_ready(engine: Engine) -> bool:
    return engine.driver is None or importlib.util.find_spec(engine.driver) is not None


@dataclass(frozen=True)
class DatabaseTarget:
    engine: Engine
    path: str = ""        # SQLite file
    host: str = ""
    port: int = 0
    user: str = ""
    password: str = ""
    name: str = ""        # database name on the server

    @property
    def url(self) -> str:
        if self.engine.dialect == "sqlite":
            return sqlite_url(self.path)
        login = quote(self.user, safe="") + (":" + quote(self.password, safe="") if self.password else "")
        return f"{self.engine.key}://{login + '@' if self.user else ''}{self.host}:{self.port}/{quote(self.name, safe='')}"

    @property
    def display(self) -> str:
        """Safe to print: never includes the password."""
        if self.engine.dialect == "sqlite":
            return f"SQLite file {self.path}"
        return f"{self.engine.label} {self.host}:{self.port}/{self.name} (user {self.user or '-'})"


def parse_url(spec: str) -> DatabaseTarget:
    spec = spec.strip()
    if not spec:
        raise DatabaseConfigError("No database given.")
    if "://" not in spec:
        spec = sqlite_url(spec)
    parts = urlsplit(spec)
    key = _ALIASES.get(parts.scheme.lower(), parts.scheme.lower())
    engine = ENGINES.get(key)
    if engine is None:
        raise DatabaseConfigError(f"Unknown database type '{parts.scheme}'. Choose one of: {', '.join(ENGINES)}.")

    if engine.dialect == "sqlite":
        path = unquote(parts.path)[1:]  # sqlite:///a.db -> a.db ; sqlite:////abs/a.db -> /abs/a.db
        if not path:
            raise DatabaseConfigError("A SQLite database needs a file path, e.g. " + engine.example)
        if not os.path.isabs(path):
            path = os.path.join(BASE_DIR, path)
        return DatabaseTarget(engine, path=os.path.normpath(path))

    name = unquote(parts.path.lstrip("/"))
    try:
        port = parts.port
    except ValueError:
        raise DatabaseConfigError("The port in the database address is not a number.") from None
    if not parts.hostname or not name:
        raise DatabaseConfigError(f"{engine.label} needs a server and a database name, e.g. {engine.example}")
    return DatabaseTarget(engine, host=parts.hostname, port=port or engine.port,
                          user=unquote(parts.username or ""), password=unquote(parts.password or ""), name=name)


def load_saved() -> str | None:
    try:
        with open(SAVED_FILE, "r", encoding="utf-8") as f:
            url = json.load(f)["url"]
        return url if isinstance(url, str) and url else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save(url: str):
    """Remember the choice. The file can hold a password, so only its owner may read it."""
    parse_url(url)
    fd = os.open(SAVED_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"url": url}, f)
    try:
        os.chmod(SAVED_FILE, 0o600)
    except OSError:
        pass


def resolve(spec: str | None = None) -> DatabaseTarget:
    """spec if given, else $BILLFLOW_DB, else the saved choice, else the SQLite default."""
    return parse_url(spec or os.environ.get("BILLFLOW_DB") or load_saved() or DEFAULT_URL)
