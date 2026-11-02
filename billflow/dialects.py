"""
BillFlow's SQL is written once, for SQLite, with ? placeholders. This module
rewrites it for the other databases and tidies the values they hand back.
"""
import re
from decimal import Decimal

_QUOTED = re.compile(r"('(?:[^']|'')*')")
_INSERT_OR_IGNORE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO", re.I)
_INSERT = re.compile(r"^\s*INSERT\b", re.I)


def translate(sql: str, dialect: str) -> str:
    """SQLite-style SQL -> SQL for dialect ('sqlite', 'postgresql' or 'mysql')."""
    if dialect == "sqlite":
        return sql
    # PostgreSQL and MySQL drivers treat % as a format character, even inside quotes.
    parts = _QUOTED.split(sql.replace("%", "%%"))
    # Odd entries are quoted text, which is data and must stay as it is.
    for i in range(0, len(parts), 2):
        parts[i] = parts[i].replace("?", "%s")
        if dialect == "postgresql":
            # SQLite's LIKE ignores case; PostgreSQL's does not.
            parts[i] = re.sub(r"\bLIKE\b", "ILIKE", parts[i], flags=re.I)
    sql = "".join(parts)
    if _INSERT_OR_IGNORE.match(sql):
        if dialect == "mysql":
            sql = _INSERT_OR_IGNORE.sub("INSERT IGNORE INTO", sql, count=1)
        else:
            sql = _INSERT_OR_IGNORE.sub("INSERT INTO", sql, count=1) + " ON CONFLICT DO NOTHING"
    return sql


def wants_returning(sql: str) -> bool:
    """PostgreSQL has no cursor.lastrowid, so INSERTs ask for the new id back instead."""
    return bool(_INSERT.match(sql)) and "RETURNING" not in sql.upper()


def clean_value(value):
    """MySQL returns SUM() of integers as Decimal; hand back plain numbers."""
    if isinstance(value, Decimal):
        whole = value == value.to_integral_value() and value.as_tuple().exponent >= 0
        return int(value) if whole else float(value)
    return value


class Row(dict):
    """A result row: look values up by column name or by position, as with sqlite3.Row."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def make_row(raw):
    return None if raw is None else Row((name, clean_value(value)) for name, value in raw.items())
