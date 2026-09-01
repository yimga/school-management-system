"""Seals for the edge-sync rail coverage declaration (G1).

The rail replicates ~4.6% of the tenant model surface. That fraction is allowed to
be small; what is not allowed is for it to be small *by accident*. These tests
seal the four properties that make the declaration a decision rather than a
description:

1. **Complete today.** Every model in every ``TENANT_APPS`` app has a posture.
2. **Bites tomorrow.** A model that appears with no posture is a hard failure --
   proved by registering a REAL model into the live app registry, not by mocking
   the enumeration.
3. **Honest.** A ``HELD`` with no rationale, or no pointer to where it is argued,
   fails; and a ``NOT_YET`` may not smuggle an argument in.
4. **Derived, not transcribed.** ``RIDES`` comes from the live registry in
   ``apps.api.sync_services`` -- proved by adding an entity there at runtime and
   watching the report change with NO edit to ``DECLARATIONS``.

No database access: every assertion here is about the model registry, the
settings source, and the declaration, so these run without a test DB.
"""
from __future__ import annotations

import importlib.util
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import TestCase, mock

from apps.api import sync_services
from apps.sync_engine import rail_coverage
from apps.sync_engine.rail_coverage import (
    DECLARABLE_POSTURES,
    DECLARATIONS,
    HELD,
    NOT_YET,
    RIDES,
    UNDECLARED,
    Declaration,
)

REPO_ROOT = Path(rail_coverage.__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "var" / "edge-sync-rail-coverage-baseline.json"
AUDITOR = REPO_ROOT / "scripts" / "audit_rail_coverage.py"


def _kinds(report) -> list[str]:
    return [v["kind"] for v in report.violations]


def _findings(report, kind) -> list[dict]:
    return [v for v in report.violations if v["kind"] == kind]


class RailCoverageDeclarationTests(TestCase):
    """Property 1: the declaration is complete and clean for today's models."""

    def test_every_tenant_model_has_a_posture(self):
        report = rail_coverage.evaluate()
        self.assertEqual(
            report.total_undeclared,
            0,
            "tenant models with no rail posture: "
            + ", ".join(m for a in report.apps for m in a.undeclared),
        )

    def test_head_has_no_violations_at_all(self):
        report = rail_coverage.evaluate()
        self.assertEqual(
            report.violations,
            [],
            f"rail coverage violations at HEAD: {report.violations}",
        )

    def test_counts_are_measured_not_asserted(self):
        """The denominator is the live registry, and it is the whole of it."""
        report = rail_coverage.evaluate()
        live = rail_coverage.tenant_models()
        self.assertEqual(report.total_models, len(live))
        self.assertEqual(
            report.total_models,
            report.total_rides
            + report.total_held
            + report.total_not_yet
            + report.total_undeclared,
            "every model must land in exactly one bucket",
        )
        # A sanity floor: if this ever collapses, the enumeration broke rather
        # than the platform shrinking to nothing. A scan that reports almost no
        # models is the failure mode that makes a green result meaningless.
        self.assertGreater(report.total_models, 250)
        self.assertGreater(len(report.apps), 10)

    def test_no_posture_is_hand_written_as_rides(self):
        """RIDES is derived. Asserting it by hand is how a matrix starts lying."""
        self.assertNotIn(RIDES, DECLARABLE_POSTURES)
        for label, decl in DECLARATIONS.items():
            self.assertIn(
                decl.posture,
                DECLARABLE_POSTURES,
                f"{label}: {decl.posture!r} is not declarable",
            )

    def test_declaration_keys_are_all_live_tenant_models(self):
        """A typo'd or stale key would look like coverage for nothing."""
        live = set(rail_coverage.tenant_models())
        stale = sorted(k for k in DECLARATIONS if k not in live)
        self.assertEqual(stale, [], f"declarations naming no live tenant model: {stale}")

    def test_no_riding_model_carries_a_contradicting_declaration(self):
        """What rides is read, never written.

        A leftover ``NOT_YET`` on a model that now rides is untidy but not a
        contradiction -- nobody claimed it should stay off -- so it is reported
        as housekeeping and asserted to still resolve as RIDES. A leftover
        ``HELD`` IS a contradiction and must never be present.
        """
        riding = set(rail_coverage.rail_models())
        held_and_riding = sorted(
            label
            for label in riding & set(DECLARATIONS)
            if DECLARATIONS[label].posture == HELD
        )
        self.assertEqual(
            held_and_riding,
            [],
            f"declared HELD yet registered on the live rail: {held_and_riding}",
        )
        for label in riding & set(DECLARATIONS):
            self.assertEqual(rail_coverage.posture_of(label), RIDES)

    def test_todays_declaration_carries_no_leftover_lines(self):
        """Housekeeping seal for the state as seeded on 2026-08-31."""
        report = rail_coverage.evaluate()
        self.assertEqual(
            report.stale_not_yet_now_riding,
            [],
            "delete these NOT_YET lines -- the models now ride: "
            f"{report.stale_not_yet_now_riding}",
        )

    def test_a_leftover_not_yet_on_a_riding_model_is_housekeeping_not_a_violation(self):
        riding = sorted(
            label
            for label in rail_coverage.rail_models()
            if label in rail_coverage.tenant_models()
        )
        self.assertTrue(riding)
        stale = dict(DECLARATIONS)
        stale[riding[0]] = Declaration(posture=NOT_YET)
        report = rail_coverage.evaluate(declarations=stale)
        self.assertIn(riding[0], report.stale_not_yet_now_riding)
        self.assertEqual(report.violations, [], "this must not fail the build")
        self.assertIn(riding[0], {m for a in report.apps for m in a.rides})

    def test_posture_of_answers_each_of_the_four_states(self):
        self.assertEqual(rail_coverage.posture_of("academics.attendance"), RIDES)
        self.assertEqual(rail_coverage.posture_of("finance.payment"), HELD)
        self.assertEqual(rail_coverage.posture_of("portal.announcement"), NOT_YET)
        self.assertEqual(rail_coverage.posture_of("nosuchapp.nosuchmodel"), UNDECLARED)


class RailCoverageHonestyTests(TestCase):
    """Property 3: HELD must be argued, NOT_YET must not pretend to be."""

    def test_held_entries_all_carry_a_rationale_and_a_pointer(self):
        held = {k: v for k, v in DECLARATIONS.items() if v.posture == HELD}
        self.assertTrue(held, "the seed should record at least the argued finance holds")
        for label, decl in held.items():
            self.assertTrue(decl.rationale.strip(), f"{label}: HELD with no rationale")
            self.assertTrue(decl.argued_in.strip(), f"{label}: HELD with no argued_in")

    def test_held_pointers_resolve_to_files_that_exist(self):
        """A rationale pointing at a deleted doc is a rationale nobody can check."""
        for label, decl in DECLARATIONS.items():
            if decl.posture != HELD:
                continue
            for ref in decl.argued_in.split(";"):
                ref = ref.strip()
                if not ref:
                    continue
                path = REPO_ROOT / ref.split("::", 1)[0].strip()
                self.assertTrue(
                    path.exists(),
                    f"{label}: argued_in points at {ref!r}, which does not exist",
                )

    def test_not_yet_entries_carry_no_argument(self):
        for label, decl in DECLARATIONS.items():
            if decl.posture != NOT_YET:
                continue
            self.assertEqual(decl.rationale, "", f"{label}: NOT_YET with a rationale")
            self.assertEqual(decl.argued_in, "", f"{label}: NOT_YET with a pointer")

    def test_a_held_without_a_rationale_is_a_violation(self):
        broken = dict(DECLARATIONS)
        broken["finance.paymentproofupload"] = Declaration(posture=HELD)
        report = rail_coverage.evaluate(declarations=broken)
        self.assertIn("held_without_rationale", _kinds(report))
        self.assertIn("held_without_pointer", _kinds(report))
        self.assertEqual(
            _findings(report, "held_without_rationale")[0]["model"],
            "finance.paymentproofupload",
        )

    def test_a_held_with_a_rationale_but_no_pointer_is_still_a_violation(self):
        broken = dict(DECLARATIONS)
        broken["finance.paymentproofupload"] = Declaration(
            posture=HELD, rationale="because I said so"
        )
        report = rail_coverage.evaluate(declarations=broken)
        self.assertIn("held_without_pointer", _kinds(report))
        self.assertNotIn("held_without_rationale", _kinds(report))

    def test_a_not_yet_carrying_a_rationale_is_a_violation(self):
        broken = dict(DECLARATIONS)
        broken["portal.announcement"] = Declaration(
            posture=NOT_YET, rationale="we thought about it a bit"
        )
        report = rail_coverage.evaluate(declarations=broken)
        self.assertIn("not_yet_with_rationale", _kinds(report))

    def test_a_hand_written_rides_posture_is_rejected(self):
        broken = dict(DECLARATIONS)
        broken["portal.announcement"] = Declaration(posture=RIDES)
        report = rail_coverage.evaluate(declarations=broken)
        self.assertIn("invalid_posture", _kinds(report))

    def test_a_declaration_naming_no_live_model_is_a_violation(self):
        broken = dict(DECLARATIONS)
        broken["portal.anouncement"] = Declaration(posture=NOT_YET)  # typo on purpose
        report = rail_coverage.evaluate(declarations=broken)
        kinds = _kinds(report)
        self.assertIn("unknown_model", kinds)
        self.assertEqual(_findings(report, "unknown_model")[0]["model"], "portal.anouncement")

    def test_declaring_a_riding_model_as_held_is_a_contradiction(self):
        """Someone wrote 'must not ride' and then wired it. That must not pass."""
        riding = sorted(
            label
            for label in rail_coverage.rail_models()
            if label in rail_coverage.tenant_models()
        )
        self.assertTrue(riding)
        broken = dict(DECLARATIONS)
        broken[riding[0]] = Declaration(
            posture=HELD, rationale="stale decision", argued_in="docs/EDGE_SYNC_FINANCE_HOLD.md"
        )
        report = rail_coverage.evaluate(declarations=broken)
        self.assertIn("held_but_riding", _kinds(report))
        self.assertEqual(_findings(report, "held_but_riding")[0]["model"], riding[0])


class RailCoverageDetectorBitesTests(TestCase):
    """Property 2: a NEW tenant model with no posture fails, for real.

    The model below is a genuine ``models.Model`` subclass registered into the
    LIVE ``django.apps`` registry under the tenant app ``student360`` -- the exact
    object ``tenant_models()`` enumerates. Nothing about the enumeration is
    mocked, so a zero from this auditor is only trustworthy because this test has
    seen it return non-zero.
    """

    APP_LABEL = "student360"
    MODEL_NAME = "railcoverageplantedmutation"

    @property
    def LABEL(self) -> str:
        return f"{self.APP_LABEL}.{self.MODEL_NAME}"

    def _planted(self):
        """Patch the enumeration to the REAL migration state PLUS one new model.

        A new tenant model reaches this gate as a new ``CreateModel`` migration,
        so that -- not a runtime ``type()`` call -- is the shape of the mutation
        worth planting. Only the source is stubbed, and it is stubbed with the
        genuine state plus one row; ``evaluate()``, the violation path and the
        auditor's ``main()`` all run for real against it.

        That the enumeration ITSELF is correct is proved separately and without
        any mocking by ``test_enumeration_sees_lazily_imported_models``, against
        three real lazily-imported models in the repo.
        """
        real = rail_coverage._migration_state_models()
        self.assertNotIn(self.LABEL, real)
        planted = dict(real)
        planted[self.LABEL] = self.APP_LABEL
        return mock.patch.object(
            rail_coverage, "_migration_state_models", return_value=planted
        )

    def test_a_newly_declared_tenant_model_is_reported_undeclared(self):
        before = rail_coverage.evaluate()
        self.assertEqual(before.total_undeclared, 0)
        with self._planted():
            self.assertIn(
                self.LABEL,
                rail_coverage.tenant_models(),
                "the plant did not reach the enumeration; this would prove nothing",
            )
            after = rail_coverage.evaluate()
            self.assertEqual(after.total_models, before.total_models + 1)
            self.assertEqual(after.total_undeclared, 1)
            self.assertIn("undeclared", _kinds(after))
            self.assertEqual(_findings(after, "undeclared")[0]["model"], self.LABEL)
            app = [a for a in after.apps if a.label == self.APP_LABEL][0]
            self.assertEqual(app.undeclared, [self.LABEL])

        healed = rail_coverage.evaluate()
        self.assertEqual(healed.total_models, before.total_models)
        self.assertEqual(healed.violations, [], "the plant was not fully removed")

    def test_the_auditor_script_exits_nonzero_on_the_plant(self):
        """End to end through the real ``main()``, i.e. the code CI runs."""
        spec = importlib.util.spec_from_file_location("_audit_rail_coverage", AUDITOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(module.sys, "argv", ["audit_rail_coverage.py"]):
            with redirect_stdout(out), redirect_stderr(err):
                clean_code = module.main()
        self.assertEqual(clean_code, 0, out.getvalue() + err.getvalue())

        with self._planted():
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(module.sys, "argv", ["audit_rail_coverage.py"]):
                with redirect_stdout(out), redirect_stderr(err):
                    planted_code = module.main()

        self.assertEqual(planted_code, 1, "the auditor passed a planted undeclared model")
        self.assertIn(f"[undeclared] {self.LABEL}", err.getvalue())

    def test_json_output_is_pure_json_on_stdout(self):
        """A trailing "OK: ..." line makes --json unparseable by anything.

        Found by piping the real command into ``json.load``: it raised
        ``Extra data: line 481``, so every machine consumer of this gate would
        have failed on a PASSING tree.
        """
        spec = importlib.util.spec_from_file_location("_audit_rail_coverage", AUDITOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for argv in (
            ["audit_rail_coverage.py", "--json"],
            ["audit_rail_coverage.py", "--json", "--compare"],
        ):
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(module.sys, "argv", argv):
                with redirect_stdout(out), redirect_stderr(err):
                    module.main()
            payload = json.loads(out.getvalue())  # raises if anything else printed
            self.assertIn("total_models", payload)
            self.assertIn("violations", payload)

    def test_update_baseline_refuses_over_a_broken_declaration(self):
        """A baseline written over a violation records the backlog as if sound."""
        spec = importlib.util.spec_from_file_location("_audit_rail_coverage", AUDITOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        before = BASELINE.read_bytes()
        with self._planted():
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(
                module.sys, "argv", ["audit_rail_coverage.py", "--update-baseline"]
            ):
                with redirect_stdout(out), redirect_stderr(err):
                    code = module.main()

        self.assertEqual(code, 1)
        self.assertIn("refusing to write a baseline", err.getvalue())
        self.assertEqual(
            BASELINE.read_bytes(), before, "the baseline was rewritten anyway"
        )


class RailCoverageIsDerivedTests(TestCase):
    """Property 4: RIDES tracks the live registry, with no edit here."""

    def test_rides_equals_the_live_registry_restricted_to_tenant_apps(self):
        report = rail_coverage.evaluate()
        tenant_labels = set(rail_coverage.tenant_app_labels())
        expected = sorted(
            label
            for label in rail_coverage.rail_models()
            if label.split(".", 1)[0] in tenant_labels
        )
        actual = sorted(m for a in report.apps for m in a.rides)
        self.assertEqual(actual, expected)

    def test_registering_a_new_entity_changes_the_report_with_no_declaration_edit(self):
        """The whole point: the RIDES set is read, not transcribed."""
        before = rail_coverage.evaluate()
        payroll_before = [a for a in before.apps if a.label == "payroll"][0]
        self.assertEqual(payroll_before.rides, [])
        self.assertIn("payroll.payscale", payroll_before.not_yet)

        patched = list(sync_services._DERIVED_ENTITY_SPECS) + [
            ("pay_scale", "payroll", "PayScale")
        ]
        with mock.patch.object(sync_services, "_DERIVED_ENTITY_SPECS", patched):
            after = rail_coverage.evaluate()

        self.assertEqual(after.total_rides, before.total_rides + 1)
        payroll_after = [a for a in after.apps if a.label == "payroll"][0]
        self.assertEqual(payroll_after.rides, ["payroll.payscale"])
        self.assertNotIn("payroll.payscale", payroll_after.not_yet)
        self.assertEqual(after.total_not_yet, before.total_not_yet - 1)
        # Crucially: registering an entity never FAILS the build. The leftover
        # NOT_YET line is reported as housekeeping, not as a violation.
        self.assertEqual(after.violations, [])
        self.assertIn("payroll.payscale", after.stale_not_yet_now_riding)

        restored = rail_coverage.evaluate()
        self.assertEqual(restored.total_rides, before.total_rides)

    def test_rail_config_accessor_is_resolved_by_name_not_hard_bound(self):
        config = rail_coverage.rail_entity_config()
        self.assertIn("attendance", config)
        self.assertGreaterEqual(len(config), 15)

    def test_shared_app_rail_entities_are_not_counted_as_business_coverage(self):
        """sync_schedule / sync_policy are the rail's OWN config, not school data."""
        report = rail_coverage.evaluate()
        tenant_labels = set(rail_coverage.tenant_app_labels())
        for label in report.rides_outside_tenant_apps:
            self.assertNotIn(label.split(".", 1)[0], tenant_labels)
        counted = {m for a in report.apps for m in a.rides}
        self.assertEqual(counted & set(report.rides_outside_tenant_apps), set())
        self.assertIn("sync_engine.syncschedule", report.rides_outside_tenant_apps)
        self.assertIn("sync_engine.syncpolicy", report.rides_outside_tenant_apps)


class RailCoverageTenantAppsResolutionTests(TestCase):
    """The denominator must survive both deployment modes."""

    def test_tenant_apps_are_read_from_the_settings_source(self):
        labels = rail_coverage.tenant_app_labels()
        self.assertIn("finance", labels)
        self.assertIn("academics", labels)
        self.assertIn("studio_os", labels)
        self.assertEqual(len(labels), len(set(labels)))

    def test_resolution_does_not_depend_on_the_setting_being_defined(self):
        """``TENANT_APPS`` only exists under ``USE_DJANGO_TENANTS``.

        Under the default ``config.settings`` the attribute is absent, so an
        auditor that read ``settings.TENANT_APPS`` would report ZERO tenant
        models on a developer's machine and in the RLS-mode CI job -- a green
        result that means nothing.
        """
        from django.conf import settings

        # This assertion is the finding, not a formality: the attribute really is
        # missing under the settings this repo's pytest runs with.
        self.assertFalse(
            hasattr(settings, "TENANT_APPS"),
            "config.settings now defines TENANT_APPS; the note above needs revisiting",
        )
        labels = rail_coverage.tenant_app_labels()
        self.assertGreaterEqual(len(labels), 15)
        self.assertEqual(
            labels,
            [
                rail_coverage._app_label(d)
                for d in rail_coverage._tenant_apps_from_settings_source()
            ],
        )

    def test_enumeration_sees_lazily_imported_models(self):
        """Regression seal for the defect that made this gate's first zero a lie.

        apps/portal/models_forums.py defines three MIGRATED tenant models but is
        imported lazily by views_forums.py, not by portal/models.py. The first
        version of tenant_models() walked the runtime app registry, so on a cold
        process it returned 323 tenant models instead of 326, the seeded
        DECLARATIONS silently missed all three, and the auditor reported a
        confident "0 undeclared" against an incomplete denominator. It only
        surfaced when the whole apps/sync_engine/tests/ directory ran in one
        process -- some earlier test imported a forum view and six of these
        tests went red.
        """
        models = rail_coverage.tenant_models()
        for label in (
            "portal.communityforumcategory",
            "portal.communityforumtopic",
            "portal.communityforumreply",
        ):
            self.assertIn(
                label,
                models,
                "the enumeration regressed to a runtime-registry walk and is no "
                "longer import-order-proof",
            )
            self.assertEqual(rail_coverage.posture_of(label), NOT_YET)

    def test_never_migrated_classes_are_not_counted(self):
        """apps/evals/models_enhanced.py has 12 classes and zero migrations.

        They have no tables, so they cannot ride anything and must not inflate
        either the denominator or the backlog.
        """
        models = rail_coverage.tenant_models()
        for label in (
            "evals.gradeimportjob",
            "evals.gradeimportrowlog",
            "evals.evaluationdelta",
            "evals.competencyrubric",
        ):
            self.assertNotIn(label, models)

    def test_enumeration_is_stable_across_calls(self):
        self.assertEqual(rail_coverage.tenant_models(), rail_coverage.tenant_models())

    def test_an_unparseable_settings_path_yields_nothing_rather_than_lying(self):
        missing = REPO_ROOT / "config" / "no_such_settings_file.py"
        self.assertEqual(rail_coverage.tenant_app_labels(path=missing), [])


class RailCoverageBaselineTests(TestCase):
    """The ``--compare`` baseline is the house pattern; keep it truthful."""

    def test_baseline_exists_and_is_readable(self):
        self.assertTrue(BASELINE.exists(), f"missing baseline: {BASELINE}")
        json.loads(BASELINE.read_text(encoding="utf-8"))

    def test_baseline_lists_only_live_tenant_models(self):
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
        live = set(rail_coverage.tenant_models())
        stale = sorted(m for m in data["not_yet"] if m not in live)
        self.assertEqual(stale, [], f"baseline names models that no longer exist: {stale}")

    def test_current_backlog_does_not_exceed_the_baseline(self):
        """A NEW NOT_YET must be a deliberate, visible act -- not a side effect."""
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
        known = set(data["not_yet"])
        report = rail_coverage.evaluate()
        grown = sorted(m for m in report.not_yet_labels if m not in known)
        self.assertEqual(
            grown,
            [],
            "the undecided backlog grew without a baseline update; either declare a "
            f"posture with an argument, put it on the rail, or update the baseline: {grown}",
        )
