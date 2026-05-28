"""Wave L (v3.95.0 — 2026-05-26) — Certified Administrator registry tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.customersuccess.certified_administrator import (
    CertificationExam,
    get_track,
    list_tracks,
    summary,
    total_estimated_hours,
    total_modules,
    tracks_for_audience,
)


class SeededRegistryTests(SimpleTestCase):

    def test_seeded_five_tracks(self):
        tracks = list_tracks()
        self.assertGreaterEqual(len(tracks), 5)

    def test_known_track_ids_present(self):
        expected = {
            "rmc-tenant-admin-foundational",
            "rmc-tenant-admin-professional",
            "rmc-bursar-specialist",
            "rmc-teacher-champion-foundational",
            "rmc-migration-specialist-concierge",
        }
        ids = {t.track_id for t in list_tracks()}
        self.assertTrue(expected.issubset(ids))

    def test_get_track_by_id(self):
        t = get_track("rmc-tenant-admin-foundational")
        self.assertIsNotNone(t)
        self.assertEqual(t.audience, "Tenant-Admin")
        self.assertEqual(t.level, "Foundational")

    def test_get_unknown_track(self):
        self.assertIsNone(get_track("nonexistent"))

    def test_tracks_for_audience_filters(self):
        tenant_admin = tracks_for_audience("Tenant-Admin")
        self.assertEqual(len(tenant_admin), 2)
        # All tracks for this audience should match audience field.
        for t in tenant_admin:
            self.assertEqual(t.audience, "Tenant-Admin")

    def test_total_modules_at_least_20(self):
        # Wave L seed ships 23 modules across 5 tracks; Wave L+ will expand.
        self.assertGreaterEqual(total_modules(), 20)

    def test_total_estimated_hours_is_positive(self):
        self.assertGreater(total_estimated_hours(), 0.0)


class TrackShapeTests(SimpleTestCase):

    def test_each_track_has_exam(self):
        for t in list_tracks():
            self.assertIsInstance(t.exam, CertificationExam)
            self.assertGreater(t.exam.question_count, 0)
            self.assertGreaterEqual(t.exam.pass_threshold_pct, 50)
            self.assertLessEqual(t.exam.pass_threshold_pct, 100)

    def test_each_track_has_at_least_one_module(self):
        for t in list_tracks():
            self.assertGreater(len(t.modules), 0)

    def test_module_minutes_positive(self):
        for t in list_tracks():
            for m in t.modules:
                self.assertGreater(m.minutes_estimated, 0)
                self.assertGreater(len(m.objectives), 0)

    def test_module_prerequisites_reference_existing_modules(self):
        for t in list_tracks():
            module_ids = {m.module_id for m in t.modules}
            for m in t.modules:
                for prereq in m.prerequisites:
                    self.assertIn(prereq, module_ids,
                                  f"prereq {prereq} on {m.module_id} not in track {t.track_id}")

    def test_badge_slug_set(self):
        for t in list_tracks():
            self.assertTrue(t.badge_slug.startswith("rmc-"))


class SummaryTests(SimpleTestCase):

    def test_summary_shape(self):
        s = summary()
        self.assertIn("track_count", s)
        self.assertIn("module_count", s)
        self.assertIn("exam_count", s)
        self.assertIn("total_estimated_hours", s)
        self.assertIn("by_level", s)
        self.assertIn("by_audience", s)

    def test_summary_levels(self):
        s = summary()
        self.assertGreaterEqual(s["by_level"]["Foundational"], 1)
        self.assertGreaterEqual(s["by_level"]["Professional"], 1)
        self.assertGreaterEqual(s["by_level"]["Expert"], 1)

    def test_track_count_matches_list(self):
        s = summary()
        self.assertEqual(s["track_count"], len(list_tracks()))
        self.assertEqual(s["exam_count"], len(list_tracks()))
