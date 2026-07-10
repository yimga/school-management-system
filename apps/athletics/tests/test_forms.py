"""SeasonForm regression (fix #9).

``school`` is not a ``SeasonForm`` field, so ``ModelForm.validate_unique`` skips
the ``(school, sport, academic_year, name)`` constraint — a duplicate-season POST
used to reach the DB as an ``IntegrityError`` 500 (or silently create a duplicate
when ``academic_year`` is NULL, which the constraint treats as distinct in some
backends). ``SeasonForm.clean()`` now does a school-scoped existence check (the
view binds ``instance.school`` before ``is_valid``) and surfaces a graceful
``add_error("name", ...)`` instead.
"""

from __future__ import annotations

from apps.athletics.forms import SeasonForm
from apps.athletics.models import Season
from apps.athletics.tests.base import BaseAthleticsTestCase


class SeasonFormUniquenessTests(BaseAthleticsTestCase):
    def _data(self, **overrides):
        data = {
            "sport": self.fx.sport.pk,
            "academic_year": self.fx.year.pk,
            "name": "Fall",
            "start_date": "2025-09-01",
            "end_date": "2026-01-31",
            "status": Season.Status.PLANNING,
        }
        data.update(overrides)
        return data

    def _bind(self, data):
        form = SeasonForm(data=data, school=self.fx.school)
        # The admin view binds instance.school before calling is_valid().
        form.instance.school = self.fx.school
        return form

    def test_duplicate_season_rejected_as_form_error(self):
        Season.objects.create(
            school=self.fx.school, sport=self.fx.sport, academic_year=self.fx.year,
            name="Fall", start_date="2025-09-01", end_date="2026-01-31",
        )
        form = self._bind(self._data())
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_null_academic_year_duplicate_rejected(self):
        Season.objects.create(
            school=self.fx.school, sport=self.fx.sport, academic_year=None,
            name="Fall", start_date="2025-09-01", end_date="2026-01-31",
        )
        data = self._data()
        data.pop("academic_year")  # omitted -> NULL academic_year
        form = self._bind(data)
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_distinct_name_is_valid(self):
        Season.objects.create(
            school=self.fx.school, sport=self.fx.sport, academic_year=self.fx.year,
            name="Fall", start_date="2025-09-01", end_date="2026-01-31",
        )
        form = self._bind(self._data(name="Spring"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_distinct_academic_year_is_valid(self):
        from apps.academics.models import AcademicYear

        Season.objects.create(
            school=self.fx.school, sport=self.fx.sport, academic_year=self.fx.year,
            name="Fall", start_date="2025-09-01", end_date="2026-01-31",
        )
        other_year = AcademicYear.objects.create(
            school=self.fx.school, name="2026/2027-a",
            start_date="2026-09-01", end_date="2027-07-01",
        )
        form = self._bind(self._data(academic_year=other_year.pk))
        self.assertTrue(form.is_valid(), form.errors)
