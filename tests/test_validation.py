"""
Unit tests for validation and utility functions.
"""

import unittest
from billflow.utils import validate_phone, validate_email, safe_float, clamp_discount, clamp_tax, rnd


class TestValidationUtils(unittest.TestCase):
    def test_phone_validation(self):
        self.assertIsNone(validate_phone("9876543210"))
        self.assertIsNone(validate_phone("+91 9876543210"))
        self.assertIsNotNone(validate_phone("123"))
        self.assertIsNotNone(validate_phone("abcde"))

    def test_email_validation(self):
        self.assertIsNone(validate_email("user@example.com"))
        self.assertIsNone(validate_email("john.doe@company.org"))
        self.assertIsNotNone(validate_email("invalid-email"))
        self.assertIsNotNone(validate_email("@missing.com"))

    def test_clamp_discount(self):
        self.assertEqual(clamp_discount(15.0), 15.0)
        self.assertEqual(clamp_discount(-5.0), 0.0)
        self.assertEqual(clamp_discount(120.0), 100.0)

    def test_safe_float(self):
        self.assertEqual(safe_float("12.34"), 12.34)
        self.assertEqual(safe_float("invalid"), 0.0)

    def test_rnd_rounding(self):
        self.assertEqual(rnd(10.556, 2), 10.56)
        self.assertEqual(rnd(10.551, 2), 10.55)


if __name__ == "__main__":
    unittest.main()
