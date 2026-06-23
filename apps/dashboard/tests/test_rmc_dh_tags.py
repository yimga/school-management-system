"""Unit tests for the rmc_dh dashboard-home template helpers (pure, no DB)."""
from decimal import Decimal

from types import SimpleNamespace

from django.template import Context, Template
from django.test import SimpleTestCase

from apps.dashboard.templatetags.rmc_dh import (
    dh_areachart_points,
    dh_donut_gradient,
    dh_fee_donut_segments,
    dh_fill,
    dh_heat_levels,
    dh_ratio,
    dh_spark_heights,
    dh_syllabus_segbar,
)


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


class DhExtendedHelpersTests(SimpleTestCase):
    def test_spark_heights_scales_to_peak(self):
        trend = [{"value": 10}, {"value": 50}, {"value": 25}]
        heights = dh_spark_heights(trend)
        self.assertEqual(heights, [4, 22, 11])

    def test_heat_levels_buckets(self):
        cells = dh_heat_levels([{"label": "M", "value": 90}, {"label": "T", "value": 0}])
        self.assertEqual(cells[0]["level"], "l3")
        self.assertEqual(cells[1]["level"], "")

    def test_syllabus_segbar_splits_counts(self):
        segs = dh_syllabus_segbar({"approved": 5, "pending": 3, "draft": 2, "needs_revision": 0})
        self.assertEqual(sum(s["pct"] for s in segs), 100)
        self.assertEqual(segs[0]["fill"], "success")

    def test_fee_donut_segments_complements(self):
        segs = dh_fee_donut_segments(68)
        self.assertEqual(segs[0]["pct"], 68)
        self.assertEqual(segs[1]["pct"], 32)

    def test_areachart_points_nonempty(self):
        pts = dh_areachart_points([{"value": 1}, {"value": 3}])
        self.assertIn("line", pts)
        self.assertIn("area", pts)
        self.assertIn("0,", pts["line"])


class DhChildCardTagsTests(SimpleTestCase):
    def test_child_tags_attendance_good(self):
        card = SimpleNamespace(
            attendance=92,
            finance_balance=0,
            missing_work=0,
            badges=[],
        )
        from apps.dashboard.templatetags.rmc_dh import dh_child_tags

        tags = dh_child_tags(card, can_view_finance=True)
        self.assertTrue(any(t.get("kind") == "good" for t in tags))

    def test_child_meta_linked_when_no_results(self):
        from apps.dashboard.templatetags.rmc_dh import dh_child_meta

        card = SimpleNamespace(rank=3, average=78)
        self.assertEqual(dh_child_meta(card, can_view_results=False), "Linked")
