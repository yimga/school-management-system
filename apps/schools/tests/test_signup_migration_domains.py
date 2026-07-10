"""Signup 'data domains to import' capture — validation helper (no DB).

Enriches the migration intent captured at signup so the auto-drafted
MigrationBundle knows which record families the school is bringing over.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools.signup_views import _SIGNUP_DOMAIN_SLUGS, _clean_migration_domains


class CleanMigrationDomainsTests(SimpleTestCase):
    def test_valid_slugs_preserved_in_order_and_deduped(self):
        self.assertEqual(
            _clean_migration_domains(["grades", "students", "grades"]),
            ["grades", "students"],
        )

    def test_unknown_dropped_and_case_and_whitespace_normalized(self):
        self.assertEqual(
            _clean_migration_domains(["STUDENTS", " bogus ", "Fees"]),
            ["students", "fees"],
        )

    def test_empty_and_none_yield_empty_list(self):
        self.assertEqual(_clean_migration_domains([]), [])
        self.assertEqual(_clean_migration_domains(None), [])

    def test_template_checkbox_slugs_match_allowlist(self):
        # The 10 checkbox values hardcoded in signup_school.html must all be
        # accepted by the server-side allowlist (drift guard).
        template_slugs = {
            "students", "guardians", "staff", "enrollments", "grades",
            "attendance", "timetable", "fees", "discipline", "health",
        }
        self.assertEqual(template_slugs, _SIGNUP_DOMAIN_SLUGS)
