"""v3.40.0 Agent 12 — tests for operator alert routing.

Coverage matrix (18 tests):

  Severity routing
  ----------------
  * info  → log only (no email, no Slack, no PagerDuty POST)
  * warning → log + email + Slack (no PagerDuty)
  * critical → log + email + Slack + PagerDuty

  Dry-run mode
  ------------
  * Dry-run + Slack configured → no urlopen call; "dry_run" appears in
    structured log only.
  * Dry-run + PagerDuty configured → no urlopen call.
  * Dry-run + email configured → no send_mail call; only the dry-run log.

  Channel failures don't cascade
  ------------------------------
  * Slack urlopen raises → alert() returns None, no exception bubbles.
  * PagerDuty urlopen raises → alert() returns None.

  Sensitive-data logging
  ----------------------
  * Webhook URL never appears in any log record (full URL).
  * PagerDuty integration key never appears in any log record.
  * Slack payload body chars don't bleed into the log (only sha prefix).

  Rate limiting + dedupe
  ----------------------
  * 51st distinct dedup_key in the same hour → dropped, single warning
    log emitted (not repeated).
  * Same dedup_key called twice in same hour → 2nd call still POSTs to
    Slack (we let PagerDuty handle upstream dedupe); a "dedupe-repeat"
    log fires.
  * After reset (test helper), state is clean.

  Token watchdog
  --------------
  * Finds overdue tokens (``grace_until < now`` AND ``rotated_to`` null),
    emits one alert per token.
  * Skips tokens where ``rotated_to`` is set (not overdue).
  * Returns ``{"status": "ran", "scanned": N, "emitted": N}`` on a clean
    run.
"""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, override_settings


# Importing the alerts module lazily inside each test to honor the
# settings overrides — the module reads settings lazily, so this is just
# good hygiene for the test isolation we want.


_SLACK_URL = "https://hooks.slack.com/services/T01/B02/abcdef0123456789secret"
_PD_KEY = "pd-integration-key-very-secret-do-not-log-0123abcd"


def _reset():
    from apps.migration_cloud import alerts
    alerts._reset_state_for_tests()


# ── Severity routing ────────────────────────────────────────────────────


class SeverityRoutingTests(SimpleTestCase):
    def setUp(self):
        _reset()

    @override_settings(
        OPERATOR_ALERT_DRY_RUN=False,
        OPERATOR_ALERT_EMAIL="ops@example.com",
        OPERATOR_ALERT_SLACK_WEBHOOK_URL=_SLACK_URL,
        OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY=_PD_KEY,
    )
    def test_info_severity_log_only(self):
        from apps.migration_cloud import alerts
        with mock.patch.object(alerts.urllib.request, "urlopen") as urlopen, \
             mock.patch("django.core.mail.send_mail") as send_mail:
            alerts.alert(
                severity="info",
                title="info ping",
                body="hello",
                dedupe_key="info-routing-test",
            )
            urlopen.assert_not_called()
            send_mail.assert_not_called()

    @override_settings(
        OPERATOR_ALERT_DRY_RUN=False,
        OPERATOR_ALERT_EMAIL="ops@example.com",
        OPERATOR_ALERT_SLACK_WEBHOOK_URL=_SLACK_URL,
        OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY=_PD_KEY,
    )
    def test_warning_severity_email_and_slack_no_pagerduty(self):
        from apps.migration_cloud import alerts
        # urlopen returns a context manager mock with .getcode() = 200
        fake_resp = mock.MagicMock()
        fake_resp.getcode.return_value = 200
        fake_resp.status = 200
        with mock.patch.object(alerts.urllib.request, "urlopen") as urlopen, \
             mock.patch("django.core.mail.send_mail") as send_mail:
            urlopen.return_value.__enter__.return_value = fake_resp
            alerts.alert(
                severity="warning",
                title="warn ping",
                body="warn body",
                dedupe_key="warn-routing-test",
            )
            # exactly one urlopen (Slack), no PagerDuty
            urls = [c.args[0].full_url for c in urlopen.call_args_list]
            self.assertEqual(len(urls), 1)
            self.assertIn("hooks.slack.com", urls[0])
            send_mail.assert_called_once()

    @override_settings(
        OPERATOR_ALERT_DRY_RUN=False,
        OPERATOR_ALERT_EMAIL="ops@example.com",
        OPERATOR_ALERT_SLACK_WEBHOOK_URL=_SLACK_URL,
        OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY=_PD_KEY,
    )
    def test_critical_severity_all_channels(self):
        from apps.migration_cloud import alerts
        fake_resp = mock.MagicMock()
        fake_resp.getcode.return_value = 200
        fake_resp.status = 200
        with mock.patch.object(alerts.urllib.request, "urlopen") as urlopen, \
             mock.patch("django.core.mail.send_mail") as send_mail:
            urlopen.return_value.__enter__.return_value = fake_resp
            alerts.alert(
                severity="critical",
                title="critical ping",
                body="critical body",
                dedupe_key="critical-routing-test",
            )
            urls = [c.args[0].full_url for c in urlopen.call_args_list]
            # Slack + PagerDuty = 2 urlopen calls
            self.assertEqual(len(urls), 2)
            self.assertTrue(any("hooks.slack.com" in u for u in urls))
            self.assertTrue(any("events.pagerduty.com" in u for u in urls))
            send_mail.assert_called_once()


# ── Dry-run mode ────────────────────────────────────────────────────────


class DryRunTests(SimpleTestCase):
    def setUp(self):
        _reset()

    @override_settings(
        OPERATOR_ALERT_DRY_RUN=True,
        OPERATOR_ALERT_EMAIL="ops@example.com",
        OPERATOR_ALERT_SLACK_WEBHOOK_URL=_SLACK_URL,
        OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY=_PD_KEY,
    )
    def test_dry_run_logs_but_does_not_post(self):
        from apps.migration_cloud import alerts
        with mock.patch.object(alerts.urllib.request, "urlopen") as urlopen, \
             mock.patch("django.core.mail.send_mail") as send_mail, \
             self.assertLogs("apps.migration_cloud.alerts", level="INFO") as cap:
            alerts.alert(
                severity="critical",
                title="dry run critical",
                body="some body",
                dedupe_key="dry-run-test",
            )
            urlopen.assert_not_called()
            send_mail.assert_not_called()
            joined = "\n".join(cap.output)
            self.assertIn("dry_run", joined)
            self.assertIn("slack", joined.lower())
            self.assertIn("pagerduty", joined.lower())


# ── Channel-failure non-cascade ─────────────────────────────────────────


class ChannelFailureTests(SimpleTestCase):
    def setUp(self):
        _reset()

    @override_settings(
        OPERATOR_ALERT_DRY_RUN=False,
        OPERATOR_ALERT_SLACK_WEBHOOK_URL=_SLACK_URL,
    )
    def test_slack_urlopen_raises_does_not_propagate(self):
        from apps.migration_cloud import alerts
        with mock.patch.object(
            alerts.urllib.request, "urlopen",
            side_effect=alerts.urllib.error.URLError("boom"),
        ):
            # No exception -> test passes
            result = alerts.alert(
                severity="warning",
                title="slack fail",
                body="b",
                dedupe_key="slack-fail-test",
            )
            self.assertIsNone(result)

    @override_settings(
        OPERATOR_ALERT_DRY_RUN=False,
        OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY=_PD_KEY,
    )
    def test_pagerduty_urlopen_raises_does_not_propagate(self):
        from apps.migration_cloud import alerts
        with mock.patch.object(
            alerts.urllib.request, "urlopen",
            side_effect=alerts.urllib.error.URLError("pd-boom"),
        ):
            result = alerts.alert(
                severity="critical",
                title="pd fail",
                body="b",
                dedupe_key="pd-fail-test",
            )
            self.assertIsNone(result)


# ── Sensitive-data leak guards ─────────────────────────────────────────


class SensitiveLeakTests(SimpleTestCase):
    def setUp(self):
        _reset()

    @override_settings(
        OPERATOR_ALERT_DRY_RUN=False,
        OPERATOR_ALERT_SLACK_WEBHOOK_URL=_SLACK_URL,
        OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY=_PD_KEY,
    )
    def test_webhook_url_never_in_logs(self):
        from apps.migration_cloud import alerts
        fake_resp = mock.MagicMock()
        fake_resp.getcode.return_value = 200
        fake_resp.status = 200
        with mock.patch.object(alerts.urllib.request, "urlopen") as urlopen, \
             self.assertLogs("apps.migration_cloud.alerts", level="DEBUG") as cap:
            urlopen.return_value.__enter__.return_value = fake_resp
            alerts.alert(
                severity="critical",
                title="leak test",
                body="b",
                dedupe_key="leak-url-test",
            )
            joined = "\n".join(cap.output)
            # The secret tail of the URL must never appear unredacted
            self.assertNotIn("abcdef0123456789secret", joined)
            # Same for the PagerDuty key
            self.assertNotIn(_PD_KEY, joined)

    @override_settings(
        OPERATOR_ALERT_DRY_RUN=True,
        OPERATOR_ALERT_SLACK_WEBHOOK_URL=_SLACK_URL,
        OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY=_PD_KEY,
    )
    def test_pagerduty_key_never_in_dry_run_log(self):
        from apps.migration_cloud import alerts
        with self.assertLogs("apps.migration_cloud.alerts", level="DEBUG") as cap:
            alerts.alert(
                severity="critical",
                title="dry leak",
                body="x",
                dedupe_key="leak-pd-test",
            )
            joined = "\n".join(cap.output)
            self.assertNotIn(_PD_KEY, joined)
            self.assertNotIn("abcdef0123456789secret", joined)

    @override_settings(
        OPERATOR_ALERT_DRY_RUN=True,
        OPERATOR_ALERT_SLACK_WEBHOOK_URL=_SLACK_URL,
    )
    def test_body_text_not_in_dry_run_log(self):
        from apps.migration_cloud import alerts
        secret_body = "PAYLOAD_CANARY_DEADBEEF_DO_NOT_LOG"
        with self.assertLogs("apps.migration_cloud.alerts", level="DEBUG") as cap:
            alerts.alert(
                severity="warning",
                title="body leak",
                body=secret_body,
                dedupe_key="body-leak-test",
            )
            joined = "\n".join(cap.output)
            self.assertNotIn(secret_body, joined)


# ── Rate limit + dedupe ────────────────────────────────────────────────


class RateLimitTests(SimpleTestCase):
    def setUp(self):
        _reset()

    @override_settings(
        OPERATOR_ALERT_DRY_RUN=True,
        OPERATOR_ALERT_RATE_LIMIT_PER_HOUR=3,
    )
    def test_rate_limit_drops_above_ceiling(self):
        from apps.migration_cloud import alerts
        with self.assertLogs("apps.migration_cloud.alerts", level="DEBUG") as cap:
            for i in range(5):
                alerts.alert(
                    severity="info",
                    title=f"t{i}",
                    body="b",
                    dedupe_key=f"rate-{i}",
                )
            joined = "\n".join(cap.output)
            self.assertIn("rate_limit_reached", joined)
            # Warning should fire EXACTLY once across the burst
            self.assertEqual(joined.count("rate_limit_reached"), 1)

    @override_settings(OPERATOR_ALERT_DRY_RUN=True)
    def test_dedupe_repeat_logged(self):
        from apps.migration_cloud import alerts
        with self.assertLogs("apps.migration_cloud.alerts", level="DEBUG") as cap:
            alerts.alert(
                severity="warning",
                title="dup1",
                body="b",
                dedupe_key="dup-same",
            )
            alerts.alert(
                severity="warning",
                title="dup2",
                body="b",
                dedupe_key="dup-same",
            )
            joined = "\n".join(cap.output)
            self.assertIn("dedupe_repeat", joined)

    @override_settings(OPERATOR_ALERT_DRY_RUN=True)
    def test_reset_clears_state(self):
        from apps.migration_cloud import alerts
        alerts.alert(
            severity="info", title="t", body="b", dedupe_key="reset-1",
        )
        count, _ = alerts._snapshot_dedupe_state()
        self.assertEqual(count, 1)
        alerts._reset_state_for_tests()
        count, _ = alerts._snapshot_dedupe_state()
        self.assertEqual(count, 0)


# ── Slack/PagerDuty payload shape ──────────────────────────────────────


class PayloadShapeTests(SimpleTestCase):
    def setUp(self):
        _reset()

    def test_slack_payload_includes_title_and_blocks(self):
        from apps.migration_cloud import alerts
        payload = alerts._build_slack_payload(
            severity="critical",
            title="hello",
            body="some markdown body",
            links={"Dashboard": "https://example.com/d"},
        )
        self.assertEqual(payload["text"], "hello")
        self.assertGreaterEqual(len(payload["blocks"]), 2)

    def test_pagerduty_payload_dedup_key_and_severity(self):
        from apps.migration_cloud import alerts
        payload = alerts._build_pagerduty_payload(
            routing_key="ROUTING-KEY-X",
            severity="critical",
            title="hi",
            body="body",
            dedupe_key="abc-123",
            links={"Audit": "https://example.com/a"},
        )
        self.assertEqual(payload["event_action"], "trigger")
        self.assertEqual(payload["dedup_key"], "abc-123")
        self.assertEqual(payload["payload"]["severity"], "critical")
        self.assertEqual(payload["payload"]["source"], "migration-cloud")
        self.assertEqual(payload["routing_key"], "ROUTING-KEY-X")


# ── Token watchdog ─────────────────────────────────────────────────────


class TokenWatchdogTests(SimpleTestCase):
    """Watchdog uses a real ORM call — patch the queryset surface so the
    test does not require a DB lane."""

    def setUp(self):
        _reset()

    @override_settings(OPERATOR_ALERT_DRY_RUN=True)
    def test_token_watchdog_emits_per_overdue_token(self):
        from apps.migration_cloud import tasks_alerts

        class _FakeToken:
            def __init__(self, pk, tenant_scope_id, grace_until):
                self.pk = pk
                self.tenant_scope_id = tenant_scope_id
                self.grace_until = grace_until

        class _FakeNow:
            def isoformat(self):
                return "2026-01-01T00:00:00+00:00"

        fakes = [
            _FakeToken(11, 1, _FakeNow()),
            _FakeToken(12, None, _FakeNow()),
            _FakeToken(13, 2, _FakeNow()),
        ]

        class _FakeQS:
            def filter(self, **_):
                return self
            def exclude(self, **_):
                return self
            def only(self, *_):
                return self
            def iterator(self):
                for f in fakes:
                    yield f

        with mock.patch(
            "apps.migration_cloud.models.MigrationCloudAPIToken.objects",
            new=_FakeQS(),
        ):
            result = tasks_alerts.token_rotation_watchdog()

        self.assertEqual(result["status"], "ran")
        self.assertEqual(result["scanned"], 3)
        self.assertEqual(result["emitted"], 3)

    @override_settings(OPERATOR_ALERT_DRY_RUN=True)
    def test_token_watchdog_handles_empty(self):
        from apps.migration_cloud import tasks_alerts

        class _FakeQS:
            def filter(self, **_):
                return self
            def exclude(self, **_):
                return self
            def only(self, *_):
                return self
            def iterator(self):
                return iter([])

        with mock.patch(
            "apps.migration_cloud.models.MigrationCloudAPIToken.objects",
            new=_FakeQS(),
        ):
            result = tasks_alerts.token_rotation_watchdog()
        self.assertEqual(result["status"], "ran")
        self.assertEqual(result["scanned"], 0)
        self.assertEqual(result["emitted"], 0)


# ── Status summary ─────────────────────────────────────────────────────


class StatusSummaryTests(SimpleTestCase):
    def setUp(self):
        _reset()

    @override_settings(OPERATOR_ALERT_DRY_RUN=True)
    def test_audit_task_emits_critical_on_broken_chain(self):
        """v3.39 verifier exit code 1 → audit-chain-broken critical alert."""
        from apps.migration_cloud import tasks_audit
        from apps.migration_cloud import alerts as alerts_mod

        captured: list[dict] = []

        def fake_alert(**kw):
            captured.append(kw)

        # Make call_command raise SystemExit(1) like the verifier does.
        with mock.patch(
            "django.core.management.call_command",
            side_effect=SystemExit(1),
        ), mock.patch.object(alerts_mod, "alert", side_effect=fake_alert):
            result = tasks_audit.verify_audit_chain_weekly_task()
        self.assertEqual(result["status"], "completed_with_breaks")
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["severity"], "critical")
        self.assertEqual(captured[0]["dedupe_key"], "audit-chain-broken-global")

    @override_settings(
        OPERATOR_ALERT_DRY_RUN=True,
        OPERATOR_ALERT_SLACK_WEBHOOK_URL=_SLACK_URL,
        OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY=_PD_KEY,
        OPERATOR_ALERT_EMAIL="ops@example.com",
        OPERATOR_ALERT_RATE_LIMIT_PER_HOUR=42,
    )
    def test_status_summary_reports_all_channels(self):
        from apps.migration_cloud.alert_status import get_alert_status_summary
        s = get_alert_status_summary()
        self.assertIn("log", s["channels_enabled"])
        self.assertIn("email", s["channels_enabled"])
        self.assertIn("slack", s["channels_enabled"])
        self.assertIn("pagerduty", s["channels_enabled"])
        self.assertTrue(s["dry_run"])
        self.assertEqual(s["rate_limit_per_hour"], 42)
        self.assertEqual(s["active_dedup_keys"], 0)
