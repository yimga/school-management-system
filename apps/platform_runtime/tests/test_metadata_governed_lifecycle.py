from django.test import SimpleTestCase

from apps.platform_runtime.metadata_governance import (
    analyze_metadata_impact,
    build_metadata_audit_event,
    build_metadata_change_set,
    preview_metadata_change_set,
)


class MetadataGovernedLifecycleTests(SimpleTestCase):
    def test_metadata_preview_is_non_mutating_tenant_safe_and_auditable(self):
        change_set = build_metadata_change_set(
            [
                {
                    "entity": "Student",
                    "field": "health_note",
                    "owner": "Metadata platform",
                    "current_privacy": "confidential",
                    "proposed_privacy": "restricted",
                }
            ],
            scope="tenant",
            tenant_id="school-a",
        )

        preview = preview_metadata_change_set(change_set, tenant_context="school-a")
        impact = analyze_metadata_impact(change_set)
        audit = build_metadata_audit_event(
            actor="operator@example.com",
            action="metadata_preview",
            entity="Student",
            field="health_note",
            scope="tenant",
            tenant_id="school-a",
            reason="regional privacy hardening",
            evidence_path="docs/generated/admin_config_wiring_matrix.json",
        )

        self.assertTrue(change_set["ok"])
        self.assertTrue(change_set["requires_approval"])
        self.assertTrue(preview["non_mutating"])
        self.assertTrue(preview["tenant_safe"])
        self.assertFalse(preview["leaks_other_tenants"])
        self.assertIn("people", impact["affected_modules"])
        self.assertEqual(audit["tenant_id"], "school-a")
        self.assertTrue(audit["evidence_path"])

    def test_privacy_downgrade_is_blocked_not_silent(self):
        change_set = build_metadata_change_set(
            [
                {
                    "entity": "Student",
                    "field": "medical_flag",
                    "owner": "Metadata platform",
                    "current_privacy": "restricted",
                    "proposed_privacy": "public",
                }
            ]
        )

        self.assertFalse(change_set["ok"])
        self.assertIn("downgrade privacy", change_set["errors"][0])
