"""
Tests for LAN mode: the access PIN, session cookies, and the request checks that
protect BillFlow when other devices on the network can reach it.
"""

import http.client
import http.server
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock

import billflow.web.access as access_mod
from billflow.database import db_run
from billflow.web.access import (
    COOKIE_NAME, LOCKOUT_SECONDS, MAX_FAILURES, AccessControl, host_allowed, is_loopback,
)
from billflow.web.server import BillFlowAPIHandler, create_server
from support import DatabaseTestCase

PIN = "123456"


class QuietHandler(BillFlowAPIHandler):
    def log_message(self, *args):
        pass


class RemoteHandler(QuietHandler):
    """Every request looks like it came from another device on the network."""
    def is_trusted_local(self):
        return False


class TestAccessControl(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "access.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_pin_is_generated_once_and_remembered(self):
        first = AccessControl(self.path)
        self.assertRegex(first.pin, r"^\d{6}$")
        self.assertEqual(AccessControl(self.path).pin, first.pin)

    @unittest.skipUnless(os.name == "posix", "file modes are POSIX only")
    def test_access_file_is_private(self):
        AccessControl(self.path)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_bad_pins_rejected(self):
        for bad in ("abc", "12", "1234567890123", "12 34", ""):
            with self.assertRaises(ValueError, msg=bad):
                AccessControl(self.path, pin=bad)

    def test_token_checks(self):
        ctl = AccessControl(self.path, pin=PIN)
        token = ctl.make_token()
        self.assertTrue(ctl.valid_token(token))
        self.assertFalse(ctl.valid_token(token[:-1] + ("0" if token[-1] != "0" else "1")))
        self.assertFalse(ctl.valid_token("garbage"))
        self.assertFalse(ctl.valid_token(""))
        past = str(int(time.time()) - 10)
        self.assertFalse(ctl.valid_token(f"{past}.{ctl._sign(past)}"))

    def test_changing_pin_signs_everyone_out(self):
        ctl = AccessControl(self.path, pin=PIN)
        token = ctl.make_token()
        ctl.set_pin("654321")
        self.assertFalse(ctl.valid_token(token))
        self.assertTrue(ctl.valid_token(ctl.make_token()))

    def test_same_pin_keeps_sessions(self):
        ctl = AccessControl(self.path, pin=PIN)
        token = ctl.make_token()
        again = AccessControl(self.path, pin=PIN)
        self.assertTrue(again.valid_token(token))

    def test_lockout_after_repeated_failures(self):
        ctl = AccessControl(self.path, pin=PIN)
        for _ in range(MAX_FAILURES - 1):
            self.assertEqual(ctl.check_pin("10.0.0.5", "000000"), (False, 0))
        accepted, wait = ctl.check_pin("10.0.0.5", "000000")
        self.assertFalse(accepted)
        self.assertGreater(wait, 0)
        # Locked out even with the right PIN, so guessing cannot continue
        self.assertFalse(ctl.check_pin("10.0.0.5", PIN)[0])
        # Other devices are unaffected
        self.assertEqual(ctl.check_pin("10.0.0.6", PIN), (True, 0))
        # The lockout ends
        later = time.time() + LOCKOUT_SECONDS + 5
        with mock.patch("billflow.web.access.time.time", return_value=later):
            self.assertEqual(ctl.check_pin("10.0.0.5", PIN), (True, 0))

    def test_success_clears_failures(self):
        ctl = AccessControl(self.path, pin=PIN)
        for _ in range(MAX_FAILURES - 1):
            ctl.check_pin("10.0.0.5", "000000")
        self.assertTrue(ctl.check_pin("10.0.0.5", PIN)[0])
        self.assertEqual(ctl.check_pin("10.0.0.5", "000000"), (False, 0))


class TestAddressChecks(unittest.TestCase):
    def test_is_loopback(self):
        for addr in ("127.0.0.1", "127.5.5.5", "::1", "::ffff:127.0.0.1"):
            self.assertTrue(is_loopback(addr), addr)
        for addr in ("192.168.1.20", "10.0.0.2", "8.8.8.8", "fe80::1", "not-an-ip", ""):
            self.assertFalse(is_loopback(addr), addr)

    def test_host_header(self):
        me = socket.gethostname().lower()
        for host in ("127.0.0.1:5050", "[::1]:5050", "192.168.1.20", "localhost:5050", f"{me}.local:5050", me):
            self.assertTrue(host_allowed(host), host)
        for host in ("", "evil.example.com", "evil.example.com:5050", "127.0.0.1.evil.com", "billflow.attacker.net"):
            self.assertFalse(host_allowed(host), host)


class ServerTestCase(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.servers = []

    def tearDown(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()
        super().tearDown()

    def start(self, handler=QuietHandler, lan=True):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        if lan:
            server.access = AccessControl(os.path.join(self.tmp.name, "access.json"), pin=PIN)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.servers.append(server)
        self.port = server.server_address[1]
        return server

    def call(self, method, path, body=None, headers=None, cookie=None):
        hdrs = dict(headers or {})
        payload = None
        if body is not None:
            hdrs["Content-Type"] = "application/json"
            payload = json.dumps(body)
        if cookie:
            hdrs["Cookie"] = cookie
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=payload, headers=hdrs)
            resp = conn.getresponse()
            raw = resp.read()
        finally:
            conn.close()
        try:
            data = json.loads(raw)
        except ValueError:
            data = raw.decode("utf-8", "replace")
        return resp.status, data, {k.lower(): v for k, v in resp.getheaders()}

    def sign_in(self):
        status, _, headers = self.call("POST", "/api/login", {"pin": PIN})
        self.assertEqual(status, 200)
        return headers["set-cookie"].split(";")[0]


class TestRequestChecks(ServerTestCase):
    def test_no_cors_headers_and_basic_hardening(self):
        self.start()
        status, _, headers = self.call("GET", "/api/overview")
        self.assertEqual(status, 200)
        self.assertNotIn("access-control-allow-origin", headers)
        self.assertEqual(headers["x-frame-options"], "DENY")
        self.assertEqual(headers["x-content-type-options"], "nosniff")

    def test_preflight_not_allowed(self):
        self.start()
        status, _, headers = self.call("OPTIONS", "/api/products", headers={"Origin": "http://evil.example.com"})
        self.assertEqual(status, 405)
        self.assertNotIn("access-control-allow-origin", headers)

    def test_unknown_host_refused(self):
        self.start()
        status, _, _ = self.call("GET", "/api/overview", headers={"Host": "evil.example.com"})
        self.assertEqual(status, 400)

    def test_cross_origin_requests_refused(self):
        self.start()
        evil = {"Origin": "http://evil.example.com"}
        self.assertEqual(self.call("POST", "/api/expenses", {"amount": 5}, headers=evil)[0], 403)
        self.assertEqual(self.call("GET", "/api/overview", headers=evil)[0], 403)
        own = {"Origin": f"http://127.0.0.1:{self.port}"}
        self.assertEqual(self.call("GET", "/api/overview", headers=own)[0], 200)

    def test_proxied_request_is_not_local(self):
        self.start()
        status, body, _ = self.call("GET", "/api/overview", headers={"X-Forwarded-For": "203.0.113.9"})
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "PIN required")

    def test_large_body_refused(self):
        self.start()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/api/login")
        conn.putheader("Content-Length", "5000000")
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 413)
        conn.close()


class TestRemoteSignIn(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.start(RemoteHandler)

    def test_api_needs_pin(self):
        status, body, _ = self.call("GET", "/api/overview")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "PIN required")
        self.assertEqual(self.call("POST", "/api/checkout", {"items": []})[0], 401)

    def test_changes_need_pin(self):
        db_run("INSERT INTO products (name, price, quantity) VALUES ('Widget', 10, 5)")
        self.assertEqual(self.call("DELETE", "/api/products/1")[0], 401)
        self.assertEqual(self.call("PUT", "/api/products/1", {"price": 1})[0], 401)
        status, products, _ = self.call("GET", "/api/products", cookie=self.sign_in())
        self.assertEqual([p["name"] for p in products["products"]], ["Widget"])
        self.assertEqual(products["products"][0]["price"], 10)

    def test_pages_redirect_to_login(self):
        for path in ("/", "/app.js", "/styles.css", "/index.html"):
            status, _, headers = self.call("GET", path)
            self.assertEqual((status, headers.get("location")), (302, "/login"), path)
        self.assertEqual(self.call("HEAD", "/")[0], 302)

    def test_login_page_is_public(self):
        status, page, _ = self.call("GET", "/login")
        self.assertEqual(status, 200)
        self.assertIn("Access PIN", page)

    def test_wrong_pin_rejected(self):
        status, body, headers = self.call("POST", "/api/login", {"pin": "000000"})
        self.assertEqual(status, 401)
        self.assertNotIn("set-cookie", headers)
        self.assertEqual(self.call("POST", "/api/login", {})[0], 401)
        self.assertEqual(self.call("POST", "/api/login", ["not", "an", "object"])[0], 401)

    def test_correct_pin_opens_everything(self):
        status, _, headers = self.call("POST", "/api/login", {"pin": PIN})
        self.assertEqual(status, 200)
        cookie_header = headers["set-cookie"]
        self.assertTrue(cookie_header.startswith(f"{COOKIE_NAME}="))
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("SameSite=Lax", cookie_header)
        cookie = cookie_header.split(";")[0]
        self.assertEqual(self.call("GET", "/api/overview", cookie=cookie)[0], 200)
        self.assertEqual(self.call("GET", "/", cookie=cookie)[0], 200)
        self.assertEqual(self.call("GET", "/app.js", cookie=cookie)[0], 200)

    def test_forged_cookie_rejected(self):
        self.assertEqual(self.call("GET", "/api/overview", cookie=f"{COOKIE_NAME}=9999999999.deadbeef")[0], 401)
        self.assertEqual(self.call("GET", "/api/overview", cookie=f"{COOKIE_NAME}=")[0], 401)

    def test_lockout_returns_429(self):
        for _ in range(MAX_FAILURES - 1):
            self.assertEqual(self.call("POST", "/api/login", {"pin": "000000"})[0], 401)
        self.assertEqual(self.call("POST", "/api/login", {"pin": "000000"})[0], 429)
        status, body, headers = self.call("POST", "/api/login", {"pin": PIN})
        self.assertEqual(status, 429)
        self.assertNotIn("set-cookie", headers)

    def test_logout_clears_cookie(self):
        status, _, headers = self.call("POST", "/api/logout", cookie=self.sign_in())
        self.assertEqual(status, 200)
        self.assertIn("Max-Age=0", headers["set-cookie"])

    def test_network_info_hides_pin_from_other_devices(self):
        status, info, _ = self.call("GET", "/api/network-info", cookie=self.sign_in())
        self.assertEqual(status, 200)
        self.assertTrue(info["lan_enabled"])
        self.assertFalse(info["local"])
        self.assertIsNone(info["pin"])
        self.assertNotIn(PIN, json.dumps(info))


class TestHostComputer(ServerTestCase):
    def test_host_needs_no_pin_and_sees_pin(self):
        self.start()
        status, info, _ = self.call("GET", "/api/network-info")
        self.assertEqual(status, 200)
        self.assertTrue(info["local"])
        self.assertTrue(info["lan_enabled"])
        self.assertEqual(info["pin"], PIN)
        self.assertEqual(info["urls"], [f"http://127.0.0.1:{self.port}/"])
        self.assertEqual(self.call("GET", "/api/overview")[0], 200)
        self.assertEqual(self.call("GET", "/")[0], 200)

    def test_without_lan_mode_other_devices_are_refused(self):
        self.start(RemoteHandler, lan=False)
        status, body, _ = self.call("GET", "/api/overview")
        self.assertEqual(status, 403)
        self.assertEqual(self.call("POST", "/api/login", {"pin": PIN})[0], 403)

    def test_without_lan_mode_network_info_says_off(self):
        self.start(QuietHandler, lan=False)
        status, info, _ = self.call("GET", "/api/network-info")
        self.assertEqual(status, 200)
        self.assertFalse(info["lan_enabled"])
        self.assertIsNone(info["pin"])


class TestCreateServer(unittest.TestCase):
    def test_lan_mode_only_for_non_loopback_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(access_mod, "ACCESS_FILE", os.path.join(tmp, "access.json")):
                local = create_server("127.0.0.1", 0)
                shared = create_server("0.0.0.0", 0, pin="4321")
                try:
                    self.assertFalse(hasattr(local, "access"))
                    self.assertEqual(shared.access.pin, "4321")
                finally:
                    local.server_close()
                    shared.server_close()


if __name__ == "__main__":
    unittest.main()
