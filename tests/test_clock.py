"""
Tests for the shop's clock: bills and "today" follow the time zone chosen in setup.
"""

import datetime
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from billflow import clock
from billflow.config import APP_SETTINGS


class TestClock(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(APP_SETTINGS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def close(self, a, b, seconds=5):
        return abs((a - b).total_seconds()) < seconds

    def test_follows_the_shops_zone(self):
        APP_SETTINGS["timezone"] = "Asia/Kolkata"
        expected = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
        self.assertTrue(self.close(clock.now(), expected))

    def test_zones_a_day_apart_give_different_dates(self):
        APP_SETTINGS["timezone"] = "Pacific/Kiritimati"   # UTC+14
        east = clock.now()
        APP_SETTINGS["timezone"] = "Pacific/Pago_Pago"    # UTC-11
        west = clock.now()
        self.assertTrue(self.close(east - west, datetime.timedelta(hours=25)))

    def test_today_comes_from_the_same_clock(self):
        APP_SETTINGS["timezone"] = "Pacific/Kiritimati"
        self.assertEqual(clock.today(), clock.now().date())
        self.assertIsInstance(clock.today(), datetime.date)

    def test_empty_or_unknown_zone_uses_the_computers_own(self):
        for name in ("", "Mars/Olympus", "not a zone"):
            APP_SETTINGS["timezone"] = name
            self.assertTrue(self.close(clock.now(), datetime.datetime.now()), name)

    def test_now_has_no_zone_attached(self):
        APP_SETTINGS["timezone"] = "Asia/Kolkata"
        self.assertIsNone(clock.now().tzinfo)

    def test_valid_zone(self):
        for name in ("", "Asia/Kolkata", "America/New_York", "UTC"):
            self.assertTrue(clock.valid_zone(name), name)
        for name in ("Mars/Olympus", "asia", "Asia/", " "):
            self.assertFalse(clock.valid_zone(name), name)

    def test_zone_list(self):
        names = clock.timezone_names()
        for name in ("Asia/Kolkata", "America/New_York", "Europe/London", "UTC"):
            self.assertIn(name, names)
        self.assertFalse([n for n in names if n.startswith("Etc/")])
        self.assertEqual(names[:-1], sorted(names[:-1]))

    def test_system_zone_is_empty_or_listed(self):
        found = clock.system_timezone()
        self.assertTrue(found == "" or found in clock.timezone_names())


if __name__ == "__main__":
    unittest.main()
