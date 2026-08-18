"""Cloning a year must be reachable on a school that has only one year.

The reported symptom was "I tried to clone a year and had no options available".
`clone_year_setup` renders the SAME list of academic years into both the source and the
target select, and refuses a POST where the two are equal. A school in its first year
has exactly ONE academic year — so both selects offered one identical option and the
only reachable outcome was the "Source and target year must be different" error, with
the page's only escape hatch being prose telling the operator to go create the year in
the Django admin (itself visually broken; see test_tenant_admin_header_chrome).

Two defects are pinned here:
  * usability — a one-year school can create the target inline and finish the job, and
  * isolation — the year list and the id lookups are scoped to the operator's school,
    so a POSTed id belonging to another campus cannot be read or written.

`clone_academic_year` also refuses a cross-school pair outright, because the service is
reachable from management commands that never pass through the view's scoping.
"""

from __future__ import annotations

import datetime

from django.test import SimpleTestCase

from apps.academics.services_year_setup import clone_academic_year
from apps.accounts.views_rollover import (
    _bumped_year_date,
    _suggest_next_year_name,
)


class _FakeYear:
    """Stand-in with just the attributes the pure helpers read."""

    def __init__(self, name="", start_date=None, end_date=None, school_id=None, pk=1):
        self.name = name
        self.start_date = start_date
        self.end_date = end_date
        self.school_id = school_id
        self.pk = pk


class SuggestNextYearNameTests(SimpleTestCase):
    """The inline "create the target" form must arrive pre-filled, not blank."""

    def test_slash_pair_is_advanced_by_one(self):
        self.assertEqual(_suggest_next_year_name([_FakeYear("2025/2026")]), "2026/2027")

    def test_single_year_label_is_advanced_by_one(self):
        self.assertEqual(_suggest_next_year_name([_FakeYear("2025")]), "2026")

    def test_falls_back_to_dates_when_the_name_has_no_digits(self):
        year = _FakeYear(
            "Michaelmas",
            start_date=datetime.date(2025, 9, 1),
            end_date=datetime.date(2026, 7, 31),
        )
        self.assertEqual(_suggest_next_year_name([year]), "2026/2027")

    def test_no_years_yields_no_suggestion(self):
        self.assertEqual(_suggest_next_year_name([]), "")

    def test_unparseable_name_and_no_dates_is_blank_not_a_crash(self):
        self.assertEqual(_suggest_next_year_name([_FakeYear("Session A")]), "")


class BumpedYearDateTests(SimpleTestCase):
    def test_shifts_by_one_year(self):
        self.assertEqual(
            _bumped_year_date(datetime.date(2025, 9, 1)), datetime.date(2026, 9, 1)
        )

    def test_leap_day_does_not_raise(self):
        self.assertEqual(
            _bumped_year_date(datetime.date(2024, 2, 29)), datetime.date(2025, 2, 28)
        )

    def test_empty_input_is_empty_output(self):
        self.assertEqual(_bumped_year_date(None), "")


class CloneAcademicYearGuardTests(SimpleTestCase):
    """The service refuses pairs the view's scoping would never produce."""

    def test_cross_school_clone_is_refused(self):
        source = _FakeYear("2025/2026", school_id=1, pk=1)
        target = _FakeYear("2026/2027", school_id=2, pk=2)
        with self.assertRaises(ValueError) as ctx:
            clone_academic_year(source, target)
        self.assertIn("Cannot clone across schools", str(ctx.exception))

    def test_same_year_clone_is_refused(self):
        year = _FakeYear("2025/2026", school_id=1, pk=7)
        with self.assertRaises(ValueError) as ctx:
            clone_academic_year(year, year)
        self.assertIn("must be different", str(ctx.exception))

    def test_same_school_pair_passes_the_guard(self):
        """Guard must not fire on the legitimate case (it then hits the ORM)."""
        source = _FakeYear("2025/2026", school_id=1, pk=1)
        target = _FakeYear("2026/2027", school_id=1, pk=2)
        with self.assertRaises(Exception) as ctx:
            clone_academic_year(source, target)
        self.assertNotIn("Cannot clone across schools", str(ctx.exception))
        self.assertNotIn("must be different", str(ctx.exception))

    def test_legacy_null_school_rows_are_not_blocked(self):
        """Pre-tenancy rows carry school_id=None; the guard must skip, not refuse."""
        source = _FakeYear("2025/2026", school_id=None, pk=1)
        target = _FakeYear("2026/2027", school_id=2, pk=2)
        with self.assertRaises(Exception) as ctx:
            clone_academic_year(source, target)
        self.assertNotIn("Cannot clone across schools", str(ctx.exception))


class CloneYearTemplateContractTests(SimpleTestCase):
    """The page must offer a way forward when there is no clonable pair."""

    def setUp(self):
        from pathlib import Path

        from django.conf import settings

        self.markup = (
            Path(settings.BASE_DIR)
            / "templates"
            / "accounts"
            / "clone_year_setup.html"
        ).read_text(encoding="utf8")

    def test_offers_inline_target_year_creation(self):
        self.assertIn('name="create_target_year"', self.markup)
        self.assertIn('name="new_year_name"', self.markup)

    def test_inline_form_is_gated_on_having_no_clonable_pair(self):
        self.assertIn("{% if not has_clonable_pair %}", self.markup)

    def test_clone_controls_are_disabled_without_a_pair(self):
        self.assertIn("{% if not has_clonable_pair %}disabled{% endif %}", self.markup)

    def test_selects_are_kept_mutually_exclusive_client_side(self):
        self.assertIn("data-rmc-clone-year-source", self.markup)
        self.assertIn("data-rmc-clone-year-target", self.markup)
        self.assertIn("addEventListener", self.markup)

    def test_inline_script_carries_a_csp_nonce(self):
        self.assertIn('<script nonce="{{ csp_nonce }}">', self.markup)

    def test_no_inline_event_handler_attributes(self):
        """A strict script-src blocks on*= attributes outright."""
        for handler in ('onclick="', 'onchange="', 'onsubmit="'):
            self.assertNotIn(handler, self.markup)
