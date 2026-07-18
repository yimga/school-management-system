"""Stall-watch must flag LIVE schools stuck in onboarding.

Dead-guard backlog item 18. ``detect_stalled_onboarding`` filtered
``school__is_active=False`` in both walks. ``School.is_active`` defaults True and
nothing flips a never-provisioned school to False, so the target population
(active schools stuck under 20% after 3 days) was excluded by construction and
the walk returned empty every run -- the stall alert could never fire.

NOTE: the task is deliberately NOT wired to Celery beat (out of scope here); this
test drives the function directly to prove the query now matches the intended
population.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.lifecycle.tasks_stall_watch import detect_stalled_onboarding
from apps.platform_runtime.models import SchoolOnboardingProgress
from apps.schools.models import School


class StallWatchActiveSchoolFilterTests(TestCase):
    def test_live_stalled_school_is_flagged(self):
        school = School.objects.create(name="Stuck Academy", slug="stuck-academy-sw")
        # created_at is auto_now_add; push it 5 days into the past so it clears
        # the 3-day floor cutoff.
        School.objects.filter(pk=school.pk).update(
            created_at=timezone.now() - timedelta(days=5)
        )
        self.assertTrue(school.is_active)  # live school -- the stall-watch target
        SchoolOnboardingProgress.objects.create(school=school, progress_percent=5)

        summary = detect_stalled_onboarding(dry_run=True)

        self.assertGreaterEqual(
            summary["stalled_low_progress_count"],
            1,
            "a live school stuck at 5% for 5 days was not flagged -- the "
            "is_active=False filter excluded the entire active population",
        )
        slugs = [row["school_slug"] for row in summary["stalled_low_progress"]]
        self.assertIn("stuck-academy-sw", slugs)

    def test_deactivated_school_is_not_flagged(self):
        # Offboarded/deactivated schools are NOT stalled-onboarding candidates.
        school = School.objects.create(
            name="Gone Academy", slug="gone-academy-sw", is_active=False
        )
        School.objects.filter(pk=school.pk).update(
            created_at=timezone.now() - timedelta(days=5)
        )
        SchoolOnboardingProgress.objects.create(school=school, progress_percent=5)

        summary = detect_stalled_onboarding(dry_run=True)

        slugs = [row["school_slug"] for row in summary["stalled_low_progress"]]
        self.assertNotIn("gone-academy-sw", slugs)
