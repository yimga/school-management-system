"""Wave L3 — readiness + stall watch + concierge context."""

from __future__ import annotations

from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.schools.models import School

from .context_processors import lifecycle_readiness
from .models import SchoolLifecycleStage
from .readiness import (
    compute_unified_score,
    maybe_record_launch_ready_stage,
    needs_concierge,
)
from .tasks_stall_watch import (
    STALL_DAYS_FOR_FLOOR,
    detect_stalled_onboarding,
)


class ComputeUnifiedScoreTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Readiness Test",
            slug="readiness-test",
            subdomain="readiness-test",
        )

    def test_returns_none_for_unsaved_school(self):
        self.assertIsNone(compute_unified_score(None))

    def test_returns_zero_when_no_progress_rows(self):
        snapshot = compute_unified_score(self.school)
        self.assertEqual(snapshot.unified_score, 0)
        self.assertEqual(snapshot.band, "not-started")

    def test_score_band_for_in_progress(self):
        # Stub via direct DB write.
        from apps.platform_runtime.models import SchoolOnboardingProgress

        SchoolOnboardingProgress.objects.update_or_create(
            school=self.school,
            defaults={"progress_percent": 40},
        )
        snapshot = compute_unified_score(self.school)
        # 40 * 0.4 + 0 * 0.6 = 16
        self.assertEqual(snapshot.checklist_percent, 40)
        self.assertEqual(snapshot.band, "not-started")

    def test_score_band_for_near_launch(self):
        from apps.platform_runtime.models import SchoolOnboardingProgress
        from apps.setup_studio.models import SetupProgress

        SchoolOnboardingProgress.objects.update_or_create(
            school=self.school, defaults={"progress_percent": 80}
        )
        SetupProgress.objects.update_or_create(
            school=self.school, defaults={"health_score": 75, "launch_ready": False}
        )
        snapshot = compute_unified_score(self.school)
        # 80*0.4 + 75*0.6 = 32 + 45 = 77 → near-launch
        self.assertEqual(snapshot.unified_score, 77)
        self.assertEqual(snapshot.band, "near-launch")


class MaybeRecordLaunchReadyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Launch Test",
            slug="launch-test",
            subdomain="launch-test",
        )

    def test_skips_below_threshold(self):
        wrote = maybe_record_launch_ready_stage(self.school)
        self.assertFalse(wrote)

    def test_records_when_score_and_flag_both_met(self):
        from apps.platform_runtime.models import SchoolOnboardingProgress
        from apps.setup_studio.models import SetupProgress

        SchoolOnboardingProgress.objects.update_or_create(
            school=self.school, defaults={"progress_percent": 100}
        )
        SetupProgress.objects.update_or_create(
            school=self.school, defaults={"health_score": 95, "launch_ready": True}
        )
        wrote = maybe_record_launch_ready_stage(self.school)
        self.assertTrue(wrote)
        self.assertTrue(
            SchoolLifecycleStage.objects.filter(
                school=self.school,
                stage=SchoolLifecycleStage.Stage.ONBOARDING_LAUNCH_READY,
            ).exists()
        )

    def test_idempotent_second_call(self):
        from apps.platform_runtime.models import SchoolOnboardingProgress
        from apps.setup_studio.models import SetupProgress

        SchoolOnboardingProgress.objects.update_or_create(
            school=self.school, defaults={"progress_percent": 100}
        )
        SetupProgress.objects.update_or_create(
            school=self.school, defaults={"health_score": 95, "launch_ready": True}
        )
        first = maybe_record_launch_ready_stage(self.school)
        second = maybe_record_launch_ready_stage(self.school)
        self.assertTrue(first)
        self.assertFalse(second)


class NeedsConciergeTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Concierge Test",
            slug="concierge-test",
            subdomain="concierge-test",
        )

    def test_returns_true_for_zero_score(self):
        self.assertTrue(needs_concierge(self.school))

    def test_returns_false_for_advanced_school(self):
        from apps.platform_runtime.models import SchoolOnboardingProgress
        from apps.setup_studio.models import SetupProgress

        SchoolOnboardingProgress.objects.update_or_create(
            school=self.school, defaults={"progress_percent": 80}
        )
        SetupProgress.objects.update_or_create(
            school=self.school, defaults={"health_score": 80, "launch_ready": False}
        )
        # Score = 80*0.4 + 80*0.6 = 80 — above 50%, no concierge
        self.assertFalse(needs_concierge(self.school))


class StallWatchTests(TestCase):
    def test_dry_run_returns_summary(self):
        result = detect_stalled_onboarding(dry_run=True)
        self.assertIn("checked_at", result)
        self.assertIn("stalled_low_progress_count", result)
        self.assertTrue(result["dry_run"])

    def test_detects_low_progress_stall(self):
        old = timezone.now() - timedelta(days=STALL_DAYS_FOR_FLOOR + 1)
        school = School.objects.create(
            name="Stalled School",
            slug="stalled-school",
            subdomain="stalled-school",
            is_active=False,
        )
        # Backdate the created_at to simulate an old onboarding.
        School.objects.filter(pk=school.pk).update(created_at=old)
        from apps.platform_runtime.models import SchoolOnboardingProgress

        SchoolOnboardingProgress.objects.update_or_create(
            school=school, defaults={"progress_percent": 5}
        )
        result = detect_stalled_onboarding(dry_run=True)
        slugs = [r["school_slug"] for r in result["stalled_low_progress"]]
        self.assertIn("stalled-school", slugs)


class LifecycleContextProcessorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Ctx School",
            slug="ctx-school",
            subdomain="ctx-school",
        )

    def test_returns_empty_for_manager_host(self):
        request = self.factory.get("/")
        request.public_host_kind = "manager"
        request.school = self.school
        self.assertEqual(lifecycle_readiness(request), {})

    def test_returns_empty_when_no_school(self):
        request = self.factory.get("/")
        request.public_host_kind = "tenant"
        self.assertEqual(lifecycle_readiness(request), {})

    def test_includes_readiness_and_concierge_for_tenant(self):
        request = self.factory.get("/")
        request.public_host_kind = "tenant"
        request.school = self.school
        ctx = lifecycle_readiness(request)
        self.assertIn("lifecycle_readiness", ctx)
        self.assertIn("lifecycle_concierge_enabled", ctx)
