"""Terminal 'needs attention' state ends the ~forever provisioning retry loop.

A deterministically-broken provision used to be auto-resumed ~12x/hour forever,
and the owner never saw an honest failure. The watchdog now tracks forward
progress; after N consecutive no-progress resumes it declares the school
terminally ``needs_attention``, STOPS auto-resuming, alerts, and surfaces the
state honestly. A human retry (or genuine forward progress) clears it.
"""

from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.schools import provision_watchdog as pw
from apps.schools.models import School, SchoolProvisioningEvent
from apps.schools.provisioning_progress import resolve_provisioning_progress


@override_settings(PROVISION_MAX_NO_PROGRESS_RESUMES=3)
class ProvisionTerminalStateTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Term", slug="term-a", subdomain="term-a", is_active=False
        )

    def _resume(self, reason="poll"):
        # Each resume takes a single-flight lock (timeout=stale); clear it so the
        # test can drive consecutive resumes deterministically. The no-progress
        # STREAK lives durably in School.settings, so clearing the cache does not
        # reset it — exactly what lets the terminal state accrue.
        cache.clear()
        result = pw.resume_provision_if_stuck(self.school, reason=reason)
        self.school.refresh_from_db()
        return result

    def test_repeated_no_progress_resumes_go_terminal_and_stop(self):
        with patch(
            "apps.schools.tasks.kick_complete_provisioning_background"
        ) as kick:
            # No milestone events + RLS mode => signature never advances => every
            # resume is "no progress".
            actions = [self._resume()["action"] for _ in range(6)]
        self.assertIn(
            "needs_attention",
            actions,
            f"terminal state must be reached; got {actions}",
        )
        self.assertTrue(pw.provision_needs_attention(self.school))
        # Once terminal, further AUTO resumes are a no-op (no more kicks).
        kick.reset_mock()
        with patch("apps.schools.tasks.kick_complete_provisioning_background") as kick2:
            self.assertEqual(self._resume()["action"], "needs_attention")
            kick2.assert_not_called()

    def test_manual_retry_clears_terminal_and_drives(self):
        with patch("apps.schools.tasks.kick_complete_provisioning_background"):
            for _ in range(6):
                self._resume()
        self.assertTrue(pw.provision_needs_attention(self.school))
        with patch("apps.schools.tasks.kick_complete_provisioning_background") as kick:
            result = self._resume(reason="manual")
        self.assertEqual(result["action"], "resumed")
        kick.assert_called_once()
        self.assertFalse(pw.provision_needs_attention(self.school))

    def test_forward_progress_resets_streak(self):
        with patch("apps.schools.tasks.kick_complete_provisioning_background"):
            self._resume()
            self._resume()  # streak now 1
            # Genuine forward progress: a further milestone event appears.
            SchoolProvisioningEvent.objects.create(
                school=self.school,
                event_type="TENANT_SCHEMA_READY",
                status="SUCCESS",
                message="",
            )
            result = self._resume()  # should detect progress -> reset, NOT terminal
        self.assertEqual(result["action"], "resumed")
        self.school.refresh_from_db()
        self.assertEqual(
            int((self.school.settings.get("provisioning") or {}).get("no_progress_streak") or 0),
            0,
        )
        self.assertFalse(pw.provision_needs_attention(self.school))

    def test_progress_payload_surfaces_needs_attention_and_stuck(self):
        pw._write_provisioning_settings(self.school, needs_attention=True)
        self.school.refresh_from_db()
        payload = resolve_provisioning_progress(self.school)
        self.assertTrue(payload["needs_attention"])
        self.assertTrue(payload["stuck"], "needs_attention must drive the retry UI (stuck)")
        self.assertEqual(payload["current_phase"], "needs_attention")
