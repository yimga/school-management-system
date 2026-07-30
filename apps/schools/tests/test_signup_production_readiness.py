"""Signup production readiness — portal email, subdomain, tenant login isolation."""

from __future__ import annotations

from unittest import mock

from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.schools.middleware import _enforce_tenant_host_membership
from apps.schools.models import School, SchoolMembership, SignupVerification
from apps.schools.signup_completion_notifications import (
    build_signup_completed_payload,
    notify_tenant_signup_completed,
)
from apps.schools.tasks import provision_school_sync


@override_settings(
    ALLOWED_HOSTS=["*", "runmycampus.com", "st-jude.runmycampus.com", "testserver"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    RMC_PUBLIC_SITE_URL="https://runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    CELERY_TASK_ALWAYS_EAGER=True,
)
class SignupProductionReadinessTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Saint Jude the Great",
            slug="st-jude",
            subdomain="st-jude",
            is_active=False,
        )
        self.owner = User.objects.create_user(
            username="owner@stjude.test",
            email="owner@stjude.test",
            password="OwnerPass123!",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.owner,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        SignupVerification.objects.create(
            school=self.school,
            email=self.owner.email,
            expires_at=timezone.now() + timezone.timedelta(days=2),
            verified_at=timezone.now(),
        )

    @mock.patch(
        "apps.schools.signup_completion_notifications.publish_event",
        create=True,
    )
    def test_provision_activates_and_builds_tenant_portal_payload(self, publish_event):
        publish_event.return_value = object()
        with mock.patch(
            "apps.platform_runtime.event_bus.publish_event",
            publish_event,
        ):
            # complete_provisioning_for_school is enqueue-only (HTTP path) and
            # returns is_active=False for a fresh school — the durable outbox
            # finishes later. This test needs the school actually provisioned on
            # return, so it uses the synchronous entry point the docstring names.
            result = provision_school_sync(
                str(self.school.pk), contact_email=self.owner.email
            )
        self.school.refresh_from_db(fields=["is_active", "settings"])
        self.assertTrue((result or {}).get("is_active") or self.school.is_active)
        # Password alone is not "claimed" — stamp the token-gated onboarding step
        # the real signup path writes after the owner sets their credential.
        settings = dict(self.school.settings or {})
        settings["owner_onboarding"] = {"step": "school", "completed": False}
        self.school.settings = settings
        self.school.save(update_fields=["settings"])
        payload = build_signup_completed_payload(
            self.school, self.owner.email, admin_user=self.owner
        )
        self.assertTrue(payload["account_ready"])
        self.assertIn("st-jude.runmycampus.com", payload["tenant_portal_url"])
        self.assertIn("st-jude.runmycampus.com", payload["portal_url"])
        self.assertEqual(payload["activation_url"], "")

    def test_active_subdomain_resolves_not_school_not_found(self):
        self.school.is_active = True
        self.school.save(update_fields=["is_active"])
        client = Client(HTTP_HOST="st-jude.runmycampus.com")
        response = client.get("/authentication/login/", follow=False)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("/school-not-found/", response.get("Location", ""))

    @mock.patch("django.contrib.messages.warning")
    def test_cross_tenant_user_blocked_on_subdomain(self, warning_mock):
        self.school.is_active = True
        self.school.save(update_fields=["is_active"])
        outsider = User.objects.create_user(
            username="outsider@test.local",
            email="outsider@test.local",
            password="Outsider123!",
            role=User.Role.TEACHER,
        )
        other = School.objects.create(
            name="Other School",
            slug="other-school",
            subdomain="other-school",
            is_active=True,
        )
        SchoolMembership.objects.create(
            user=outsider, school=other, role=User.Role.TEACHER, is_primary=True
        )
        factory = RequestFactory()
        request = factory.get(
            "/authentication/backend/", HTTP_HOST="st-jude.runmycampus.com"
        )
        request.user = outsider
        request.session = {}
        request.school = self.school
        response = _enforce_tenant_host_membership(request, self.school)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 302)
        self.assertIn("runmycampus.com", response["Location"])
        warning_mock.assert_called_once()

    @mock.patch("apps.platform_runtime.event_bus.publish_event")
    def test_notify_idempotent_after_completion(self, publish_event):
        publish_event.return_value = object()
        self.school.is_active = True
        self.school.settings = {
            **(self.school.settings or {}),
            "provisioning": {"phase_b_complete": True},
        }
        self.school.save(update_fields=["is_active", "settings"])
        self.assertTrue(
            notify_tenant_signup_completed(
                self.school, self.owner.email, admin_user=self.owner
            )
        )
        publish_event.reset_mock()
        self.assertTrue(
            notify_tenant_signup_completed(
                self.school, self.owner.email, admin_user=self.owner
            )
        )
        publish_event.assert_not_called()

    @mock.patch("apps.platform_runtime.event_bus.publish_event")
    def test_notify_deferred_until_phase_b_complete(self, publish_event):
        """PGL-007: Phase A alone must not send portal-ready / welcome email."""
        publish_event.return_value = object()
        self.school.is_active = True
        self.school.settings = {
            **(self.school.settings or {}),
            "provisioning": {"phase_a_complete": True, "phase_b_complete": False},
        }
        self.school.save(update_fields=["is_active", "settings"])
        self.assertFalse(
            notify_tenant_signup_completed(
                self.school, self.owner.email, admin_user=self.owner
            )
        )
        publish_event.assert_not_called()
        self.school.settings["provisioning"]["phase_b_complete"] = True
        self.school.save(update_fields=["settings"])
        self.assertTrue(
            notify_tenant_signup_completed(
                self.school, self.owner.email, admin_user=self.owner
            )
        )
        publish_event.assert_called_once()

    def test_owner_can_access_own_tenant_subdomain(self):
        self.school.is_active = True
        self.school.save(update_fields=["is_active"])
        factory = RequestFactory()
        request = factory.get(
            "/authentication/backend/", HTTP_HOST="st-jude.runmycampus.com"
        )
        request.user = self.owner
        request.session = {}
        request.school = self.school
        self.assertIsNone(_enforce_tenant_host_membership(request, self.school))

    def test_inactive_subdomain_renders_setup_page(self):
        client = Client(HTTP_HOST="st-jude.runmycampus.com")
        response = client.get("/", follow=False)
        self.assertEqual(response.status_code, 202)
        self.assertIn(b"Setting up", response.content)

    def test_public_redirect_hands_off_to_tenant_workspace_when_pending(self):
        self.school.is_active = False
        self.school.save(update_fields=["is_active"])
        client = Client(HTTP_HOST="runmycampus.com")
        client.login(username="owner@stjude.test", password="OwnerPass123!")
        response = client.get("/authentication/redirect/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("st-jude.runmycampus.com", response["Location"])
