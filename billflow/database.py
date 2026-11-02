"""
Connections to whichever database is selected (see dbconfig), behind one interface.

The rest of BillFlow writes SQLite-style SQL with ? placeholders and reads rows
by column name; this module adapts that for PostgreSQL, MySQL and MariaDB.
"""
import os
import queue
import sqlite3
import threading
import time

from billflow import dbconfig, dialects, schema
from billflow.dbconfig import DatabaseConfigError

_lock = threading.Lock()
_target = None
_pool = None


def configure(spec: str | None = None):
    """Choose the database (a URL, see dbconfig); None picks the saved or default one."""
    global _target, _pool
    target = dbconfig.resolve(spec)
    with _lock:
        if _pool is not None:
            _pool.close_all()
        _target = target
        _pool = Pool(target) if target.engine.dialect != "sqlite" else None
    return target


def current():
    """The DatabaseTarget in use."""
    if _target is None:
        configure()
    return _target


def connect(target):
    """Open one raw connection to target, with rows as dicts (SQLite: sqlite3.Row)."""
    engine = target.engine
    if engine.dialect == "sqlite":
        os.makedirs(os.path.dirname(target.path), exist_ok=True)
        # SQLite lets one writer in at a time. When several devices bill at once the others wait
        # for their turn; 30 seconds (not the default 5) keeps a busy moment slow rather than failed.
        raw = sqlite3.connect(target.path, timeout=30)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        raw.execute("PRAGMA journal_mode = WAL")
        return raw
    if not dbconfig.driver_ready(engine):
        raise DatabaseConfigError(f"{engine.label} needs the {engine.driver} driver. Install it with:  pip install {engine.pip}")
    if engine.dialect == "postgresql":
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(host=target.host, port=target.port, user=target.user, password=target.password,
                               dbname=target.name, row_factory=dict_row, connect_timeout=10)
    import pymysql
    return pymysql.connect(host=target.host, port=target.port, user=target.user, password=target.password,
                           database=target.name, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
                           autocommit=False, connect_timeout=10,
                           init_command="SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")


def _alive(raw) -> bool:
    try:
        cur = raw.cursor()
        cur.execute("SELECT 1")
        cur.fetchall()
        raw.rollback()
        return True
    except Exception:
        return False


class Pool:
    """Keeps a few server connections open so each query does not pay to log in again."""
    MAX_IDLE = 8
    CHECK_AFTER = 30  # seconds idle before a connection is tested before reuse

    def __init__(self, target):
        self.target = target
        self._idle = queue.LifoQueue()

    def acquire(self):
        while True:
            try:
                raw, since = self._idle.get_nowait()
            except queue.Empty:
                return Connection(connect(self.target), self.target.engine.dialect, self)
            if time.time() - since > self.CHECK_AFTER and not _alive(raw):
                self._discard(raw)
                continue
            return Connection(raw, self.target.engine.dialect, self)

    def release(self, raw):
        try:
            raw.rollback()  # anything not committed is abandoned
        except Exception:
            self._discard(raw)
            return
        if self._idle.qsize() >= self.MAX_IDLE:
            self._discard(raw)
        else:
            self._idle.put((raw, time.time()))

    def close_all(self):
        while True:
            try:
                self._discard(self._idle.get_nowait()[0])
            except queue.Empty:
                return

    @staticmethod
    def _discard(raw):
        try:
            raw.close()
        except Exception:
            pass


class Cursor:
    """The result of Connection.execute on a server database."""

    def __init__(self, cur, returning=False):
        self._cur = cur
        self.lastrowid = getattr(cur, "lastrowid", None)
        if returning:
            row = cur.fetchone()
            self.lastrowid = row["id"] if row else None

    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        if self._cur.description is None:
            return None
        return dialects.make_row(self._cur.fetchone())

    def fetchall(self):
        if self._cur.description is None:
            return []
        return [dialects.make_row(r) for r in self._cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class Connection:
    """One connection. Use it like sqlite3's: execute(), then `with conn:` to commit or roll back."""

    def __init__(self, raw, dialect, pool=None):
        self.raw = raw
        self.dialect = dialect
        self._pool = pool

    @property
    def for_update(self) -> str:
        """Add to a SELECT whose rows you are about to change, so no one else changes them first."""
        return "" if self.dialect == "sqlite" else " FOR UPDATE"

    def begin_write(self):
        """Start a transaction that will write. SQLite takes its write lock now; the server
        databases lock individual rows instead (see for_update)."""
        if self.dialect == "sqlite":
            self.raw.execute("BEGIN IMMEDIATE")

    def execute(self, sql, params=()):
        if self.dialect == "sqlite":
            return self.raw.execute(sql, params)
        sql = dialects.translate(sql, self.dialect)
        returning = self.dialect == "postgresql" and dialects.wants_returning(sql)
        if returning:
            sql += " RETURNING id"
        cur = self.raw.cursor()
        cur.execute(sql, tuple(params))
        return Cursor(cur, returning)

    def executemany(self, sql, seq):
        if self.dialect == "sqlite":
            return self.raw.executemany(sql, seq)
        cur = self.raw.cursor()
        cur.executemany(dialects.translate(sql, self.dialect), [tuple(p) for p in seq])
        return Cursor(cur)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.rollback() if exc_type else self.commit()
        return False

    def close(self):
        if self._pool is not None:
            self._pool.release(self.raw)
        else:
            self.raw.close()


def get_conn() -> Connection:
    target = current()
    if _pool is not None:
        return _pool.acquire()
    return Connection(connect(target), target.engine.dialect)


def init_db():
    """Create any missing tables and indexes."""
    conn = get_conn()
    try:
        with conn:
            schema.create_schema(conn)
    finally:
        conn.close()


def _run(sql, params, fetch):
    conn = get_conn()
    try:
        with conn:
            return fetch(conn.execute(sql, params))
    finally:
        conn.close()


def db_all(sql: str, params: tuple = ()) -> list[dict]:
    return _run(sql, params, lambda cur: [dict(r) for r in cur.fetchall()])


def db_one(sql: str, params: tuple = ()) -> dict | None:
    row = _run(sql, params, lambda cur: cur.fetchone())
    return dict(row) if row else None


def db_run(sql: str, params: tuple = ()) -> int:
    return _run(sql, params, lambda cur: cur.lastrowid)


def db_runmany(sql: str, seq: list):
    conn = get_conn()
    try:
        with conn:
            conn.executemany(sql, seq)
    finally:
        conn.close()


def database_info() -> dict:
    """What the Settings page shows about the database in use."""
    target = current()
    version_sql = "SELECT sqlite_version() AS v" if target.engine.dialect == "sqlite" else "SELECT version() AS v"
    counts = {t: db_one(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in ("bills", "products", "customers")}
    return {
        "engine": target.engine.key,
        "label": target.engine.label,
        "location": target.display,
        "version": str(db_one(version_sql)["v"]).split(" on ")[0][:60],
        "counts": counts,
    }
