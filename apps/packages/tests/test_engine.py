"""
CI enforcement: PackageEngine validate, preview, apply, promote, rollback.
"""

from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase

from apps.metadata.models import MetadataDependency
from apps.packages.engine import (
    apply_package,
    promote_package,
    rollback,
    validate_package,
)
from apps.packages.models import InstalledPackage, PackageChangeLog, PackageVersion


class PackageEngineValidateTests(TestCase):
    def test_validate_requires_id_and_version(self):
        result = validate_package({})
        self.assertFalse(result["ok"])
        msg = " ".join(result["errors"]).lower()
        self.assertTrue(
            "id" in msg or "version" in msg,
            f"Expected id/version errors, got: {result}",
        )

    def test_validate_accepts_valid_payload(self):
        result = validate_package(
            {"id": "test-pack", "version": "1.0", "payload_sections": {"policy": {}}}
        )
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
        self.assertTrue(
            any(item["consumer_code"] == "dashboard:principal-home" for item in preview)
        )
        self.assertTrue(
            any(item["consumer_code"] == "api:student-api" for item in preview)
        )
        self.assertTrue(
            any(item["consumer_code"] == "package:lineage-pack" for item in preview)
        )


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
        self.assertEqual(result.get("apply_state"), "committed")
        self.assertIn("installed_id", result)
        self.assertIn("rollback_token", result)
        self.assertIn("changelog_id", result)
        inst = InstalledPackage.objects.get(pk=result["installed_id"])
        self.assertEqual(inst.package_id, "ci-test-pack")
        self.assertEqual(inst.version, "1.0")
        self.assertEqual(inst.apply_stage, "production")
        self.assertEqual(inst.reconciliation_status, "reconciled")
        self.assertTrue(inst.is_active)
        pkg_version = PackageVersion.objects.get(
            package_id="ci-test-pack", version="1.0"
        )
        self.assertIn("policy", pkg_version.payload_sections)
        self.assertEqual(
            PackageChangeLog.objects.filter(
                package_id="ci-test-pack", action="apply"
            ).count(),
            1,
        )

    def test_apply_package_structured_failure_on_unexpected_mid_apply_error(self):
        with patch(
            "apps.packages.engine._register_metadata_usages",
            side_effect=AttributeError("simulated mid-apply bug"),
        ):
            result = apply_package(
                tenant_id=None,
                package_id="ci-unexpected-apply-pack",
                version="1.0",
                payload_sections={"policy": {"entity_codes": ["student"]}},
                mode="production",
                actor_id=None,
            )
        self.assertFalse(result["ok"], result)
        self.assertEqual(result.get("apply_state"), "rolled_back")
        self.assertEqual(result.get("reconciliation_status"), "failed")
        self.assertTrue(result.get("errors"))
        self.assertIn("simulated mid-apply bug", result["errors"][0])
        failed = PackageChangeLog.objects.filter(
            package_id="ci-unexpected-apply-pack",
            reconciliation_status="failed",
        ).order_by("-created_at")
        self.assertTrue(failed.exists())
        summary = failed.first().impact_summary
        self.assertEqual(summary.get("mid_apply_error_type"), "AttributeError")

    def test_apply_package_integrity_error_atomic_block_leaves_no_installed_row(self):
        """§6.4: mid-apply DB error rolls back the atomic apply block; no InstalledPackage row."""
        # Patch update_or_create, which is what apply_package calls now. It used
        # to call create() unconditionally -- and because rollback() only soft-
        # deactivates, that made a rolled-back package permanently un-
        # reinstallable for its tenant (unique_together is package/version/
        # school). The contract under test is unchanged: any DB error inside the
        # atomic block leaves no install row behind.
        with patch(
            "apps.packages.engine.InstalledPackage.objects.update_or_create",
            side_effect=IntegrityError("simulated unique violation"),
        ):
            result = apply_package(
                tenant_id=None,
                package_id="ci-integrity-apply-pack",
                version="1.0",
                payload_sections={"policy": {"entity_codes": ["student"]}},
                mode="production",
                actor_id=None,
            )
        self.assertFalse(result["ok"], result)
        self.assertEqual(result.get("apply_state"), "rolled_back")
        self.assertEqual(result.get("reconciliation_status"), "failed")
        self.assertFalse(
            InstalledPackage.objects.filter(package_id="ci-integrity-apply-pack").exists()
        )

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
        self.assertEqual(result.get("apply_state"), "not_attempted")
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
        self.assertEqual(
            PackageChangeLog.objects.filter(
                package_id="ci-rollback-pack", action="rollback"
            ).count(),
            1,
        )

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
        self.assertEqual(
            PackageChangeLog.objects.filter(
                package_id="ci-promote-pack", action="promote"
            ).count(),
            1,
        )


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
        self.assertEqual(
            InstalledPackage.objects.filter(
                school=school_a, package_id="isolation-pack"
            ).count(),
            1,
        )
        self.assertEqual(
            InstalledPackage.objects.filter(
                school=school_b, package_id="isolation-pack"
            ).count(),
            0,
        )


class NormalizeDeclaredDependenciesTests(TestCase):
    def test_normalize_declared_dependencies_strings_dedupes_preserves_order(self):
        from apps.packages.engine import normalize_declared_dependencies

        out = normalize_declared_dependencies(
            ["  a  ", "b", "a", "", "  ", "b"]
        )
        self.assertEqual(out, ["a", "b"])

    def test_normalize_declared_dependencies_dict_entries_use_package_id_or_id(self):
        from apps.packages.engine import normalize_declared_dependencies

        out = normalize_declared_dependencies(
            [
                {"package_id": "pkg-a"},
                {"id": "pkg-b"},
                {"package_id": ""},
            ]
        )
        self.assertEqual(out, ["pkg-a", "pkg-b"])

    def test_normalize_declared_dependencies_rejects_non_list_or_bad_entry_type(self):
        from apps.packages.engine import normalize_declared_dependencies

        self.assertEqual(normalize_declared_dependencies(None), [])
        with self.assertRaises(ValueError):
            normalize_declared_dependencies("not-a-list")
        with self.assertRaises(ValueError):
            normalize_declared_dependencies([42])


class PackageDependencyGraphTests(TestCase):
    def test_list_reverse_dependent_package_ids(self):
        from apps.packages.engine import list_reverse_dependent_package_ids
        from apps.packages.models import PackageVersion

        PackageVersion.objects.create(
            package_id="parent-pkg",
            version="1.0.0",
            dependencies=[],
            payload_sections={"theme": {}},
        )
        PackageVersion.objects.create(
            package_id="child-pkg",
            version="1.0.0",
            dependencies=["parent-pkg"],
            payload_sections={"theme": {}},
        )
        rev = list_reverse_dependent_package_ids("parent-pkg")
        self.assertIn("child-pkg", rev)
        self.assertNotIn("parent-pkg", rev)

    def test_metadata_apply_preview_bundle_includes_graph(self):
        from apps.packages.engine import metadata_apply_preview_bundle
        from apps.schools.models import School

        school = School.objects.create(
            name="Prev School",
            slug="prev-school",
            subdomain="prev-school",
            is_active=True,
        )
        PackageVersion.objects.create(
            package_id="tmpl-a",
            version="1.0.0",
            dependencies=["base-theme"],
            payload_sections={"theme": {"name": "A"}},
        )
        PackageVersion.objects.create(
            package_id="other",
            version="1.0.0",
            dependencies=["tmpl-a"],
            payload_sections={"theme": {}},
        )
        bundle = metadata_apply_preview_bundle(
            school.pk, "tmpl-a", "1.0.0", {"theme": {"name": "A"}}
        )
        self.assertEqual(bundle["package_id"], "tmpl-a")
        self.assertIn("base-theme", bundle["dependency_graph"]["upstream_package_ids"])
        self.assertIn("other", bundle["dependency_graph"]["downstream_package_ids"])
        self.assertIsNotNone(bundle.get("preview"))
        self.assertTrue(bundle.get("has_registered_version"))
