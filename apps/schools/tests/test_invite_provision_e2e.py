"""Invite → accept → bind → verify kick → provision E2E (mocked migrate)."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.platform_runtime.models import WorkflowRun
from apps.schools.models import School, SignupVerification, TenantInvite
from apps.schools.signup_views import _bind_tenant_invite_if_present
from apps.schools.tasks import provision_school_sync


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    CELERY_TASK_ALWAYS_EAGER=True,
)
class InviteProvisionE2ETests(TestCase):
    def test_invite_bind_then_provision_finalizes_workflow(self):
        inv = TenantInvite.objects.create(
            email="head@invite-e2e.test",
            school_name="Invite E2E Academy",
            country_code="US",
            expires_at=timezone.now() + timedelta(days=7),
        )
        client = Client()
        resp = client.get(f"/accept-invite/?token={inv.token}", HTTP_HOST="testserver")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(client.session.get("tenant_invite_token"), str(inv.token))

        school = School.objects.create(
            name="Invite E2E Academy",
            slug="invite-e2e-academy",
            subdomain="invite-e2e-academy",
            is_active=False,
            country_code="US",
            settings={},
        )
        rf = RequestFactory()
        req = rf.post("/signup/")
        req.session = SessionStore()
        req.session["tenant_invite_token"] = str(inv.token)
        _bind_tenant_invite_if_present(req, school)
        inv.refresh_from_db()
        self.assertEqual(inv.status, "accepted")
        self.assertEqual(inv.school_id, school.id)

        User = get_user_model()
        owner = User.objects.create_user(
            username="head@invite-e2e.test",
            email="head@invite-e2e.test",
            password="InvitePass123!",
            role=User.Role.ADMIN,
        )
        SignupVerification.objects.create(
            school=school,
            email=owner.email,
            expires_at=timezone.now() + timedelta(days=2),
            verified_at=timezone.now(),
        )

        with mock.patch(
            "apps.schools.tasks._do_provision_tracked",
            side_effect=lambda sch, sid, **kw: School.objects.filter(pk=sch.pk).update(
                is_active=True,
                settings={
                    **(sch.settings or {}),
                    "provisioning": {
                        "phase_a_complete": True,
                        "phase_b_complete": True,
                    },
                },
            ),
        ):
            provision_school_sync(str(school.id), contact_email=owner.email)

        school.refresh_from_db()
        self.assertTrue(school.is_active)
        run = WorkflowRun.objects.filter(
            workflow_key="tenant_school_provision",
            school_id=str(school.pk),
        ).first()
        self.assertIsNotNone(run)
        self.assertEqual((run.status or "").lower(), "succeeded")
