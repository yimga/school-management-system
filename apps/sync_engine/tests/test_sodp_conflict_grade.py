"""SODP: grade / money-adjacent conflicts never auto-merge."""

from django.test import SimpleTestCase

from apps.sync_engine.conflict_resolver import (
    DEFAULT_STRATEGY_PER_ENTITY,
    ResolutionStrategy,
    resolve_one,
)


class SodpGradeConflictTests(SimpleTestCase):
    def test_grade_entry_defaults_to_manual_review(self):
        self.assertEqual(
            DEFAULT_STRATEGY_PER_ENTITY.get("grade_entry"),
            ResolutionStrategy.MANUAL_REVIEW,
        )

    def test_grade_entry_conflict_never_auto_applies(self):
        decision = resolve_one(
            {
                "entity": "grade_entry",
                "remote": {"timestamp": "2026-05-23T12:00:00Z", "score": 88},
                "server": {"timestamp": "2026-05-22T12:00:00Z", "score": 90},
            }
        )
        self.assertEqual(decision["action"], "manual_review")
