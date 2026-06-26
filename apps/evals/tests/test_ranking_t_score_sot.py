"""Regression-lock: the ranking T-score path now delegates to the single SOT
implementation ``grading.cohort_t_scores`` instead of an inline copy of the
formula. These no-DB tests prove the refactor preserves the EXACT output the
inline code produced for representative cohorts (incl. the zero-spread edge),
so a future change to the helper cannot silently shift live rankings.

Legacy inline formula that lived in ``ranking._compute_rankings``:

    mean  = statistics.mean(scores)
    stdev = statistics.pstdev(scores) or 1.0
    t     = round(50.0 + 10.0 * ((avg - mean) / stdev), 2)
"""

from __future__ import annotations

import statistics

from django.test import SimpleTestCase

from apps.evals.grading import cohort_t_scores


def _legacy_inline_t_scores(scores):
    """The exact pre-refactor inline computation, for equivalence assertions."""
    mean = statistics.mean(scores)
    stdev = statistics.pstdev(scores) or 1.0
    return [round(50.0 + 10.0 * ((avg - mean) / stdev), 2) for avg in scores]


class RankingTScoreDelegatesToSOT(SimpleTestCase):
    def test_matches_legacy_for_spread_cohort(self):
        scores = [12.5, 9.0, 15.75, 8.0, 11.0]
        self.assertEqual(
            cohort_t_scores(scores, ndigits=2),
            _legacy_inline_t_scores(scores),
        )

    def test_matches_legacy_for_wide_cohort(self):
        scores = [0.0, 25.0, 50.0, 75.0, 100.0]
        self.assertEqual(
            cohort_t_scores(scores, ndigits=2),
            _legacy_inline_t_scores(scores),
        )

    def test_zero_spread_is_neutral_50_both_paths(self):
        # Everyone identical: legacy used `pstdev or 1.0` but the numerator is 0,
        # so it also yields 50.0 — the helper returns 50.0 directly. Equivalent.
        scores = [14.0, 14.0, 14.0]
        self.assertEqual(cohort_t_scores(scores, ndigits=2), [50.0, 50.0, 50.0])
        self.assertEqual(
            cohort_t_scores(scores, ndigits=2),
            _legacy_inline_t_scores(scores),
        )

    def test_input_order_preserved_for_zip_repair(self):
        # The ranking re-pairs each student to their T-score by zip(), which is
        # only correct because the helper returns one value per input in order.
        scores = [11.0, 9.0, 13.0]
        out = cohort_t_scores(scores, ndigits=2)
        self.assertEqual(len(out), len(scores))
        # Higher raw average => higher T-score, position-aligned.
        self.assertGreater(out[2], out[0])
        self.assertGreater(out[0], out[1])


class ResolveRankingModeIsPublic(SimpleTestCase):
    def test_public_accessor_exists(self):
        from apps.evals import ranking

        self.assertTrue(hasattr(ranking, "resolve_ranking_mode"))
        # Thin wrapper over the private resolver — same callable contract.
        self.assertTrue(callable(ranking.resolve_ranking_mode))
