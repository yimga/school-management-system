"""
CI enforcement: PackageEngine validate, apply, rollback (metadata plan todo 9).
"""
from django.test import TestCase

from apps.packages.engine import PackageEngine, validate_package, apply_package, rollback
from apps.packages.models import InstalledPackage, PackageChangeLog


class PackageEngineValidateTests(TestCase):
    def test_validate_requires_id_and_version(self):
        ok, errs = validate_package({})
        self.assertFalse(ok)
        msg = " ".join(errs).lower()
        self.assertTrue("id" in msg or "version" in msg, f"Expected id/version errors, got: {errs}")

    def test_validate_accepts_valid_payload(self):
        ok, errs = validate_package({"id": "test-pack", "version": "1.0", "payload_sections": {}})
        self.assertTrue(ok, errs)
        self.assertEqual(len(errs), 0)


class PackageEngineApplyRollbackTests(TestCase):
    def test_apply_package_creates_installed_and_changelog(self):
        result = apply_package(
            tenant_id=None,
            package_id="ci-test-pack",
            version="1.0",
            payload_sections={"policy": {}},
            mode="production",
            actor_id=None,
        )
        self.assertIn("installed_id", result)
        self.assertIn("rollback_token", result)
        self.assertIn("changelog_id", result)
        inst = InstalledPackage.objects.get(pk=result["installed_id"])
        self.assertEqual(inst.package_id, "ci-test-pack")
        self.assertEqual(inst.version, "1.0")
        self.assertTrue(inst.is_active)
        self.assertEqual(PackageChangeLog.objects.filter(package_id="ci-test-pack", action="apply").count(), 1)

    def test_rollback_deactivates_and_logs(self):
        result = apply_package(
            tenant_id=None,
            package_id="ci-rollback-pack",
            version="1.0",
            payload_sections={},
            actor_id=None,
        )
        inst = InstalledPackage.objects.get(pk=result["installed_id"])
        rollback(inst, actor_id=None)
        inst.refresh_from_db()
        self.assertFalse(inst.is_active)
        self.assertEqual(PackageChangeLog.objects.filter(package_id="ci-rollback-pack", action="rollback").count(), 1)


class PackageEngineTenantIsolationTests(TestCase):
    """Tenant-scoped metadata isolation: install for school A does not apply to school B (metadata plan todo 9)."""

    def test_installed_package_is_scoped_by_school(self):
        from apps.schools.models import School
        school_a = School.objects.create(
            name="Isolation School A",
            slug="isolation-a",
            subdomain="isolation-a",
            is_active=True,
        )
        school_b = School.objects.create(
            name="Isolation School B",
            slug="isolation-b",
            subdomain="isolation-b",
            is_active=True,
        )
        apply_package(
            tenant_id=school_a.id,
            package_id="isolation-pack",
            version="1.0",
            payload_sections={},
            actor_id=None,
        )
        self.assertEqual(InstalledPackage.objects.filter(school=school_a, package_id="isolation-pack").count(), 1)
        self.assertEqual(InstalledPackage.objects.filter(school=school_b, package_id="isolation-pack").count(), 0)
        school_a.delete()
        school_b.delete()
