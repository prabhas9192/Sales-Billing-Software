"""
Append-only audit log.

CGST Rule 56(8) requires an electronic log of every edit or deletion, with who did it and when.
This module writes one row per action; the table has no UPDATE or DELETE routes.
"""
from billflow import clock
from billflow.database import db_all, get_conn


def log_action(conn, *, staff_id=None, staff_name="", action, entity, entity_id=None, detail=""):
    """Record one action inside the caller's transaction, so it is committed or rolled back together."""
    conn.execute(
        "INSERT INTO audit_log (date, staff_id, staff_name, action, entity, entity_id, detail) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (clock.now().strftime("%Y-%m-%d %H:%M:%S"), staff_id, str(staff_name)[:255],
         str(action)[:50], str(entity)[:50], entity_id, str(detail)[:1000]))


def log_action_standalone(*, staff_id=None, staff_name="", action, entity, entity_id=None, detail=""):
    """Record one action in its own transaction (for routes that don't hold one open)."""
    from contextlib import closing
    with closing(get_conn()) as conn:
        with conn:
            log_action(conn, staff_id=staff_id, staff_name=staff_name,
                       action=action, entity=entity, entity_id=entity_id, detail=detail)


def get_audit_log(entity=None, entity_id=None, staff_id=None, limit=200):
    """Read recent audit entries, newest first, with optional filters."""
    sql = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    if entity:
        sql += " AND entity = ?"
        params.append(entity)
    if entity_id is not None:
        sql += " AND entity_id = ?"
        params.append(int(entity_id))
    if staff_id is not None:
        sql += " AND staff_id = ?"
        params.append(int(staff_id))
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 5000)))
    return db_all(sql, tuple(params))
