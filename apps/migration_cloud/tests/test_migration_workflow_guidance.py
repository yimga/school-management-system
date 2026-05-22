"""Phase 11 — Migration Cloud workflow guidance contracts.

Locks that Migration Cloud workflows expose audit events, MAA-related
external blockers are declared, and counsel-pending items (MAA v2.0 flip)
carry the external-required tag.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime import workflow_registry


class MigrationCloudWorkflowRegistryTests(SimpleTestCase):
    def test_at_least_one_migration_cloud_workflow_seeded(self):
        mc_keys = [
            k for k, w in workflow_registry.WORKFLOWS.items()
            if w.module == "migration_cloud" or "migration" in k
        ]
        self.assertGreater(
            len(mc_keys), 0,
            "No Migration Cloud workflows in registry — expected at least one",
        )

    def test_maa_workflows_declare_external_blockers(self):
        """MAA v2.0 promotion is counsel-pending per CLAUDE.md / memory — any
        workflow with 'maa' in its key MUST declare external_blockers."""
        for key, wf in workflow_registry.WORKFLOWS.items():
            if "maa" not in key.lower():
                continue
            if "promotion" not in key.lower() and "v2" not in key.lower():
                continue
            blockers = getattr(wf, "external_blockers", ()) or ()
            self.assertTrue(
                len(blockers) > 0,
                f"MAA workflow {key} declares no external_blockers — counsel signoff is pending",
            )


class MigrationCloudAuditEventTests(SimpleTestCase):
    """Migration Cloud workflows that touch the audit log MUST declare a
    related_audit_event so the audit-logged chip surfaces honestly."""

    def test_critical_migration_workflows_have_audit_events(self):
        critical_substrings = ("sign-maa", "connect-sis", "upload", "key-rotate")
        for key, wf in workflow_registry.WORKFLOWS.items():
            if not any(s in key for s in critical_substrings):
                continue
            if wf.module != "migration_cloud":
                continue
            audit_evt = getattr(wf, "related_audit_event", None)
            # We accept None for non-MC workflows that happen to share substrings
            # but expect MC workflows to declare audit events
            if wf.module == "migration_cloud":
                self.assertIsNotNone(
                    audit_evt,
                    f"Migration Cloud workflow {key} touches audit-sensitive surface but declares no related_audit_event",
                )


class MigrationCloudBoundaryTests(SimpleTestCase):
    """Migration Cloud workflows must NEVER expose write-paths to FACTS/Skyward
    (counsel-blocked per docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md)."""

    def test_no_facts_skyward_write_workflow_exists(self):
        for key, wf in workflow_registry.WORKFLOWS.items():
            lower = key.lower()
            if ("facts" in lower or "skyward" in lower) and "write" in lower:
                self.fail(
                    f"Workflow {key} appears to expose FACTS/Skyward write path — counsel-blocked",
                )
