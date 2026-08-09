"""Seal: dedup must not auto-merge on FAMILY/HOUSEHOLD signals alone (2026-08-09).

``ai_dedup.deterministic_score`` normalised by only the co-present fields, so a
match on last_name + date_of_birth (twins) or last_name + a shared
guardian_phone (household) saturated to 1.0 >= the migration_cloud auto-link
floor (0.95) whenever the distinguishing first name was blank on one side. That
silently merged two distinct people (a twin into their sibling's record, an
uncle into a parent's account).

The fix caps a match with NO matching individual discriminator (first name or
email) below the auto-link floor. These tests FAIL against the pre-fix score
(1.0) and PASS against the fix; legitimate first-name/email matches are
unaffected.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.people.ai_dedup import deterministic_score

# The migration_cloud auto-link floor (apps/migration_cloud/defaults.py
# migration_cloud.dedup.autolink_min_score). A candidate must clear this to be
# auto-linked without review.
_AUTOLINK_FLOOR = 0.95


class DedupIndividualCorroborationTests(SimpleTestCase):
    def test_last_name_plus_dob_alone_below_autolink(self):
        # Existing row has a BLANK first name; incoming shares only surname + DOB.
        score = deterministic_score(
            {"last_name": "Smith", "date_of_birth": "2010-01-01"},
            {"last_name": "Smith", "date_of_birth": "2010-01-01", "first_name": "John"},
        )
        self.assertLess(score, _AUTOLINK_FLOOR)

    def test_shared_household_phone_and_surname_below_autolink(self):
        # Uncle vs parent on a shared household phone, same surname, no first name.
        score = deterministic_score(
            {"last_name": "Smith", "guardian_phone": "+237650000000"},
            {"last_name": "Smith", "guardian_phone": "+237650000000", "first_name": "John"},
        )
        self.assertLess(score, _AUTOLINK_FLOOR)

    def test_matching_first_name_still_autolinks(self):
        # Same person re-imported: first name corroborates -> auto-link preserved.
        score = deterministic_score(
            {"last_name": "Smith", "date_of_birth": "2010-01-01", "first_name": "John"},
            {"last_name": "Smith", "date_of_birth": "2010-01-01", "first_name": "John"},
        )
        self.assertGreaterEqual(score, _AUTOLINK_FLOOR)

    def test_matching_email_corroborates(self):
        score = deterministic_score(
            {"last_name": "Smith", "email": "john@example.com"},
            {"last_name": "Smith", "email": "john@example.com", "first_name": "John"},
        )
        self.assertGreaterEqual(score, _AUTOLINK_FLOOR)

    def test_twins_differing_first_names_below_autolink(self):
        score = deterministic_score(
            {"last_name": "Smith", "date_of_birth": "2010-01-01", "first_name": "John"},
            {"last_name": "Smith", "date_of_birth": "2010-01-01", "first_name": "Jane"},
        )
        self.assertLess(score, _AUTOLINK_FLOOR)

    def test_family_only_match_is_capped_to_review_band(self):
        # Two records matching ONLY on family signals (surname + DOB, both first
        # names blank) land exactly at the review cap (0.90), never the raw 1.0.
        score = deterministic_score(
            {"last_name": "Smith", "date_of_birth": "2010-01-01"},
            {"last_name": "Smith", "date_of_birth": "2010-01-01"},
        )
        self.assertEqual(score, 0.9)
