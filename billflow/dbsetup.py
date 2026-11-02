"""Choosing and checking the database: the list of types, a connection test, and the setup questions."""
import getpass
import re

from billflow import database, dbconfig
from billflow.dbconfig import ENGINES, DatabaseConfigError, DatabaseTarget

_SAFE_NAME = re.compile(r"[A-Za-z0-9_]{1,63}")
_DEFAULT_USER = {"postgresql": "postgres", "mysql": "root"}


def describe_engines() -> str:
    lines = ["Databases BillFlow can use:", ""]
    for number, engine in enumerate(ENGINES.values(), 1):
        status = "ready" if dbconfig.driver_ready(engine) else f"needs: pip install {engine.pip}"
        lines += [f"  {number}) {engine.label:<11} [{status}]",
                  f"       {engine.about}",
                  f"       e.g. {engine.example}"]
    return "\n".join(lines)


def test_connection(target: DatabaseTarget) -> tuple[bool, str]:
    try:
        raw = database.connect(target)
        try:
            cur = raw.cursor()
            cur.execute("SELECT 1")
        finally:
            raw.close()
        return True, "Connected."
    except DatabaseConfigError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def database_missing(message: str) -> bool:
    return "does not exist" in message or "Unknown database" in message


def create_database(target: DatabaseTarget):
    """Create the empty database on a PostgreSQL, MySQL or MariaDB server."""
    if not _SAFE_NAME.fullmatch(target.name):
        raise DatabaseConfigError("Use only letters, digits and underscores in the database name.")
    login = dict(host=target.host, port=target.port, user=target.user, password=target.password, connect_timeout=10)
    if target.engine.dialect == "postgresql":
        import psycopg
        with psycopg.connect(dbname="postgres", autocommit=True, **login) as conn:
            conn.execute(f'CREATE DATABASE "{target.name}"')
    else:
        import pymysql
        conn = pymysql.connect(charset="utf8mb4", autocommit=True, **login)
        try:
            conn.cursor().execute(f"CREATE DATABASE IF NOT EXISTS `{target.name}` CHARACTER SET utf8mb4")
        finally:
            conn.close()


def run_wizard(ask=input, ask_secret=getpass.getpass, say=print) -> DatabaseTarget | None:
    """Ask which database to use, check it works and remember it. Returns None if nothing was saved."""
    say(describe_engines())
    say("")
    engines = list(ENGINES.values())
    choice = ask("Choose a database by number [1]: ").strip() or "1"
    if not (choice.isdigit() and 1 <= int(choice) <= len(engines)):
        say("That is not one of the numbers above. Nothing was saved.")
        return None
    engine = engines[int(choice) - 1]
    if not dbconfig.driver_ready(engine):
        say(f"{engine.label} needs a Python driver first. Install it with:\n    pip install {engine.pip}\n"
            "then run the setup again. Nothing was saved.")
        return None

    try:
        if engine.dialect == "sqlite":
            path = ask("Database file [data/billflow.db]: ").strip() or "data/billflow.db"
            target = dbconfig.parse_url(dbconfig.sqlite_url(path))
        else:
            host = ask("Server address [localhost]: ").strip() or "localhost"
            port = ask(f"Port [{engine.port}]: ").strip() or str(engine.port)
            name = ask("Database name [billflow]: ").strip() or "billflow"
            user = ask(f"User name [{_DEFAULT_USER[engine.dialect]}]: ").strip() or _DEFAULT_USER[engine.dialect]
            password = ask_secret("Password (typing is hidden): ")
            target = DatabaseTarget(engine, host=host, port=int(port), user=user, password=password, name=name)
    except (ValueError, DatabaseConfigError) as exc:
        say(f"{exc}. Nothing was saved.")
        return None

    ok, message = test_connection(target)
    if not ok and engine.dialect != "sqlite" and database_missing(message):
        if ask(f"The database '{target.name}' does not exist yet. Create it? [Y/n]: ").strip().lower() in ("", "y", "yes"):
            try:
                create_database(target)
                ok, message = test_connection(target)
            except Exception as exc:
                ok, message = False, f"Could not create it: {exc}"
    if not ok:
        say(f"Could not connect: {message}\nNothing was saved.")
        return None

    dbconfig.save(target.url)
    say(f"Saved. BillFlow will use {target.display}.")
    return target
