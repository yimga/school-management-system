"""
CI enforcement: PackageEngine validate, preview, apply, promote, rollback.
"""
from django.test import TestCase

from apps.metadata.models import MetadataDependency
from apps.packages.engine import PackageEngine, apply_package, promote_package, rollback, validate_package
from apps.packages.models import InstalledPackage, PackageChangeLog, PackageVersion


class PackageEngineValidateTests(TestCase):
    def test_validate_requires_id_and_version(self):
        result = validate_package({})
        self.assertFalse(result["ok"])
        msg = " ".join(result["errors"]).lower()
        self.assertTrue("id" in msg or "version" in msg, f"Expected id/version errors, got: {result}")

    def test_validate_accepts_valid_payload(self):
        result = validate_package({"id": "test-pack", "version": "1.0", "payload_sections": {"policy": {}}})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["package_type"], "policy")
        self.assertIn("impact_summary", result)
        self.assertIn("rollback_blast_radius", result["impact_summary"])

    def test_validate_builds_metadata_usage_preview(self):
        result = validate_package(
            {
                "id": "lineage-pack",
                "version": "1.0",
                "payload_sections": {
                    "dashboard": {
                        "dashboards": [
                            {
                                "code": "principal-home",
                                "entity_code": "student",
                                "field_names": ["admission_number", "first_name"],
                            }
                        ],
                        "apis": [
                            {
                                "code": "student-api",
                                "entity_code": "student",
                                "field_name": "admission_number",
                            }
                        ],
                    }
                },
            }
        )
        self.assertTrue(result["ok"], result)
        preview = result["metadata_usage_preview"]
        self.assertTrue(any(item["consumer_code"] == "dashboard:principal-home" for item in preview))
        self.assertTrue(any(item["consumer_code"] == "api:student-api" for item in preview))
        self.assertTrue(any(item["consumer_code"] == "package:lineage-pack" for item in preview))


class PackageEngineApplyRollbackTests(TestCase):
    def test_apply_package_creates_installed_version_and_changelog(self):
        result = apply_package(
            tenant_id=None,
            package_id="ci-test-pack",
            version="1.0",
            payload_sections={"policy": {"entity_codes": ["student"]}},
            mode="production",
            actor_id=None,
        )
        self.assertTrue(result["ok"], result)
        self.assertIn("installed_id", result)
        self.assertIn("rollback_token", result)
        self.assertIn("changelog_id", result)
        inst = InstalledPackage.objects.get(pk=result["installed_id"])
        self.assertEqual(inst.package_id, "ci-test-pack")
        self.assertEqual(inst.version, "1.0")
        self.assertEqual(inst.apply_stage, "production")
        self.assertEqual(inst.reconciliation_status, "reconciled")
        self.assertTrue(inst.is_active)
        pkg_version = PackageVersion.objects.get(package_id="ci-test-pack", version="1.0")
        self.assertIn("policy", pkg_version.payload_sections)
        self.assertEqual(PackageChangeLog.objects.filter(package_id="ci-test-pack", action="apply").count(), 1)

    def test_apply_package_rejects_incompatible_scope(self):
        from apps.schools.models import School

        school = School.objects.create(
            name="Scoped School",
            slug="scoped-school",
            subdomain="scoped-school",
            is_active=True,
        )
        result = apply_package(
            tenant_id=school.id,
            package_id="scoped-pack",
            version="1.0",
            payload_sections={"dashboard": {}},
            compatibility={"allowed_scopes": ["platform"]},
            actor_id=None,
        )
        self.assertFalse(result["ok"])
        self.assertIn("allowed", " ".join(result["errors"]).lower())

    def test_apply_package_registers_metadata_dependencies(self):
        result = apply_package(
            tenant_id=None,
            package_id="lineage-apply-pack",
            version="1.0",
            payload_sections={
                "dashboard": {
                    "dashboards": [
                        {
                            "code": "principal-home",
                            "entity_code": "student",
                            "field_names": ["admission_number"],
                        }
                    ],
                    "templates": [
                        {
                            "code": "student-card",
                            "entity_code": "student",
                            "field_names": ["first_name"],
                        }
                    ],
                }
            },
            actor_id=None,
        )
        self.assertTrue(result["ok"], result)
        self.assertIn("rollback_blast_radius", result)
        self.assertGreaterEqual(result["rollback_blast_radius"]["consumer_count"], 1)
        self.assertTrue(
            MetadataDependency.objects.filter(
                consumer_type="dashboard",
                consumer_code="dashboard:principal-home",
                field__entity__code="student",
                field__field_name="admission_number",
            ).exists()
        )
        self.assertTrue(
            MetadataDependency.objects.filter(
                consumer_type="template",
                consumer_code="template:student-card",
                field__entity__code="student",
                field__field_name="first_name",
            ).exists()
        )
        self.assertTrue(
            MetadataDependency.objects.filter(
                consumer_type="other",
                consumer_code="package:lineage-apply-pack",
                field__entity__code="student",
                field__field_name="admission_number",
            ).exists()
        )

    def test_rollback_deactivates_and_logs(self):
        result = apply_package(
            tenant_id=None,
            package_id="ci-rollback-pack",
            version="1.0",
            payload_sections={"policy": {}},
            actor_id=None,
        )
        inst = InstalledPackage.objects.get(pk=result["installed_id"])
        rollback_result = rollback(inst, actor_id=None)
        inst.refresh_from_db()
        self.assertTrue(rollback_result["ok"])
        self.assertIn("rollback_blast_radius", rollback_result)
        self.assertFalse(inst.is_active)
        self.assertEqual(inst.reconciliation_status, "rolled_back")
        self.assertEqual(PackageChangeLog.objects.filter(package_id="ci-rollback-pack", action="rollback").count(), 1)

    def test_promote_package_records_transition(self):
        result = apply_package(
            tenant_id=None,
            package_id="ci-promote-pack",
            version="1.0",
            payload_sections={"theme": {}},
            mode="sandbox",
            actor_id=None,
        )
        inst = InstalledPackage.objects.get(pk=result["installed_id"])
        promote_result = promote_package(inst, actor_id=None, target_mode="production")
        inst.refresh_from_db()
        self.assertTrue(promote_result["ok"])
        self.assertEqual(inst.reconciliation_status, "reconciled")
        self.assertEqual(inst.promoted_from_mode, "sandbox")
        self.assertEqual(PackageChangeLog.objects.filter(package_id="ci-promote-pack", action="promote").count(), 1)


class PackageEngineTenantIsolationTests(TestCase):
    """Tenant-scoped metadata isolation: install for school A does not apply to school B."""

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
            payload_sections={"dashboard": {"entity_codes": ["student"]}},
            actor_id=None,
        )
        self.assertEqual(InstalledPackage.objects.filter(school=school_a, package_id="isolation-pack").count(), 1)
        self.assertEqual(InstalledPackage.objects.filter(school=school_b, package_id="isolation-pack").count(), 0)
