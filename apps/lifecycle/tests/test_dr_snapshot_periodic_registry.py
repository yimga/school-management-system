"""DR snapshot capture must run on a BROKER-LESS box via the periodic registry.

The tenant immutable DR snapshot task was wired ONLY into ``CELERY_BEAT_SCHEDULE``
(``lifecycle-tenant-immutable-snapshot-daily``) and had no management command and
no entry in the in-process periodic registry. On a sovereign edge mini-PC (and the
no-worker cloud default) there is no Celery beat, so the tenant's ONLY
disaster-recovery backup silently never captured. This seals that gap: the job is
registered in ``apps.platform_runtime.periodic`` so the ``run_periodic_jobs`` cron
/ secured cron endpoint drives it without a worker.

RULE ZERO: a registration-shape assertion alone proves nothing about whether the
job actually captures anything. The load-bearing test is ``test_running_...`` —
it invokes the job through the SAME path ``run_periodic_jobs`` uses and asserts a
real ``TenantImmutableSnapshot`` row lands (must-FIRE, effect-probing).
"""
from __future__ import annotations

from django.test import TestCase, override_settings

from apps.platform_runtime import periodic

_JOB = "lifecycle.capture_tenant_immutable_snapshots_daily"


class _DefaultsInstalledMixin:
    """Install the real default registry for the test, then restore it."""

    def setUp(self):
        super().setUp()
        self._saved_registry = dict(periodic._REGISTRY)
        self._saved_installed = periodic._DEFAULTS_INSTALLED
        periodic._REGISTRY.clear()
        periodic._DEFAULTS_INSTALLED = False  # let ensure_default_jobs install
        from django.core.cache import cache

        cache.clear()  # _claim() reads/writes cache last_run + lock
        periodic.ensure_default_jobs()

    def tearDown(self):
        from django.core.cache import cache

        periodic._REGISTRY.clear()
        periodic._REGISTRY.update(self._saved_registry)
        periodic._DEFAULTS_INSTALLED = self._saved_installed
        cache.clear()
        super().tearDown()


class DrSnapshotRegisteredCronOnlyDailyTests(_DefaultsInstalledMixin, TestCase):
    def test_registered_cron_only_daily_heavy(self):
        job = periodic._REGISTRY.get(_JOB)
        self.assertIsNotNone(
            job,
            f"{_JOB} is absent from the periodic registry — DR snapshots never run "
            "on a broker-less box.",
        )
        # Heavy tenant-fan-out: MUST stay off the hot /health/ thread.
        self.assertFalse(job.auto_eligible)
        self.assertEqual(job.interval_seconds, periodic.DAILY_SECONDS)
        self.assertEqual(job.lock_ttl_seconds, periodic.HEAVY_JOB_LOCK_TTL_SECONDS)
        self.assertIn("dr", job.tags)

    def test_auto_health_tick_never_runs_dr(self):
        # The AUTO (/health/-tick) path must EXCLUDE this heavy job entirely.
        auto = periodic.run_due_jobs(force=True, auto_only=True)
        self.assertNotIn(_JOB, {r["job"] for r in auto})


@override_settings(SECRET_KEY="test-dr-periodic-signing-key")
class DrSnapshotPeriodicRunCapturesTests(_DefaultsInstalledMixin, TestCase):
    """Must-FIRE: driving the registered job through the cron path actually
    captures a snapshot for an active school (not merely 'is registered')."""

    def test_running_registered_job_captures_snapshot_for_active_school(self):
        from apps.lifecycle.models_dr_snapshot import TenantImmutableSnapshot
        from apps.schools.models import School

        school = School.objects.create(
            name="DR Cron School", slug="dr-cron-school", subdomain="dr-cron-school"
        )
        self.assertEqual(
            TenantImmutableSnapshot.objects.filter(school=school).count(), 0
        )

        # Exactly what `python manage.py run_periodic_jobs --job <name> --force`
        # does — the broker-less rail an edge box runs on OS cron.
        result = periodic.run_job(_JOB, force=True)
        self.assertEqual(result["status"], "ran", result)

        # EFFECT: the active school now has a durable immutable snapshot row.
        self.assertEqual(
            TenantImmutableSnapshot.objects.filter(school=school).count(),
            1,
            "the registered DR job ran but captured no snapshot — the wiring is a "
            "no-op.",
        )

    def test_second_run_same_day_is_idempotent_not_duplicated(self):
        # Beat + cron could both fire in a mixed topology; capture is keyed on
        # (school, snapshot_date) so a duplicate tick re-captures, never doubles.
        from apps.lifecycle.models_dr_snapshot import TenantImmutableSnapshot
        from apps.schools.models import School

        school = School.objects.create(
            name="DR Idem School", slug="dr-idem-school", subdomain="dr-idem-school"
        )
        periodic.run_job(_JOB, force=True)
        periodic.run_job(_JOB, force=True)
        self.assertEqual(
            TenantImmutableSnapshot.objects.filter(school=school).count(), 1
        )
