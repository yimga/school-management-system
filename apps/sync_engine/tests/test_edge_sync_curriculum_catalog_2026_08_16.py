"""Edge parity Slice 3 — the curriculum catalog (Subject / Specialty / SpecialtySubject)
rides the edge sync rail so the box mirrors the cloud's curriculum.

Locks: (1) the three entities are REGISTERED in the two-way entity config with their
expected auto-derived fields; (2) they are benign LWW master data (NOT protected /
down-only); (3) a real build->rewind->apply round-trip through the shared sync engine
lands the cloud value on the box (proving the newly-registered entity actually flows,
incl. the specialty↔subject FK remap onto registered entities).
"""
from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import Department, Specialty, Subject, SpecialtySubject
from apps.accounts.models import User
from apps.api.sync_services import (
    _get_entity_config,
    _sync_conflict_policy,
)
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import verify_and_parse_bundle
from apps.sync_engine.edge_inbox import apply_pulled_bundle
from apps.sync_engine.edge_outbox import build_edge_delta_bundle
from apps.sync_engine.policy_registry import MergeStrategy

_SIGN_KEY = "edge-catalog-test-key"


def _rows(bundle_bytes, school_id, entity_type):
    rows, errors = verify_and_parse_bundle(bundle_bytes, expected_school_id=school_id)
    assert not errors, errors
    return [r for r in rows if r.get("entity_type") == entity_type]


class CatalogEntityRegistrationTests(TestCase):
    def test_three_catalog_entities_registered_with_fields(self):
        cfg = _get_entity_config(include_derived=True)
        for et in ("subject", "specialty", "specialty_subject"):
            self.assertIn(et, cfg, f"{et} not registered in the two-way entity config")
        # Auto-derived field sets (scalars + FKs to tenant models; school/anchor excluded).
        _subj_model, subj_fields = cfg["subject"]
        self.assertIn("name", subj_fields)
        self.assertIn("code", subj_fields)
        self.assertNotIn("school", subj_fields)          # scope, never a data field
        self.assertNotIn("client_offline_id", subj_fields)  # identity anchor, engine-managed
        self.assertNotIn("updated_at", subj_fields)         # cursor, engine-managed

        _spec_model, spec_fields = cfg["specialty"]
        self.assertIn("department_id", spec_fields)  # FK to a registered tenant entity

        _link_model, link_fields = cfg["specialty_subject"]
        self.assertIn("specialty_id", link_fields)
        self.assertIn("subject_id", link_fields)

    def test_catalog_entities_are_benign_lww_not_protected(self):
        for et in ("subject", "specialty", "specialty_subject"):
            strategy, protected = _sync_conflict_policy(et)
            self.assertEqual(strategy, MergeStrategy.CAUSAL_LWW, et)
            self.assertFalse(protected, f"{et} must be two-way LWW, not down-only")


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class CatalogRoundTripTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Cat {uid}", slug=f"cat-{uid}", subdomain=f"cat{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"cat_admin_{uid}", password="Test1234", email=f"c{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.dept = Department.objects.create(
            name=f"Dept {uid}", code=f"D{uid[:5]}", school=self.school
        )

    def test_subject_round_trips_cloud_value_onto_box(self):
        subj = Subject.objects.create(school=self.school, name="Mathematics", code="MTH")
        # Capture the fresh (cloud) value into a delta bundle.
        data, _meta = build_edge_delta_bundle(self.school, since=None, entities=["subject"])
        self.assertTrue(any(r["id"] == subj.pk for r in _rows(data, self.school.id, "subject")))

        # Rewind the local (box) copy to an older, different value.
        old = timezone.now() - timezone.timedelta(days=1)
        Subject.objects.filter(pk=subj.pk).update(name="Stale", updated_at=old)

        # Apply the pulled bundle: the newer cloud value wins by LWW.
        result = apply_pulled_bundle(self.school, self.user, data, origin="cloud-pull")
        self.assertTrue(result["ok"], result)
        subj.refresh_from_db()
        self.assertEqual(subj.name, "Mathematics")

    def test_specialty_and_link_ship_with_fk_values_in_delta(self):
        spec = Specialty.objects.create(
            school=self.school, department=self.dept, name="Science", code=f"SCI{uuid.uuid4().hex[:6]}"
        )
        subj = Subject.objects.create(school=self.school, name="Physics", code="PHY")
        link = SpecialtySubject.objects.create(
            school=self.school, specialty=spec, subject=subj, coefficient=3, is_core=True
        )
        data, _meta = build_edge_delta_bundle(
            self.school, since=None, entities=["specialty", "subject", "specialty_subject"]
        )
        spec_rows = _rows(data, self.school.id, "specialty")
        link_rows = _rows(data, self.school.id, "specialty_subject")
        self.assertTrue(any(r["id"] == spec.pk for r in spec_rows))
        this_link = next((r for r in link_rows if r["id"] == link.pk), None)
        self.assertIsNotNone(this_link, "specialty_subject link not present in delta")
        # The link's FKs to the (also-registered) specialty + subject ride as data.
        self.assertEqual(this_link["changes"].get("specialty_id"), spec.pk)
        self.assertEqual(this_link["changes"].get("subject_id"), subj.pk)
