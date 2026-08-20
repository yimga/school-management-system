"""Edge Onboarding Runbook engine — proves the ordered bring-up model.

Each test FAILS without ``apps.lifecycle.edge_onboarding`` (import error) and PASSES
once the engine lands. The engine is entirely self-healing, so the suite also proves
that a fresh school yields failing-but-not-exploding validations, that a raising
validate() is caught (never aborts the suite), and that the mandatory dry sync gate
clears only when edge sync is enabled AND the operator is reachable.
"""
from __future__ import annotations

import dataclasses
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.academics.models import AcademicYear
from apps.lifecycle import edge_onboarding
from apps.lifecycle.edge_onboarding import (
    EDGE_ONBOARDING_STEPS,
    generate_runbook,
    heal_step,
    run_sync_gate,
    run_verification_suite,
)
from apps.schools.models import School, SchoolMembership
from apps.schools.rls_context import rls_bypass

_EXPECTED_KEYS = (
    "cloud_entitle_pin",
    "migration_cloud_apply",
    "sync_ownership_repair",
    "export_cloud_artifacts",
    "provision_shell",
    "migrate_identities",
    "media_branding",
    "seed_operational_data",
    "seed_baseline",
    "conversion_first_action",
    "configure_box_env",
    "configure_lan_hostname",
    "enable_configure_sync",
    "verify_and_sync_gate",
    "live_sync_proof",
    "go_dark_checklist",
)
_CLOUD_PREVIEW_EXCLUDED = (
    "verify_and_sync_gate",
    "live_sync_proof",
    "go_dark_checklist",
)
_STEP_COUNT = len(_EXPECTED_KEYS)


class EdgeOnboardingEngineTests(TestCase):
    SLUG = "gilead-tech"

    def _make_school(self, *, slug=SLUG, active=True):
        with rls_bypass():
            School.objects.filter(slug=slug).delete()
        return School.objects.create(
            id=uuid.uuid4(),
            name="Gilead Technical High School",
            slug=slug,
            subdomain=slug,
            is_active=active,
            is_approved=True,
            country_code="CM",
            settings={},
        )

    # --- generate_runbook -------------------------------------------------- #
    def test_generate_runbook_returns_all_ordered_filled_steps(self):
        school = self._make_school()
        runbook = generate_runbook(school)
        steps = runbook["steps"]

        self.assertEqual(runbook["total"], _STEP_COUNT)
        self.assertEqual(len(steps), _STEP_COUNT)
        self.assertEqual(tuple(s["key"] for s in steps), _EXPECTED_KEYS)

        for s in steps:
            # Every runbook line is copy-pasteable and school-specific.
            self.assertTrue(s["command"], f"empty command for {s['key']}")
            self.assertIn(school.slug, s["command"])
            # Placeholders must have been filled — none may survive.
            self.assertNotIn("{slug}", s["command"])
            self.assertNotIn("{school_id}", s["command"])
            self.assertNotIn("{country}", s["command"])
            for required in ("key", "title", "purpose", "command", "workaround", "runs_on"):
                self.assertIn(required, s)
                self.assertTrue(s[required], f"empty {required} for {s['key']}")
            self.assertIn(s["runs_on"], ("cloud", "box", "lan"))

        # The {school_id} placeholder is really filled somewhere in the runbook.
        self.assertIn(str(school.id), " ".join(s["command"] for s in steps))

    def test_generate_runbook_is_deterministic(self):
        school = self._make_school()
        self.assertEqual(generate_runbook(school), generate_runbook(school))

    # --- run_verification_suite ------------------------------------------- #
    def test_verification_suite_covers_all_steps_and_never_raises_on_fresh_school(self):
        # A fresh, un-provisioned school: no owner, no academics, no branding.
        school = self._make_school(active=False)
        res = run_verification_suite(school)

        self.assertEqual(res["total"], _STEP_COUNT)
        self.assertEqual(len(res["steps"]), _STEP_COUNT)
        self.assertIsInstance(res["ok"], bool)
        self.assertFalse(res["ok"])  # a fresh box is not "done"
        self.assertIsInstance(res["passed"], int)

        for s in res["steps"]:
            self.assertIn("key", s)
            self.assertIn("ok", s)
            self.assertIn("detail", s)
            self.assertIsInstance(s["ok"], bool)
            self.assertTrue(s["detail"], f"no detail for {s['key']}")

        failing = [s for s in res["steps"] if not s["ok"]]
        # provision (inactive), identities (no owner), baseline (no academics),
        # branding (no logo), enable-sync (off), sync-gate (off) all fail.
        self.assertGreaterEqual(len(failing), 3)

    def test_verification_suite_excludes_gate_when_include_gate_false(self):
        # Cloud preview omits cloud_preview=False steps (dry gate, live proof,
        # go-dark). No network probe, and NO EdgeSyncRun recorded.
        from apps.sync_engine.models import EdgeSyncRun

        school = self._make_school(active=False)
        before = EdgeSyncRun.objects.count()
        res = run_verification_suite(school, include_gate=False)
        self.assertEqual(res["total"], _STEP_COUNT - len(_CLOUD_PREVIEW_EXCLUDED))
        self.assertEqual(len(res["steps"]), _STEP_COUNT - len(_CLOUD_PREVIEW_EXCLUDED))
        keys = tuple(s["key"] for s in res["steps"])
        for excluded in _CLOUD_PREVIEW_EXCLUDED:
            self.assertNotIn(excluded, keys)
        self.assertIn("seed_operational_data", keys)
        self.assertEqual(EdgeSyncRun.objects.count(), before)

    def test_verification_suite_catches_a_raising_validate(self):
        school = self._make_school()

        def _boom(_school):
            raise RuntimeError("kaboom")

        patched = list(EDGE_ONBOARDING_STEPS)
        patched[0] = dataclasses.replace(patched[0], validate=_boom)
        with mock.patch.object(edge_onboarding, "EDGE_ONBOARDING_STEPS", tuple(patched)):
            res = run_verification_suite(school)

        self.assertEqual(res["total"], _STEP_COUNT)  # suite ran every step despite the raise
        self.assertFalse(res["steps"][0]["ok"])
        self.assertIn("kaboom", res["steps"][0]["detail"])

    # --- run_sync_gate ----------------------------------------------------- #
    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_sync_gate_not_cleared_when_disabled(self):
        school = self._make_school()
        res = run_sync_gate(school)  # no patching, no network — flag-gated no-op

        self.assertFalse(res["cleared"])
        self.assertTrue(res["detail"])
        self.assertIn("not enabled", res["detail"].lower())
        self.assertFalse(res["run"]["enabled"])

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_sync_gate_cleared_when_enabled_and_operator_reachable(self):
        school = self._make_school()
        # Patch the edge transport so the dry probe "succeeds": the delta builds,
        # nothing is posted (dry), and the operator download returns HTTP 200.
        with mock.patch(
            "apps.sync_engine.edge_outbox.build_edge_delta_bundle",
            return_value=(b"bundle", {"row_count": 0, "counts": {}, "high_water_iso": None}),
        ), mock.patch(
            "apps.sync_engine.edge_outbox.post_bundle",
            return_value=(200, {"ok": True}),
        ), mock.patch(
            "apps.sync_engine.edge_outbox.pull_bundle",
            return_value=(200, b"", None),
        ):
            res = run_sync_gate(school)

        self.assertTrue(res["cleared"], res["detail"])
        self.assertTrue(res["run"]["enabled"])
        self.assertTrue(res["run"]["ok"])

    # --- heal_step --------------------------------------------------------- #
    def test_heal_step_without_self_heal_returns_false(self):
        school = self._make_school()
        res = heal_step(school, "verify_and_sync_gate")  # no self-heal defined
        self.assertFalse(res["healed"])
        self.assertIn("no self-heal", res["detail"].lower())

    def test_heal_step_unknown_key_returns_false(self):
        school = self._make_school()
        res = heal_step(school, "does-not-exist")
        self.assertFalse(res["healed"])
        self.assertTrue(res["detail"])

    # --- real checks, not stubs ------------------------------------------- #
    def test_minimally_provisioned_school_passes_the_corresponding_checks(self):
        """active + owner + one AcademicYear (+ an entitlement) makes provision,
        identities, and baseline report ok=True — proving the checks are real."""
        school = self._make_school(active=True)
        User = get_user_model()
        with rls_bypass():
            owner = User.objects.create_user(
                username="gilead_owner",
                email="owner@gilead.school.lan",
                password="x",
            )
            SchoolMembership.objects.create(
                school=school,
                user=owner,
                role="ADMIN",
                is_school_owner=True,
                is_primary=True,
            )
            AcademicYear.objects.create(
                school=school,
                name="2025/2026",
                starts_on="2025-09-01",
                ends_on="2026-07-31",
            )
            from apps.billing.models import Entitlement

            Entitlement.objects.create(school=school, code="reports")

        res = run_verification_suite(school)
        by_key = {s["key"]: s for s in res["steps"]}

        self.assertTrue(by_key["provision_shell"]["ok"], by_key["provision_shell"]["detail"])
        self.assertTrue(by_key["migrate_identities"]["ok"], by_key["migrate_identities"]["detail"])
        self.assertTrue(by_key["seed_baseline"]["ok"], by_key["seed_baseline"]["detail"])

    def test_data_seed_is_distinct_from_fresh_shell_and_cannot_be_skipped(self):
        school = self._make_school()
        runbook = generate_runbook(school)
        by_key = {s["key"]: s for s in runbook["steps"]}
        self.assertIn("seed_operational_data", by_key)
        shell_cmd = by_key["provision_shell"]["command"]
        data_cmd = by_key["seed_operational_data"]["command"]
        self.assertIn("--fresh", shell_cmd)
        self.assertNotIn("--fresh", data_cmd)
        self.assertIn("import_tenant_bundle", data_cmd)
        gate_cmd = by_key["verify_and_sync_gate"]["command"]
        self.assertIn("edge_onboarding_verify", gate_cmd)
        self.assertNotIn("shell -c", gate_cmd)

    def test_migration_cloud_skip_reason_must_be_at_least_12_chars(self):
        from apps.lifecycle.edge_onboarding import (
            set_migration_cloud_skip_reason,
        )

        school = self._make_school()
        res = run_verification_suite(school, include_gate=False)
        by_key = {s["key"]: s for s in res["steps"]}
        self.assertFalse(by_key["migration_cloud_apply"]["ok"])

        ok, detail = set_migration_cloud_skip_reason(school, "too-short")
        self.assertFalse(ok)
        self.assertIn("12", detail)

        ok, _ = set_migration_cloud_skip_reason(
            school, "Empty shell — no SIS files for this campus."
        )
        self.assertTrue(ok)
        school.refresh_from_db()
        res = run_verification_suite(school, include_gate=False)
        by_key = {s["key"]: s for s in res["steps"]}
        self.assertTrue(by_key["migration_cloud_apply"]["ok"], by_key["migration_cloud_apply"]["detail"])

    def test_manager_host_skips_box_settings_evidence(self):
        school = self._make_school()
        res = run_verification_suite(school, include_gate=False, host_kind="manager")
        by_key = {s["key"]: s for s in res["steps"]}
        self.assertTrue(by_key["configure_box_env"]["skipped"])
        self.assertTrue(by_key["configure_lan_hostname"]["skipped"])
        self.assertTrue(by_key["enable_configure_sync"]["skipped"])
        self.assertFalse(by_key["seed_operational_data"].get("skipped"))
        self.assertIn("seed_operational_data", by_key)
        # Cloud GET still evaluates source-tenant data seed (honest empty roster).
        self.assertFalse(by_key["seed_operational_data"]["ok"])

    def test_verify_command_never_uses_shell_and_fails_fresh_school(self):
        from io import StringIO

        from django.core.management import call_command

        school = self._make_school(active=False)
        buf = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command("edge_onboarding_verify", "--slug", school.slug, stdout=buf)
        self.assertEqual(ctx.exception.code, 1)
        out = buf.getvalue()
        self.assertIn("seed_operational_data", out)
        self.assertNotIn("shell -c", out)

    def test_live_sync_proof_is_read_only_and_does_not_write_edge_sync_run(self):
        from apps.sync_engine.models import EdgeSyncRun

        school = self._make_school()
        before = EdgeSyncRun.objects.count()
        ok, detail = edge_onboarding._validate_live_sync_proof(school)
        self.assertFalse(ok)
        self.assertIn("No live", detail)
        self.assertEqual(EdgeSyncRun.objects.count(), before)

        with rls_bypass():
            EdgeSyncRun.objects.create(
                school=school, mode="live", ok=True, conflicts=0, pushed=1, pulled=1
            )
        after_write = EdgeSyncRun.objects.count()
        ok, detail = edge_onboarding._validate_live_sync_proof(school)
        self.assertTrue(ok, detail)
        self.assertIn("conflicts=0", detail)
        self.assertEqual(EdgeSyncRun.objects.count(), after_write)

    def test_conversion_and_go_dark_are_real_not_theater(self):
        from apps.people.models import StudentProfile
        from apps.schools.conversion_lock_state import record_conversion_first_action
        from apps.sync_engine.models import EdgeSyncRun

        school = self._make_school()
        conv_ok, _ = edge_onboarding._validate_conversion_first_action(school)
        self.assertFalse(conv_ok)
        go_ok, go_detail = edge_onboarding._validate_go_dark_checklist(school)
        self.assertFalse(go_ok)
        self.assertIn("roster=empty", go_detail)
        self.assertIn("conversion=locked", go_detail)
        self.assertIn("cloud owns", go_detail.lower())

        with rls_bypass():
            StudentProfile.objects.create(
                school=school, first_name="Ada", last_name="Okoro", student_code="S1"
            )
            EdgeSyncRun.objects.create(school=school, mode="dry", ok=True, conflicts=0)
            EdgeSyncRun.objects.create(
                school=school, mode="live", ok=True, conflicts=0, pushed=1, pulled=2
            )
        record_conversion_first_action(school, source="edge-onboarding-test")
        school.refresh_from_db()

        conv_ok, _ = edge_onboarding._validate_conversion_first_action(school)
        self.assertTrue(conv_ok)
        data_ok, _ = edge_onboarding._validate_seed_operational_data(school)
        self.assertTrue(data_ok)
        go_ok, go_detail = edge_onboarding._validate_go_dark_checklist(school)
        self.assertTrue(go_ok, go_detail)
        self.assertIn("Go-dark checklist cleared", go_detail)
