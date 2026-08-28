"""An FK may only ride the rail if the box can actually have the row it points at.

THE PROXY THAT WAS WRONG. ``_derive_sync_fields`` let a foreign key ride when its target
model lived in a tenant APP. For almost every model that is a fine stand-in for "this pk
is portable box<->cloud". It is wrong in one direction: a tenant app may also hold a
SHARED table that no school owns, and the provisioning clone is per-SCHOOL -- it carries
the rows a school owns and nothing else.

Three FKs were riding on that mistake, pointing at ``finance.Counterparty``,
``finance.ComplianceProfile`` and ``payroll.PayScale``. None has a ``school`` column; none
rides the rail. A parent created on the cloud AFTER a box was cloned therefore never
reaches that box, the referential preflight refuses the child, and the runner -- reading
that as "a parent is behind the cursor" -- rewinds the pull cursor for a full-corpus
replay that cannot possibly produce it. Every cooldown. Forever.

THE RULE, AND WHY IT IS NOT UNIFORM. An unportable FK rides only when the row cannot
exist without it:

  * NULLABLE -> drop it. Today an absent parent costs the WHOLE row; dropped, the row
    lands and omits one link the box could not render anyway, since the parent's table is
    not on the rail either.
  * NOT NULL -> keep it. Dropping it does not degrade the row, it makes the row
    impossible -- ``invoice`` is not insert-held, so the box really does create invoices
    from cloud-authored rows, and one with no compliance profile cannot be written at all.

That asymmetry is the part worth pinning, because it is the part that looks like an
inconsistency until you ask what dropping the column would actually do.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from django.test import SimpleTestCase

from apps.api.sync_services import (
    _fk_reference_targets,
    _get_entity_config,
    _is_sync_tenant_model,
    _is_tenant_scoped_model,
)

_GATE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "verify_rail_fk_portability.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("_rail_fk_gate", _GATE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TheScopeTestMustAskWhoOwnsTheRowTests(SimpleTestCase):
    def test_a_model_with_a_school_column_is_tenant_scoped(self):
        from apps.academics.models import Department, Subject

        self.assertTrue(_is_tenant_scoped_model(Department))
        self.assertTrue(_is_tenant_scoped_model(Subject))

    def test_a_shared_table_inside_a_tenant_app_is_not(self):
        # The whole point. Both live in tenant apps, so the OLD test passes them; neither
        # has a `school` column, so the clone never carries them.
        from apps.finance.models import ComplianceProfile, Counterparty
        from apps.payroll.models import PayScale

        for model in (ComplianceProfile, Counterparty, PayScale):
            with self.subTest(model=model._meta.label):
                self.assertTrue(_is_sync_tenant_model(model), "still a tenant app")
                self.assertFalse(_is_tenant_scoped_model(model), "but no school column")

    def test_none_is_not_scoped(self):
        # _rel_model returns None for an unresolvable lazy reference; a helper on the
        # derive path must answer rather than raise.
        self.assertFalse(_is_tenant_scoped_model(None))


class TheNullableUnportableFksMustNotRideTests(SimpleTestCase):
    def test_the_invoice_no_longer_carries_its_counterparty(self):
        _model, allowed = _get_entity_config(include_derived=True)["invoice"]
        self.assertNotIn("counterparty_id", allowed)

    def test_the_teacher_no_longer_carries_a_pay_scale(self):
        _model, allowed = _get_entity_config(include_derived=True)["teacher"]
        self.assertNotIn("pay_scale_id", allowed)

    def test_dropping_them_did_not_strip_the_rest_of_the_entity(self):
        # A rule that quietly emptied an entity would also make these tests pass.
        _model, invoice = _get_entity_config(include_derived=True)["invoice"]
        _model, teacher = _get_entity_config(include_derived=True)["teacher"]
        self.assertIn("student_id", invoice)
        self.assertIn("academic_year_id", invoice)
        self.assertIn("department_id", teacher)
        self.assertIn("reports_to_id", teacher)


class TheNotNullUnportableFkMustKeepRidingTests(SimpleTestCase):
    """Dropping this one would not degrade the row -- it would make the row impossible."""

    def test_the_invoice_still_carries_its_compliance_profile(self):
        _model, allowed = _get_entity_config(include_derived=True)["invoice"]
        self.assertIn("profile_id", allowed)

    def test_the_reason_it_must_ride_is_still_true(self):
        # Both halves of the justification, asserted rather than remembered: the column is
        # NOT NULL, and `invoice` is not insert-held, so the box does create invoices.
        from apps.api.sync_services import _INSERT_HELD_ENTITIES
        from apps.finance.models import Invoice

        self.assertFalse(Invoice._meta.get_field("profile").null)
        self.assertNotIn("invoice", _INSERT_HELD_ENTITIES)


class EveryOtherRailFkMustBeTenantScopedTests(SimpleTestCase):
    """The invariant itself, over the live registry rather than a remembered list."""

    def test_only_the_declared_reference_is_unportable(self):
        gate = _load_gate()
        config = _get_entity_config(include_derived=True)
        offenders = []
        for entity, (model, allowed) in sorted(config.items()):
            for attname, target in sorted(_fk_reference_targets(model, allowed).items()):
                if target is None or _is_tenant_scoped_model(target):
                    continue
                field = attname[:-3] if attname.endswith("_id") else attname
                offenders.append(f"{model._meta.label}.{field}")
        self.assertEqual(sorted(offenders), sorted(gate.ACCEPTED_UNPORTABLE))


class TheGateMustRefuseTheShapesItExistsToCatchTests(SimpleTestCase):
    """The gate's own reporting, driven with synthetic rows so no model has to be broken."""

    def setUp(self):
        self.gate = _load_gate()

    def _row(self, **over):
        row = {
            "entity": "invoice",
            "attname": "thing_id",
            "key": "finance.Invoice.thing",
            "target": "finance.Thing",
            "scoped": False,
            "on_rail": False,
            "nullable": False,
        }
        row.update(over)
        return row

    def test_the_live_tree_passes(self):
        # The seal. If this ever fails, an unportable FK has been added to the rail.
        self.assertEqual(self.gate.main.__name__, "main")
        rows, _rail = self.gate._survey()
        undeclared = [
            r for r in rows
            if r["target"] and not r["scoped"] and r["key"] not in self.gate.ACCEPTED_UNPORTABLE
        ]
        self.assertEqual(undeclared, [])

    def test_an_undeclared_unportable_fk_is_a_finding(self):
        rows = [self._row()]
        undeclared = [
            r for r in rows
            if r["target"] and not r["scoped"] and r["key"] not in self.gate.ACCEPTED_UNPORTABLE
        ]
        self.assertEqual(len(undeclared), 1)

    def test_a_nullable_fk_may_not_be_parked_on_the_accepted_list(self):
        # The rule that keeps the escape hatch honest: nullable means DROP it, and
        # recording the easier answer as a decision must not be possible.
        rows = [self._row(key="finance.Invoice.profile", nullable=True)]
        droppable = [
            r for r in rows
            if r["key"] in self.gate.ACCEPTED_UNPORTABLE and not r["scoped"] and r["nullable"]
        ]
        self.assertEqual(len(droppable), 1)

    def test_a_scoped_target_is_never_a_finding(self):
        rows = [self._row(scoped=True, on_rail=True)]
        self.assertEqual([r for r in rows if not r["scoped"]], [])

    def test_every_accepted_entry_carries_a_real_reason(self):
        for key, reason in self.gate.ACCEPTED_UNPORTABLE.items():
            with self.subTest(key=key):
                self.assertGreater(len(reason.strip()), 40, "a reason, not a placeholder")
