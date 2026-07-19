"""Wave I (2026-05-15): solve_timetable CLI smoke test.

The underlying constraint solver
(``apps.academics.scheduling_solver.generate_timetable_with_solver``) routes
to the real, wired CSP generator
(``apps.academics.scheduling.TimetableGenerator``) in every deployed
environment, because ``ortools`` is intentionally NOT a declared dependency
(so the CP-SAT path ``_solve_with_ortools`` is dormant by default — see the
``scheduling_solver`` module docstring). This file verifies:

* the CLI wrapper's operator-facing contract (clean ``CommandError`` on
  unknown year/term, ``--no-ortools`` honoured, success summary line);
* and — without mocking the solver out — that ``generate_timetable_with_solver``
  ACTUALLY runs the wired ``TimetableGenerator`` (CSP) and that the dormant
  CP-SAT entrypoint refuses to masquerade as having run when ortools is absent.

The CLI-contract tests use ``mock.patch`` so we exercise the wrapper without
spinning up TimeSlots/Rooms/SubjectAssignments — that is the solver's
responsibility, not the CLI's. The two solver-reality tests at the bottom do
NOT mock the solver; they assert against the genuinely wired code path.
"""

from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class SolveTimetableCommandTests(TestCase):
    databases = {"default"}

    def test_unknown_year_raises_command_error(self):
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "solve_timetable",
                "--year", "9999999",
                "--term", "1",
                stdout=StringIO(), stderr=StringIO(),
            )
        self.assertIn("AcademicYear", str(ctx.exception))

    def test_cli_prints_ortools_label_only_when_ortools_actually_available(self):
        """The CLI's ``solver=ortools`` label tracks REAL ortools availability.

        This used to patch ``_ortools_available`` to ``True`` while also mocking
        ``generate_timetable_with_solver`` out entirely — claiming "ortools
        coverage" without ever exercising CP-SAT or even the real solver. That
        was fake-green: in production ortools is never installed, so the label
        is always ``solver=csp``. Here we (a) mock ONLY the solver-return so the
        CLI's summary-formatting branch is reachable, and (b) drive the label
        off the genuine ``_ortools_available()`` probe instead of forcing it,
        so the assertion reflects the deployed reality rather than a fiction.
        """
        from apps.academics.scheduling_solver import _ortools_available

        class _FakeSchedule:
            pk = 42
            class entries:
                @staticmethod
                def count(): return 17

        with mock.patch(
            "apps.academics.management.commands.solve_timetable.Command._resolve_year",
            return_value=object(),
        ), mock.patch(
            "apps.academics.management.commands.solve_timetable.Command._resolve_term",
            return_value=object(),
        ), mock.patch(
            "apps.academics.management.commands.solve_timetable.Command._resolve_user",
            return_value=None,
        ), mock.patch(
            "apps.academics.management.commands.solve_timetable.generate_timetable_with_solver",
            return_value=_FakeSchedule(),
        ):
            out = StringIO()
            call_command("solve_timetable", "--year", "1", "--term", "1", stdout=out)
        body = out.getvalue()
        self.assertIn("schedule #42", body)
        self.assertIn("entries=17", body)
        # The label MUST match the real probe, not a forced one. In CI/prod
        # (ortools absent) this is "solver=csp"; if an operator has installed
        # ortools the same assertion still holds because it reads the probe.
        expected_label = "solver=ortools" if _ortools_available() else "solver=csp"
        self.assertIn(expected_label, body)

    def test_no_ortools_flag_falls_back_to_csp(self):
        class _FakeSchedule:
            pk = 7
            class entries:
                @staticmethod
                def count(): return 3

        with mock.patch(
            "apps.academics.management.commands.solve_timetable.Command._resolve_year",
            return_value=object(),
        ), mock.patch(
            "apps.academics.management.commands.solve_timetable.Command._resolve_term",
            return_value=object(),
        ), mock.patch(
            "apps.academics.management.commands.solve_timetable.Command._resolve_user",
            return_value=None,
        ), mock.patch(
            "apps.academics.management.commands.solve_timetable.generate_timetable_with_solver",
            return_value=_FakeSchedule(),
        ):
            out = StringIO()
            call_command(
                "solve_timetable", "--year", "1", "--term", "1",
                "--no-ortools",
                stdout=out,
            )
        self.assertIn("solver=csp", out.getvalue())

    def test_solver_returning_none_exits_nonzero(self):
        with mock.patch(
            "apps.academics.management.commands.solve_timetable.Command._resolve_year",
            return_value=object(),
        ), mock.patch(
            "apps.academics.management.commands.solve_timetable.Command._resolve_term",
            return_value=object(),
        ), mock.patch(
            "apps.academics.management.commands.solve_timetable.Command._resolve_user",
            return_value=None,
        ), mock.patch(
            "apps.academics.management.commands.solve_timetable.generate_timetable_with_solver",
            return_value=None,
        ):
            with self.assertRaises(SystemExit) as ctx:
                call_command(
                    "solve_timetable", "--year", "1", "--term", "1",
                    stdout=StringIO(), stderr=StringIO(),
                )
            self.assertEqual(ctx.exception.code, 1)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class SolverRealityTests(TestCase):
    """No-mock tests that exercise the ACTUALLY wired solver.

    These replace the old fake "ortools coverage" claim: rather than patching
    ``_ortools_available`` to ``True`` and mocking the solver out, they run the
    genuine ``generate_timetable_with_solver`` and assert it produced a real
    ``Schedule`` via ``TimetableGenerator`` (the CSP path that is wired in
    production), and that the dormant CP-SAT entrypoint cannot silently no-op.
    """

    databases = {"default"}

    def _make_year_term(self):
        from datetime import date

        from apps.schools.models import School
        from apps.academics.models import AcademicYear, Term

        school = School.objects.create(name="Solver Test School", slug="solver-test-school")
        year = AcademicYear.objects.create(
            school=school,
            name="2026-2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_active=True,
        )
        term = Term.objects.create(
            school=school,
            academic_year=year,
            name="Term 1",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 20),
        )
        return year, term

    def test_generate_uses_wired_csp_generator_when_ortools_absent(self):
        """generate_timetable_with_solver runs the real TimetableGenerator.

        With ortools not installed (the project default), the function must
        fall back to ``TimetableGenerator.generate_schedule``, which produces a
        persisted Schedule named ``"<term> Schedule"`` (NOT the CP-SAT path's
        ``"<term> Schedule (OR-tools)"``). Asserting on that name proves the
        wired CSP solver actually ran — no mocks.
        """
        from apps.academics.scheduling_solver import (
            _ortools_available,
            generate_timetable_with_solver,
        )
        from apps.academics.scheduling import Schedule

        if _ortools_available():
            self.skipTest("ortools installed in this env; CSP-fallback assertion N/A")

        year, term = self._make_year_term()
        # created_by must be a real user: Schedule.created_by is a non-null FK, so
        # passing None raised IntegrityError before the assertions below could run
        # (the test never actually exercised the solver wiring it is named for).
        # Every production caller supplies the acting user; only this test did not.
        actor = User.objects.create_user(
            username="csp_fallback_actor_%s" % id(self),
            email="csp_fallback_actor_%s@example.com" % id(self),
            password="password123",
        )
        schedule = generate_timetable_with_solver(
            academic_year=year, term=term, created_by=actor,
        )
        self.assertIsInstance(schedule, Schedule)
        self.assertIsNotNone(schedule.pk)
        # CSP generator names it "<term> Schedule"; the CP-SAT path would have
        # appended " (OR-tools)". Absence of that suffix == the wired path ran.
        self.assertNotIn("(OR-tools)", schedule.name)
        self.assertIn(term.name, schedule.name)

    def test_dormant_cp_sat_entrypoint_refuses_to_run_without_ortools(self):
        """_solve_with_ortools raises ImportError when ortools is absent.

        Locks the honesty fix: the dormant CP-SAT path can never masquerade as
        having executed. If ortools is genuinely installed, this assertion is
        not applicable.
        """
        from apps.academics.scheduling_solver import (
            _ortools_available,
            _solve_with_ortools,
        )

        if _ortools_available():
            self.skipTest("ortools installed in this env; dormant-path guard N/A")

        with self.assertRaises(ImportError):
            _solve_with_ortools(object(), object(), None)


class SolveTimetableDryRunPersistenceTests(TestCase):
    """Metric 15 — --dry-run must not leave Schedule rows committed."""

    def test_dry_run_rolls_back_persisted_schedule(self):
        from apps.academics.scheduling import Schedule
        from apps.academics.tests.test_timetable_publish_flow import _TimetableGraphMixin
        from apps.schools.models import School

        mixin = _TimetableGraphMixin()
        uid = "dryrun1"
        school = School.objects.create(
            name=f"DryRun School {uid}",
            slug=f"dryrun-{uid}",
            subdomain=f"dryrun-{uid}",
            is_active=True,
        )
        graph = mixin.build_graph(school, uid)
        actor = User.objects.create_user(
            username=f"dryrun_actor_{uid}",
            password="password123",
        )
        before = Schedule.objects.filter(
            academic_year=graph["year"], term=graph["term"]
        ).count()
        out = StringIO()
        call_command(
            "solve_timetable",
            "--year",
            str(graph["year"].pk),
            "--term",
            str(graph["term"].pk),
            "--created-by",
            str(actor.pk),
            "--no-ortools",
            "--dry-run",
            stdout=out,
            stderr=StringIO(),
        )
        self.assertIn("dry-run, rolled back", out.getvalue())
        after = Schedule.objects.filter(
            academic_year=graph["year"], term=graph["term"]
        ).count()
        self.assertEqual(after, before)


class OrtoolsOptionalInstallContractTests(SimpleTestCase):
    """Metric 15 — CP-SAT is opt-in via requirements_optional, not core deps."""

    def test_ortools_pinned_only_in_optional_requirements(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        optional = (root / "requirements_optional.txt").read_text(encoding="utf-8")
        core = (root / "requirements.txt").read_text(encoding="utf-8")
        self.assertRegex(optional, r"(?m)^ortools>=")
        self.assertNotRegex(core, r"(?m)^ortools")
