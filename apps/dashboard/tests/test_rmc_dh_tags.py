"""Unit tests for the rmc_dh dashboard-home template helpers (pure, no DB)."""
from decimal import Decimal

from django.template import Context, Template
from django.test import SimpleTestCase

from apps.dashboard.templatetags.rmc_dh import dh_donut_gradient, dh_fill, dh_ratio


class DhRatioTests(SimpleTestCase):
    def test_basic_ratio(self):
        self.assertEqual(dh_ratio(50, 100), 50)
        self.assertEqual(dh_ratio(1, 4), 25)

    def test_clamps_high(self):
        self.assertEqual(dh_ratio(150, 100), 100)

    def test_clamps_negative(self):
        self.assertEqual(dh_ratio(-5, 100), 0)

    def test_zero_or_negative_max_is_flat(self):
        self.assertEqual(dh_ratio(5, 0), 0)
        self.assertEqual(dh_ratio(5, -10), 0)

    def test_decimal_and_string_inputs(self):
        self.assertEqual(dh_ratio(Decimal("9.2"), Decimal("11.2")), 82)
        self.assertEqual(dh_ratio("3", "6"), 50)

    def test_garbage_is_flat_not_crash(self):
        self.assertEqual(dh_ratio(None, 100), 0)
        self.assertEqual(dh_ratio("abc", "xyz"), 0)


class DhFillTests(SimpleTestCase):
    def test_known_keys_map_to_tokens(self):
        self.assertEqual(dh_fill("paid"), "var(--rmc-dh-accent)")
        self.assertEqual(dh_fill("overdue"), "var(--rmc-dh-danger)")
        self.assertEqual(dh_fill("PARTIAL"), "var(--rmc-dh-warn)")

    def test_unknown_key_defaults_to_brand(self):
        self.assertEqual(dh_fill("mystery"), "var(--rmc-dh-brand)")
        self.assertEqual(dh_fill(None), "var(--rmc-dh-brand)")


class DhDonutGradientTests(SimpleTestCase):
    def test_accumulates_stops_and_closes_circle(self):
        out = dh_donut_gradient([
            {"fill": "paid", "pct": 68},
            {"fill": "partial", "pct": 18},
            {"fill": "overdue", "pct": 14},
        ])
        self.assertTrue(out.startswith("conic-gradient("))
        self.assertIn("var(--rmc-dh-accent) 0% 68%", out)
        self.assertIn("var(--rmc-dh-warn) 68% 86%", out)
        self.assertIn("var(--rmc-dh-danger) 86% 100%", out)
        # No raw colour literal must ever appear.
        self.assertNotIn("#", out)
        self.assertNotIn("rgb", out)

    def test_partial_dataset_fills_remainder_with_hairline(self):
        out = dh_donut_gradient([{"fill": "paid", "pct": 40}])
        self.assertIn("var(--rmc-dh-accent) 0% 40%", out)
        self.assertIn("var(--hairline) 40% 100%", out)

    def test_empty_is_neutral_ring(self):
        out = dh_donut_gradient([])
        self.assertEqual(out, "conic-gradient(var(--hairline) 0% 100%)")

    def test_tuple_segments_supported(self):
        out = dh_donut_gradient([("brand", 100)])
        self.assertIn("var(--rmc-dh-brand) 0% 100%", out)

    def test_overflow_caps_at_100(self):
        out = dh_donut_gradient([
            {"fill": "paid", "pct": 80},
            {"fill": "overdue", "pct": 50},
        ])
        self.assertIn("var(--rmc-dh-accent) 0% 80%", out)
        self.assertIn("var(--rmc-dh-danger) 80% 100%", out)
        self.assertNotIn("130%", out)


class DhTemplateIntegrationTests(SimpleTestCase):
    def test_loads_and_renders_in_template(self):
        tpl = Template(
            "{% load rmc_dh %}"
            "{% dh_donut_gradient segs as grad %}"
            "{{ value|dh_ratio:max }}|{{ grad }}|{{ 'paid'|dh_fill }}"
        )
        rendered = tpl.render(Context({
            "segs": [{"fill": "paid", "pct": 50}],
            "value": 3,
            "max": 6,
        }))
        self.assertIn("50|", rendered)
        self.assertIn("conic-gradient(", rendered)
        self.assertIn("var(--rmc-dh-accent)", rendered)
