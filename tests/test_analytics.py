"""
Unit tests for analytics calculations and utilities.
"""

import unittest
from billflow.analytics import WEEKDAYS, EXPENSE_CATS, get_best_day_of_week


class TestAnalytics(unittest.TestCase):
    def test_constants_defined(self):
        self.assertEqual(len(WEEKDAYS), 7)
        self.assertIn("Rent", EXPENSE_CATS)
        self.assertIn("Salaries", EXPENSE_CATS)

    def test_get_best_day_empty_db(self):
        best_day = get_best_day_of_week()
        self.assertIsInstance(best_day, str)


if __name__ == "__main__":
    unittest.main()
