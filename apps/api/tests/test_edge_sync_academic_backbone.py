"""Phase 3 slice 2 — academic-backbone master data joins bidirectional sync.

academics.AcademicYear / Term / Department gained a client_offline_id anchor + an
auto_now updated_at (migration 0075) and are now registered sync entities. Proves:
  * update-by-pk for a registered backbone model,
  * a new Term referencing a NEW AcademicYear in the same bundle is remapped onto the
    year's operator pk (cross-entity FK remap within the new batch), and
  * echo-suppression applies to these entities too.
"""
from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import AcademicYear, Department, Term
from apps.accounts.models import User
from apps.api.sync_services import _get_entity_config, apply_changes, apply_edge_inserts
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import verify_and_parse_bundle
from apps.sync_engine.edge_outbox import build_edge_delta_bundle

_SIGN_KEY = "academic-backbone-test-key"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class AcademicBackboneSyncTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Bb {uid}", slug=f"bb-{uid}", subdomain=f"bb{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"bb_admin_{uid}", password="Test1234", email=f"b{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.uid = uid
        self.future = (timezone.now() + timezone.timedelta(minutes=10)).isoformat()

    def test_registry_includes_academic_backbone(self):
        cfg = _get_entity_config()
        for e in ("academic_year", "term", "department"):
            self.assertIn(e, cfg)
        self.assertIn("academic_year_id", cfg["term"][1])  # remappable FK carried
        self.assertFalse(cfg["academic_year"][1] & {"school", "client_offline_id", "updated_at"})

    def test_term_and_year_update_by_pk(self):
        year = AcademicYear.objects.create(
            school=self.school, name="2024/2025", start_date="2024-09-01", end_date="2025-06-30"
        )
        term = Term.objects.create(
            school=self.school, academic_year=year, name="FIRST",
            start_date="2024-09-01", end_date="2024-12-20",
        )
        out = apply_changes(
            str(self.school.id), self.user,
            [
                {"entity_type": "term", "id": term.pk,
                 "changes": {"custom_label": "Semester 1"}, "updated_at": self.future},
                {"entity_type": "academic_year", "id": year.pk,
                 "changes": {"is_active": True}, "updated_at": self.future},
            ],
            persist_conflicts=True,
        )
        self.assertEqual(out["success_count"], 2, out)
        term.refresh_from_db(); year.refresh_from_db()
        self.assertEqual(term.custom_label, "Semester 1")
        self.assertTrue(year.is_active)

    def test_new_term_references_new_year_is_remapped(self):
        local_year_pk = 515151
        rows = [
            {"entity_type": "academic_year", "id": local_year_pk, "client_offline_id": "box-ay",
             "changes": {"name": "2099/2100", "start_date": "2099-09-01", "end_date": "2100-06-30"},
             "updated_at": self.future},
            {"entity_type": "term", "id": 525252, "client_offline_id": "box-term",
             "changes": {"academic_year_id": local_year_pk, "name": "FIRST",
                         "start_date": "2099-09-01", "end_date": "2099-12-20"},
             "updated_at": self.future},
        ]
        out = apply_edge_inserts(str(self.school.id), self.user, rows)
        self.assertEqual(out["created"], 2, out)
        new_year = AcademicYear.objects.get(school=self.school, client_offline_id="box-ay")
        new_term = Term.objects.get(school=self.school, client_offline_id="box-term")
        self.assertEqual(new_term.academic_year_id, new_year.pk)   # remapped to operator pk
        self.assertNotEqual(new_term.academic_year_id, local_year_pk)

    def test_echo_suppression_for_department(self):
        dept = Department.objects.create(
            school=self.school, name="Science", code=f"SCI-{self.uid}"
        )
        apply_changes(
            str(self.school.id), self.user,
            [{"entity_type": "department", "id": dept.pk,
              "changes": {"name": "Applied Science"}, "updated_at": self.future}],
            persist_conflicts=True, sync_origin="cloud-pull",
        )
        data, _m = build_edge_delta_bundle(self.school, since=None, entities=["department"])
        rows, errs = verify_and_parse_bundle(data, expected_school_id=self.school.id)
        self.assertFalse(errs, errs)
        self.assertEqual([r for r in rows if r["id"] == dept.pk], [], "echoed a synced department")

        dept.refresh_from_db()
        dept.name = "Natural Science"
        dept.save(update_fields=["name", "updated_at"])
        data2, _m2 = build_edge_delta_bundle(self.school, since=None, entities=["department"])
        rows2, _e2 = verify_and_parse_bundle(data2, expected_school_id=self.school.id)
        shipped = [r for r in rows2 if r["id"] == dept.pk]
        self.assertEqual(len(shipped), 1, "local edit suppressed")
        self.assertEqual(shipped[0]["changes"].get("name"), "Natural Science")
