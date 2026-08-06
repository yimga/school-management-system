"""Workflow Center access + engine hardening (2026-08-03 audit remediation).

Seven verified fixes across the three workflow systems (tenant `automation`
engine, operator `orchestration` engine, Studio hubs). Every test below fails on
the pre-2026-08-03 code (must-fire).

  #1  Tenant workflow engine (visual builder + outcomes) admits the host-aware
      tenant-admin tier, not `is_staff` alone (role-based admins are never staff).
  #2  Import Hub + Automation Hub gate on `settings.manage` (was `_is_admin_user`),
      matching the Workflow Center that links to them.
  #3  Automation Hub's execution-log button points at the tenant-reachable
      `automation:outcomes_console`, not a Django-admin changelist.
  #4  Operator orchestration workbench refuses non-super surfaces (was
      `@staff_member_required`, reachable by is_staff tenant admins on the tenant host).
  #5  Orchestration drain + SLO rollup are registered in the no-worker/edge
      in-process scheduler (were beat-only).
  #6  Seed definitions match runners (student_transfer seeded, migration_run
      dropped) + a run with no runner is FAILED, not left PENDING forever.
  #7  Parents get a Workflow nav pill (teacher/student already had one).
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.accounts.models import User


def _src(module) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


# ── #1 — tenant workflow engine gate ────────────────────────────────────────
class EngineGateHardeningTests(SimpleTestCase):
    def _req(self, role, *, is_staff=False, is_superuser=False):
        req = RequestFactory().get("/automation/visual/api/nodes/")
        req.user = SimpleNamespace(
            is_authenticated=True,
            is_staff=is_staff,
            is_superuser=is_superuser,
            role=role,
        )
        req.school = SimpleNamespace(pk=1)
        return req

    def test_role_admin_non_staff_reaches_engine(self):
        from apps.automation.views_visual_workflow import _staff_school

        school, err = _staff_school(self._req(User.Role.ADMIN))
        self.assertIsNone(err, "role ADMIN (non-staff) must reach the workflow engine")
        self.assertIsNotNone(school)

    def test_non_admin_non_staff_blocked(self):
        from apps.automation.views_visual_workflow import _staff_school

        school, err = _staff_school(self._req(User.Role.TEACHER))
        self.assertIsNone(school)
        self.assertIsNotNone(err)
        self.assertEqual(err.status_code, 403)

    def test_engine_views_use_studio_contract_not_bare_is_staff(self):
        import apps.automation.views as av
        import apps.automation.views_visual_workflow as vw

        vw_src, av_src = _src(vw), _src(av)
        self.assertIn("user_can_access_studio_on_request", vw_src)
        self.assertIn("user_can_access_studio_on_request", av_src)
        # outcomes_console no longer gates on the is_staff-only helper.
        self.assertNotIn("user_passes_test(_staff_required)", av_src)


# ── #2 / #3 — Studio hub gating + link target ───────────────────────────────
class HubGatingAlignmentTests(SimpleTestCase):
    def setUp(self):
        import apps.accounts.views_workflow as vwf

        self.src = _src(vwf)

    def _decorators_above(self, fn: str) -> str:
        m = re.search(r"((?:@[^\n]+\n)+)def " + fn + r"\(", self.src)
        self.assertIsNotNone(m, f"{fn} not found")
        return m.group(1)

    def test_import_and_automation_hubs_use_settings_manage(self):
        for fn in ("import_hub", "automation_hub"):
            decorators = self._decorators_above(fn)
            self.assertIn(
                'permission_required("settings.manage")',
                decorators,
                f"{fn} must gate on settings.manage",
            )
            self.assertNotIn(
                "_is_admin_user", decorators, f"{fn} still uses the _is_admin_user gate"
            )

    def test_automation_hub_execution_log_targets_outcomes_console(self):
        self.assertIn("automation:outcomes_console", self.src)


# ── #4 — operator orchestration workbench gate ──────────────────────────────
class OrchestrationWorkbenchGateTests(SimpleTestCase):
    def test_workbench_forbidden_on_non_super_surface(self):
        from apps.orchestration.views import operator_workbench

        req = RequestFactory().get("/orchestration/workbench/")
        req.user = SimpleNamespace(
            is_authenticated=True, is_staff=True, is_superuser=False, role="ADMIN"
        )
        resp = operator_workbench(req)
        self.assertEqual(
            resp.status_code,
            403,
            "operator workbench must refuse a tenant-host (non-super) surface",
        )

    def test_no_staff_member_required_left(self):
        import apps.orchestration.views as ov

        src = _src(ov)
        self.assertNotIn("staff_member_required", src)
        self.assertIn("require_super_access_with_host", src)


# ── #5 — no-worker/edge scheduler registration ──────────────────────────────
class PeriodicOrchestrationRegistrationTests(SimpleTestCase):
    def test_orchestration_drain_and_slo_registered(self):
        from apps.platform_runtime import periodic

        periodic.ensure_default_jobs()
        for key in ("orchestration.process_due_runs", "orchestration.aggregate_slos"):
            self.assertIn(
                key,
                periodic._REGISTRY,
                f"{key} must run on the no-worker/edge in-process scheduler",
            )
            self.assertTrue(callable(periodic._REGISTRY[key].func))


# ── #6a — seed ↔ runner alignment ───────────────────────────────────────────
class SeedRunnerAlignmentTests(SimpleTestCase):
    def test_seed_defaults_swap_migration_run_for_student_transfer(self):
        from apps.orchestration.management.commands.seed_process_definitions import (
            DEFAULTS,
        )

        codes = {d["code"] for d in DEFAULTS}
        self.assertIn("student_transfer", codes)
        self.assertNotIn("migration_run", codes)

    def test_every_seeded_definition_has_a_runner(self):
        from apps.orchestration.management.commands.seed_process_definitions import (
            DEFAULTS,
        )
        from apps.orchestration.runners import get_runner

        for d in DEFAULTS:
            fake_run = SimpleNamespace(
                definition=SimpleNamespace(code=d["code"]), definition_id=1
            )
            self.assertIsNotNone(
                get_runner(fake_run),
                f"seeded definition '{d['code']}' has no runner (would sit PENDING forever)",
            )


# ── #6b — no-runner run is FAILED, not stuck PENDING ────────────────────────
class NoRunnerRunFailedTests(TestCase):
    def test_no_runner_run_marked_failed(self):
        from apps.orchestration.management.commands.process_orchestration_runs import (
            fail_unrunnable_run,
        )
        from apps.orchestration.models import OrchestrationRun, ProcessDefinition

        defn = ProcessDefinition.objects.create(
            code="__no_runner_test__", name="No runner test"
        )
        run = OrchestrationRun.objects.create(
            definition=defn,
            status=OrchestrationRun.Status.PENDING,
            input_payload={},
        )
        fail_unrunnable_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, OrchestrationRun.Status.FAILED)
        self.assertIn("No runner", run.error_message)


# ── #7 — parent workflow nav pill ───────────────────────────────────────────
class ParentWorkflowNavTests(SimpleTestCase):
    def test_parent_nav_has_workflow_pill(self):
        tpl = get_template("partials/tenant_primary_nav.html")
        src = Path(tpl.origin.name).read_text(encoding="utf-8")
        self.assertIn("portal:parent_workflow", src)
