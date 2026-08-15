"""Increment (r) — representative-calendar provenance + confirm-before-go-live.

Seeded term-date calendars are *representative* defaults, not official ministry
dates. This proves: (1) ``term_windows_source`` reports which cascade layer supplied
a calendar; (2) ``academic_calendar`` records that provenance and lets an admin
confirm it; (3) ``setup_health_score`` surfaces a score-neutral advisory until it is
confirmed; (4) the confirm view is POST-only and open-redirect safe.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase
from django.test.client import RequestFactory

from apps.academics.academic_calendar import (
    calendar_confirmation_state,
    confirm_calendar,
    needs_calendar_confirmation,
    record_calendar_provenance,
)
from apps.academics.country_term_calendars import term_windows_source
from apps.academics.views_calendar import _safe_redirect_target, confirm_academic_calendar
from apps.schools.models import School


class TermWindowsSourceTests(SimpleTestCase):
    def test_curated_country_reports_curated(self):
        self.assertEqual(term_windows_source(School(country_code="CM"), 3), "curated")
        self.assertEqual(term_windows_source(School(country_code="KE"), 3), "curated")

    def test_unknown_country_reports_none(self):
        self.assertIsNone(term_windows_source(School(country_code="XX"), 3))

    def test_school_override_reports_school(self):
        s = School(
            country_code="XX",
            settings={"term_windows": [[9, 1, 12, 15], [1, 8, 4, 10], [4, 25, 7, 25]]},
        )
        self.assertEqual(term_windows_source(s, 3), "school")

    def test_shape_mismatched_override_falls_through(self):
        # A 2-window override cannot satisfy a 3-term ask → not "school".
        s = School(country_code="XX", settings={"term_windows": [[9, 1, 12, 15], [1, 8, 4, 10]]})
        self.assertIsNone(term_windows_source(s, 3))


class ProvenanceRecordingTests(SimpleTestCase):
    """Uses UNSAVED schools — record/confirm mutate settings in memory only
    (``_state.adding`` short-circuits the save), so no DB is touched."""

    def test_representative_sources(self):
        for src in ("curated", "even_split", None, "garbage-value"):
            entry = record_calendar_provenance(School(country_code="CM"), src)
            self.assertTrue(entry["representative"], src)

    def test_real_override_sources_are_not_representative(self):
        for src in ("school", "profile"):
            entry = record_calendar_provenance(School(country_code="CM"), src)
            self.assertFalse(entry["representative"], src)
            self.assertEqual(entry["source"], src)

    def test_state_defaults_for_school_with_no_key(self):
        state = calendar_confirmation_state(School(country_code="CM"))
        self.assertFalse(state["representative"])
        self.assertFalse(state["needs_confirmation"])

    def test_representative_calendar_needs_confirmation(self):
        s = School(country_code="CM")
        record_calendar_provenance(s, "curated")
        self.assertTrue(needs_calendar_confirmation(s))

    def test_real_override_never_needs_confirmation(self):
        s = School(country_code="CM")
        record_calendar_provenance(s, "school")
        self.assertFalse(needs_calendar_confirmation(s))

    def test_confirm_clears_the_need_and_keeps_source(self):
        s = School(country_code="CM")
        record_calendar_provenance(s, "curated")
        state = confirm_calendar(s, user=None)
        self.assertTrue(state["confirmed"])
        self.assertFalse(state["needs_confirmation"])
        self.assertEqual(state["source"], "curated")  # still a representative default
        self.assertTrue(state["confirmed_at"])

    def test_reseeding_preserves_a_prior_confirmation(self):
        s = School(country_code="CM")
        record_calendar_provenance(s, "curated")
        confirm_calendar(s, user=None)
        when = calendar_confirmation_state(s)["confirmed_at"]
        # A later re-seed (same representative source) must not silently un-confirm.
        record_calendar_provenance(s, "curated")
        after = calendar_confirmation_state(s)
        self.assertTrue(after["confirmed"])
        self.assertEqual(after["confirmed_at"], when)
        self.assertFalse(after["needs_confirmation"])

    def test_confirmed_by_records_the_user_label(self):
        s = School(country_code="CM")
        record_calendar_provenance(s, "curated")

        class _U:
            username = "registrar@example.test"

        state = confirm_calendar(s, user=_U())
        self.assertEqual(state["confirmed_by"], "registrar@example.test")


class ConfirmViewGuardTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_get_is_rejected_post_only(self):
        resp = confirm_academic_calendar(self.rf.get("/academics/calendar/confirm/"))
        self.assertEqual(resp.status_code, 405)

    def test_safe_redirect_allows_same_host_relative(self):
        req = self.rf.post("/academics/calendar/confirm/", {"next": "/academics/foo/"})
        self.assertEqual(_safe_redirect_target(req), "/academics/foo/")

    def test_safe_redirect_rejects_external_host(self):
        req = self.rf.post("/academics/calendar/confirm/", {"next": "http://evil.example/"})
        target = _safe_redirect_target(req)
        self.assertNotIn("evil.example", target)
        self.assertTrue(target.startswith("/"))


class SetupHealthAdvisoryTests(TestCase):
    def test_advisory_appears_until_confirmed(self):
        from apps.schools.setup_health import setup_health_score

        school = School.objects.create(name="Adv", subdomain="adv-cal-r", country_code="CM")
        record_calendar_provenance(school, "curated")

        health = setup_health_score(school)
        self.assertIn("advisories", health)
        keys = {a["key"] for a in health["advisories"]}
        self.assertIn("confirm_academic_calendar", keys)

        confirm_calendar(school, user=None)
        health2 = setup_health_score(school)
        keys2 = {a["key"] for a in health2["advisories"]}
        self.assertNotIn("confirm_academic_calendar", keys2)

    def test_score_unaffected_by_advisory(self):
        # An unconfirmed representative calendar must not lower the numeric score.
        from apps.schools.setup_health import setup_health_score

        school = School.objects.create(name="Adv2", subdomain="adv-cal-r2", country_code="CM")
        before = setup_health_score(school)["score"]
        record_calendar_provenance(school, "curated")
        after = setup_health_score(school)["score"]
        self.assertEqual(before, after)
