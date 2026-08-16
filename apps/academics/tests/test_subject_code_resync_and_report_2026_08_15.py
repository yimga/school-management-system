"""Audit upgrade — subject-code resync, report, baseline predicate, fast path.

Increment (q) gave subject codes a region-level override home, and (s) an importer
that fills it — but a subject SEEDED before the import kept its old mnemonic code,
because ``backfill_subject_codes`` only fills BLANK codes. Report cards render the
stored ``Subject.code``, so an operator's real-code import never reached those
rows. This proves the closure:

* ``_baseline_code`` / ``is_default_subject_code`` — tell a system default apart
  from an admin's explicit edit.
* ``build_override_map`` + ``resolve_subject_code(override_map=)`` — the profile is
  resolved ONCE for a whole catalog, not per subject, and is behaviour-equivalent.
* ``resync_subject_codes`` — updates the stale defaults to the imported code and
  leaves admin edits + already-correct codes untouched; idempotent; dry-run diffs.
* ``subject_code_report`` — the read-only surface behind the hub panel + advisory.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.academics.country_subject_codes import (
    _baseline_code,
    build_override_map,
    is_default_subject_code,
    resolve_subject_code,
    subject_code_report,
)
from apps.schools.models import School


class BaselinePredicateTests(SimpleTestCase):
    def test_baseline_is_curated_then_mnemonic(self):
        ke = School(country_code="KE")
        self.assertEqual(_baseline_code(ke, "English"), "101")        # curated KNEC
        self.assertEqual(_baseline_code(ke, "Basket Weaving"), "BW")  # mnemonic initials

    def test_is_default_true_for_curated_and_mnemonic(self):
        ke = School(country_code="KE")
        self.assertTrue(is_default_subject_code(ke, "English", "101"))
        self.assertTrue(is_default_subject_code(ke, "Basket Weaving", "BW"))

    def test_is_default_false_for_admin_edit(self):
        ke = School(country_code="KE")
        self.assertFalse(is_default_subject_code(ke, "English", "ENG-CUSTOM"))

    def test_is_default_false_for_blank(self):
        # Blank is backfill's job, not resync's — never treated as a default here.
        self.assertFalse(is_default_subject_code(School(country_code="KE"), "English", ""))
        self.assertFalse(is_default_subject_code(School(country_code="KE"), "English", "   "))


class OverrideMapFastPathTests(SimpleTestCase):
    def test_build_override_map_merges_profile_then_school(self):
        ke = School(country_code="KE", settings={"subject_codes": {"English": "SCHOOL"}})
        with patch(
            "apps.academics.country_subject_codes._profile_subject_codes",
            return_value={"english": "PROF", "biology": "PROF-BIO"},
        ):
            m = build_override_map(ke)
        self.assertEqual(m["english"], "SCHOOL")     # school wins over profile
        self.assertEqual(m["biology"], "PROF-BIO")   # profile-only key kept
        self.assertNotIn("mathematics", m)           # curated is NOT in the override map

    def test_fast_path_equivalent_to_slow_path(self):
        ke = School(country_code="KE", settings={"subject_codes": {"English": "ENG-X"}})
        with patch(
            "apps.academics.country_subject_codes._profile_subject_codes",
            return_value={"biology": "PROF-BIO"},
        ):
            om = build_override_map(ke)
            for name in ("English", "Biology", "Mathematics", "Basket Weaving"):
                self.assertEqual(
                    resolve_subject_code(ke, name, override_map=om),
                    resolve_subject_code(ke, name),
                    name,
                )

    def test_override_map_skips_profile_resolution(self):
        # When override_map is supplied, _profile_subject_codes is never consulted.
        ke = School(country_code="KE")
        with patch(
            "apps.academics.country_subject_codes._profile_subject_codes",
            side_effect=AssertionError("profile must not be resolved on the fast path"),
        ):
            self.assertEqual(resolve_subject_code(ke, "English", override_map={}), "101")


class ResyncSubjectCodesTests(TestCase):
    """DB — an imported profile override reaches subjects seeded before the import."""

    def _ke_school(self, subdomain):
        from apps.siteconfig.education_profile_engine import ensure_region_for_country

        region = ensure_region_for_country("KE")
        return School.objects.create(
            name="Nairobi Academy", subdomain=subdomain, country_code="KE", default_region=region
        )

    def _import_english_override(self, code):
        from apps.academics.official_catalog import import_catalog, parse_catalog

        import_catalog(parse_catalog({"country": "KE", "subject_codes": {"english": code}}))

    def test_resync_updates_stale_default_but_preserves_admin_edit(self):
        from apps.academics.models import Subject
        from apps.academics.structure_provisioning import resync_subject_codes

        school = self._ke_school("resync-ke-1")
        english = Subject.objects.create(school=school, name="English", code="101")   # curated default
        maths = Subject.objects.create(school=school, name="Mathematics", code="MY-OWN")  # admin edit
        blank = Subject.objects.create(school=school, name="History", code="")        # blank

        self._import_english_override("ENG-2024")   # official code lands in shared profile
        result = resync_subject_codes(school)

        english.refresh_from_db()
        maths.refresh_from_db()
        blank.refresh_from_db()
        self.assertEqual(english.code, "ENG-2024")   # stale default refreshed
        self.assertEqual(maths.code, "MY-OWN")       # admin edit untouched
        self.assertEqual(blank.code, "")             # blank left for backfill
        self.assertEqual(result["resynced_subjects"], 1)
        self.assertEqual(result["changes"][0]["subject"], "English")

    def test_resync_is_idempotent(self):
        from apps.academics.models import Subject
        from apps.academics.structure_provisioning import resync_subject_codes

        school = self._ke_school("resync-ke-2")
        Subject.objects.create(school=school, name="English", code="101")
        self._import_english_override("ENG-2024")
        resync_subject_codes(school)
        second = resync_subject_codes(school)
        self.assertEqual(second["resynced_subjects"], 0)

    def test_dry_run_reports_diffs_without_writing(self):
        from apps.academics.models import Subject
        from apps.academics.structure_provisioning import resync_subject_codes

        school = self._ke_school("resync-ke-3")
        english = Subject.objects.create(school=school, name="English", code="101")
        self._import_english_override("ENG-2024")
        preview = resync_subject_codes(school, dry_run=True)
        english.refresh_from_db()
        self.assertEqual(english.code, "101")   # nothing written
        self.assertEqual(preview["resynced_subjects"], 1)
        self.assertEqual(preview["changes"][0]["old"], "101")
        self.assertEqual(preview["changes"][0]["new"], "ENG-2024")


class SubjectCodeReportTests(TestCase):
    def test_report_counts_sources_and_flags(self):
        from apps.academics.models import Subject
        from apps.siteconfig.education_profile_engine import ensure_region_for_country

        region = ensure_region_for_country("KE")
        school = School.objects.create(
            name="Report High", subdomain="report-ke", country_code="KE",
            default_region=region,
            settings={"subject_codes": {"English": "ENG-X"}},
        )
        Subject.objects.create(school=school, name="English", code="ENG-X")       # school override
        Subject.objects.create(school=school, name="Mathematics", code="121")     # curated
        Subject.objects.create(school=school, name="Robotics", code="ROBO")       # mnemonic
        Subject.objects.create(school=school, name="Biology", code="STALE")       # drift vs curated 231

        report = subject_code_report(school)
        self.assertEqual(report["total"], 4)
        self.assertEqual(report["by_source"]["school"], 1)
        self.assertEqual(report["by_source"]["curated"], 2)   # Mathematics + Biology
        self.assertEqual(report["by_source"]["mnemonic"], 1)  # Robotics
        self.assertEqual(report["mnemonic_count"], 1)
        self.assertEqual(report["drift_count"], 1)            # Biology STALE != 231

    def test_unsaved_school_report_is_empty_no_db(self):
        # SimpleTestCase-style safety: _state.adding short-circuits before any query.
        report = subject_code_report(School(country_code="KE"))
        self.assertEqual(report["total"], 0)
        self.assertEqual(report["by_source"]["mnemonic"], 0)
