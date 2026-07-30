"""Per-wave validation contracts for Workflow Progress 10x (mirrors waves-complete gate)."""

from __future__ import annotations

from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

REPO_ROOT = Path(__file__).resolve().parents[3]

WAVE10X_URLS = (
    "platform_runtime:workflow_progress_flight_deck",
    "platform_runtime:workflow_progress_flight_deck_json",
    "platform_runtime:workflow_progress_tenant_trusted_active",
    "platform_runtime:workflow_progress_tenant_trusted_stream",
    "platform_runtime:workflow_progress_autopilot_policy",
    "platform_runtime:workflow_progress_enable_autopilot",
)

BUS_URLS = (
    "platform_runtime:workflow_progress_active_runs",
    "platform_runtime:workflow_progress_stream",
    "platform_runtime:workflow_progress_apply_fix",
)


class Workflow10xWaveUrlTests(SimpleTestCase):
    def test_bus_and_wave_urls_resolve(self):
        kwargs_by_name = {
            "platform_runtime:workflow_progress_apply_fix": {"run_id": 1},
            "platform_runtime:workflow_progress_cancel": {"run_id": 1},
        }
        for name in (*BUS_URLS, *WAVE10X_URLS):
            with self.subTest(url=name):
                path = reverse(name, kwargs=kwargs_by_name.get(name))
                self.assertTrue(path)


class Workflow10xWaveRegistryTests(SimpleTestCase):
    def test_lifecycle_workflows_have_slo(self):
        from apps.platform_runtime.workflow_registry import WORKFLOWS

        for key in (
            "tenant_school_provision",
            "tenant_school_purge",
            "migration_bundle_apply",
            "evals_bulk_grades",
        ):
            with self.subTest(key=key):
                self.assertGreater(getattr(WORKFLOWS[key], "slo_seconds", 0) or 0, 0)

    def test_single_tenant_school_purge_entry(self):
        from apps.platform_runtime.workflow_registry import WORKFLOWS

        self.assertEqual(list(WORKFLOWS.keys()).count("tenant_school_purge"), 1)


class Workflow10xWaveModelTests(TestCase):
    def test_10x_models_importable(self):
        from apps.platform_runtime.models_workflow_10x import (
            WorkflowAutopilotApplyLog,
            WorkflowAutopilotPolicy,
            WorkflowDurationStat,
            WorkflowSlaBreach,
        )

        self.assertEqual(WorkflowAutopilotPolicy._meta.app_label, "platform_runtime")
        self.assertTrue(WorkflowAutopilotApplyLog._meta.db_table)
        self.assertTrue(WorkflowDurationStat._meta.db_table)
        self.assertTrue(WorkflowSlaBreach._meta.db_table)


class Workflow10xWaveShellTests(SimpleTestCase):
    def test_tenant_experience_includes_workflow_trust_strip(self):
        # The tools-tray wave (11326592a) relocated the workflow tenant-trust
        # strip out of portal_base.html and INTO the shared tools-tray context
        # stack, which the tenant backend shell (backend_base.html) and the
        # control-plane skeleton both include — so it renders in the operational
        # tenant experience via one SOT partial instead of being pinned to
        # portal_base. Assert it ships in that stack.
        stack = (REPO_ROOT / "templates/partials/rmc_tools_tray_context_stack.html").read_text(encoding="utf-8")
        self.assertIn("rmc_workflow_tenant_trust_strip.html", stack)
        backend = (REPO_ROOT / "templates/backend_base.html").read_text(encoding="utf-8")
        self.assertIn("rmc_tools_tray_context_stack.html", backend)

    def test_control_plane_includes_progress_and_copilot(self):
        text = (REPO_ROOT / "templates/control_plane_skeleton.html").read_text(encoding="utf-8")
        self.assertIn("rmc-workflow-progress.js", text)
        self.assertIn("rmc-copilot-context-lens.js", text)

    def test_flight_deck_in_super_operational_frames(self):
        from apps.platform_runtime.super_operational_frames import WORKFLOW_FLIGHT_DECK_NAV

        self.assertGreater(len(WORKFLOW_FLIGHT_DECK_NAV), 0)


class Workflow10xWaveIntegrationTests(SimpleTestCase):
    def test_flight_deck_nav_for_superuser(self):
        from apps.schools.control_plane_nav import build_control_plane_nav

        request = RequestFactory().get("/super/")
        request.urlconf = "config.manager_urls"
        request.user = get_user_model()(is_superuser=True, username="wave_val_nav")
        ids = [
            item.get("id")
            for grp in build_control_plane_nav(request)
            for item in (grp.get("items") or [])
            if isinstance(item, dict)
        ]
        self.assertIn("super_workflow_flight_deck", ids)
