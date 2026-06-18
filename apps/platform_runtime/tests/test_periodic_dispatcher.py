"""Seal: the in-process periodic dispatcher + secured cron endpoint.

Covers the three trigger paths converging on one locked registry:
  * run_job/run_due_jobs due-gating, force, and cross-worker lock claim
  * inprocess_scheduler_enabled() auto-yield when a Celery broker is configured
  * maybe_run_due_jobs() inert under tests / when disabled (never blocks /health/)
  * the token-authed /api/internal/cron/run/ endpoint (disabled / 403 / GET / POST)
"""
from __future__ import annotations

import os
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.platform_runtime import periodic


class _RegistryIsolationMixin:
    def setUp(self):
        super().setUp()
        self._saved_registry = dict(periodic._REGISTRY)
        self._saved_installed = periodic._DEFAULTS_INSTALLED
        periodic._REGISTRY.clear()
        # Block benchmark auto-registration so tests are deterministic + fast.
        periodic._DEFAULTS_INSTALLED = True
        cache.clear()
        self.calls = {"n": 0}

        def _job():
            self.calls["n"] += 1

        periodic.register_job(
            "test.job", interval_seconds=3600, func=_job, description="unit test job"
        )

    def tearDown(self):
        periodic._REGISTRY.clear()
        periodic._REGISTRY.update(self._saved_registry)
        periodic._DEFAULTS_INSTALLED = self._saved_installed
        cache.clear()
        super().tearDown()


class PeriodicDispatcherTests(_RegistryIsolationMixin, TestCase):
    def test_runs_when_due_then_skips_until_interval(self):
        r1 = periodic.run_job("test.job")
        self.assertEqual(r1["status"], "ran")
        self.assertEqual(self.calls["n"], 1)

        r2 = periodic.run_job("test.job")
        self.assertEqual(r2["status"], "not_due")
        self.assertEqual(self.calls["n"], 1)

    def test_force_overrides_interval(self):
        periodic.run_job("test.job")
        r = periodic.run_job("test.job", force=True)
        self.assertEqual(r["status"], "ran")
        self.assertEqual(self.calls["n"], 2)

    def test_lock_prevents_concurrent_run(self):
        # Simulate another worker holding the per-job lock.
        cache.add(periodic._lock_key("test.job"), "1", 600)
        r = periodic.run_job("test.job", force=True)
        self.assertEqual(r["status"], "skipped_locked")
        self.assertEqual(self.calls["n"], 0)

    def test_unknown_and_disabled_jobs(self):
        self.assertEqual(periodic.run_job("nope.nope")["status"], "unknown")
        periodic.register_job(
            "test.off", interval_seconds=1, func=lambda: None, enabled=False
        )
        self.assertEqual(periodic.run_job("test.off", force=True)["status"], "disabled")

    def test_failing_job_never_raises(self):
        def _boom():
            raise RuntimeError("kaboom")

        periodic.register_job("test.boom", interval_seconds=1, func=_boom)
        r = periodic.run_job("test.boom", force=True)
        self.assertEqual(r["status"], "error")
        self.assertIn("kaboom", r["error"])

    def test_run_due_jobs_runs_each_once(self):
        results = periodic.run_due_jobs()
        statuses = {r["job"]: r["status"] for r in results}
        self.assertEqual(statuses["test.job"], "ran")
        self.assertEqual(self.calls["n"], 1)

    def test_registry_status_shape(self):
        rows = periodic.registry_status()
        row = next(r for r in rows if r["job"] == "test.job")
        self.assertEqual(row["interval_seconds"], 3600)
        self.assertTrue(row["due_now"])  # never run yet
        self.assertTrue(row["enabled"])

    def test_maybe_run_due_jobs_inert_under_tests(self):
        # RUNNING_TESTS is True during the suite → the auto trigger must no-op
        # (no thread, no job run) so /health/ stays untouched.
        periodic.maybe_run_due_jobs()
        self.assertEqual(self.calls["n"], 0)


class HealthEndpointSchedulerFlagTests(TestCase):
    def test_health_reports_inprocess_scheduler_flag(self):
        resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("inprocess_scheduler", body)
        # Boolean (or None only if the periodic import failed — it shouldn't here).
        self.assertIsInstance(body["inprocess_scheduler"], bool)


class SchedulerModeTests(TestCase):
    def _enabled(self, env):
        with mock.patch.dict(os.environ, env, clear=False):
            for k in ("RMC_INPROCESS_SCHEDULER", "CELERY_BROKER_URL"):
                if k not in env:
                    os.environ.pop(k, None)
            return periodic.inprocess_scheduler_enabled()

    def test_auto_enabled_without_broker(self):
        self.assertTrue(self._enabled({"RMC_INPROCESS_SCHEDULER": "auto"}))

    def test_auto_disabled_when_broker_present(self):
        self.assertFalse(
            self._enabled(
                {"RMC_INPROCESS_SCHEDULER": "auto", "CELERY_BROKER_URL": "redis://x"}
            )
        )

    def test_explicit_off(self):
        self.assertFalse(self._enabled({"RMC_INPROCESS_SCHEDULER": "off"}))

    def test_explicit_on_overrides_broker(self):
        self.assertTrue(
            self._enabled(
                {"RMC_INPROCESS_SCHEDULER": "on", "CELERY_BROKER_URL": "redis://x"}
            )
        )


class InternalCronEndpointTests(_RegistryIsolationMixin, TestCase):
    def _url(self):
        return reverse("internal_cron_run")

    def test_disabled_when_token_unset(self):
        # Default test settings have no INTERNAL_CRON_TOKEN → endpoint is 404.
        self.assertEqual(self.client.get(self._url()).status_code, 404)
        self.assertEqual(self.client.post(self._url()).status_code, 404)

    @override_settings(INTERNAL_CRON_TOKEN="x" * 20)
    def test_rejects_missing_and_wrong_token(self):
        self.assertEqual(self.client.get(self._url()).status_code, 403)
        self.assertEqual(
            self.client.get(self._url(), HTTP_AUTHORIZATION="Bearer wrong").status_code,
            403,
        )

    @override_settings(INTERNAL_CRON_TOKEN="x" * 20)
    def test_status_get(self):
        resp = self.client.get(self._url(), HTTP_AUTHORIZATION="Bearer " + "x" * 20)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("jobs", data)
        self.assertTrue(any(j["job"] == "test.job" for j in data["jobs"]))

    @override_settings(INTERNAL_CRON_TOKEN="x" * 20)
    def test_post_runs_named_job(self):
        resp = self.client.post(
            self._url(),
            data={"job": "test.job", "force": True},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + "x" * 20,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.calls["n"], 1)
        results = resp.json()["results"]
        self.assertEqual(results[0]["status"], "ran")

    @override_settings(INTERNAL_CRON_TOKEN="x" * 20)
    def test_oversized_body_413(self):
        big = "y" * 5000  # > MAX_BODY_BYTES (4096)
        resp = self.client.post(
            self._url(),
            data='{"pad":"' + big + '"}',
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + "x" * 20,
        )
        self.assertEqual(resp.status_code, 413)

    @override_settings(INTERNAL_CRON_TOKEN="x" * 20)
    def test_malformed_body_400(self):
        resp = self.client.post(
            self._url(),
            data="{not json",
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + "x" * 20,
        )
        self.assertEqual(resp.status_code, 400)

    @override_settings(INTERNAL_CRON_TOKEN="x" * 20)
    def test_non_ascii_token_is_403_not_500(self):
        # A weird/non-ASCII token must be rejected, never raise into a 500.
        resp = self.client.get(
            self._url(), HTTP_AUTHORIZATION="Bearer " + "ü" * 20
        )
        self.assertEqual(resp.status_code, 403)

    @override_settings(INTERNAL_CRON_TOKEN="x" * 20)
    def test_background_returns_202(self):
        resp = self.client.post(
            self._url(),
            data={"job": "test.job", "force": True, "background": True},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + "x" * 20,
        )
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json()["status"], "accepted")
