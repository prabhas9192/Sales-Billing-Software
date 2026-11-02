"""
Shared test setup: every test runs on its own empty database.

By default that is a throwaway SQLite file. To run the same tests on another
database, point BILLFLOW_TEST_DB at an empty PostgreSQL / MySQL / MariaDB
database, for example:

    BILLFLOW_TEST_DB=postgresql://postgres@localhost/billflow_test python -m unittest discover -s tests

The tables are dropped between tests, so the database name must contain "test".
"""
import os
import tempfile
import unittest

from billflow import database, dbconfig, schema


def reset_tables():
    conn = database.get_conn()
    try:
        with conn:
            if conn.dialect == "mysql":
                conn.execute("SET FOREIGN_KEY_CHECKS = 0")
            for name in reversed(schema.TABLE_NAMES):
                conn.execute(f"DROP TABLE IF EXISTS {name}" + (" CASCADE" if conn.dialect == "postgresql" else ""))
            if conn.dialect == "mysql":
                conn.execute("SET FOREIGN_KEY_CHECKS = 1")
    finally:
        conn.close()


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        url = os.environ.get("BILLFLOW_TEST_DB")
        if url:
            target = database.configure(url)
            if "test" not in target.name.lower():
                raise RuntimeError("BILLFLOW_TEST_DB must name a database with 'test' in its name: "
                                   "the tables in it are dropped between tests.")
            reset_tables()
        else:
            database.configure(dbconfig.sqlite_url(os.path.join(self.tmp.name, "test.db")))
        database.init_db()

    def tearDown(self):
        database.configure()  # back to the normal choice
        self.tmp.cleanup()
        super().tearDown()


def isolate_setup(test):
    """Give a test its own setup state: its own saved-database file, shop settings, PIN file and
    'setup finished' marker, so it cannot read or change the real ones. Returns the folder they live in."""
    import os
    from unittest import mock
    from billflow import config, onboarding
    from billflow.config import APP_SETTINGS
    from billflow.web import access

    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    for module, name, filename in ((onboarding, "SETUP_FILE", "setup.json"), (dbconfig, "SAVED_FILE", "db.json"),
                                   (config, "SETTINGS_FILE", "settings.json"), (access, "ACCESS_FILE", "access.json")):
        patcher = mock.patch.object(module, name, os.path.join(tmp.name, filename))
        patcher.start()
        test.addCleanup(patcher.stop)
    env = mock.patch.dict(os.environ)
    env.start()
    test.addCleanup(env.stop)
    os.environ.pop("BILLFLOW_DB", None)

    before = dict(APP_SETTINGS)
    test.addCleanup(lambda: (APP_SETTINGS.clear(), APP_SETTINGS.update(before)))
    test.addCleanup(database.configure)  # the database choice goes back to normal
    return tmp.name
