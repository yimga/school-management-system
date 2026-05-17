"""Tests for ``apps.platform_runtime.rum_cls_budget``."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.rum_cls_budget import (
    CLS_GOOD_BUDGET,
    compute_p75,
    evaluate,
)


class ComputeP75Tests(SimpleTestCase):
    def test_returns_none_below_four_samples(self):
        self.assertIsNone(compute_p75([]))
        self.assertIsNone(compute_p75([0.05]))
        self.assertIsNone(compute_p75([0.05, 0.1, 0.2]))

    def test_p75_basic(self):
        # quantiles(n=4) on [1,2,3,4,5] -> Q1=1.5 Q2=3 Q3=4.5
        self.assertAlmostEqual(compute_p75([1, 2, 3, 4, 5]), 4.5)

    def test_p75_below_budget(self):
        # 10 good samples; p75 ~ 0.06
        samples = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.06, 0.05, 0.04, 0.05]
        self.assertLess(compute_p75(samples), CLS_GOOD_BUDGET)

    def test_skips_non_numeric(self):
        # Mixed list with some bad entries — non-numeric is filtered.
        self.assertAlmostEqual(
            compute_p75([0.01, 0.02, 0.03, 0.04, "skip", None, 0.05]),
            compute_p75([0.01, 0.02, 0.03, 0.04, 0.05]),
        )


class EvaluateTests(SimpleTestCase):
    def test_no_patterns_no_breaches(self):
        result = evaluate({})
        self.assertEqual(result["breach_count"], 0)
        self.assertEqual(result["breaches"], [])
        self.assertEqual(result["insufficient_samples"], [])

    def test_insufficient_samples_not_a_breach(self):
        result = evaluate({"/portal/": [0.5, 0.6]})  # only 2 samples
        self.assertEqual(result["breach_count"], 0)
        self.assertIn("/portal/", result["insufficient_samples"])

    def test_good_pattern_no_breach(self):
        samples = [0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
        result = evaluate({"/marketing/": samples})
        self.assertEqual(result["breach_count"], 0)
        row = result["rows"][0]
        self.assertEqual(row["pattern"], "/marketing/")
        self.assertLess(row["p75"], CLS_GOOD_BUDGET)

    def test_bad_pattern_breaches(self):
        # All samples above budget -> p75 > 0.1
        samples = [0.2, 0.3, 0.25, 0.4, 0.35]
        result = evaluate({"/portal/finance/invoices/": samples})
        self.assertEqual(result["breach_count"], 1)
        self.assertEqual(result["breaches"][0]["pattern"], "/portal/finance/invoices/")
        self.assertGreater(result["breaches"][0]["p75"], CLS_GOOD_BUDGET)

    def test_custom_budget(self):
        samples = [0.05, 0.06, 0.07, 0.08, 0.09]
        # Strict 0.05 budget -> breach.
        result = evaluate({"/x/": samples}, budget=0.05)
        self.assertEqual(result["breach_count"], 1)
        # Loose 0.5 budget -> pass.
        result2 = evaluate({"/x/": samples}, budget=0.5)
        self.assertEqual(result2["breach_count"], 0)
