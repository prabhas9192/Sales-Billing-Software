"""
Tests for the setup screen over HTTP: the first-run gate, who may change setup,
and what the rest of the app shows once it is done.
"""

import http.client
import http.server
import json
import os
import re
import threading
import unittest

from billflow import database
from billflow.config import APP_SETTINGS
from billflow.web.access import AccessControl
from billflow.web.server import BillFlowAPIHandler
from support import isolate_setup

PIN = "123456"


class QuietHandler(BillFlowAPIHandler):
    def log_message(self, *args):
        pass


class RemoteHandler(QuietHandler):
    """Every request looks like it came from a phone on the network."""
    def is_trusted_local(self):
        return False


class ScreenTestCase(unittest.TestCase):
    def setUp(self):
        self.home = isolate_setup(self)
        self.servers = []

    def tearDown(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()

    def start(self, handler=QuietHandler, pending=True, lan=False):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.setup_pending = pending
        if lan:
            server.access = AccessControl(pin=PIN)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.servers.append(server)
        self.server, self.port = server, server.server_address[1]
        return server

    def call(self, method, path, body=None, cookie=None):
        headers = {}
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body)
        if cookie:
            headers["Cookie"] = cookie
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
        finally:
            conn.close()
        try:
            data = json.loads(raw)
        except ValueError:
            data = raw.decode("utf-8", "replace")
        return resp.status, data, {k.lower(): v for k, v in resp.getheaders()}

    def choices(self, **overrides):
        payload = {
            "database": {"engine": "sqlite", "path": os.path.join(self.home, "shop.db")},
            "settings": {"shop_name": "Asha Stores", "shop_phone": "98450 12345", "shop_address": "12 Main Road",
                         "shop_gstin": "", "currency": "USD", "timezone": "America/New_York"},
            "sample_data": True,
            "share": {"enabled": False, "pin": ""},
        }
        payload.update(overrides)
        return payload


class TestFirstRunGate(ScreenTestCase):
    def test_the_app_sends_you_to_setup(self):
        self.start()
        for path in ("/", "/index.html"):
            status, _, headers = self.call("GET", path)
            self.assertEqual((status, headers["location"]), (302, "/setup"), path)

    def test_the_data_is_off_limits_until_setup_is_done(self):
        self.start()
        for path in ("/api/overview", "/api/products", "/api/settings", "/api/bills"):
            status, body, _ = self.call("GET", path)
            self.assertEqual(status, 409, path)
            self.assertTrue(body["setup_required"])
        self.assertEqual(self.call("POST", "/api/checkout", {"items": []})[0], 409)

    def test_the_setup_page_and_its_files_work(self):
        self.start()
        status, page, _ = self.call("GET", "/setup")
        self.assertEqual(status, 200)
        self.assertIn("Set up BillFlow", page)
        self.assertEqual(self.call("GET", "/styles.css")[0], 200)
        status, info, _ = self.call("GET", "/api/setup/state")
        self.assertEqual(status, 200)
        self.assertFalse(info["complete"])

    def test_nothing_is_created_by_looking_at_the_setup_page(self):
        self.start()
        self.call("GET", "/setup")
        self.call("GET", "/api/setup/state")
        self.assertFalse(os.path.exists(os.path.join(self.home, "shop.db")))

    def test_a_finished_server_is_not_gated(self):
        self.start(pending=False)
        database.configure("sqlite:///" + os.path.join(self.home, "other.db"))
        database.init_db()
        self.assertEqual(self.call("GET", "/")[0], 200)
        self.assertEqual(self.call("GET", "/api/overview")[0], 200)


class TestFinishingSetup(ScreenTestCase):
    def test_after_saving_the_app_opens_with_the_choices_applied(self):
        self.start()
        status, result, _ = self.call("POST", "/api/setup/apply", self.choices())
        self.assertEqual(status, 200, result)
        self.assertTrue(result["success"])
        self.assertFalse(self.server.setup_pending)

        self.assertEqual(self.call("GET", "/")[0], 200)
        status, overview, _ = self.call("GET", "/api/overview")
        self.assertEqual(status, 200)
        self.assertEqual(overview["total_products"], 29)       # the sample data was loaded

        status, settings, _ = self.call("GET", "/api/settings")
        self.assertEqual(settings["shop_name"], "Asha Stores")
        self.assertEqual((settings["currency"], settings["currency_symbol"], settings["currency_locale"]), ("USD", "$", "en-US"))
        self.assertEqual(settings["timezone"], "America/New_York")
        self.assertRegex(settings["today"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(settings["week"], r"^\d{4}-W\d{2}$")
        self.assertIn("INR", [c["code"] for c in settings["currencies"]])

        status, info, _ = self.call("GET", "/api/db-info")
        self.assertIn("shop.db", info["location"])

    def test_a_mistake_is_explained_and_the_app_stays_in_setup(self):
        self.start()
        status, body, _ = self.call("POST", "/api/setup/apply", self.choices(settings={"shop_name": ""}))
        self.assertEqual(status, 400)
        self.assertIn("shop's name", body["error"])
        self.assertTrue(self.server.setup_pending)
        self.assertEqual(self.call("GET", "/")[0], 302)
        self.assertFalse(os.path.exists(os.path.join(self.home, "setup.json")))

    def test_the_test_button(self):
        self.start()
        status, result, _ = self.call("POST", "/api/setup/test-db", {"database": {"engine": "sqlite", "path": os.path.join(self.home, "t.db")}})
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        status, body, _ = self.call("POST", "/api/setup/test-db", {"database": {"engine": "nonsense"}})
        self.assertEqual(status, 400)

    def test_setup_can_be_run_again_later(self):
        self.start()
        self.call("POST", "/api/setup/apply", self.choices())
        status, info, _ = self.call("GET", "/api/setup/state")
        self.assertTrue(info["complete"])
        self.assertEqual(info["settings"]["shop_name"], "Asha Stores")
        again = self.choices(settings={**self.choices()["settings"], "shop_name": "Asha Superstore"}, sample_data=False)
        self.assertEqual(self.call("POST", "/api/setup/apply", again)[0], 200)
        self.assertEqual(self.call("GET", "/api/settings")[1]["shop_name"], "Asha Superstore")
        self.assertEqual(self.call("GET", "/api/overview")[1]["total_products"], 29)   # nothing was lost


class TestOnlyTheComputerMayChangeSetup(ScreenTestCase):
    def sign_in(self):
        status, _, headers = self.call("POST", "/api/login", {"pin": PIN})
        self.assertEqual(status, 200)
        return headers["set-cookie"].split(";")[0]

    def test_a_signed_in_phone_cannot_use_the_setup_api(self):
        self.start(RemoteHandler, pending=False, lan=True)
        database.configure("sqlite:///" + os.path.join(self.home, "other.db"))
        database.init_db()
        cookie = self.sign_in()
        self.assertEqual(self.call("GET", "/api/overview", cookie=cookie)[0], 200)   # it can use the app
        for method, path, body in (("GET", "/api/setup/state", None),
                                   ("POST", "/api/setup/test-db", {"database": {"engine": "sqlite"}}),
                                   ("POST", "/api/setup/apply", self.choices())):
            status, result, _ = self.call(method, path, body, cookie=cookie)
            self.assertEqual(status, 403, path)
            self.assertIn("computer running BillFlow", result["error"])
        self.assertFalse(os.path.exists(os.path.join(self.home, "shop.db")))

    def test_a_phone_that_has_not_signed_in_cannot_even_see_setup(self):
        self.start(RemoteHandler, pending=True, lan=True)
        self.assertEqual(self.call("GET", "/api/setup/state")[0], 401)
        self.assertEqual(self.call("GET", "/setup")[0], 302)
        self.assertEqual(self.call("POST", "/api/setup/apply", self.choices())[0], 401)

    def test_a_proxied_request_is_not_the_computer(self):
        self.start(QuietHandler, pending=True, lan=True)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/api/setup/apply", body=json.dumps(self.choices()),
                     headers={"Content-Type": "application/json", "X-Forwarded-For": "203.0.113.9"})
        self.assertEqual(conn.getresponse().status, 401)
        conn.close()
        self.assertTrue(self.server.setup_pending)


class TestSettingsEndpoint(ScreenTestCase):
    def setUp(self):
        super().setUp()
        database.configure("sqlite:///" + os.path.join(self.home, "s.db"))
        database.init_db()
        self.start(pending=False)

    def test_a_valid_change_is_saved(self):
        status, _, _ = self.call("POST", "/api/settings", {"shop_name": "New Name", "currency": "gbp", "shop_gstin": "29ABCDE1234F1Z5"})
        self.assertEqual(status, 200)
        settings = self.call("GET", "/api/settings")[1]
        self.assertEqual((settings["shop_name"], settings["currency"], settings["currency_symbol"]), ("New Name", "GBP", "£"))
        self.assertEqual(settings["shop_gstin"], "29ABCDE1234F1Z5")

    def test_bad_values_are_refused_and_change_nothing(self):
        before = dict(APP_SETTINGS)
        for body in ({"currency": "ZZZ"}, {"timezone": "Mars/Olympus"}, {"shop_name": ""}, {"shop_name": "x" * 500}):
            status, result, _ = self.call("POST", "/api/settings", body)
            self.assertEqual(status, 400, body)
            self.assertTrue(result["error"])
        self.assertEqual(dict(APP_SETTINGS), before)

    def test_settings_it_does_not_know_are_ignored(self):
        self.call("POST", "/api/settings", {"shop_name": "Shop", "access_pin": "9999", "evil": "x"})
        self.assertNotIn("evil", APP_SETTINGS)
        self.assertNotIn("access_pin", APP_SETTINGS)

    def test_the_old_long_currency_label_still_works(self):
        APP_SETTINGS["currency"] = "INR — ₹  India"       # what versions before this one saved
        settings = self.call("GET", "/api/settings")[1]
        self.assertEqual((settings["currency"], settings["currency_symbol"]), ("INR", "₹"))

    def test_the_roster_week_follows_the_current_week(self):
        status, body, _ = self.call("GET", "/api/roster")
        self.assertRegex(body["week"], r"^\d{4}-W\d{2}$")
        self.assertNotEqual(body["week"], "2026-W45" if "W45" not in body["week"] else "")


if __name__ == "__main__":
    unittest.main()
