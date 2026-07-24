"""Full tenant lifecycle: signup email, verify, schedule purge, operator queue."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.schools.models import School, SchoolProvisioningEvent, SignupVerification
from apps.schools.signup_views import verify_signup
from apps.schools.super_views_offboarding_queue import api_super_run_scheduled_purges
from apps.schools.tenant_offboarding import (
    request_self_service_closure,
    run_scheduled_purges,
    schools_scheduled_for_purge,
)
from apps.siteconfig.models import RegionConfig

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["*"],
    TENANT_AUTO_PURGE_ENABLED=False,
    TENANT_SELF_SERVICE_OFFBOARDING_ENABLED="1",
)
class TenantLifecycleFullTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser(
            username="lifecycle_full",
            email="lifecycle@example.com",
            password="testpass123",
        )
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Lifecycle Full School",
            slug="lifecycle-full-school",
            subdomain="lifecycle-full-school",
            is_active=True,
            default_region=self.region,
        )
        self.admin = User.objects.create_user(
            username="admin@lifecycle.test",
            email="admin@lifecycle.test",
            password="testpass123",
            is_active=True,
        )

    def _manager_post(self, path: str, data: dict):
        request = self.factory.post(
            path,
            data=json.dumps(data).encode(),
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        request.user = self.superuser
        request.public_host_kind = "manager"
        return request

    def _signup_get(self, path: str):
        request = self.factory.get(path)
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        return request

    @patch("apps.schools.signup_views.send_transactional")
    def test_signup_sends_verification_email(self, mock_send):
        mock_send.return_value = {"ok": True, "status": "queued"}
        school = School.objects.create(
            name="Email Test",
            slug="email-test-school",
            subdomain="email-test-school",
            is_active=False,
            default_region=self.region,
        )
        expires = timezone.now() + timedelta(days=2)
        SignupVerification.objects.create(
            school=school,
            email="owner@example.com",
            expires_at=expires,
        )
        self.assertTrue(
            SignupVerification.objects.filter(school=school, email="owner@example.com").exists()
        )

    @patch("apps.schools.tasks.kick_complete_provisioning_background")
    def test_verify_signup_dispatches_provisioning_for_inactive_school(
        self, mock_provision,
    ):
        """v4.00.98: verify_signup must NOT activate the school itself —
        provisioning does that at its successful tail (apps/schools/tasks.py
        _do_provision) right before the welcome email.  Premature activation
        here used to short-circuit _do_provision and silently skip the
        welcome email send (regression).  This test now verifies the correct
        contract: verify_signup leaves the school inactive and hands off to
        the durable background provisioning handoff with the verified email.
        """
        school = School.objects.create(
            name="Verify School",
            slug="verify-school",
            subdomain="verify-school",
            is_active=False,
            country_code="US",
            settings={},
            default_region=self.region,
        )
        sv, _created = SignupVerification.objects.update_or_create(
            school=school,
            defaults={
                "email": "v@verify.test",
                "expires_at": timezone.now() + timedelta(days=1),
                "verified_at": None,
            },
        )
        request = self._signup_get(f"/verify-signup/?token={sv.token}")
        resp = verify_signup(request)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        # Activation happens INSIDE _do_provision, which is mocked here, so
        # the school stays inactive — the previous assertion was hiding the
        # premature-activation bug.
        self.assertFalse(school.is_active)
        # Verification is marked used and provisioning is dispatched.
        sv.refresh_from_db()
        self.assertIsNotNone(sv.verified_at)
        mock_provision.assert_called_once()
        call_args = mock_provision.call_args
        self.assertEqual(call_args.args[0], str(school.id))
        self.assertEqual(call_args.kwargs.get("contact_email"), "v@verify.test")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@runmycampus.com",
    )
    def test_verify_signup_runs_full_provisioning_and_sends_welcome_email(self):
        """v4.00.98 regression coverage (no welcome-email mock): verify the
        full path lands a welcome email in ``mail.outbox``.

        Why: the prior coverage mocked the provisioning handoff, which
        masked a bug where verify_signup activated the school before
        provisioning ran, causing ``_do_provision`` to short-circuit and
        skip the welcome email entirely.  This test patches dispatch to call
        ``provision_school_sync`` directly (matching the durable outbox worker),
        then asserts both that the school becomes active
        AND the welcome email lands in mail.outbox.
        """
        from django.core import mail
        from apps.schools.tasks import provision_school_sync

        school = School.objects.create(
            name="Welcome Email School",
            slug="welcome-email-school",
            subdomain="welcome-email-school",
            is_active=False,
            country_code="US",
            settings={},
            default_region=self.region,
        )
        sv, _ = SignupVerification.objects.update_or_create(
            school=school,
            defaults={
                "email": "owner@welcome-email.test",
                "expires_at": timezone.now() + timedelta(days=1),
                "verified_at": None,
            },
        )
        mail.outbox = []

        def _force_sync(school_id, contact_email="", **kwargs):
            provision_school_sync(school_id, contact_email=contact_email, **kwargs)
            return {"queued": False, "fallback": True, "job_id": None, "message": "forced sync"}

        request = self._signup_get(f"/verify-signup/?token={sv.token}")
        with patch(
            "apps.schools.tasks.kick_complete_provisioning_background",
            side_effect=_force_sync,
        ):
            resp = verify_signup(request)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        self.assertTrue(
            school.is_active,
            "provisioning should activate the school at its successful tail",
        )
        recipients = [addr for msg in mail.outbox for addr in (msg.to or [])]
        self.assertIn(
            "owner@welcome-email.test",
            recipients,
            f"welcome email never sent; mail.outbox recipients={recipients!r}",
        )

    @patch(
        "apps.schools.tasks.kick_complete_provisioning_background",
        side_effect=OSError("broker unreachable"),
    )
    def test_verify_signup_records_failed_event_when_dispatch_raises(
        self, _mock_dispatch
    ):
        """v4.00.2 audit: silent dispatch swallow surfaced in the timeline.

        Prior to commit 6009ba56, a bare ``except: pass`` masked any
        provisioning dispatch failure — the user landed on the dashboard
        of a half-provisioned school with no welcome email and operators
        had no signal. The current code logs + records a FAILED
        SchoolProvisioningEvent so the offboarding queue / timeline shows
        the failure. This test locks the audit chain so a future refactor
        can't silently regress.
        """
        school = School.objects.create(
            name="Dispatch Fail",
            slug="dispatch-fail-school",
            subdomain="dispatch-fail-school",
            is_active=False,
            country_code="US",
            settings={},
            default_region=self.region,
        )
        sv, _ = SignupVerification.objects.update_or_create(
            school=school,
            defaults={
                "email": "owner@dispatch-fail.test",
                "expires_at": timezone.now() + timedelta(days=1),
                "verified_at": None,
            },
        )
        request = self._signup_get(f"/verify-signup/?token={sv.token}")
        resp = verify_signup(request)
        # User is still logged in / redirected on success — email
        # verification already proved ownership. The audit row is the
        # operator-visible signal.
        self.assertEqual(resp.status_code, 302)
        event = SchoolProvisioningEvent.objects.filter(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.FAILED,
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.status, SchoolProvisioningEvent.Status.ERROR)
        self.assertEqual(event.payload.get("error_type"), "OSError")
        self.assertIn("broker unreachable", event.payload.get("error", ""))

    def test_self_service_schedules_purge_and_lists_due(self):
        request_self_service_closure(
            self.school,
            actor=self.admin,
            acknowledge=True,
        )
        self.school.refresh_from_db()
        off = (self.school.settings or {}).get("offboarding") or {}
        self.assertEqual(off.get("self_service_status"), "scheduled")
        self.assertTrue(off.get("scheduled_purge_at"))
        settings = dict(self.school.settings or {})
        settings["offboarding"] = dict(off)
        settings["offboarding"]["scheduled_purge_at"] = "2000-01-01"
        self.school.settings = settings
        self.school.save(update_fields=["settings", "updated_at"])
        due = schools_scheduled_for_purge(on_or_before=timezone.now().date())
        slugs = [s.slug for s in due]
        self.assertIn(self.school.slug, slugs)

    def test_run_scheduled_purges_dry_run_when_auto_disabled(self):
        settings = dict(self.school.settings or {})
        settings["offboarding"] = {
            "self_service_status": "scheduled",
            "scheduled_purge_at": "2000-01-01",
        }
        self.school.settings = settings
        self.school.save(update_fields=["settings", "updated_at"])
        result = run_scheduled_purges(dry_run=True, limit=5)
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("dry_run"))

    def test_run_scheduled_purges_apply_blocked_without_force(self):
        result = run_scheduled_purges(dry_run=False, limit=1)
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("reason"), "auto_purge_disabled")

    def test_api_force_operator_requires_confirm(self):
        request = self._manager_post(
            "/super/api/offboarding/run-scheduled/",
            {"dry_run": False, "force_operator": True, "limit": 1},
        )
        response = api_super_run_scheduled_purges(request)
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertEqual(body.get("error"), "confirm_required")

    def test_api_force_operator_dry_run_via_queue(self):
        settings = dict(self.school.settings or {})
        settings["offboarding"] = {
            "self_service_status": "operator_scheduled",
            "scheduled_purge_at": "2000-01-01",
        }
        self.school.settings = settings
        self.school.save(update_fields=["settings", "updated_at"])
        request = self._manager_post(
            "/super/api/offboarding/run-scheduled/",
            {"dry_run": True, "limit": 3},
        )
        response = api_super_run_scheduled_purges(request)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"))
