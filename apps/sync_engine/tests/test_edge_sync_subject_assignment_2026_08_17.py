"""Edge parity Slice 4 — the teaching grid (``academics.SubjectAssignment``) rides the
edge sync rail, so a term's gradeable slots exist on a sovereign box.

Locks: (1) the entity is REGISTERED with its expected auto-derived fields; (2) it is
benign LWW master data (NOT protected / down-only); (3) all five FKs remap onto
registered entities, so a new-references-new insert resolves on the operator; (4) a real
build->rewind->apply round-trip lands the cloud value on the box.

It ALSO carries the regression seal for the many-to-many hole this slice uncovered.
Django reports an M2M as concrete+editable, so ``_derive_sync_fields`` used to hand
``teachers`` to the rail. That breaks both directions — the outbox ``getattr``s each
allowed field and an M2M yields a ManyRelatedManager the bundle cannot JSON-serialize,
and since ONE bundle packs EVERY registered entity, that single column would take down
the whole push/pull cycle rather than just this entity; inbound, an M2M in
``save(update_fields=[...])`` is a FieldError. SubjectAssignment is the first DERIVED
entity to own an M2M, so the hole was latent until now (``student`` has one but uses a
curated field set). The cross-entity test below fails for ANY future entity that
reintroduces it.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.api.sync_services import (
    _get_entity_config,
    _insert_fk_targets,
    _sync_conflict_policy,
)
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import verify_and_parse_bundle
from apps.sync_engine.edge_inbox import apply_pulled_bundle
from apps.sync_engine.edge_outbox import build_edge_delta_bundle
from apps.sync_engine.policy_registry import MergeStrategy

_SIGN_KEY = "edge-teaching-grid-test-key"
_ENTITY = "subject_assignment"


def _rows(bundle_bytes, school_id, entity_type):
    rows, errors = verify_and_parse_bundle(bundle_bytes, expected_school_id=school_id)
    assert not errors, errors
    return [r for r in rows if r.get("entity_type") == entity_type]


class SubjectAssignmentRegistrationTests(TestCase):
    def test_entity_registered_with_expected_derived_fields(self):
        cfg = _get_entity_config(include_derived=True)
        self.assertIn(_ENTITY, cfg, "subject_assignment not registered in the two-way config")
        _model, fields = cfg[_ENTITY]
        # The teaching-grid join: all five FKs plus the two benign scalars.
        self.assertEqual(
            fields,
            {
                "academic_year_id",
                "term_id",
                "classroom_id",
                "specialty_id",
                "subject_id",
                "coefficient",
                "grading_deadline_at",
            },
        )
        self.assertNotIn("school", fields)  # tenant scope, never a data field
        self.assertNotIn("client_offline_id", fields)  # identity anchor, engine-managed
        self.assertNotIn("updated_at", fields)  # delta cursor, engine-managed

    def test_teachers_m2m_never_rides_the_sync_rail(self):
        """Regression seal: the M2M must not be a synced field (see module docstring)."""
        _model, fields = _get_entity_config(include_derived=True)[_ENTITY]
        self.assertNotIn(
            "teachers",
            fields,
            "the teachers M2M must never be a synced field — it targets the SHARED "
            "accounts.User (pk not portable box<->cloud) and would break bundle export",
        )

    def test_no_registered_entity_leaks_a_many_to_many(self):
        """Cross-entity guardrail — fails if ANY future entity reintroduces the hole."""
        offenders = {}
        for entity_type, (model, fields) in _get_entity_config(include_derived=True).items():
            m2m = {f.name for f in model._meta.get_fields() if getattr(f, "many_to_many", False)}
            leaked = sorted(m2m & set(fields))
            if leaked:
                offenders[entity_type] = leaked
        self.assertEqual(
            offenders,
            {},
            "a many-to-many reached a synced field set; register the through-model as its "
            "own entity with its own anchor instead",
        )

    def test_entity_is_benign_lww_not_protected(self):
        strategy, protected = _sync_conflict_policy(_ENTITY)
        self.assertEqual(strategy, MergeStrategy.CAUSAL_LWW)
        self.assertFalse(protected, "the teaching grid must be two-way LWW, not down-only")

    def test_all_five_fks_remap_onto_registered_entities(self):
        cfg = _get_entity_config(include_derived=True)
        self.assertEqual(
            _insert_fk_targets(cfg).get(_ENTITY),
            {
                "academic_year_id": "academic_year",
                "term_id": "term",
                "classroom_id": "classroom",
                "specialty_id": "specialty",
                "subject_id": "subject",
            },
        )


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class SubjectAssignmentRoundTripTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Grid {uid}", slug=f"grid-{uid}", subdomain=f"grid{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"grid_admin_{uid}", password="Test1234", email=f"g{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.dept = Department.objects.create(
            name=f"Dept {uid}", code=f"D{uid[:5]}", school=self.school
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name=f"20{uid[:2]}/20{uid[2:4]}",
            start_date=dt.date(2026, 9, 1),
            end_date=dt.date(2027, 6, 30),
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="Term 1",
            start_date=dt.date(2026, 9, 1),
            end_date=dt.date(2026, 12, 20),
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.dept,
            name=f"Form 5 {uid[:3]}",
            code=f"F5{uid[:5]}",
        )
        self.specialty = Specialty.objects.create(
            school=self.school,
            department=self.dept,
            name="Electrical Trade",
            code=f"ELE{uid[:6]}",
        )
        self.subject = Subject.objects.create(
            school=self.school, name="Circuit Theory", code=f"CT{uid[:5]}"
        )

    def _assignment(self, coefficient="4.00"):
        return SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
            coefficient=Decimal(coefficient),
        )

    def test_assignment_round_trips_cloud_value_onto_box(self):
        assignment = self._assignment(coefficient="4.00")

        # Capture the fresh (cloud) value into a delta bundle.
        data, _meta = build_edge_delta_bundle(self.school, since=None, entities=[_ENTITY])
        self.assertTrue(
            any(r["id"] == assignment.pk for r in _rows(data, self.school.id, _ENTITY)),
            "the new assignment did not reach the delta bundle",
        )

        # Rewind the local (box) copy to an older, different coefficient.
        old = timezone.now() - timezone.timedelta(days=1)
        SubjectAssignment.objects.filter(pk=assignment.pk).update(
            coefficient=Decimal("1.00"), updated_at=old
        )

        # Apply the pulled bundle: the newer cloud value wins by LWW.
        result = apply_pulled_bundle(self.school, self.user, data, origin="cloud-pull")
        self.assertTrue(result["ok"], result)
        assignment.refresh_from_db()
        self.assertEqual(assignment.coefficient, Decimal("4.00"))

    def test_delta_carries_every_fk_value_and_no_m2m_key(self):
        assignment = self._assignment()
        data, _meta = build_edge_delta_bundle(self.school, since=None, entities=[_ENTITY])
        row = next(
            (r for r in _rows(data, self.school.id, _ENTITY) if r["id"] == assignment.pk), None
        )
        self.assertIsNotNone(row, "assignment row not present in delta")
        changes = row["changes"]
        self.assertEqual(changes.get("academic_year_id"), self.year.pk)
        self.assertEqual(changes.get("term_id"), self.term.pk)
        self.assertEqual(changes.get("classroom_id"), self.classroom.pk)
        self.assertEqual(changes.get("specialty_id"), self.specialty.pk)
        self.assertEqual(changes.get("subject_id"), self.subject.pk)
        # The M2M must not appear on the wire at all.
        self.assertNotIn("teachers", changes)

    def test_whole_rail_builds_with_the_grid_registered(self):
        """``entities=None`` packs EVERY registered entity into ONE bundle — the exact
        path an M2M leak would break for all entities at once."""
        self._assignment()
        data, meta = build_edge_delta_bundle(self.school, since=None)
        self.assertGreaterEqual(meta["counts"].get(_ENTITY, 0), 1)
        rows, errors = verify_and_parse_bundle(data, expected_school_id=self.school.id)
        self.assertFalse(errors, errors)
        self.assertTrue(rows)
