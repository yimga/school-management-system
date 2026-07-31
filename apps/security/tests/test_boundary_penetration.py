"""Stage 2 boundary penetration: cross-tenant access attempts must fail closed."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings, tag
from django.urls import reverse

from apps.accounts.models import User
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.schools.rls_context import rls_bypass, rls_school

_HOST_A = "pen-a.runmycampus.com"
_HOST_B = "pen-b.runmycampus.com"
_MGR = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _HOST_A, _HOST_B, _MGR],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    MULTI_TENANT_LEGACY_BASE_DOMAINS="",
)
@tag("tenants_rls")
class CrossTenantBoundaryPenetrationTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        with rls_bypass():
            cls.school_a = School.objects.create(
                name="Pen School A",
                slug="pen-a",
                subdomain="pen-a",
                is_active=True,
            )
            cls.school_b = School.objects.create(
                name="Pen School B",
                slug="pen-b",
                subdomain="pen-b",
                is_active=True,
            )
            cls.admin_a = User.objects.create_user(
                username=f"pen_a_{uuid.uuid4().hex[:6]}",
                password="y" * 8,
                role=User.Role.ADMIN,
                is_staff=True,
            )
            SchoolMembership.objects.create(
                user=cls.admin_a,
                school=cls.school_a,
                role=User.Role.ADMIN,
                is_primary=True,
            )
            cls.student_b = StudentProfile.objects.create(
                school=cls.school_b,
                first_name="Foreign",
                last_name="Student",
                admission_number=f"PEN-{uuid.uuid4().hex[:6]}",
            )

    def test_cross_tenant_pk_on_wrong_host_not_served(self):
        """PK from school B must not resolve on school A tenant host."""
        c = Client(HTTP_HOST=_HOST_A)
        c.force_login(self.admin_a)
        session = c.session
        session["school_id"] = str(self.school_a.id)
        session["mfa_verified"] = True
        session.save()
        with override_settings(ROOT_URLCONF="config.tenant_urls"):
            url = reverse(
                "accounts:backend_student_detail",
                kwargs={"student_id": self.student_b.pk},
            )
            response = c.get(url, secure=True)
        self.assertIn(response.status_code, (302, 403, 404))

    def test_forged_session_school_id_does_not_grant_foreign_rows(self):
        """A school-B admin who forges ``session['school_id']=A`` on B's host is
        never served school A's data.

        The platform resolves the active tenant from the HOST + membership, never
        from the session hint. ``SessionSchoolBindingMiddleware`` REALIGNS a
        disagreeing session ``school_id`` to the host campus when the user is a
        member of it (soft-correct), and only force-logs-out + 403 when the user
        is NOT entitled to the host campus. admin_b IS a member of host B, so the
        forged ``A`` is discarded — the request serves B (admin_b's own campus) or
        is blocked, but the foreign ``A`` is never honored. Asserting the forged id
        is not honored is a STRONGER cross-tenant-leak check than a bare status
        code: it fails if a regression ever makes the session hint load-bearing.
        A hard 302/403 here would be wrong — it would break the intentional
        bookmark-drift realignment path for legitimate multi-campus admins.
        """
        with rls_bypass():
            admin_b = User.objects.create_user(
                username=f"pen_b_{uuid.uuid4().hex[:6]}",
                password="y" * 8,
                role=User.Role.ADMIN,
                is_staff=True,
            )
            SchoolMembership.objects.create(
                user=admin_b,
                school=self.school_b,
                role=User.Role.ADMIN,
                is_primary=True,
            )
        c = Client(HTTP_HOST=_HOST_B)
        c.force_login(admin_b)
        session = c.session
        session["school_id"] = str(self.school_a.id)  # forged to the FOREIGN campus
        session["mfa_verified"] = True
        session.save()
        with override_settings(ROOT_URLCONF="config.tenant_urls"):
            url = reverse("siteconfig:compliance_exports")
            resp = c.get(url, secure=True)
        # Secure outcomes only: realign→serve own campus (200) or hard-block
        # (302/403); never a 200 that resolved to the foreign campus.
        self.assertIn(resp.status_code, (200, 302, 403))
        # Load-bearing assertion: the forged foreign school_id must NOT survive as
        # the active tenant. The binding middleware either realigns the session to
        # the host campus (B) or flushes it on logout — in both secure paths the
        # session ends pointing at B or empty, never at A. If the forge were ever
        # honored (the leak this test guards), school A would remain the selected
        # campus and this would fail. (A UUID/None comparison, not a body substring,
        # so it can never collide incidentally.)
        resolved_school_id = c.session.get("school_id")
        self.assertIn(resolved_school_id, (str(self.school_b.id), None, ""))
        self.assertNotEqual(resolved_school_id, str(self.school_a.id))

    def test_slug_manipulation_on_manager_super_route(self):
        """Tenant admin cannot reach control-plane super dashboard via host swap."""
        c = Client(HTTP_HOST=_MGR)
        c.force_login(self.admin_a)
        response = c.get(reverse("super:dashboard"))
        self.assertIn(response.status_code, (302, 403))

    def test_host_header_attack_manager_export_blocked_for_tenant_admin(self):
        c = Client(HTTP_HOST=_MGR)
        c.force_login(self.admin_a)
        response = c.get(reverse("super:export_schools_csv"))
        self.assertIn(response.status_code, (302, 403))

    def test_rls_school_context_blocks_foreign_student_query(self):
        from django.conf import settings
        from django.db import connection

        if connection.vendor == "sqlite" or not getattr(
            settings, "USE_DJANGO_TENANTS", False
        ):
            found = StudentProfile.objects.filter(
                pk=self.student_b.pk, school_id=self.school_a.id
            ).exists()
        else:
            with rls_school(self.school_a.id):
                found = StudentProfile.objects.filter(pk=self.student_b.pk).exists()
        self.assertFalse(found)


@override_settings(
    IMPERSONATION_REQUIRE_JUSTIFICATION=True,
    JIT_IMPERSONATION_REQUIRE_CONSENT=False,
)
@tag("tenants_rls")
class ImpersonationWithoutReasonPenetrationTests(TestCase):
    databases = {"default"}

    def test_switch_to_tenant_rejects_empty_reason(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.backends.db import SessionStore
        from django.test import RequestFactory

        from apps.schools.super_views_impersonation import switch_to_tenant

        with rls_bypass():
            school = School.objects.create(
                name="Reason Gate School",
                slug="reason-gate",
                subdomain="reason-gate",
                is_active=True,
            )
            actor = User.objects.create_user(
                username=f"imp_{uuid.uuid4().hex[:6]}",
                password="y" * 8,
                is_superuser=True,
                is_staff=True,
            )
        request = RequestFactory().post(
            "/super/switch-to-tenant/",
            data={"school_id": str(school.id), "impersonation_reason": "  "},
        )
        request.user = actor
        request.public_host_kind = "manager"
        request.META["HTTP_HOST"] = _MGR
        request.session = SessionStore()
        setattr(request, "_messages", FallbackStorage(request))
        response = switch_to_tenant(request)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("impersonate=", response.url or "")
