"""Multi-file canonical-CSV upload with per-file domain tagging (2026-07-11).

The operator uploads many canonical CSVs at once and tells us which record type
each file is (students / teachers / subjects / …). Those tags are stored on the
bundle and, at classify time, OVERRIDE both the content classifier and the
deterministic accelerator — the operator's explicit "this file is X" always
wins. These tests lock the auto-detect, validation, and override contracts.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.migration_cloud.accelerators.runmycampus_canonical import (
    DOMAIN_CANONICAL_HEADERS,
    canonical_domain_choices,
    canonical_domain_label,
    guess_domain_from_filename,
    is_valid_canonical_domain,
)
from apps.migration_cloud.pipeline import _operator_domain_for


class CanonicalDomainHelperTests(SimpleTestCase):
    def test_filename_auto_detect(self):
        cases = {
            "students.csv": "students",
            "STUDENT_ROSTER.CSV": "students",
            "teachers_2025.csv": "staff",
            "staff-list.xlsx": "staff",
            "parents.csv": "guardians",
            "courses.csv": "academics",
            "subjects.csv": "academics",
            "classes_10a.csv": "sections",
            "sections_fall.csv": "sections",
            "invoices_q1.csv": "finance",
            "fees.csv": "finance",
            "attendance.csv": "attendance",
            "grades_final.csv": "grades",
            "behaviour_log.csv": "behavior",
            "transport_assignments.csv": "transport_assignments",
        }
        for filename, expected in cases.items():
            self.assertEqual(guess_domain_from_filename(filename), expected, filename)

    def test_filename_auto_detect_unknown_is_blank(self):
        self.assertEqual(guess_domain_from_filename("random_export_2025.csv"), "")
        self.assertEqual(guess_domain_from_filename(""), "")

    def test_is_valid_canonical_domain(self):
        self.assertTrue(is_valid_canonical_domain("students"))
        self.assertTrue(is_valid_canonical_domain("finance"))
        self.assertFalse(is_valid_canonical_domain("not_a_domain"))
        self.assertFalse(is_valid_canonical_domain(""))

    def test_choices_cover_every_canonical_domain_with_labels(self):
        choices = canonical_domain_choices()
        slugs = {c["slug"] for c in choices}
        self.assertEqual(slugs, set(DOMAIN_CANONICAL_HEADERS))
        for c in choices:
            self.assertTrue(c["label"])  # every option is labelled
        self.assertEqual(canonical_domain_label("staff"), "Teachers / Staff")
        # Unknown slug falls back to a title-cased label (never blank).
        self.assertEqual(canonical_domain_label("brand_new_domain"), "Brand New Domain")


class OperatorDomainOverrideTests(SimpleTestCase):
    def _artifact(self, path, filename):
        return SimpleNamespace(path_within_bundle=path, filename=filename)

    def test_matches_by_path_then_filename(self):
        art = self._artifact("students.csv", "students.csv")
        self.assertEqual(
            _operator_domain_for({"students.csv": "students"}, art), "students"
        )

    def test_matches_by_filename_when_path_differs(self):
        art = self._artifact("bundle/sub/roster.csv", "roster.csv")
        self.assertEqual(
            _operator_domain_for({"roster.csv": "staff"}, art), "staff"
        )

    def test_invalid_tag_is_ignored(self):
        art = self._artifact("x.csv", "x.csv")
        self.assertEqual(_operator_domain_for({"x.csv": "bogus_domain"}, art), "")

    def test_no_tag_returns_blank(self):
        art = self._artifact("x.csv", "x.csv")
        self.assertEqual(_operator_domain_for({}, art), "")
        self.assertEqual(_operator_domain_for({"other.csv": "students"}, art), "")


class StoreOperatorDomainsTests(TestCase):
    def setUp(self):
        from apps.migration_cloud.models import MigrationBundle
        from apps.migration_cloud.views import MigrationCloudIntakeView

        self.MigrationBundle = MigrationBundle
        self.view = MigrationCloudIntakeView()
        self.rf = RequestFactory()
        self.bundle = MigrationBundle.objects.create(
            schema_name="", label="tag-test", idempotency_key="tag-test-1"
        )

    def _post(self, mapping):
        return self.rf.post("/x/", data={"artifact_domain_map": json.dumps(mapping)})

    def test_valid_tags_land_in_discovery_summary(self):
        req = self._post({"students.csv": "students", "teachers.csv": "staff"})
        self.view._store_operator_domains(request=req, bundle=self.bundle)
        self.bundle.refresh_from_db()
        assigned = (self.bundle.discovery_summary or {}).get("operator_assigned_domains")
        self.assertEqual(assigned, {"students.csv": "students", "teachers.csv": "staff"})

    def test_invalid_tags_are_filtered_out(self):
        req = self._post({"a.csv": "students", "b.csv": "bogus", "c.csv": "auto", "d.csv": ""})
        self.view._store_operator_domains(request=req, bundle=self.bundle)
        self.bundle.refresh_from_db()
        assigned = (self.bundle.discovery_summary or {}).get("operator_assigned_domains")
        self.assertEqual(assigned, {"a.csv": "students"})

    def test_no_map_is_a_noop(self):
        req = self.rf.post("/x/", data={})
        self.view._store_operator_domains(request=req, bundle=self.bundle)
        self.bundle.refresh_from_db()
        self.assertNotIn(
            "operator_assigned_domains", (self.bundle.discovery_summary or {})
        )

    def test_malformed_json_is_a_noop(self):
        req = self.rf.post("/x/", data={"artifact_domain_map": "{not json"})
        self.view._store_operator_domains(request=req, bundle=self.bundle)
        self.bundle.refresh_from_db()
        self.assertNotIn(
            "operator_assigned_domains", (self.bundle.discovery_summary or {})
        )
