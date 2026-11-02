"""
Tests for choosing a database: the guided setup and the launcher's database options.
Connections to real servers are replaced with stand-ins, so these run anywhere.
"""

import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from billflow import dbconfig, dbsetup, launcher, onboarding
from support import isolate_setup


class Script:
    """Stands in for the person at the keyboard."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.said = []

    def ask(self, prompt=""):
        self.said.append(prompt)
        return self.answers.pop(0)

    def say(self, text=""):
        self.said.append(text)

    @property
    def output(self):
        return "\n".join(self.said)


class WizardTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saved = os.path.join(self.tmp.name, "billflow_db.json")
        patcher = mock.patch.object(dbconfig, "SAVED_FILE", self.saved)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_wizard(self, script):
        return dbsetup.run_wizard(ask=script.ask, ask_secret=script.ask, say=script.say)


class TestWizard(WizardTestCase):
    def test_sqlite_file(self):
        path = os.path.join(self.tmp.name, "shop.db")
        script = Script("1", path)
        target = self.run_wizard(script)
        self.assertEqual(target.path, path)
        self.assertEqual(dbconfig.load_saved(), f"sqlite:///{path}")
        self.assertTrue(os.path.exists(path))
        self.assertIn("Saved", script.output)

    def test_not_a_choice(self):
        for answer in ("9", "0", "abc"):
            self.assertIsNone(self.run_wizard(Script(answer)))
        self.assertFalse(os.path.exists(self.saved))

    def test_missing_driver_says_what_to_install(self):
        script = Script("2")
        with mock.patch.object(dbconfig, "driver_ready", return_value=False):
            self.assertIsNone(self.run_wizard(script))
        self.assertIn("pip install psycopg[binary]", script.output)
        self.assertFalse(os.path.exists(self.saved))

    def test_server_database_is_tested_then_saved(self):
        script = Script("3", "db.local", "3307", "shop", "bob", "pw")
        with mock.patch.object(dbconfig, "driver_ready", return_value=True), \
                mock.patch.object(dbsetup, "test_connection", return_value=(True, "Connected.")) as tested:
            target = self.run_wizard(script)
        self.assertEqual((target.engine.key, target.host, target.port, target.user, target.password, target.name),
                         ("mysql", "db.local", 3307, "bob", "pw", "shop"))
        self.assertEqual(tested.call_count, 1)
        self.assertEqual(dbconfig.load_saved(), "mysql://bob:pw@db.local:3307/shop")

    def test_defaults_for_a_local_server(self):
        script = Script("2", "", "", "", "", "pw")
        with mock.patch.object(dbconfig, "driver_ready", return_value=True), \
                mock.patch.object(dbsetup, "test_connection", return_value=(True, "Connected.")):
            target = self.run_wizard(script)
        self.assertEqual((target.host, target.port, target.name, target.user), ("localhost", 5432, "billflow", "postgres"))

    def test_missing_database_can_be_created(self):
        script = Script("2", "", "", "shop", "", "pw", "y")
        results = [(False, 'FATAL: database "shop" does not exist'), (True, "Connected.")]
        with mock.patch.object(dbconfig, "driver_ready", return_value=True), \
                mock.patch.object(dbsetup, "test_connection", side_effect=results), \
                mock.patch.object(dbsetup, "create_database") as create:
            target = self.run_wizard(script)
        create.assert_called_once()
        self.assertEqual(create.call_args[0][0].name, "shop")
        self.assertIsNotNone(target)
        self.assertIsNotNone(dbconfig.load_saved())

    def test_declining_to_create_the_database_saves_nothing(self):
        script = Script("2", "", "", "shop", "", "pw", "n")
        with mock.patch.object(dbconfig, "driver_ready", return_value=True), \
                mock.patch.object(dbsetup, "test_connection", return_value=(False, "Unknown database 'shop'")), \
                mock.patch.object(dbsetup, "create_database") as create:
            self.assertIsNone(self.run_wizard(script))
        create.assert_not_called()
        self.assertFalse(os.path.exists(self.saved))

    def test_failed_connection_saves_nothing(self):
        script = Script("4", "", "", "", "", "wrong")
        with mock.patch.object(dbconfig, "driver_ready", return_value=True), \
                mock.patch.object(dbsetup, "test_connection", return_value=(False, "Access denied")):
            self.assertIsNone(self.run_wizard(script))
        self.assertIn("Access denied", script.output)
        self.assertIn("Nothing was saved", script.output)
        self.assertFalse(os.path.exists(self.saved))

    def test_bad_port(self):
        script = Script("2", "", "abc", "", "", "pw")
        with mock.patch.object(dbconfig, "driver_ready", return_value=True):
            self.assertIsNone(self.run_wizard(script))
        self.assertFalse(os.path.exists(self.saved))


class TestDatabaseList(unittest.TestCase):
    def test_lists_every_type_and_what_is_missing(self):
        with mock.patch.object(dbconfig, "driver_ready", side_effect=lambda e: e.key == "sqlite"):
            text = dbsetup.describe_engines()
        for name in ("SQLite", "PostgreSQL", "MySQL", "MariaDB"):
            self.assertIn(name, text)
        self.assertIn("[ready]", text)
        self.assertIn("pip install psycopg[binary]", text)
        self.assertIn("pip install PyMySQL", text)

    def test_database_names_are_checked_before_creating_one(self):
        target = dbconfig.parse_url("mysql://u@localhost/shop")
        bad = dbconfig.DatabaseTarget(target.engine, host="h", port=1, user="u", password="", name="x`; DROP DATABASE y;--")
        with self.assertRaises(dbconfig.DatabaseConfigError):
            dbsetup.create_database(bad)


class TestLauncherDatabaseOptions(unittest.TestCase):
    def setUp(self):
        isolate_setup(self)

    def test_list_databases(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(launcher.main(["--list-databases"]), 0)
        self.assertIn("PostgreSQL", out.getvalue())
        self.assertIn("In use now", out.getvalue())

    def test_unknown_database_type_is_explained(self):
        message = launcher.main(["--db", "oracle://u@h/d"])
        self.assertIn("Unknown database type", message)
        self.assertIn("--setup-db", message)

    def test_unreachable_database_is_explained(self):
        with mock.patch.object(launcher.database, "init_db", side_effect=OSError("connection refused")):
            message = launcher.main(["--db", "sqlite:////tmp/never-created.db"])
        self.assertIn("Cannot open the database", message)
        self.assertIn("connection refused", message)

    def test_missing_driver_is_explained(self):
        with mock.patch.object(dbconfig, "driver_ready", return_value=False):
            message = launcher.main(["--db", "mysql://root@127.0.0.1/shop"])
        self.assertIn("pip install PyMySQL", message)
        self.assertIn("--setup-db", message)

    def test_pin_needs_sharing(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            launcher.main(["--pin", "1234"])


class TestFirstRunAndSharing(unittest.TestCase):
    def setUp(self):
        self.home = isolate_setup(self)

    def args(self, *flags):
        return launcher.build_parser().parse_args(list(flags))

    def test_a_plain_start_with_nothing_chosen_is_a_first_run(self):
        self.assertTrue(launcher.needs_setup(self.args()))
        self.assertTrue(launcher.needs_setup(self.args("--lan", "--port", "6000")))

    def test_anything_that_picks_a_database_skips_the_setup_screen(self):
        for flags in (("--db", "sqlite:////tmp/x.db"), ("--sample-data",), ("--setup-db",)):
            self.assertFalse(launcher.needs_setup(self.args(*flags)), flags)

    def test_a_saved_choice_skips_the_setup_screen(self):
        dbconfig.save("sqlite:////tmp/x.db")
        self.assertFalse(launcher.needs_setup(self.args()))

    def test_having_finished_setup_skips_the_setup_screen(self):
        with open(onboarding.SETUP_FILE, "w") as f:
            f.write('{"completed": true}')
        self.assertFalse(launcher.needs_setup(self.args()))

    def test_the_environment_variable_skips_the_setup_screen(self):
        os.environ["BILLFLOW_DB"] = "sqlite:////tmp/x.db"
        self.assertFalse(launcher.needs_setup(self.args()))

    def test_listens_on_this_computer_only_by_default(self):
        self.assertEqual(launcher.listen_host(self.args()), "127.0.0.1")

    def test_lan_flag_opens_it_to_the_network(self):
        self.assertEqual(launcher.listen_host(self.args("--lan")), "0.0.0.0")

    def test_phone_sharing_chosen_in_setup_is_remembered(self):
        with open(onboarding.SETUP_FILE, "w") as f:
            f.write('{"completed": true, "share_on_network": true}')
        self.assertEqual(launcher.listen_host(self.args()), "0.0.0.0")
        self.assertEqual(launcher.listen_host(self.args("--host", "192.168.1.5")), "192.168.1.5")   # an explicit choice wins

    def test_a_pin_is_allowed_when_setup_turned_sharing_on(self):
        with open(onboarding.SETUP_FILE, "w") as f:
            f.write('{"completed": true, "share_on_network": true}')
        args = self.args("--pin", "1234")
        self.assertEqual(launcher.listen_host(args), "0.0.0.0")


if __name__ == "__main__":
    unittest.main()
