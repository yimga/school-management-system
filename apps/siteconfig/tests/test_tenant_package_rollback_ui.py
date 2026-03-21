"""N20: tenant UI for PackageEngine rollback."""

import uuid

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.packages.engine import apply_package
from apps.packages.models import InstalledPackage, PackageChangeLog
from apps.platform_runtime.models import PlatformEventLog
from apps.siteconfig.views_package_rollback import tenant_installed_packages_rollback
from apps.schools.models import School

User = get_user_model()


class TenantPackageRollbackUiTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Pkg School",
            slug=f"pkg-{uuid.uuid4().hex[:10]}",
            subdomain=f"pkg-{uuid.uuid4().hex[:10]}",
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="a@t.test",
            password="x",
            role=User.Role.ADMIN,
        )

    def _req(self, method, path, data=None):
        if method == "GET":
            r = self.factory.get(path)
        else:
            r = self.factory.post(path, data or {})
        r.user = self.admin
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_list_and_rollback(self):
        apply_package(
            tenant_id=self.school.pk,
            package_id="n20-ui-pack",
            version="1.0",
            payload_sections={"theme": {}},
            actor_id=self.admin.pk,
        )
        inst = InstalledPackage.objects.get(
            school_id=self.school.pk, package_id="n20-ui-pack"
        )
        self.assertTrue(inst.is_active)

        resp = tenant_installed_packages_rollback(
            self._req(
                "POST",
                "/",
                {"installed_id": str(inst.pk), "confirm_rollback": "ROLLBACK"},
            )
        )
        self.assertEqual(resp.status_code, 302)
        inst.refresh_from_db()
        self.assertFalse(inst.is_active)
        self.assertTrue(
            PackageChangeLog.objects.filter(
                school_id=self.school.pk, action="rollback", package_id="n20-ui-pack"
            ).exists()
        )
        ev = PlatformEventLog.objects.filter(event_type="package_rolled_back").first()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.payload.get("package_id"), "n20-ui-pack")
        self.assertEqual(ev.payload.get("version"), "1.0")
        self.assertEqual(ev.payload.get("school_id"), str(self.school.pk))
        self.assertEqual(ev.payload.get("actor_id"), self.admin.pk)

    def test_requires_rollback_keyword(self):
        apply_package(
            tenant_id=self.school.pk,
            package_id="n20-noack",
            version="1.0",
            payload_sections={"theme": {}},
            actor_id=self.admin.pk,
        )
        inst = InstalledPackage.objects.get(package_id="n20-noack")
        tenant_installed_packages_rollback(
            self._req(
                "POST",
                "/",
                {"installed_id": str(inst.pk), "confirm_rollback": "no"},
            )
        )
        inst.refresh_from_db()
        self.assertTrue(inst.is_active)

    def test_redirect_without_school(self):
        r = self.factory.get("/")
        r.user = self.admin
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        resp = tenant_installed_packages_rollback(r)
        self.assertEqual(resp.status_code, 302)

    def test_package_activity_table_after_apply(self):
        apply_package(
            tenant_id=self.school.pk,
            package_id="n20-activity",
            version="2.0",
            payload_sections={"theme": {}},
            actor_id=self.admin.pk,
        )
        resp = tenant_installed_packages_rollback(self._req("GET", "/"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Package activity")
        self.assertContains(resp, "n20-activity")
        self.assertContains(resp, "package-impact")

    def test_rollback_page_shows_dependency_column(self):
        apply_package(
            tenant_id=self.school.pk,
            package_id="n20-deps",
            version="1.0",
            payload_sections={"theme": {}},
            actor_id=self.admin.pk,
        )
        resp = tenant_installed_packages_rollback(self._req("GET", "/"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Dependencies (snapshot)")
