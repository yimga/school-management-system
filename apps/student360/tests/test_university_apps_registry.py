"""Wave O (v3.95.0 — 2026-05-26) — University pathway registry tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.student360.university_apps_registry import (
    DocumentRequirement,
    FieldRequirement,
    UniversityPathway,
    check_completeness,
    get_pathway,
    list_pathways,
    pathways_for_region,
    summary,
)


class SeededRegistryTests(SimpleTestCase):

    def test_seven_pathways_seeded(self):
        ids = {p.pathway_id for p in list_pathways()}
        for must in ("ucas-uk", "common-app-us", "ib-dp-result-release",
                     "waec-nigeria", "jamb-utme-nigeria", "cuet-india",
                     "kuccps-kenya"):
            self.assertIn(must, ids)

    def test_get_known_pathway(self):
        p = get_pathway("ucas-uk")
        self.assertIsNotNone(p)
        self.assertEqual(p.region, "UK")
        self.assertEqual(p.transcript_format, "ucas_xml")

    def test_get_unknown_pathway(self):
        self.assertIsNone(get_pathway("nonexistent"))

    def test_each_pathway_has_required_fields(self):
        for p in list_pathways():
            required = [f for f in p.fields_required if f.required]
            self.assertGreater(len(required), 0,
                                f"{p.pathway_id} has no required fields")

    def test_pathways_for_region_uk(self):
        uk = pathways_for_region("UK")
        self.assertEqual({p.pathway_id for p in uk}, {"ucas-uk"})

    def test_pathways_for_region_nigeria(self):
        ng = pathways_for_region("Nigeria")
        self.assertEqual(
            {p.pathway_id for p in ng},
            {"waec-nigeria", "jamb-utme-nigeria"},
        )

    def test_unknown_region_empty(self):
        self.assertEqual(pathways_for_region("nowhere"), ())


class CompletenessCheckerTests(SimpleTestCase):

    def _make_pathway(self):
        return UniversityPathway(
            pathway_id="test-pw",
            display_name="Test Pathway",
            region="Test",
            submission_window_months=(1,),
            transcript_format="test",
            fields_required=(
                FieldRequirement("student.full_name", True),
                FieldRequirement("student.gpa", True),
                FieldRequirement("student.optional_essay", False),
            ),
            documents_required=(
                DocumentRequirement("transcript", "Transcript", True),
                DocumentRequirement("photo", "Photo", False),
            ),
        )

    def test_complete_record_ready(self):
        p = self._make_pathway()
        rep = check_completeness(
            p,
            field_value_resolver=lambda _f: "value",
            document_present_resolver=lambda _d: True,
        )
        self.assertTrue(rep.ready)
        self.assertEqual(rep.missing_fields, [])
        self.assertEqual(rep.missing_documents, [])

    def test_missing_required_field_blocks(self):
        p = self._make_pathway()
        rep = check_completeness(
            p,
            field_value_resolver=lambda f: None if f == "student.gpa" else "v",
            document_present_resolver=lambda _d: True,
        )
        self.assertFalse(rep.ready)
        self.assertEqual(rep.missing_fields, ["student.gpa"])

    def test_missing_optional_field_does_not_block(self):
        p = self._make_pathway()
        rep = check_completeness(
            p,
            field_value_resolver=lambda f: None if f == "student.optional_essay" else "v",
            document_present_resolver=lambda _d: True,
        )
        self.assertTrue(rep.ready)
        self.assertEqual(rep.missing_fields, [])

    def test_missing_required_document_blocks(self):
        p = self._make_pathway()
        rep = check_completeness(
            p,
            field_value_resolver=lambda _f: "v",
            document_present_resolver=lambda d: False if d == "transcript" else True,
        )
        self.assertFalse(rep.ready)
        self.assertEqual(rep.missing_documents, ["transcript"])

    def test_field_resolver_exception_treated_as_missing(self):
        p = self._make_pathway()

        def broken_resolver(_f):
            raise RuntimeError("DB exploded")

        rep = check_completeness(
            p,
            field_value_resolver=broken_resolver,
            document_present_resolver=lambda _d: True,
        )
        self.assertFalse(rep.ready)
        self.assertEqual(len(rep.missing_fields), 2)  # both required fields

    def test_document_resolver_exception_treated_as_missing(self):
        p = self._make_pathway()

        def broken_doc_resolver(_d):
            raise RuntimeError("FS exploded")

        rep = check_completeness(
            p,
            field_value_resolver=lambda _f: "v",
            document_present_resolver=broken_doc_resolver,
        )
        self.assertFalse(rep.ready)
        self.assertIn("transcript", rep.missing_documents)


class SummaryTests(SimpleTestCase):

    def test_summary_shape(self):
        s = summary()
        self.assertIn("pathway_count", s)
        self.assertIn("by_region", s)
        self.assertIn("total_fields_tracked", s)
        self.assertGreater(s["pathway_count"], 0)
        self.assertGreater(s["total_fields_tracked"], 0)

    def test_summary_region_counts_total(self):
        s = summary()
        total = sum(s["by_region"].values())
        self.assertEqual(total, s["pathway_count"])
