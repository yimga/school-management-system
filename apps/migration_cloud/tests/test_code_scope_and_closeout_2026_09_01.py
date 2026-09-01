"""Closeout guards for the 2026-09-01 repo audit (Agent M scope).

Five findings, one file, because each of them is a claim that was TRUE in a comment
and FALSE in the code, and the only thing that keeps those apart is a test that runs.

1. THE REAL ONE -- a tenant-isolation marker justified by a false premise.

   ``specialty_lander._pick_code`` asked ``model.objects.filter(code=sc).exists()``
   under this marker:

       # tenant-isolation-allow: code is a GLOBALLY-unique column;
       #                         global existence check is intentional

   The premise is false, and has been since academics migration 0076 (Department)
   and 0085 (Classroom + Specialty). All three declare
   ``UniqueConstraint(fields=["school", "code"])``. There is no global unique index
   on ``code`` left anywhere in academics.

   So the lander asked a GLOBAL question about a PER-SCHOOL column, and the answer
   changed what another tenant got: with school A holding ``EPS``, school B's import
   of its own ``EPS`` silently received a minted ``SPC...`` code instead. One
   tenant's rows deciding another tenant's import result -- underneath a marker
   whose entire function is to tell a reviewer not to look here. That is the
   finding, and ``AnotherSchoolsCodeMustNotVetoThisImportTests`` is the proof: it
   fails on the pre-fix code and passes on the fixed code.

   Severity, stated honestly: no row is lost and no IntegrityError is raised. The
   source code survives in ``DynamicFieldValue`` either way. What is lost is the
   human-meaningful code the school actually uses, non-deterministically, depending
   on what an unrelated tenant did first -- and the reviewer's chance of noticing.

2. ``template_runtime`` held a bare ``assert``, stripped under ``python -O``.
3. ``_pairing_error_message`` had no ``school_already_paired`` branch.
4. ``mint_claim_ticket`` discarded the refusal body the service returns.
5. ``compensating_control_violations()`` only ever ran inside a test.
"""

from __future__ import annotations

import ast
import inspect
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.db import IntegrityError, models, transaction
from django.test import SimpleTestCase, TestCase

from apps.academics.models import Classroom, Department, Specialty
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.specialty_lander import SpecialtyLander, _pick_code
from apps.schools.models import School

CODE_MODELS = (Department, Specialty, Classroom)


def _school(tag: str) -> School:
    # A blank subdomain is itself a value and the column is unique, so a second
    # School.objects.create() with no subdomain crashes. Always pass a distinct one.
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(name=f"School {slug}", slug=slug, subdomain=slug)


def _unique_constraint_fields(model) -> list:
    return [
        tuple(c.fields)
        for c in model._meta.constraints
        if isinstance(c, models.UniqueConstraint)
    ]


# --------------------------------------------------------------------------- #
# 1a. The premise, checked against the models rather than against a comment.
# --------------------------------------------------------------------------- #
class CodeUniquenessIsDeclaredPerSchoolTests(SimpleTestCase):
    """What the three models ACTUALLY declare.

    Checked one model at a time and not assumed to match each other: Department
    moved in 0076 and the other two only in 0085, so "they are all the same" was
    itself an assumption worth failing on.
    """

    def test_no_code_column_is_globally_unique(self):
        globally_unique = [
            m.__name__ for m in CODE_MODELS if m._meta.get_field("code").unique
        ]
        self.assertEqual(
            globally_unique,
            [],
            "a code column is globally unique again -- the lander's school-scoped "
            "existence check assumes it is not",
        )

    def test_every_code_column_is_unique_per_school(self):
        for model in CODE_MODELS:
            with self.subTest(model=model.__name__):
                self.assertIn(
                    ("school", "code"),
                    _unique_constraint_fields(model),
                    f"{model.__name__} no longer declares UniqueConstraint(school, code)",
                )

    def test_the_named_constraints_are_the_ones_the_migrations_added(self):
        """Names, not just shapes: the corrected docstrings cite these by name."""
        expected = {
            Department: "uniq_department_school_code",
            Specialty: "uniq_specialty_school_code",
            Classroom: "uniq_classroom_school_code",
        }
        for model, name in expected.items():
            with self.subTest(model=model.__name__):
                self.assertIn(name, [c.name for c in model._meta.constraints])


class TheFalseJustificationIsGoneTests(SimpleTestCase):
    """The marker text, and the prose that repeated it.

    A comment is the only artefact here that a reviewer reads INSTEAD of the code,
    so a false one is worse than none. These assert the specific false sentences are
    gone and the scoped check is present -- not merely that "something changed".
    """

    def _source(self, dotted: str) -> str:
        import importlib

        return Path(importlib.import_module(dotted).__file__).read_text(
            encoding="utf-8"
        )

    def test_pick_code_scopes_its_existence_check_to_the_school(self):
        src = inspect.getsource(_pick_code)
        self.assertIn("filter(school=school, code=sc)", src)
        self.assertNotIn(
            "objects.filter(code=sc)",
            src,
            "the existence check is global again: another tenant's code can veto "
            "this school's import",
        )

    def test_pick_code_no_longer_claims_a_global_unique(self):
        src = inspect.getsource(_pick_code)
        self.assertNotIn("GLOBALLY-unique column", src)
        self.assertNotIn("tenant-isolation-allow", src)

    def test_the_specialty_lander_docstring_states_the_real_constraint(self):
        src = self._source("apps.migration_cloud.landers.specialty_lander")
        self.assertNotIn("are GLOBALLY unique", src)
        self.assertIn("uniq_specialty_school_code", src)

    def test_the_structure_lander_prose_states_the_real_constraint(self):
        src = self._source("apps.migration_cloud.landers.structure_lander")
        self.assertNotIn("GLOBALLY-unique ``code``", src)
        self.assertIn("uniq_classroom_school_code", src)


# --------------------------------------------------------------------------- #
# 1b. The premise, checked against the DATABASE.
# --------------------------------------------------------------------------- #
class CodeUniquenessIsPerSchoolInTheDatabaseTests(TestCase):
    """Meta is not the index. This asks the engine the tests actually run on."""

    @classmethod
    def setUpTestData(cls):
        cls.a = _school("scope-a")
        cls.b = _school("scope-b")
        cls.dept_a = Department.objects.create(
            school=cls.a, name="Gen A", code="GEN-A"
        )
        cls.dept_b = Department.objects.create(
            school=cls.b, name="Gen B", code="GEN-B"
        )

    def test_the_fixture_really_is_two_schools(self):
        # Calibration: if both halves wrote to one school, "no collision" proves
        # nothing at all.
        self.assertNotEqual(self.a.pk, self.b.pk)

    def test_two_schools_may_hold_the_same_department_code(self):
        Department.objects.create(school=self.a, name="Electrical", code="ELEC")
        Department.objects.create(school=self.b, name="Electrical", code="ELEC")
        self.assertEqual(Department.objects.filter(code="ELEC").count(), 2)

    def test_two_schools_may_hold_the_same_specialty_code(self):
        Specialty.objects.create(
            school=self.a, department=self.dept_a, name="Power A", code="EPS"
        )
        Specialty.objects.create(
            school=self.b, department=self.dept_b, name="Power B", code="EPS"
        )
        self.assertEqual(Specialty.objects.filter(code="EPS").count(), 2)

    def test_one_school_still_may_not_reuse_a_specialty_code(self):
        """The loosening is per-school, not "no uniqueness at all" -- and that half
        is why the scoped check in the lander is still necessary."""
        Specialty.objects.create(
            school=self.a, department=self.dept_a, name="Arts", code="ART"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Specialty.objects.create(
                    school=self.a, department=self.dept_a, name="Arts II", code="ART"
                )

    def test_one_school_still_may_not_reuse_a_department_code(self):
        Department.objects.create(school=self.a, name="Building", code="BLD")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Department.objects.create(
                    school=self.a, name="Building II", code="BLD"
                )


# --------------------------------------------------------------------------- #
# 1c. THE FINDING: the interference itself, through the real lander.
# --------------------------------------------------------------------------- #
class AnotherSchoolsCodeMustNotVetoThisImportTests(TestCase):
    """School A's catalogue must not change what School B's import produces.

    Every test here runs the real ``SpecialtyLander`` against the real models. The
    only thing that varies between them is what SCHOOL A happens to hold first.
    """

    def setUp(self):
        self.a = _school("veto-a")
        self.b = _school("veto-b")
        self.dept_a = Department.objects.create(
            school=self.a, name="Electrical A", code="ELEC-A"
        )
        self.dept_b = Department.objects.create(
            school=self.b, name="Electrical Power", code="ELEC-B"
        )

    def _ctx(self, school) -> LanderContext:
        return LanderContext(
            school=school, schema_name="", bundle_id=None, artifact_id=None
        )

    def _land_into_b(self, code="EPS"):
        row = {
            "name": "ELECTRICAL POWER SYSTEMS",
            "code": code,
            "department": "Electrical Power",
            "description": "",
        }
        return SpecialtyLander().land(
            canonical_rows=iter([row]), ctx=self._ctx(self.b)
        )

    def _b_specialty(self) -> Specialty:
        return Specialty.objects.get(school=self.b, name="ELECTRICAL POWER SYSTEMS")

    # ---- control -----------------------------------------------------------
    def test_control_with_no_foreign_row_the_source_code_is_kept(self):
        """Vacuity guard. Without it the test below could 'pass' for the wrong
        reason -- a lander that never keeps a source code proves nothing about
        tenants."""
        result = self._land_into_b()
        self.assertEqual(result.errors, [])
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(self._b_specialty().code, "EPS")

    # ---- the finding -------------------------------------------------------
    def test_a_foreign_schools_code_does_not_veto_this_schools_import(self):
        """THE REGRESSION GUARD. Pre-fix, the landed code was ``SPC...``, not ``EPS``."""
        foreign = Specialty.objects.create(
            school=self.a, department=self.dept_a, name="Power Systems", code="EPS"
        )

        result = self._land_into_b()

        self.assertEqual(result.errors, [])
        self.assertEqual(result.quarantined, 0)
        landed = self._b_specialty()
        self.assertEqual(
            landed.code,
            "EPS",
            "school A holding 'EPS' changed what school B's import produced -- a "
            "global existence check on a per-school unique column",
        )
        # And the database accepted both, which is the whole point: the check the
        # lander was making was stricter than the constraint it claimed to serve.
        self.assertEqual(Specialty.objects.filter(code="EPS").count(), 2)
        # School A is untouched -- the fix must not reach across either.
        foreign.refresh_from_db()
        self.assertEqual(foreign.code, "EPS")
        self.assertEqual(foreign.school_id, self.a.pk)

    def test_the_two_rows_belong_to_the_schools_that_imported_them(self):
        Specialty.objects.create(
            school=self.a, department=self.dept_a, name="Power Systems", code="EPS"
        )
        self._land_into_b()
        owners = set(
            Specialty.objects.filter(code="EPS").values_list("school_id", flat=True)
        )
        self.assertEqual(owners, {self.a.pk, self.b.pk})

    # ---- the narrowing must not become "no check" --------------------------
    def test_this_schools_own_code_still_forces_a_mint(self):
        """The other half. Scoping the check must not disable it: within ONE school
        the code is still unique, so a taken code must still mint rather than raise."""
        Specialty.objects.create(
            school=self.b, department=self.dept_b, name="Something Else", code="EPS"
        )

        result = self._land_into_b()

        self.assertEqual(result.errors, [])
        self.assertEqual(result.quarantined, 0)
        landed = self._b_specialty()
        self.assertNotEqual(landed.code, "EPS")
        self.assertTrue(
            landed.code.startswith("SPC"),
            f"expected a minted SPC... code, got {landed.code!r}",
        )

    def test_a_taken_code_inside_this_school_is_preserved_not_lost(self):
        """No data loss: when a mint is forced, the source code still lands in the
        DynamicFieldValue engine."""
        from apps.metadata.models import DynamicFieldValue

        Specialty.objects.create(
            school=self.b, department=self.dept_b, name="Something Else", code="EPS"
        )
        self._land_into_b()
        landed = self._b_specialty()
        self.assertTrue(
            DynamicFieldValue.objects.filter(
                school=self.b,
                entity_type="specialty",
                entity_id=str(landed.pk),
                field_key="source_code",
            ).exists()
        )

    def test_the_scoped_check_reads_the_school_it_was_given(self):
        """Unit-level companion: the helper itself, with no lander around it."""
        Specialty.objects.create(
            school=self.a, department=self.dept_a, name="Power Systems", code="EPS"
        )
        kept = _pick_code(
            model=Specialty, source_code="EPS", prefix="SPC", name="X", school=self.b
        )
        minted = _pick_code(
            model=Specialty, source_code="EPS", prefix="SPC", name="X", school=self.a
        )
        self.assertEqual(kept, "EPS")
        self.assertNotEqual(minted, "EPS")


# --------------------------------------------------------------------------- #
# 2. A bare assert in production code.
# --------------------------------------------------------------------------- #
class TemplateRuntimeHasNoStrippableAssertTests(SimpleTestCase):
    def _module_source(self) -> str:
        from apps.brand_experience import template_runtime

        return Path(template_runtime.__file__).read_text(encoding="utf-8")

    def test_the_module_contains_no_assert_statement(self):
        """``python -O`` removes every ``ast.Assert``. A guard that vanishes in the
        mode production runs under is not a guard, so the count must be zero rather
        than merely documented."""
        tree = ast.parse(self._module_source())
        asserts = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Assert)]
        self.assertEqual(asserts, [], f"assert statements survive at lines {asserts}")

    def test_the_missing_pack_branch_raises_instead(self):
        """The replacement actually fires, on the SECOND, independent registry
        lookup inside ``activate_experience_template``."""
        from apps.brand_experience import template_runtime

        with patch.object(
            template_runtime,
            "build_experience_runtime_payload",
            return_value={"surface": "dashboard"},
        ), patch.object(template_runtime, "get_pack", return_value=None):
            with self.assertRaises(template_runtime.ExperienceRuntimeError) as ctx:
                template_runtime.activate_experience_template(
                    school=None, template_key="whatever"
                )
        self.assertIn("not registered", str(ctx.exception))


class TemplateRuntimeGuardIsNotVacuousTests(TestCase):
    """Control for the test above: a pack that IS found must get PAST the guard.

    Without this, a function that raised unconditionally would look identical.
    """

    def test_a_found_pack_proceeds_to_the_installation_lookup(self):
        from apps.brand_experience import template_runtime

        with patch.object(
            template_runtime,
            "build_experience_runtime_payload",
            return_value={"surface": "dashboard"},
        ), patch.object(
            template_runtime,
            "get_pack",
            return_value=SimpleNamespace(version="1.0.0"),
        ):
            with self.assertRaises(template_runtime.ExperienceRuntimeError) as ctx:
                template_runtime.activate_experience_template(
                    school=None, template_key="whatever"
                )
        # A DIFFERENT refusal, raised further down -- so the guard let it through.
        self.assertIn("No active InstalledPackage", str(ctx.exception))


# --------------------------------------------------------------------------- #
# 3. The missing pairing branch.
# --------------------------------------------------------------------------- #
class PairingRefusalIsActionableTests(SimpleTestCase):
    GENERIC = "The pairing request could not be updated."

    def _message(self, result: dict) -> str:
        from apps.siteconfig.views_sync_center import _pairing_error_message

        return str(_pairing_error_message(result))

    def test_the_service_still_emits_the_code_the_view_branches_on(self):
        """Pins the two halves together: a renamed constant fails here, rather than
        in production as a generic message."""
        from apps.sync_engine.pairing_service import ALREADY_PAIRED

        self.assertEqual(ALREADY_PAIRED, "school_already_paired")

    def test_already_paired_uses_the_services_own_words(self):
        from apps.sync_engine.pairing_service import ALREADY_PAIRED

        spoken = "Revoke its device in the operator console, then pair this one."
        self.assertEqual(
            self._message({"error": ALREADY_PAIRED, "message": spoken}), spoken
        )

    def test_already_paired_without_a_message_still_says_what_to_do(self):
        from apps.sync_engine.pairing_service import ALREADY_PAIRED

        msg = self._message({"error": ALREADY_PAIRED})
        self.assertNotEqual(msg, self.GENERIC)
        self.assertIn("revoke", msg.lower())

    def test_binding_check_unavailable_says_it_is_safe_to_retry(self):
        from apps.sync_engine.pairing_service import BINDING_CHECK_UNAVAILABLE

        msg = self._message({"error": BINDING_CHECK_UNAVAILABLE})
        self.assertNotEqual(msg, self.GENERIC)
        self.assertIn("retry", msg.lower())

    def test_an_unrecognised_code_still_falls_through_to_the_generic_line(self):
        """Calibration: the generic line still exists, so the assertions above are
        distinguishing something."""
        self.assertEqual(self._message({"error": "something_new"}), self.GENERIC)

    def test_the_existing_branches_are_untouched(self):
        self.assertIn("expired", self._message({"error": "expired"}).lower())


# --------------------------------------------------------------------------- #
# 4. The dropped refusal body.
# --------------------------------------------------------------------------- #
class MintClaimTicketSurfacesTheReasonTests(SimpleTestCase):
    def _text(self, result: dict) -> str:
        from apps.sync_engine.management.commands.mint_claim_ticket import (
            _refusal_text,
        )

        return _refusal_text(
            result,
            user=SimpleNamespace(username="admin"),
            school=SimpleNamespace(slug="gilead-tech"),
        )

    def test_the_service_message_reaches_the_operator(self):
        spoken = "Release the existing box first: revoke its device."
        text = self._text(
            {
                "ok": False,
                "error": "school_already_paired",
                "message": spoken,
                "bound_device_ids": ["box-alpha"],
            }
        )
        self.assertIn(spoken, text)
        self.assertIn("box-alpha", text)
        self.assertIn("school_already_paired", text)

    def test_a_refusal_is_never_printed_as_a_bare_code(self):
        text = self._text({"ok": False, "error": "something_unmapped"})
        self.assertIn("gilead-tech", text)
        self.assertIn("something_unmapped", text)
        self.assertNotEqual(text.strip(), "something_unmapped")

    def test_the_written_fallbacks_still_apply(self):
        text = self._text({"ok": False, "error": "forbidden"})
        self.assertIn("does not administer", text)

    def test_a_missing_error_key_does_not_produce_a_blank_reason(self):
        text = self._text({"ok": False})
        self.assertIn("unknown_error", text)


# --------------------------------------------------------------------------- #
# 5. The promotion.
# --------------------------------------------------------------------------- #
def _load_gate():
    from apps.platform_runtime.tests.support.script_loading import load_repo_script

    return load_repo_script(
        "scripts/verify_sync_semantics.py", "rmc_closeout_verify_sync_semantics"
    )


class CompensatingControlCheckIsARealGateTests(SimpleTestCase):
    def test_the_gate_defines_the_check(self):
        gate = _load_gate()
        self.assertTrue(callable(gate.compensating_control_violations))
        self.assertTrue(callable(gate.cursor_overlap_floor_seconds))
        self.assertEqual(gate.PARITY_INTERVAL_CEILING_SECONDS, 6 * 60 * 60)

    def test_the_gate_actually_runs_it(self):
        """A promotion nobody calls is a move, not a promotion."""
        gate = _load_gate()
        self.assertIn("compensating_control_violations()", inspect.getsource(gate.main))

    def test_a_failure_of_the_check_fails_the_gate(self):
        """The violations must reach ``errors``, which is what returns 1."""
        src = inspect.getsource(_load_gate().main)
        self.assertIn("errors.extend(compensating_control_violations())", src)

    def test_the_test_module_uses_the_gates_definition_not_a_copy(self):
        """Identity by ORIGIN, not by object: ``load_repo_script`` execs a fresh
        module per call, so two loads are never the same function object. What must
        hold is that the test module's callable was compiled from the gate file --
        i.e. there is one definition in the tree, not two that can drift."""
        from apps.sync_engine.tests import (
            test_accepted_risk_compensating_controls_2026_08_31 as mod,
        )

        origin = Path(mod.compensating_control_violations.__code__.co_filename)
        self.assertEqual(origin.name, "verify_sync_semantics.py")
        self.assertEqual(origin.parent.name, "scripts")

    def test_the_test_module_no_longer_defines_its_own(self):
        from apps.sync_engine.tests import (
            test_accepted_risk_compensating_controls_2026_08_31 as mod,
        )

        src = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("def compensating_control_violations", src)
        self.assertNotIn("def cursor_overlap_floor_seconds", src)
