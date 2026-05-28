"""v4.00.13 — unit tests for apps/admissions/queue_depth.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.admissions.queue_depth import (
    _QUEUE_STAGES,
    compute_admissions_queue_depth,
)


class ComputeQueueDepthTests(SimpleTestCase):
    def test_none_school_returns_empty(self):
        self.assertEqual(compute_admissions_queue_depth(None), [])

    def test_school_without_pk_returns_empty(self):
        class Dummy:
            pk = None
        self.assertEqual(compute_admissions_queue_depth(Dummy()), [])

    def test_returns_one_row_per_stage_plus_total(self):
        class Dummy:
            pk = 1

        # Mock Applicant.objects.filter().count() to return predictable counts per stage.
        fake_qs = MagicMock()
        fake_qs.count.return_value = 3

        fake_model = MagicMock()
        fake_model.objects.filter.return_value = fake_qs

        with patch.dict("sys.modules", {"apps.people.models": MagicMock(Applicant=fake_model)}):
            rows = compute_admissions_queue_depth(Dummy())

        # 5 stages + 1 total
        self.assertEqual(len(rows), len(_QUEUE_STAGES) + 1)
        stage_codes = [r["stage"] for r in rows]
        for expected_stage in ["APPLIED", "UNDER_REVIEW", "ACCEPTED", "LEAD", "REJECTED"]:
            self.assertIn(expected_stage, stage_codes)
        self.assertEqual(rows[-1]["stage"], "__TOTAL_ACTIONABLE__")

    def test_total_counts_only_actionable_stages(self):
        class Dummy:
            pk = 1
        fake_qs = MagicMock()
        fake_qs.count.return_value = 2

        fake_model = MagicMock()
        fake_model.objects.filter.return_value = fake_qs

        with patch.dict("sys.modules", {"apps.people.models": MagicMock(Applicant=fake_model)}):
            rows = compute_admissions_queue_depth(Dummy())

        total_row = rows[-1]
        # Three stages are flagged actionable (APPLIED, UNDER_REVIEW, ACCEPTED) → total = 3 * 2 = 6
        self.assertEqual(total_row["count"], 6)

    def test_drill_url_includes_stage(self):
        class Dummy:
            pk = 1
        fake_qs = MagicMock()
        fake_qs.count.return_value = 0
        fake_model = MagicMock()
        fake_model.objects.filter.return_value = fake_qs

        with patch.dict("sys.modules", {"apps.people.models": MagicMock(Applicant=fake_model)}):
            rows = compute_admissions_queue_depth(Dummy())
        applied_row = next(r for r in rows if r["stage"] == "APPLIED")
        self.assertIn("stage=APPLIED", applied_row["drill_url"])

    def test_exception_in_model_returns_empty(self):
        class Dummy:
            pk = 1
        with patch("builtins.__import__", side_effect=ImportError("simulated")):
            # Local import inside compute_admissions_queue_depth will raise;
            # function must catch and return [].
            result = compute_admissions_queue_depth(Dummy())
        self.assertEqual(result, [])

    def test_stage_order_actionable_first(self):
        actionable_stages = [code for code, _, actionable in _QUEUE_STAGES if actionable]
        non_actionable_stages = [code for code, _, actionable in _QUEUE_STAGES if not actionable]
        # All actionable stages should come before non-actionable
        all_stages = [code for code, _, _ in _QUEUE_STAGES]
        last_actionable_idx = max(all_stages.index(s) for s in actionable_stages)
        first_non_actionable_idx = min(all_stages.index(s) for s in non_actionable_stages)
        self.assertLess(last_actionable_idx, first_non_actionable_idx,
                        "actionable stages must be ordered before non-actionable for review UX")
