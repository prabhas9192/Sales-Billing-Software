"""
Tests for first-run setup: what the setup screen offers and what applying it does.
Each test has its own setup files, so the real ones are never read or changed.
"""

import json
import os
import unittest
from unittest import mock

from billflow import clock, database, dbconfig, dbsetup, onboarding
from billflow.config import APP_SETTINGS
from billflow.database import db_one, db_run
from billflow.onboarding import SetupError
from billflow.web import access
from support import isolate_setup


class SetupTestCase(unittest.TestCase):
    def setUp(self):
        self.home = isolate_setup(self)

    def choices(self, **overrides):
        """What the setup screen would send for a plain SQLite shop."""
        payload = {
            "database": {"engine": "sqlite", "path": os.path.join(self.home, "shop.db")},
            "settings": {"shop_name": "Asha Stores", "shop_phone": "98450 12345", "shop_address": "12 Main Road",
                         "shop_gstin": "29ABCDE1234F1Z5", "currency": "INR", "timezone": "Asia/Kolkata"},
            "sample_data": False,
            "share": {"enabled": False, "pin": ""},
        }
        payload.update(overrides)
        return payload

    def nothing_saved(self):
        for name in ("setup.json", "db.json", "settings.json", "access.json"):
            self.assertFalse(os.path.exists(os.path.join(self.home, name)), name)


class TestFirstRun(SetupTestCase):
    def test_a_first_run_until_something_is_chosen(self):
        self.assertFalse(onboarding.is_complete())
        onboarding.apply(self.choices())
        self.assertTrue(onboarding.is_complete())

    def test_a_chosen_database_counts_as_set_up(self):
        dbconfig.save("sqlite:///" + os.path.join(self.home, "x.db"))
        self.assertTrue(onboarding.is_complete())

    def test_the_environment_variable_counts_as_set_up(self):
        os.environ["BILLFLOW_DB"] = "sqlite:///" + os.path.join(self.home, "x.db")
        self.assertTrue(onboarding.is_complete())

    def test_phone_sharing_is_off_until_asked_for(self):
        self.assertFalse(onboarding.share_on_network())


class TestScreenContents(SetupTestCase):
    def test_everything_the_screen_needs(self):
        info = onboarding.state()
        self.assertFalse(info["complete"])
        self.assertIsNone(info["database"])
        self.assertEqual([e["key"] for e in info["engines"]], ["sqlite", "postgresql", "mysql", "mariadb"])
        sqlite = info["engines"][0]
        self.assertTrue(sqlite["ready"] and not sqlite["server"])
        self.assertTrue(all(e["server"] for e in info["engines"][1:]))
        self.assertIn("INR", [c["code"] for c in info["currencies"]])
        self.assertIn("Asia/Kolkata", info["timezones"])
        self.assertEqual(info["system_timezone"], clock.system_timezone())

    def test_after_setup_it_shows_the_choices_but_never_a_password(self):
        onboarding.apply(self.choices())
        info = onboarding.state()
        self.assertTrue(info["complete"])
        self.assertEqual(info["database"]["engine"], "sqlite")
        self.assertEqual(info["settings"]["shop_name"], "Asha Stores")
        self.assertEqual(info["settings"]["timezone"], "Asia/Kolkata")
        self.assertNotIn("password", json.dumps(info).lower().replace("default_user", ""))


class TestApplying(SetupTestCase):
    def test_saves_the_database_the_shop_and_the_time_zone(self):
        result = onboarding.apply(self.choices())
        self.assertTrue(result["success"])
        self.assertIn("shop.db", result["database"])
        # the database exists and has its tables
        self.assertEqual(db_one("SELECT COUNT(*) AS n FROM products")["n"], 0)
        # and the choice is remembered for the next start
        self.assertEqual(dbconfig.resolve().path, os.path.join(self.home, "shop.db"))
        with open(os.path.join(self.home, "settings.json")) as f:
            saved = json.load(f)
        self.assertEqual((saved["shop_name"], saved["currency"], saved["timezone"]), ("Asha Stores", "INR", "Asia/Kolkata"))
        # and the time zone is in force straight away
        self.assertEqual(APP_SETTINGS["timezone"], "Asia/Kolkata")

    def test_can_fill_an_empty_database_with_sample_data(self):
        onboarding.apply(self.choices(sample_data=True))
        self.assertEqual(db_one("SELECT COUNT(*) AS n FROM products")["n"], 29)

    def test_sample_data_is_never_added_to_a_database_with_data(self):
        onboarding.apply(self.choices())
        db_run("INSERT INTO products (name, price, quantity) VALUES ('Mine', 1, 1)")
        result = onboarding.apply(self.choices(sample_data=True))
        self.assertEqual(db_one("SELECT COUNT(*) AS n FROM products")["n"], 1)
        self.assertIn("already has data", " ".join(result["messages"]))

    def test_running_setup_again_keeps_existing_data(self):
        onboarding.apply(self.choices())
        db_run("INSERT INTO products (name, price, quantity) VALUES ('Mine', 1, 1)")
        onboarding.apply(self.choices())
        self.assertEqual(db_one("SELECT name FROM products")["name"], "Mine")

    def test_choices_that_cannot_be_used_save_nothing(self):
        good = self.choices()
        bad = [
            ("no shop name", {**good, "settings": {**good["settings"], "shop_name": "  "}}),
            ("unknown currency", {**good, "settings": {**good["settings"], "currency": "XXX"}}),
            ("unknown time zone", {**good, "settings": {**good["settings"], "timezone": "Mars/Olympus"}}),
            ("very long name", {**good, "settings": {**good["settings"], "shop_name": "x" * 500}}),
            ("no database type", {**good, "database": {}}),
            ("unknown database type", {**good, "database": {"engine": "oracle"}}),
            ("bad PIN", {**good, "share": {"enabled": True, "pin": "12ab"}}),
            ("short PIN", {**good, "share": {"enabled": True, "pin": "12"}}),
            ("port that is not a number", {**good, "database": {"engine": "mysql", "port": "abc", "name": "x"}}),
            ("server database without a name", {**good, "database": {"engine": "postgresql", "name": ""}}),
        ]
        for label, payload in bad:
            with self.assertRaises(ValueError, msg=label):
                onboarding.apply(payload)
        self.nothing_saved()

    def test_the_time_zone_may_be_left_to_the_computer(self):
        payload = self.choices()
        payload["settings"]["timezone"] = ""
        onboarding.apply(payload)
        self.assertEqual(APP_SETTINGS["timezone"], "")

    def test_a_database_that_fails_to_prepare_changes_nothing(self):
        with mock.patch.object(onboarding.database, "init_db", side_effect=RuntimeError("disk full")):
            with self.assertRaisesRegex(SetupError, "disk full"):
                onboarding.apply(self.choices())
        self.nothing_saved()

    def test_a_server_that_cannot_be_reached_saves_nothing(self):
        payload = self.choices(database={"engine": "mariadb", "host": "db.local", "name": "shop"})
        with mock.patch.object(dbconfig, "driver_ready", return_value=True), \
                mock.patch.object(dbsetup, "test_connection", return_value=(False, "Connection refused")):
            with self.assertRaisesRegex(SetupError, "Connection refused"):
                onboarding.apply(payload)
        self.nothing_saved()

    def test_a_missing_driver_says_what_to_install(self):
        payload = self.choices(database={"engine": "postgresql", "name": "shop"})
        with mock.patch.object(dbconfig, "driver_ready", return_value=False):
            with self.assertRaisesRegex(SetupError, r"pip install psycopg\[binary\]"):
                onboarding.apply(payload)
        self.nothing_saved()

    def test_a_missing_database_is_created_only_when_asked(self):
        payload = self.choices(database={"engine": "mariadb", "host": "db.local", "name": "shop", "user": "bob", "password": "pw"})
        missing = (False, "Unknown database 'shop'")
        with mock.patch.object(dbconfig, "driver_ready", return_value=True), \
                mock.patch.object(onboarding.database, "configure"), mock.patch.object(onboarding.database, "init_db"):
            with mock.patch.object(dbsetup, "test_connection", return_value=missing), \
                    mock.patch.object(dbsetup, "create_database") as create:
                with self.assertRaises(SetupError):
                    onboarding.apply(payload)
                create.assert_not_called()
            with mock.patch.object(dbsetup, "test_connection", side_effect=[missing, (True, "Connected.")]), \
                    mock.patch.object(dbsetup, "create_database") as create:
                result = onboarding.apply({**payload, "create_database": True})
                create.assert_called_once()
                self.assertEqual(create.call_args[0][0].name, "shop")
        self.assertTrue(result["success"])
        self.assertEqual(dbconfig.load_saved(), "mariadb://bob:pw@db.local:3306/shop")
        self.assertNotIn("pw", result["database"])


class TestPhoneSharing(SetupTestCase):
    def test_a_chosen_pin_is_kept_and_sharing_is_remembered(self):
        result = onboarding.apply(self.choices(share={"enabled": True, "pin": "482913"}))
        self.assertEqual(result["pin"], "482913")
        self.assertTrue(onboarding.share_on_network())
        self.assertEqual(access.AccessControl().pin, "482913")

    def test_without_a_pin_a_random_one_is_made(self):
        result = onboarding.apply(self.choices(share={"enabled": True, "pin": ""}))
        self.assertRegex(result["pin"], r"^\d{6}$")

    def test_sharing_off(self):
        result = onboarding.apply(self.choices())
        self.assertIsNone(result["pin"])
        self.assertFalse(result["share"])
        self.assertFalse(onboarding.share_on_network())

    def test_a_restart_is_needed_only_when_the_wish_differs_from_how_it_is_running(self):
        wants = self.choices(share={"enabled": True, "pin": ""})
        self.assertTrue(onboarding.apply(wants, sharing_active=False)["restart_needed"])
        self.assertFalse(onboarding.apply(wants, sharing_active=True)["restart_needed"])
        self.assertTrue(onboarding.apply(self.choices(), sharing_active=True)["restart_needed"])
        self.assertFalse(onboarding.apply(self.choices(), sharing_active=False)["restart_needed"])


class TestCleanSettings(unittest.TestCase):
    def test_tidies_up_what_it_keeps(self):
        cleaned = onboarding.clean_settings({"shop_name": "  Asha  ", "currency": "usd", "timezone": " Asia/Kolkata ", "shop_phone": None})
        self.assertEqual(cleaned, {"shop_name": "Asha", "currency": "USD", "timezone": "Asia/Kolkata", "shop_phone": ""})

    def test_ignores_anything_it_does_not_know(self):
        self.assertEqual(onboarding.clean_settings({"theme": "x", "__proto__": 1, "access_pin": "1234"}), {})

    def test_a_name_may_not_be_blanked(self):
        with self.assertRaises(SetupError):
            onboarding.clean_settings({"shop_name": " "})
        self.assertEqual(onboarding.clean_settings({"currency": "INR"}), {"currency": "INR"})


class TestDatabaseTest(SetupTestCase):
    def test_sqlite_file_that_does_not_exist_yet(self):
        result = onboarding.test_database({"engine": "sqlite", "path": os.path.join(self.home, "new.db")})
        self.assertTrue(result["ok"])
        self.assertIn("a new file", result["message"])
        self.assertFalse(os.path.exists(os.path.join(self.home, "new.db")))   # testing creates nothing

    def test_sqlite_file_that_exists(self):
        path = os.path.join(self.home, "old.db")
        open(path, "w").close()
        self.assertIn("the existing file", onboarding.test_database({"engine": "sqlite", "path": path})["message"])

    def test_a_folder_is_not_a_database_file(self):
        result = onboarding.test_database({"engine": "sqlite", "path": self.home})
        self.assertFalse(result["ok"])
        self.assertIn("folder", result["message"])

    def test_a_server_that_answers(self):
        with mock.patch.object(dbsetup, "test_connection", return_value=(True, "Connected.")) as tested:
            result = onboarding.test_database({"engine": "postgresql", "host": "h", "name": "shop", "password": "pw"})
        self.assertEqual(result, {"ok": True, "message": "Connected.", "missing": False})
        self.assertEqual(tested.call_args[0][0].password, "pw")

    def test_a_server_without_the_database_says_so(self):
        with mock.patch.object(dbsetup, "test_connection", return_value=(False, 'FATAL: database "shop" does not exist')):
            result = onboarding.test_database({"engine": "postgresql", "name": "shop"})
        self.assertFalse(result["ok"])
        self.assertTrue(result["missing"])


if __name__ == "__main__":
    unittest.main()
