"""Seal: the cron trigger must be REACHABLE, and its effect must be PROVABLE.

Two findings, both audited by running rather than reading.

FINDING 1 -- the trigger 404s on every host a real deployment serves.
``/api/internal/cron/run/`` is the only thing that runs the 26 ``auto_eligible=False``
jobs (the ``/health/`` tick runs ``auto_only=True`` on purpose). It was declared
inline in ``config/urls.py`` and ``config/manager_urls.py`` and nowhere else, while
``UrlConfSwitcherMiddleware`` routes by Host:

    config.urls          <- developer / loopback only
    config.manager_urls  <- manager.<base> only
    config.public_urls   <- the canonical base domain          [ROUTE ABSENT]
    config.tenant_urls   <- every tenant subdomain AND EVERY SOVEREIGN BOX  [ABSENT]
    config.api_urls      <- the api host                       [ROUTE ABSENT]

``is_sovereign_single_tenant_box()`` routes a box to ``config.tenant_urls``
explicitly, so on a box the documented trigger mechanism returned 404. The view
ALSO returns 404 when ``INTERNAL_CRON_TOKEN`` is unset ("indistinguishable from no
such URL" -- its words), so the two failures are the same response: an operator
would set the secret, see 404 again, and have no next move.

The pre-existing suite could not catch this. ``InternalCronEndpointTests`` uses
``reverse("internal_cron_run")`` against the default ROOT_URLCONF, and the test
client's ``testserver`` host resolves to ``local`` -> ``config.urls``, the one
urlconf that mounts a superset of every route. It proved the endpoint works on the
only urlconf no deployment uses.

FINDING 2 -- nothing could prove a job ran.
Every signal available after a trigger is green-on-failure:
  * the 200 proves a request was served; ``{"background": true}`` returns 202
    BEFORE any job starts;
  * ``registry_status()`` reads the CACHE ``last_run``, which ``periodic._claim``
    writes BEFORE calling the job -- so a job that raised immediately still reports
    a fresh ``last_run_epoch`` and ``due_now: false`` (control test below);
  * the admin lists heartbeat ROWS, so a job that never ran has no row and is
    simply absent -- which is how 26 jobs stayed invisible.
Only a REGISTRY-joined durable heartbeat can answer it, and it must distinguish
"never invoked" from "invoked and crashed" (the old monitor called both
``never_succeeded``).

Load-bearing tests are prefixed ``test_``; controls are prefixed
``test_control_`` and assert ONLY pre-existing behaviour -- they must pass on both
trees.
"""
from __future__ import annotations

import json

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import Resolver404, resolve
from io import StringIO

from apps.platform_runtime import periodic
from apps.platform_runtime.models_scheduling import ScheduledJobHeartbeat
from apps.platform_runtime.scheduled_job_health import (
    VERDICT_FAILING,
    VERDICT_NEVER_INVOKED,
    VERDICT_OK,
    build_execution_evidence,
    summarize_execution_evidence,
)
from config.internal_machine_urls import DEPLOYMENT_SERVED_URLCONFS

CRON_PATH = "/api/internal/cron/run/"
TOKEN = "z" * 24
AUTH = {"HTTP_AUTHORIZATION": "Bearer " + TOKEN}

#: The 26 cron-only jobs measured on this tree by executing ``registry_status()``.
#: They are auto_eligible=False, so the /health/ tick never runs them and the
#: secured cron endpoint is their ONLY trigger.
CRON_ONLY_JOBS = (
    "advancement.mint_recurring_donation_pledges",
    "analytics.send_deadline_reminders",
    "billing.run_platform_billing_lifecycle",
    "billing.run_subscription_reminders",
    "communication.process_outbound_message_queue",
    "communication.send_due_scheduled_announcements",
    "communication.send_parent_digests_daily",
    "communication.send_parent_digests_weekly",
    "events.process_event_outbox",
    "events.process_webhook_deliveries",
    "finance.execute_approved_fee_invoice_generations",
    "finance.retry_failed_payment_reminders",
    "finance.send_payment_reminders",
    "lifecycle.capture_tenant_immutable_snapshots_daily",
    "marketplace.deliver_due_webhooks",
    "migration_cloud.deliver_due_webhooks",
    "orchestration.aggregate_slos",
    "orchestration.auto_trigger",
    "orchestration.process_due_runs",
    "people.advance_school_transfer_batches",
    "people.check_badge_expiry_alerts",
    "platform_runtime.process_due_configuration_changes",
    "requests.remind_pending_assignees",
    "schoolops.redrive_email_dead_letters",
    "schoolops.sweep_low_meal_plan_balances",
    "social_media.process_outbox_batch",
)


class _RegistryIsolation:
    """Swap in a private registry so a test cannot be decided by the real 34 jobs."""

    def setUp(self):
        super().setUp()
        self._saved = dict(periodic._REGISTRY)
        self._saved_installed = periodic._DEFAULTS_INSTALLED
        periodic._REGISTRY.clear()
        periodic._DEFAULTS_INSTALLED = True
        cache.clear()
        ScheduledJobHeartbeat.objects.all().delete()

    def tearDown(self):
        periodic._REGISTRY.clear()
        periodic._REGISTRY.update(self._saved)
        periodic._DEFAULTS_INSTALLED = self._saved_installed
        cache.clear()
        super().tearDown()


# =============================================================================
# FINDING 1 -- reachability
# =============================================================================
class CronTriggerReachabilityTests(TestCase):
    """LOAD-BEARING. The trigger must resolve on every urlconf a deployment serves."""

    def test_cron_route_resolves_on_every_deployment_served_urlconf(self):
        missing = []
        for urlconf in DEPLOYMENT_SERVED_URLCONFS:
            try:
                match = resolve(CRON_PATH, urlconf=urlconf)
            except Resolver404:
                missing.append(urlconf)
                continue
            self.assertEqual(
                match.func.__module__,
                "apps.platform_runtime.views_internal_cron",
                f"{urlconf} resolves {CRON_PATH} to the wrong view",
            )
        self.assertEqual(
            missing,
            [],
            "the cron trigger 404s on these urlconfs, so the 26 cron-only jobs "
            f"cannot be triggered on the hosts they serve: {missing}",
        )

    @override_settings(
        INTERNAL_CRON_TOKEN=TOKEN,
        RMC_IS_SELFHOST_BOX=True,
        RMC_IS_CLOUD_DEPLOYED=False,
        USE_DJANGO_TENANTS=False,
        ALLOWED_HOSTS=["*"],
    )
    def test_cron_endpoint_reachable_on_a_sovereign_box_host(self):
        """A box is routed to config.tenant_urls by UrlConfSwitcherMiddleware.

        Probed through the REAL middleware stack with a box-shaped Host, because
        ``@override_settings(ROOT_URLCONF=...)`` does not survive a request -- the
        middleware sets ``request.urlconf`` from the Host header.
        """
        resp = self.client.get(CRON_PATH, HTTP_HOST="10.10.20.137", **AUTH)
        self.assertNotEqual(
            resp.status_code,
            404,
            "the cron trigger 404s on a sovereign box -- indistinguishable from "
            "'INTERNAL_CRON_TOKEN unset', which is why it was never diagnosed",
        )
        self.assertEqual(resp.status_code, 200)

    @override_settings(
        INTERNAL_CRON_TOKEN=TOKEN,
        MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
        ALLOWED_HOSTS=["*"],
    )
    def test_cron_endpoint_reachable_on_the_canonical_base_domain(self):
        """The base domain is routed to config.public_urls."""
        resp = self.client.get(CRON_PATH, HTTP_HOST="runmycampus.com", **AUTH)
        self.assertNotEqual(resp.status_code, 404)
        self.assertEqual(resp.status_code, 200)

    def test_control_route_resolves_on_dev_and_manager_urlconfs(self):
        """CONTROL: pre-existing behaviour -- these two always mounted the route."""
        for urlconf in ("config.urls", "config.manager_urls"):
            match = resolve(CRON_PATH, urlconf=urlconf)
            self.assertEqual(match.url_name, "internal_cron_run")


# =============================================================================
# FINDING 2 -- execution evidence
# =============================================================================
class ExecutionEvidenceRuleTests(TestCase):
    """LOAD-BEARING. The verdict rule, as a pure function (no DB, no cache)."""

    def _registry(self, name="j.one", *, auto_eligible=False, interval=300):
        return [{"job": name, "interval_seconds": interval, "auto_eligible": auto_eligible}]

    def test_registered_job_with_no_heartbeat_is_never_invoked(self):
        rows = build_execution_evidence(self._registry(), {}, now=1000.0)
        self.assertEqual(rows[0]["verdict"], VERDICT_NEVER_INVOKED)
        self.assertFalse(rows[0]["ever_invoked"])
        self.assertEqual(rows[0]["trigger"], "cron_only")

    def test_invoked_but_never_succeeded_is_failing_not_never_invoked(self):
        """The discrimination the old monitor could not make.

        ``evaluate_staleness`` calls both cases ``never_succeeded`` because both
        have ``last_success_at IS NULL``. After a trigger those mean opposite
        things: one says nothing invoked the job, the other says the job crashed.
        """
        hb = {
            "j.one": {
                "last_started_epoch": 999.0,
                "last_success_epoch": None,
                "last_status": "error",
                "last_duration_ms": 5,
                "consecutive_failures": 2,
                "last_error": "kaboom",
            }
        }
        rows = build_execution_evidence(self._registry(), hb, now=1000.0)
        self.assertEqual(rows[0]["verdict"], VERDICT_FAILING)
        self.assertTrue(rows[0]["ever_invoked"])
        self.assertFalse(rows[0]["ever_succeeded"])
        self.assertEqual(rows[0]["last_error"], "kaboom")

    def test_fresh_success_is_ok(self):
        hb = {
            "j.one": {
                "last_started_epoch": 990.0,
                "last_success_epoch": 990.0,
                "last_status": "ran",
                "last_duration_ms": 12,
                "consecutive_failures": 0,
                "last_error": "",
            }
        }
        rows = build_execution_evidence(self._registry(), hb, now=1000.0)
        self.assertEqual(rows[0]["verdict"], VERDICT_OK)

    def test_summary_counts_cron_only_never_invoked_separately(self):
        registry = [
            {"job": "a", "interval_seconds": 300, "auto_eligible": False},
            {"job": "b", "interval_seconds": 300, "auto_eligible": False},
            {"job": "c", "interval_seconds": 300, "auto_eligible": True},
        ]
        summary = summarize_execution_evidence(
            build_execution_evidence(registry, {}, now=1000.0)
        )
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["never_invoked"], 3)
        self.assertEqual(summary["cron_only_total"], 2)
        self.assertEqual(summary["cron_only_never_invoked"], 2)
        self.assertEqual(summary["healthy"], 0)


class EvidenceSurfaceTests(_RegistryIsolation, TestCase):
    """LOAD-BEARING. The evidence must reach an operator through real surfaces."""

    def setUp(self):
        super().setUp()
        self.calls = {"n": 0}

        def _job():
            self.calls["n"] += 1

        periodic.register_job(
            "evidence.probe", interval_seconds=300, func=_job, auto_eligible=False
        )

    @override_settings(INTERNAL_CRON_TOKEN=TOKEN)
    def test_get_status_carries_durable_evidence_and_summary(self):
        resp = self.client.get(CRON_PATH, **AUTH)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("evidence", body)
        self.assertIn("summary", body)
        row = next(r for r in body["evidence"] if r["job"] == "evidence.probe")
        self.assertEqual(row["verdict"], VERDICT_NEVER_INVOKED)
        self.assertEqual(body["summary"]["cron_only_never_invoked"], 1)

    @override_settings(INTERNAL_CRON_TOKEN=TOKEN)
    def test_evidence_flips_to_ok_after_the_trigger_actually_runs_the_job(self):
        """End-to-end: POST the trigger, then GET and see the durable verdict flip."""
        before = self.client.get(CRON_PATH, **AUTH).json()
        row = next(r for r in before["evidence"] if r["job"] == "evidence.probe")
        self.assertEqual(row["verdict"], VERDICT_NEVER_INVOKED)

        run = self.client.post(
            CRON_PATH,
            data={"job": "evidence.probe", "force": True},
            content_type="application/json",
            **AUTH,
        )
        self.assertEqual(run.status_code, 200)
        self.assertEqual(self.calls["n"], 1)

        after = self.client.get(CRON_PATH, **AUTH).json()
        row = next(r for r in after["evidence"] if r["job"] == "evidence.probe")
        self.assertEqual(row["verdict"], VERDICT_OK)
        self.assertTrue(row["ever_succeeded"])
        self.assertEqual(after["summary"]["cron_only_never_invoked"], 0)

    def test_report_command_lists_a_never_invoked_job(self):
        out = StringIO()
        call_command("report_scheduled_job_evidence", "--cron-only", stdout=out)
        text = out.getvalue()
        self.assertIn("evidence.probe", text)
        self.assertIn(VERDICT_NEVER_INVOKED, text)

    def test_report_command_json_mode_is_machine_readable(self):
        out = StringIO()
        call_command("report_scheduled_job_evidence", "--json", stdout=out)
        payload = json.loads(out.getvalue())
        self.assertIn("evidence", payload)
        self.assertIn("summary", payload)

    def test_report_command_fails_on_never_invoked_when_asked(self):
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "report_scheduled_job_evidence",
                "--fail-on-never-invoked",
                stdout=StringIO(),
            )
        self.assertIn("evidence.probe", str(ctx.exception))

    def test_report_command_window_assertion_passes_only_after_a_real_run(self):
        """``--fail-unless-succeeded-within`` is the post-trigger assertion."""
        with self.assertRaises(CommandError):
            call_command(
                "report_scheduled_job_evidence",
                "--fail-unless-succeeded-within",
                "600",
                stdout=StringIO(),
            )
        periodic.run_job("evidence.probe", force=True)
        call_command(
            "report_scheduled_job_evidence",
            "--fail-unless-succeeded-within",
            "600",
            stdout=StringIO(),
        )

    def test_report_command_reports_a_crashing_job_as_failing(self):
        def _boom():
            raise RuntimeError("kaboom")

        periodic.register_job(
            "evidence.boom", interval_seconds=300, func=_boom, auto_eligible=False
        )
        self.assertEqual(periodic.run_job("evidence.boom", force=True)["status"], "error")
        out = StringIO()
        call_command("report_scheduled_job_evidence", "--json", stdout=out)
        rows = json.loads(out.getvalue())["evidence"]
        boom = next(r for r in rows if r["job"] == "evidence.boom")
        self.assertEqual(boom["verdict"], VERDICT_FAILING)
        self.assertIn("kaboom", boom["last_error"])


# =============================================================================
# CONTROLS -- pre-existing behaviour only. Must pass on BOTH trees.
# =============================================================================
class CronEndpointContractControlTests(_RegistryIsolation, TestCase):
    def setUp(self):
        super().setUp()
        periodic.register_job(
            "control.job", interval_seconds=3600, func=lambda: None, auto_eligible=False
        )

    def test_control_404_when_token_unset(self):
        self.assertEqual(self.client.get(CRON_PATH).status_code, 404)
        self.assertEqual(self.client.post(CRON_PATH).status_code, 404)

    @override_settings(INTERNAL_CRON_TOKEN="s" * 15)
    def test_control_404_when_token_shorter_than_minimum(self):
        """MIN_TOKEN_LEN is 16: a 15-char secret leaves the endpoint disabled."""
        self.assertEqual(
            self.client.get(CRON_PATH, HTTP_AUTHORIZATION="Bearer " + "s" * 15).status_code,
            404,
        )

    @override_settings(INTERNAL_CRON_TOKEN=TOKEN)
    def test_control_403_on_missing_and_wrong_token(self):
        self.assertEqual(self.client.get(CRON_PATH).status_code, 403)
        self.assertEqual(
            self.client.get(CRON_PATH, HTTP_AUTHORIZATION="Bearer nope").status_code, 403
        )

    @override_settings(INTERNAL_CRON_TOKEN=TOKEN)
    def test_control_accepts_x_cron_key_header_too(self):
        self.assertEqual(
            self.client.get(CRON_PATH, HTTP_X_CRON_KEY=TOKEN).status_code, 200
        )

    @override_settings(INTERNAL_CRON_TOKEN=TOKEN)
    def test_control_background_post_returns_202_accepted(self):
        resp = self.client.post(
            CRON_PATH,
            data={"job": "control.job", "force": True, "background": True},
            content_type="application/json",
            **AUTH,
        )
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json()["status"], "accepted")

    @override_settings(INTERNAL_CRON_TOKEN=TOKEN)
    def test_control_get_still_returns_the_registry_jobs_key(self):
        body = self.client.get(CRON_PATH, **AUTH).json()
        self.assertIn("jobs", body)
        self.assertTrue(any(j["job"] == "control.job" for j in body["jobs"]))

    @override_settings(INTERNAL_CRON_TOKEN=TOKEN)
    def test_control_put_is_405(self):
        self.assertEqual(self.client.put(CRON_PATH, **AUTH).status_code, 405)


class CacheStatusIsGreenOnFailureControlTests(_RegistryIsolation, TestCase):
    """CONTROL: documents the pre-existing property that motivates the evidence layer.

    ``periodic._claim`` writes ``last_run`` BEFORE calling the job, so the cache
    surface reports a job that crashed as freshly-run and not-due. Nothing here is
    new behaviour -- this asserts the trap exists, so a future change that fixes it
    will fail this test loudly rather than silently making the evidence layer moot.
    """

    def test_control_last_run_is_written_even_when_the_job_raises(self):
        def _boom():
            raise RuntimeError("kaboom")

        periodic.register_job("control.boom", interval_seconds=3600, func=_boom)
        self.assertEqual(periodic.run_job("control.boom", force=True)["status"], "error")

        row = next(r for r in periodic.registry_status() if r["job"] == "control.boom")
        self.assertIsNotNone(
            row["last_run_epoch"],
            "cache last_run is set before the job runs -- a crashed job looks fresh",
        )
        self.assertFalse(row["due_now"])


class RegistryCensusControlTests(TestCase):
    """CONTROL: the population this whole thread is about, measured by running."""

    def test_control_the_26_cron_only_jobs_are_registered_and_cron_only(self):
        rows = {r["job"]: r for r in periodic.registry_status()}
        for name in CRON_ONLY_JOBS:
            self.assertIn(name, rows, f"{name} is no longer registered")
            self.assertFalse(
                rows[name]["auto_eligible"],
                f"{name} became auto_eligible -- the /health/ tick now runs it",
            )
        self.assertEqual(len(CRON_ONLY_JOBS), 26)

    def test_control_health_tick_path_skips_every_cron_only_job(self):
        """Why the endpoint is their ONLY trigger: the auto path filters them out."""
        cron_only = {
            r["job"] for r in periodic.registry_status() if not r["auto_eligible"]
        }
        self.assertTrue(cron_only)
        for name in CRON_ONLY_JOBS:
            self.assertIn(name, cron_only)
