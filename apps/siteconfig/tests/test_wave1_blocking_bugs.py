"""Wave 1 — regression tests for the five tenant/platform blocking bugs.

Each test locks the ROOT CAUSE the audit found, so the bug can't silently return:
  * Bug 3 — the siteconfig config backend refused a tenant ``SUPERADMIN`` (502/Forbidden).
  * Bug 4 — ``studio/automation`` 500'd on a gettext ``.format()`` i18n crash.
  * Bug 5 — Portal Preferences language/region dropdowns rendered with zero options.
  * Bug 2 — the report-card builder 502'd (Postgres-only DISTINCT ON on SQLite).
(Bug 1, the configure-hub dead category cards, is a template-only change verified by
the render-safety gate + the before/after packet.)
"""

from __future__ import annotations

import django.forms as djf
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase

U = get_user_model()


# --------------------------------------------------------------------------- #
# Bug 3 — tenant SUPERADMIN may reach the configuration backend.
# --------------------------------------------------------------------------- #
class BackendConfigAccessTests(TestCase):
    def _pred(self, user):
        from apps.siteconfig.tenant_experience_policy import (
            user_may_manage_backend_config,
        )

        return user_may_manage_backend_config(user)

    def test_superadmin_scalar_role_is_allowed(self):
        """The exact bug: a role=SUPERADMIN user with no is_staff/is_superuser."""
        u = U.objects.create(username="w1-sa", role=U.Role.SUPERADMIN)
        self.assertFalse(u.is_staff)
        self.assertFalse(u.is_superuser)
        self.assertTrue(self._pred(u))

    def test_admin_scalar_role_is_allowed(self):
        u = U.objects.create(username="w1-admin", role=U.Role.ADMIN)
        self.assertTrue(self._pred(u))

    def test_staff_is_allowed(self):
        u = U.objects.create(username="w1-staff", is_staff=True)
        self.assertTrue(self._pred(u))

    def test_plain_teacher_is_not_allowed(self):
        u = U.objects.create(username="w1-teacher", role=U.Role.TEACHER)
        self.assertFalse(self._pred(u))


# --------------------------------------------------------------------------- #
# Bug 4 — studio automation mode hero must not crash on the failing/paused labels.
# --------------------------------------------------------------------------- #
class StudioAutomationHeroTests(TestCase):
    def _hero(self, summary):
        from apps.studio_os.services import get_studio_mode_hero_context

        req = RequestFactory().get("/studio/hubs/automation/")
        req.user = U.objects.create(
            username=f"w1-hero-{summary.get('failing_count', 0)}-{summary.get('paused_count', 0)}"
        )
        return get_studio_mode_hero_context(
            "automation", req, automation_health_summary=summary
        )

    def test_failing_runs_label_builds(self):
        hero = self._hero({"service_online": True, "failing_count": 3})
        # No exception (the .format()-on-gettext crash) and the count is rendered.
        self.assertIn("3", str(hero.get("mode_health_label")))
        self.assertEqual(hero.get("mode_health_status"), "warn")

    def test_paused_packs_label_builds(self):
        hero = self._hero({"service_online": True, "failing_count": 0, "paused_count": 2})
        self.assertIn("2", str(hero.get("mode_health_label")))

    def test_healthy_label_builds(self):
        hero = self._hero({"service_online": True, "failing_count": 0, "paused_count": 0})
        self.assertEqual(hero.get("mode_health_status"), "ok")


# --------------------------------------------------------------------------- #
# Bug 5 — Portal Preferences language/region dropdowns actually have options.
# --------------------------------------------------------------------------- #
class UserPreferenceLanguageRegionTests(TestCase):
    def _form(self):
        from apps.siteconfig.forms import UserPreferenceForm
        from apps.siteconfig.models_tooling import UserPreference

        u = U.objects.create(username="w1-prefs")
        pref, _ = UserPreference.objects.get_or_create(user=u)
        return UserPreferenceForm(user=u, instance=pref)

    def test_fields_are_choice_fields(self):
        form = self._form()
        self.assertIsInstance(form.fields["preferred_language"], djf.ChoiceField)
        self.assertIsInstance(form.fields["preferred_region"], djf.ChoiceField)

    def test_dropdowns_render_options(self):
        form = self._form()
        # The bug: <select> rendered with zero <option>s. Now both have real options.
        self.assertGreater(len(form.fields["preferred_language"].choices), 1)
        self.assertGreater(len(form.fields["preferred_region"].choices), 1)
        self.assertIn("<option", str(form["preferred_language"]))
        self.assertIn("<option", str(form["preferred_region"]))


# --------------------------------------------------------------------------- #
# Bug 2 — report-card builder must not use Postgres-only DISTINCT ON on SQLite.
# --------------------------------------------------------------------------- #
class ReportCardBuilderPortableTests(TestCase):
    def test_distinct_on_is_not_supported_here(self):
        """Documents WHY the fix exists: DISTINCT ON raises on the SQLite test DB."""
        from apps.people.models import StudentProfile
        from django.db.utils import NotSupportedError

        qs = StudentProfile.objects.order_by("classroom_id").distinct("classroom_id")
        with self.assertRaises(NotSupportedError):
            list(qs)

    def test_builder_context_does_not_crash_with_assignment(self):
        """The 502 path: with a ReportCardStyleAssignment present, classroom_ids is
        non-empty and the old DISTINCT ON evaluated → NotSupportedError 500. The
        portable branch must return a sample student per classroom instead."""
        from datetime import date

        from apps.academics.models import AcademicYear, Classroom, Department
        from apps.people.models import StudentProfile
        from apps.runtime_blueprints.models import ReportCardStyle
        from apps.schools.models import School
        from apps.siteconfig.models import ReportCardStyleAssignment
        from apps.siteconfig.views import build_reportcard_builder_context

        # Only the fast path matters: on Postgres this uses DISTINCT ON; here (SQLite)
        # it must take the portable branch. Guard so the test is meaningful.
        self.assertFalse(connection.features.can_distinct_on_fields)

        school = School.objects.create(
            name="Wave1 Report High",
            subdomain="wave1-report-high",
            slug="wave1-report-high",
            is_active=True,
        )
        year = AcademicYear.objects.create(
            school=school,
            name="2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        dept = Department.objects.create(school=school, name="General", code="GEN")
        classroom = Classroom.objects.create(
            school=school, academic_year=year, department=dept, name="Grade 1A", code="G1A"
        )
        StudentProfile.objects.create(
            first_name="Ada", last_name="Zephyr", classroom=classroom, is_active=True
        )
        StudentProfile.objects.create(
            first_name="Bea", last_name="Alpha", classroom=classroom, is_active=True
        )
        style = ReportCardStyle.objects.create(name="Term Standard", slug="term-standard")
        ReportCardStyleAssignment.objects.create(classroom=classroom, style=style)

        req = RequestFactory().get("/siteconfig/reportcard-builder/")
        req.user = U.objects.create(username="w1-rcb", is_staff=True)
        req.school = school

        ctx = build_reportcard_builder_context(req)  # must not raise NotSupportedError
        # The single-per-classroom sample resolved via the portable path.
        assignments = ctx.get("assignments") or []
        samples = [getattr(a, "sample_student", None) for a in assignments]
        self.assertTrue(any(s is not None for s in samples))
