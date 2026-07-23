"""``parse_int_param`` — the guarded coercion behind the unguarded-``int()`` 500 fix.

A bare ``int(request.GET.get("days"))`` on client input raises ``ValueError`` on
``?days=abc``; the DRF RFC-7807 handler only translates ``ValidationError``, so it
escaped as a 500 (and plain ``django.views.View`` endpoints have no handler at
all). ``parse_int_param`` degrades a malformed value to the default and clamps to
the given bounds instead. Each non-numeric case below raised against the old
inline ``int(...)`` call.
"""

from __future__ import annotations

import unittest

from apps.api.api_contract import parse_int_param


class ParseIntParamTests(unittest.TestCase):
    def test_valid_numeric_string(self):
        self.assertEqual(parse_int_param("42", 7), 42)

    def test_non_numeric_falls_back_to_default(self):
        self.assertEqual(parse_int_param("abc", 7), 7)

    def test_none_falls_back_to_default(self):
        # request.GET.get("days") returns None when the key is absent.
        self.assertEqual(parse_int_param(None, 30), 30)

    def test_empty_string_falls_back_to_default(self):
        self.assertEqual(parse_int_param("", 20), 20)

    def test_non_scalar_type_falls_back(self):
        # A JSON body could deliver a dict/list where an int is expected.
        self.assertEqual(parse_int_param({"x": 1}, 5), 5)
        self.assertEqual(parse_int_param(["x"], 5), 5)

    def test_maximum_clamps(self):
        self.assertEqual(parse_int_param("999999", 20, maximum=100), 100)

    def test_minimum_clamps(self):
        self.assertEqual(parse_int_param("-5", 20, minimum=1), 1)

    def test_bounds_do_not_touch_in_range_value(self):
        self.assertEqual(parse_int_param("50", 20, minimum=1, maximum=100), 50)

    def test_default_itself_is_returned_unclamped_semantics(self):
        # A bad value with bounds still yields the (in-range) default, clamped.
        self.assertEqual(parse_int_param("abc", 50, minimum=1, maximum=100), 50)


if __name__ == "__main__":
    unittest.main()
