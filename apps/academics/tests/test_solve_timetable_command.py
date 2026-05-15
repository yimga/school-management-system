"""Wave I (2026-05-15): solve_timetable CLI smoke test.

The underlying constraint solver
(``apps.academics.scheduling_solver.generate_timetable_with_solver``) has
substantial pre-existing test coverage; this test verifies the CLI
wrapper handles the operator-facing contract:

* unknown academic year / term raise a clean ``CommandError``;
* the ``--no-ortools`` flag is honoured;
* a successful run prints the expected summary line.

Uses ``mock.patch`` so we exercise the wrapper without spinning up
TimeSlots, Rooms, and SubjectAssignments — that is the solver's
responsibility, not the CLI's.
"""

from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings


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

    def test_successful_run_prints_summary(self):
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
        ), mock.patch(
            "apps.academics.management.commands.solve_timetable._ortools_available",
            return_value=True,
        ):
            out = StringIO()
            call_command("solve_timetable", "--year", "1", "--term", "1", stdout=out)
        body = out.getvalue()
        self.assertIn("schedule #42", body)
        self.assertIn("entries=17", body)
        self.assertIn("solver=ortools", body)

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
