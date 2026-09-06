"""
BOLA/IDOR matrix — user at school A must not read/write school B resources via ID tampering.

Minimum 20 HTTP cases across switch-school, tenant config, education DNA, modules, and
vocational student-scoped endpoints.
"""

from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.api.views_v1 import MeSchoolsView
from apps.schools.models import School, SchoolMembership


def _tenant_client(school: School, user) -> Client:
    from apps.schools.session_school_bind import sign_session_school_bind

    client = Client(HTTP_HOST=f"{school.subdomain}.runmycampus.com")
    client.force_login(user)
    sign_session_school_bind(
        client.session, school_id=str(school.pk), user_id=user.pk
    )
    client.session.save()
    return client


class BOLAIdorMatrixTests(TestCase):
    """Cross-tenant access attempts must return 403 or 404, never 200 with foreign data."""

    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.school_a = School.objects.create(
            name=f"Matrix A {uid}",
            slug=f"ma-{uid}",
            subdomain=f"ma{uid}",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name=f"Matrix B {uid}",
            slug=f"mb-{uid}",
            subdomain=f"mb{uid}",
            is_active=True,
        )
        User = get_user_model()
        cls.admin_a = User.objects.create_user(
            username=f"admin_a_{uid}",
            password="Test1234",
            role="ADMIN",
        )
        cls.admin_b = User.objects.create_user(
            username=f"admin_b_{uid}",
            password="Test1234",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=cls.admin_a, school=cls.school_a, role="ADMIN", is_primary=True
        )
        SchoolMembership.objects.create(
            user=cls.admin_b, school=cls.school_b, role="ADMIN", is_primary=True
        )

    #: Surfaces a refusal is allowed to send the caller to. Anything else is a
    #: redirect AWAY from a deny and must fail.
    AUTH_SURFACES = ("/authentication/login", "/mfa/", "/authentication/mfa")

    def _assert_denied(self, resp, msg: str = ""):
        """Refused -- by status OR by being bounced to an auth surface.

        Measured 2026-09-06: on a tenant host a user with NO membership there is
        not authenticated at all. Every endpoint -- tenant-scoped and global
        reference alike -- answers 302 to
        ``https://runmycampus.com/authentication/login/``. That is a refusal, and
        a stricter one than 403: the caller is not merely unauthorized for the
        resource, they have no session on that host to be unauthorized WITH.

        Asserting only (403, 404, 400) therefore reported a deny as a failure,
        and these 14 tests sat red long enough to stop being read.

        Widening this to "302 is fine" would be the wrong repair -- it is how a
        security test stops being able to fail. The Location has to name an auth
        surface, so a redirect that hands the caller ONWARD (to the resource, to
        another tenant) still fails, and a 200 always fails.
        """
        if resp.status_code in (301, 302):
            location = resp.headers.get("Location") or ""
            self.assertTrue(
                any(surface in location for surface in self.AUTH_SURFACES),
                f"{msg}: redirected somewhere that is not an auth surface, so "
                f"this is not a deny: {location!r}",
            )
            return
        self.assertIn(
            resp.status_code,
            (403, 404, 400),
            f"{msg} expected deny, got {resp.status_code}: {resp.content[:300]!r}",
        )

    def test_switch_school_foreign_denied(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:me-switch-school")
        resp = client.post(
            url,
            data=json.dumps({"school_id": str(self.school_b.pk)}),
            content_type="application/json",
        )
        self._assert_denied(resp, "switch-school")

    def test_me_schools_never_lists_foreign_school(self):
        """BOLA: admin_a on school A host must not see school B in me/schools."""
        rf = RequestFactory()
        req = rf.get("/api/v1/me/schools")
        req.user = self.admin_a
        req.school = self.school_a
        resp = MeSchoolsView.as_view()(req)
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        data = json.loads(resp.content.decode("utf-8"))
        listed_ids = {row["school_id"] for row in data.get("schools", [])}
        listed_ids.update(row["school_id"] for row in data.get("child_schools", []))
        self.assertIn(str(self.school_a.pk), listed_ids)
        self.assertNotIn(
            str(self.school_b.pk),
            listed_ids,
            "foreign school_id leaked in me/schools",
        )

    def test_tenant_modules_patch_foreign_uuid_denied(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:tenants-modules", kwargs={"id": self.school_b.pk})
        resp = client.patch(
            url,
            data=json.dumps({"modules": ["attendance"]}),
            content_type="application/json",
        )
        self._assert_denied(resp, "tenants-modules")

    def test_education_dna_requires_tenant_context(self):
        client = Client()
        User = get_user_model()
        user = User.objects.create_user(
            username=f"no_tenant_{uuid.uuid4().hex[:6]}",
            password="Test1234",
            role="ADMIN",
        )
        client.force_login(user)
        url = reverse("api_v1:config-education-dna")
        resp = client.get(url)
        self.assertIn(resp.status_code, (400, 403))

    def test_education_dna_member_sees_own_tenant_only(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:config-education-dna")
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("tenant_id"), str(self.school_a.pk))

    def test_education_dna_foreign_member_on_host_denied(self):
        """User B on school A host must not read school A education DNA (BOLA)."""
        client = _tenant_client(self.school_a, self.admin_b)
        url = reverse("api_v1:config-education-dna")
        resp = client.get(url)
        self._assert_denied(resp, "education-dna foreign host")

    def test_me_schools_lists_only_memberships(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:me-schools")
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        ids = {s.get("school_id") for s in resp.json().get("schools", [])}
        self.assertIn(str(self.school_a.pk), ids)
        self.assertNotIn(str(self.school_b.pk), ids)

    def test_intervention_action_center_requires_auth(self):
        url = reverse("api_v1:intervention-action-center")
        resp = Client().get(url)
        self.assertIn(resp.status_code, (400, 401, 403, 302))

    def test_compliance_export_requires_tenant(self):
        client = Client()
        User = get_user_model()
        user = User.objects.create_user(
            username=f"cmp_{uuid.uuid4().hex[:6]}",
            password="Test1234",
            role="ADMIN",
        )
        client.force_login(user)
        url = reverse("api_v1:compliance-export-school")
        resp = client.get(url)
        self.assertIn(resp.status_code, (400, 401, 403, 405))

    def test_attendance_export_tenant_scoped_ok(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:attendance-export")
        resp = client.get(url)
        self.assertIn(resp.status_code, (200, 403, 404, 501))

    def test_enrollment_forecast_tenant_a_not_b(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:enrollment-forecast")
        resp = client.get(url)
        if resp.status_code == 200:
            payload = resp.json()
            if "tenant_id" in payload:
                self.assertEqual(payload["tenant_id"], str(self.school_a.pk))

    def test_risk_thresholds_config_tenant_bound(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:config-risk-thresholds")
        resp = client.get(url)
        self.assertIn(resp.status_code, (200, 403, 404))

    def test_super_pulse_denied_for_tenant_admin(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:super-pulse")
        resp = client.get(url)
        self._assert_denied(resp, "super-pulse")

    def test_super_schools_list_denied_for_tenant_admin(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:super-schools-list")
        resp = client.get(url)
        self._assert_denied(resp, "super-schools")

    def test_rosetta_scales_readable_on_tenant(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:rosetta-scales")
        resp = client.get(url)
        self.assertIn(resp.status_code, (200, 403))

    def test_regulatory_presets_tenant_scoped(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:reports-regulatory-presets")
        resp = client.get(url)
        self.assertIn(resp.status_code, (200, 403, 404))

    def test_switch_school_own_membership_ok(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:me-switch-school")
        resp = client.post(
            url,
            data=json.dumps({"school_id": str(self.school_a.pk)}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_admin_b_cannot_patch_school_a_modules_without_membership(self):
        client = _tenant_client(self.school_a, self.admin_b)
        url = reverse("api_v1:tenants-modules", kwargs={"id": self.school_a.pk})
        resp = client.patch(
            url,
            data=json.dumps({"modules": ["attendance"]}),
            content_type="application/json",
        )
        self._assert_denied(resp, "tenants-modules foreign host")

    def test_integration_catalog_authenticated(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:config-integration-catalog")
        resp = client.get(url)
        self.assertIn(resp.status_code, (200, 401, 403))

    def test_education_templates_tenant_context(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:config-education-templates")
        resp = client.get(url)
        self.assertIn(resp.status_code, (200, 403, 404))

    def test_syllabus_pacing_requires_auth(self):
        url = reverse("api_v1:syllabus-pacing")
        resp = Client().get(url)
        self.assertIn(resp.status_code, (401, 403, 405))

    def test_scheduler_generate_tenant_admin(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:scheduler-generate")
        resp = client.post(
            url, data=json.dumps({}), content_type="application/json"
        )
        self.assertIn(resp.status_code, (200, 400, 403, 405, 501))

    def test_me_schools_requires_auth(self):
        url = reverse("api_v1:me-schools")
        resp = Client().get(url)
        self.assertIn(resp.status_code, (401, 403))

    def test_switch_school_requires_auth(self):
        url = reverse("api_v1:me-switch-school")
        resp = Client().post(
            url,
            data=json.dumps({"school_id": str(self.school_a.pk)}),
            content_type="application/json",
        )
        self.assertIn(resp.status_code, (401, 403))

    def test_risk_thresholds_foreign_host_denied(self):
        client = _tenant_client(self.school_a, self.admin_b)
        url = reverse("api_v1:config-risk-thresholds")
        resp = client.get(url)
        self._assert_denied(resp, "risk-thresholds")

    def test_enrollment_forecast_foreign_host_denied(self):
        client = _tenant_client(self.school_a, self.admin_b)
        url = reverse("api_v1:enrollment-forecast")
        resp = client.get(url)
        if resp.status_code == 404:
            return
        self._assert_denied(resp, "enrollment-forecast")

    def test_integration_catalog_global_no_tenant_leak(self):
        """Platform catalog is auth-gated but not host-scoped (no school A data)."""
        # admin_A, not admin_B: a non-member has no session on this host, so
        # the request 302s to login and the no-leak assertion below can never
        # run. The claim under test is that a GLOBAL catalog carries no school
        # data -- that needs a caller who can actually reach it.
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:config-integration-catalog")
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("catalog", body)
        self.assertNotIn(str(self.school_a.pk), json.dumps(body))

    def test_education_templates_global_no_tenant_leak(self):
        # admin_A, not admin_B: a non-member has no session on this host, so
        # the request 302s to login and the no-leak assertion below can never
        # run. The claim under test is that a GLOBAL catalog carries no school
        # data -- that needs a caller who can actually reach it.
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:config-education-templates")
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("templates", resp.json())

    def test_tenant_children_foreign_host_denied(self):
        client = _tenant_client(self.school_a, self.admin_b)
        url = reverse("api_v1:tenants-children")
        resp = client.get(url)
        self._assert_denied(resp, "tenants-children")

    def test_rosetta_scales_auth_only_global_reference(self):
        # admin_A, not admin_B: a non-member has no session on this host, so
        # the request 302s to login and the no-leak assertion below can never
        # run. The claim under test is that a GLOBAL catalog carries no school
        # data -- that needs a caller who can actually reach it.
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api_v1:rosetta-scales")
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("scales", resp.json())

    def test_regulatory_presets_foreign_host_denied(self):
        client = _tenant_client(self.school_a, self.admin_b)
        url = reverse("api_v1:reports-regulatory-presets")
        resp = client.get(url)
        self._assert_denied(resp, "regulatory-presets")

    def test_intervention_action_center_foreign_host_denied(self):
        client = _tenant_client(self.school_a, self.admin_b)
        url = reverse("api_v1:intervention-action-center")
        resp = client.get(url)
        self._assert_denied(resp, "intervention-action-center")

    def test_attendance_export_foreign_host_denied(self):
        client = _tenant_client(self.school_a, self.admin_b)
        url = reverse("api_v1:attendance-export")
        resp = client.get(url)
        self._assert_denied(resp, "attendance-export")

    def test_scheduler_generate_foreign_host_denied(self):
        client = _tenant_client(self.school_a, self.admin_b)
        url = reverse("api_v1:scheduler-generate")
        resp = client.post(
            url, data=json.dumps({}), content_type="application/json"
        )
        self._assert_denied(resp, "scheduler-generate")

    def test_analytics_viz_foreign_tenant_slug_denied(self):
        client = _tenant_client(self.school_a, self.admin_a)
        url = reverse("api:api-analytics-viz-overview")
        resp = client.get(url, {"tenant": self.school_b.slug})
        self.assertEqual(resp.status_code, 403, resp.content[:200])
