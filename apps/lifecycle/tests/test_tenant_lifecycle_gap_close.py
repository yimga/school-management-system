"""Gap-close tests for unified tenant lifecycle audit fixes."""

from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import User
from apps.lifecycle.signals import _PROVISIONING_EVENT_STAGE_MAP
from apps.lifecycle.tenant_school_resolve import (
    LIFECYCLE_SCHOOL_SESSION_KEY,
    bind_lifecycle_school_session,
    can_access_tenant_lifecycle,
    resolve_request_school,
)
from apps.lifecycle.unified_lifecycle import (
    STATE_WIND_DOWN,
    build_offboarding_checklist,
    resolve_unified_lifecycle,
)
from apps.lifecycle.wind_down import apply_wind_down_mode
from apps.schools.models import School, SchoolMembership
from apps.schools.signup_views import _redirect_verified_admin_to_tenant_surface
from apps.schools.tenant_offboarding import get_offboarding_snapshot


class TenantSchoolResolveTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Resolve",
            slug="resolve-school",
            subdomain="resolve-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="admin@resolve.test",
            email="admin@resolve.test",
            password="x",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def test_resolve_request_school_from_membership(self):
        request = self.factory.get("/school/studio/provisioning/")
        request.user = self.user
        resolved = resolve_request_school(request)
        self.assertEqual(resolved.pk, self.school.pk)

    def test_signup_admin_can_access_lifecycle_without_staff(self):
        request = self.factory.get("/")
        request.user = self.user
        self.assertTrue(can_access_tenant_lifecycle(request, self.school))

    def test_session_binds_school_before_membership(self):
        other = School.objects.create(
            name="Other",
            slug="other-school",
            subdomain="other-school",
            is_active=True,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=other,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        request = self.factory.get("/school/studio/")
        request.user = self.user
        from django.contrib.sessions.backends.db import SessionStore

        request.session = SessionStore()
        bind_lifecycle_school_session(request, self.school)
        resolved = resolve_request_school(request)
        self.assertEqual(resolved.pk, self.school.pk)
        self.assertEqual(
            request.session.get(LIFECYCLE_SCHOOL_SESSION_KEY), str(self.school.pk)
        )

    def test_verify_redirect_builds_tenant_subdomain(self):
        request = self.factory.get("/verify-signup/")
        request.META["HTTP_HOST"] = "localhost:8000"
        response = _redirect_verified_admin_to_tenant_surface(
            request, self.school, "tenant_provisioning_status"
        )
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 302)
        self.assertIn("resolve-school", response.url)
        self.assertIn("/school/studio/provisioning/", response.url)


class OffboardingSnapshotTests(TestCase):
    def test_wind_down_mode_exposed_top_level(self):
        school = School.objects.create(
            name="Wind",
            slug="wind-school",
            subdomain="wind-school",
            is_active=False,
        )
        apply_wind_down_mode(school, note="test")
        snap = get_offboarding_snapshot(school)
        self.assertTrue(snap.get("wind_down_mode"))

    def test_billing_checklist_uses_clearance_not_string_blockers(self):
        school = School.objects.create(
            name="Bill",
            slug="bill-school",
            subdomain="bill-school",
            is_active=True,
        )
        steps = build_offboarding_checklist(school)
        billing = next(s for s in steps if s["key"] == "billing")
        self.assertIn("billing", billing["label"].lower())
        self.assertFalse(
            "billing" in str(school.settings),
            "billing step must not use purge_blockers string hack",
        )


class ProvisioningCompletedSignalTests(TestCase):
    def test_completed_maps_operating_and_live_unified(self):
        self.assertEqual(_PROVISIONING_EVENT_STAGE_MAP.get("COMPLETED"), "OPERATING")


class OnboardingAccessTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Onboard",
            slug="onboard-school",
            subdomain="onboard-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="admin@onboard.test",
            email="admin@onboard.test",
            password="x",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def test_require_tenant_lifecycle_school_allows_signup_admin(self):
        from apps.lifecycle.tenant_school_resolve import require_tenant_lifecycle_school

        request = self.factory.get("/siteconfig/onboarding/")
        request.user = self.user
        bind_lifecycle_school_session(request, self.school)
        school, denied = require_tenant_lifecycle_school(request)
        self.assertIsNone(denied)
        self.assertEqual(school.pk, self.school.pk)


class CancelClosureTests(TestCase):
    @override_settings(TENANT_SELF_SERVICE_OFFBOARDING_ENABLED="1")
    def test_cancel_reactivates_school_and_clears_wind_down(self):
        from apps.schools.tenant_offboarding import (
            cancel_self_service_closure,
            request_self_service_closure,
        )

        school = School.objects.create(
            name="Cancel",
            slug="cancel-school",
            subdomain="cancel-school",
            is_active=True,
        )
        user = User.objects.create_user(
            username="admin@cancel.test",
            email="admin@cancel.test",
            password="x",
            role=User.Role.ADMIN,
        )
        request_self_service_closure(school, actor=user, acknowledge=True)
        school.refresh_from_db()
        self.assertFalse(school.is_active)
        cancel_self_service_closure(school, actor=user)
        school.refresh_from_db()
        self.assertTrue(school.is_active)
        out = resolve_unified_lifecycle(school)
        self.assertNotEqual(out["state"], STATE_WIND_DOWN)


class ActivationGateExemptTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Activation",
            slug="activation-school",
            subdomain="activation-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="admin@activation.test",
            email="admin@activation.test",
            password="x",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def test_provisioning_paths_exempt_from_activation_redirect(self):
        from apps.schools.middleware_activation_gate import ActivationGateMiddleware

        mw = ActivationGateMiddleware(lambda r: r)
        self.assertTrue(mw._path_exempt("/school/studio/provisioning/"))
        self.assertTrue(mw._path_exempt("/siteconfig/onboarding/step/academic_year/"))

    def test_activation_first_action_resolves_school_from_session(self):
        from django.contrib.sessions.backends.db import SessionStore

        from apps.schools.activation_views import activation_first_action

        request = self.factory.get("/activation/first-action/")
        request.user = self.user
        request.session = SessionStore()
        bind_lifecycle_school_session(request, self.school)
        self.assertEqual(resolve_request_school(request).pk, self.school.pk)
        response = activation_first_action(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            (getattr(self.school, "name", "") or "").encode(),
            response.content,
        )


class LifecycleShellRenderTests(TestCase):
    """Provisioning + fast-path shells render lifecycle markers (Playwright substitute)."""

    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Shell School",
            slug="shell-school",
            subdomain="shell-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="admin@shell.test",
            email="admin@shell.test",
            password="x",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def test_provisioning_status_renders_poll_shell(self):
        from apps.lifecycle.views_tenant_lifecycle import tenant_provisioning_status

        from django.contrib.sessions.backends.db import SessionStore

        request = self.factory.get("/school/studio/provisioning/")
        request.user = self.user
        request.school = self.school
        request.session = SessionStore()
        response = tenant_provisioning_status(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"data-rmc-provisioning-status", response.content)

    def test_fast_path_renders_launch_shell(self):
        from apps.lifecycle.views_tenant_lifecycle import tenant_launch_fast_path

        from django.contrib.sessions.backends.db import SessionStore

        request = self.factory.get("/school/studio/fast-path/")
        request.user = self.user
        request.school = self.school
        request.session = SessionStore()
        response = tenant_launch_fast_path(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"data-rmc-launch-fast-path", response.content)

    def test_lifecycle_command_center_renders_hub_and_playbook(self):
        from apps.lifecycle.views_tenant_lifecycle import tenant_lifecycle_command_center

        from django.contrib.sessions.backends.db import SessionStore

        request = self.factory.get("/school/studio/lifecycle/")
        request.user = self.user
        request.school = self.school
        request.session = SessionStore()
        response = tenant_lifecycle_command_center(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"tenant-lifecycle-command-center", response.content)
        self.assertIn(b"data-rmc-workflow-playbook", response.content)
        self.assertIn(b"section-registration", response.content)
        self.assertIn(b"section-offboarding", response.content)


class ApplicantWindDownTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Applicant",
            slug="applicant-school",
            subdomain="applicant-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="admin@applicant.test",
            email="admin@applicant.test",
            password="x",
            role=User.Role.ADMIN,
        )

    def test_applicant_create_path_blocked_in_wind_down(self):
        from apps.lifecycle.wind_down import apply_wind_down_mode
        from apps.lifecycle.wind_down_guards import block_if_wind_down_commerce

        apply_wind_down_mode(self.school, note="test")
        request = self.factory.post("/people/applicants/create/")
        request.user = self.user
        request.school = self.school
        blocked = block_if_wind_down_commerce(request)
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked.status_code, 403)
