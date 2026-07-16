"""The watchdog must not blind itself, and a resume must be able to fix an owner.

Found by an A-Z provisioning audit (2026-07-16).

P1 — the sweep filtered ``status__in=("running","stuck","failed")``, but
``_cancel_dead_run`` (the watchdog's OWN cleanup) writes ``"cancelled"`` onto a
heartbeat-dead zombie before kicking a fresh drive. If that fresh drive also
dies before writing its run row — a deploy landing mid-resume, an OOM kill — the
school's only run is left ``cancelled`` and the sweep can never see the school
again. The watchdog's cleanup made the tenant permanently unscannable: exactly
the failure it exists to prevent.

P2 — ``ensure_admin_user_for_school`` returns ``(None, False)`` on an empty
email, so the tenant-admin step silently skips. Every resume path then sourced
its email from ``_primary_owner_user`` — a SchoolMembership lookup — and the only
thing that writes that membership is the step that just skipped. No membership ->
no email -> skip -> still no membership. A FIXED POINT: the re-drive could never
repair the one thing it was re-driven to repair.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.platform_runtime.models import WorkflowRun
from apps.schools.models import School, SignupVerification


def _dead_run(school, status: str) -> WorkflowRun:
    run = WorkflowRun.objects.create(
        workflow_key="tenant_school_provision",
        school_id=str(school.pk),
        status=status,
        total_steps=5,
        current_step_ordinal=3,
        current_step_name="tenant_schema",
        expected_duration_seconds=600,
    )
    # Heartbeat frozen well past the staleness window -- the runner is dead.
    WorkflowRun.objects.filter(pk=run.pk).update(
        last_heartbeat_at=timezone.now() - timedelta(hours=2)
    )
    run.refresh_from_db()
    return run


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class CancelledRunStaysScannableTests(TestCase):
    """P1 — the watchdog's own cleanup must not hide the school from itself."""

    def setUp(self):
        self.school = School.objects.create(
            name="Cancelled Zombie Academy",
            slug="cancelled-zombie",
            subdomain="cancelled-zombie",
            is_active=False,
        )

    def test_sweep_sees_a_school_whose_only_run_is_cancelled(self):
        from apps.schools.provision_watchdog import _dead_running_school_ids

        _dead_run(self.school, "cancelled")
        self.assertIn(
            str(self.school.pk),
            _dead_running_school_ids(10),
            "a school whose only run was CANCELLED by the watchdog itself must "
            "stay scannable -- otherwise the cleanup permanently blinds the sweep",
        )

    def test_cancelled_run_school_is_actually_resumed(self):
        from apps.schools.provision_watchdog import resume_stuck_provisions

        _dead_run(self.school, "cancelled")
        with patch(
            "apps.schools.tasks.kick_complete_provisioning_background"
        ) as kick:
            result = resume_stuck_provisions(limit=5, reason="test")
        self.assertEqual(result.get("resumed"), 1)
        kick.assert_called_once()

    def test_the_pre_existing_statuses_still_scan(self):
        """The fix must widen the net, not move it."""
        from apps.schools.provision_watchdog import _dead_running_school_ids

        for status in ("running", "stuck", "failed"):
            school = School.objects.create(
                name=f"Zombie {status}",
                slug=f"zombie-{status}",
                subdomain=f"zombie-{status}",
                is_active=False,
            )
            _dead_run(school, status)
            self.assertIn(str(school.pk), _dead_running_school_ids(20), status)


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class OwnerEmailIsRecoverableTests(TestCase):
    """P2 — the missing-owner fixed point."""

    def setUp(self):
        self.school = School.objects.create(
            name="Ownerless Academy",
            slug="ownerless",
            subdomain="ownerless",
            is_active=False,
        )

    def test_signup_verification_email_is_recovered(self):
        from apps.schools.tasks import resolve_provisioning_contact_email

        SignupVerification.objects.create(
            school=self.school,
            email="founder@ownerless.test",
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertEqual(
            resolve_provisioning_contact_email(self.school),
            "founder@ownerless.test",
            "with no owner membership, the signup record is the only durable "
            "trace of the owner's address -- and it predates provisioning",
        )

    def test_onboarding_blob_email_is_recovered(self):
        from apps.schools.tasks import resolve_provisioning_contact_email

        self.school.settings = {
            "rmc_public_onboarding": {"contact_email": "blob@ownerless.test"}
        }
        self.school.save(update_fields=["settings"])
        self.assertEqual(
            resolve_provisioning_contact_email(self.school), "blob@ownerless.test"
        )

    def test_explicit_email_wins(self):
        from apps.schools.tasks import resolve_provisioning_contact_email

        SignupVerification.objects.create(
            school=self.school,
            email="stale@ownerless.test",
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertEqual(
            resolve_provisioning_contact_email(self.school, "explicit@ownerless.test"),
            "explicit@ownerless.test",
        )

    def test_unknown_owner_still_returns_empty(self):
        from apps.schools.tasks import resolve_provisioning_contact_email

        self.assertEqual(
            resolve_provisioning_contact_email(self.school),
            "",
            "the resolver must not invent an address",
        )

    def test_resume_creates_the_owner_a_first_drive_skipped(self):
        """The fixed point, end to end."""
        from apps.accounts.models import User
        from apps.schools.tasks import provision_school_sync

        # First drive: no email anywhere -> admin_user step skips.
        provision_school_sync(str(self.school.id))
        self.assertFalse(
            User.objects.filter(school_memberships__school=self.school).exists()
        )

        # The owner's address was on the signup record the whole time.
        SignupVerification.objects.create(
            school=self.school,
            email="founder@ownerless.test",
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.school.refresh_from_db()
        settings_blob = dict(self.school.settings or {})
        prov = dict(settings_blob.get("provisioning") or {})
        prov["phase_b_complete"] = False
        settings_blob["provisioning"] = prov
        self.school.settings = settings_blob
        self.school.save(update_fields=["settings"])

        provision_school_sync(str(self.school.id))

        self.assertTrue(
            User.objects.filter(
                email="founder@ownerless.test",
                school_memberships__school=self.school,
            ).exists(),
            "the resume must be able to create the owner account the first drive "
            "skipped -- sourcing the email from the membership that step would "
            "have written is a fixed point on the broken state",
        )
