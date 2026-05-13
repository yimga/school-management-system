"""Cross-host boundaries: tenant RBAC vs control plane vs tenant mismatch."""

from __future__ import annotations

import uuid

from django.test import Client, RequestFactory, TestCase, override_settings, tag
from django.urls import reverse

from apps.accounts.models import Permission as FeaturePermission
from apps.accounts.models import User, UserPasskey
from apps.compliance.models_audit import AuditLog
from apps.schools.models import School, SchoolMembership
from apps.schools.rls_context import rls_bypass, rls_school
from apps.schools.security_enforcer import best_effort_audit_export_download

_T = "leak1.runmycampus.com"
_T2 = "leak2.runmycampus.com"
_MGR = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=[
        "*",
        "testserver",
        "127.0.0.1",
        "localhost",
        _T,
        _T2,
        _MGR,
    ]
)
@tag("tenants_rls")
class TenantHostVsControlPlaneTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        with rls_bypass():
            cls.perm, _ = FeaturePermission.objects.get_or_create(
                code="settings.manage",
                defaults={"name": "Manage settings"},
            )
            cls.s_a = School.objects.create(
                name="Leak A",
                slug="leak1",
                subdomain="leak1",
                is_active=True,
            )
            cls.s_b = School.objects.create(
                name="Leak B",
                slug="leak2",
                subdomain="leak2",
                is_active=True,
            )

    def test_tenant_staff_cannot_download_super_schools_csv(self):
        """Platform schools CSV requires operator role; tenant admin alone is denied (403)."""
        with rls_bypass():
            u = User.objects.create_user(
                username=f"t_{uuid.uuid4().hex[:8]}",
                password="y" * 8,
                role=User.Role.ADMIN,
                is_staff=True,
                is_superuser=False,
            )
            SchoolMembership.objects.create(
                user=u,
                school=self.s_a,
                role=User.Role.ADMIN,
                is_primary=True,
            )
        # Manager host matches control-plane cookie isolation (rmc_manager_sessionid).
        # Without a full browser cookie jar, the client may get 302→login or 403;
        # both mean the export is not served to a tenant-only admin.
        c = Client(HTTP_HOST=_MGR)
        c.force_login(u)
        url = reverse("super:export_schools_csv")
        r = c.get(url)
        # 403: authenticated but not a platform operator. 302: unauthenticated on /super/
        # (test client + manager session cookie mirroring can present as redirect).
        self.assertIn(r.status_code, (302, 403), msg=getattr(r, "content", b"")[:400])

    def test_membership_on_school_a_blocked_on_school_b_host(self):
        """Tenant host resolves school B; user only belongs to A → export gate 403."""
        with rls_bypass():
            u = User.objects.create_user(
                username=f"w_{uuid.uuid4().hex[:8]}",
                password="y" * 8,
                role=User.Role.ADMIN,
                is_staff=True,
            )
            u.feature_permissions.add(self.perm)
            UserPasskey.objects.create(
                user=u,
                name="Test passkey",
                credential_id=f"tenant-mismatch-{uuid.uuid4().hex}",
                public_key="test-public-key",
            )
            SchoolMembership.objects.create(
                user=u,
                school=self.s_a,
                role=User.Role.ADMIN,
                is_primary=True,
            )
        c = Client(HTTP_HOST=_T2)
        c.force_login(u)
        session = c.session
        session["mfa_verified"] = True
        session.save()
        url = reverse("siteconfig:compliance_exports", urlconf="config.tenant_urls")
        self.assertEqual(c.get(url, secure=True).status_code, 403)


@override_settings(
    ALLOWED_HOSTS=[
        "*",
        "testserver",
        "127.0.0.1",
        "localhost",
        _T,
        _MGR,
    ]
)
@tag("tenants_rls")
class ManagerSecuritySurfaceIsolationTests(TestCase):
    """Control-plane security dashboard must not be reachable from tenant surfaces."""

    databases = {"default"}

    def test_security_surface_dashboard_forbidden_on_tenant_host(self):
        staff = User.objects.create_user(
            username=f"sf_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            is_staff=True,
            is_superuser=False,
        )
        c = Client(HTTP_HOST=_T)
        c.force_login(staff)
        url = reverse("super:security_surface_dashboard")
        self.assertIn(c.get(url).status_code, (302, 403))

    def test_security_surface_dashboard_requires_super_on_manager_host(self):
        staff = User.objects.create_user(
            username=f"mg_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            is_staff=True,
            is_superuser=False,
        )
        c = Client(HTTP_HOST=_MGR)
        c.force_login(staff)
        url = reverse("super:security_surface_dashboard")
        self.assertIn(c.get(url).status_code, (302, 403))


@tag("tenants_rls")
class ExportAuditHookTests(TestCase):
    databases = {"default"}

    def test_best_effort_audit_export_download_writes_audit_log(self):
        with rls_bypass():
            school = School.objects.create(
                name="Audit Hook",
                slug="audit-hook",
                subdomain="audit-hook",
                is_active=True,
            )
            u = User.objects.create_user(
                username=f"au_{uuid.uuid4().hex[:8]}",
                password="y" * 8,
            )
        rf = RequestFactory()
        request = rf.get("/")
        request.user = u
        request.school = school
        with rls_school(school.id):
            before = AuditLog.objects.count()
            best_effort_audit_export_download(
                request,
                export_key="security_test_export",
                school=school,
                app_label="security_tests",
            )
            self.assertEqual(AuditLog.objects.count(), before + 1)
            row = AuditLog.objects.order_by("-pk").first()
        assert row is not None
        self.assertEqual(row.action, AuditLog.Action.EXPORT)
        self.assertIn("security_test_export", row.object_repr)
