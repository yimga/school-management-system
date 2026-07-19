"""Wave I (2026-05-15): CLI wrapper for the timetable solver.

The platform already ships a constraint-based solver
(``apps.academics.scheduling_solver.generate_timetable_with_solver``)
that uses Google OR-Tools CP-SAT when available, falling back to a
constraint-satisfaction ``TimetableGenerator`` otherwise. This command
exposes it to operators so timetable runs are auditable and reproducible
from CI / cron.

Usage::

    python manage.py solve_timetable --year <id> --term <id>
    python manage.py solve_timetable --year <id> --term <id> --no-ortools
    python manage.py solve_timetable --year <id> --term <id> --dry-run

The CP-SAT path is industry-standard for school timetabling (better
than a genetic algorithm at this problem size — exact constraints
guarantee feasibility, not just convergence). The fallback CSP-style
generator keeps the surface useful on hosts where OR-Tools is not
installed.

Exit code 0 on success, 1 when no schedule could be produced.

``--dry-run`` runs the solver inside ``transaction.atomic()`` and marks
the transaction for rollback so no Schedule/ScheduleEntry rows persist.
(A bare ``savepoint()`` outside ``atomic()`` is a no-op under autocommit
and historically left dry-run writes committed.)
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.scheduling_solver import (
    _ortools_available,
    generate_timetable_with_solver,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Generate a timetable for an academic year + term using OR-Tools CP-SAT (or fallback)."

    def add_arguments(self, parser):
        parser.add_argument("--year", required=True, help="AcademicYear pk to schedule.")
        parser.add_argument("--term", required=True, help="Term pk to schedule.")
        parser.add_argument("--no-ortools", action="store_true",
                            help="Force the CSP-style fallback even if OR-Tools is installed.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Run the solver but roll back any persistence (debug surface).")
        parser.add_argument("--created-by", default="",
                            help="Optional user id to attribute the schedule to; defaults to first staff user.")

    def handle(self, *args, **opts):
        year = self._resolve_year(opts["year"])
        term = self._resolve_term(opts["term"])
        created_by = self._resolve_user(opts.get("created_by") or "")

        use_ortools = not opts.get("no_ortools")
        if use_ortools and not _ortools_available():
            self.stdout.write(self.style.WARNING(
                "OR-Tools not installed — falling back to CSP-style TimetableGenerator."
            ))

        dry_run = bool(opts.get("dry_run"))
        try:
            with transaction.atomic():
                schedule = generate_timetable_with_solver(
                    academic_year=year,
                    term=term,
                    created_by=created_by,
                    use_ortools=use_ortools,
                )
                if schedule is None:
                    self.stderr.write(self.style.ERROR(
                        "Solver produced no schedule (no rooms / time slots / demands)."
                    ))
                    raise SystemExit(1)

                entry_count = getattr(schedule, "entries", None)
                entry_count = entry_count.count() if entry_count is not None else "?"
                suffix = " (dry-run, rolled back)" if dry_run else ""
                self.stdout.write(self.style.SUCCESS(
                    f"schedule #{getattr(schedule, 'pk', '?')} entries={entry_count}"
                    f" solver={'ortools' if use_ortools and _ortools_available() else 'csp'}{suffix}"
                ))
                if dry_run:
                    transaction.set_rollback(True)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 — surface every failure mode
            raise CommandError(f"solve_timetable failed: {exc}") from exc

    def _resolve_year(self, year_id: str):
        from django.apps import apps as django_apps
        try:
            AcademicYear = django_apps.get_model("academics", "AcademicYear")
        except LookupError as exc:
            raise CommandError("AcademicYear model not registered") from exc
        obj = AcademicYear.objects.filter(pk=year_id).first()
        if obj is None:
            raise CommandError(f"AcademicYear #{year_id} not found.")
        return obj

    def _resolve_term(self, term_id: str):
        from django.apps import apps as django_apps
        try:
            Term = django_apps.get_model("academics", "Term")
        except LookupError as exc:
            raise CommandError("Term model not registered") from exc
        obj = Term.objects.filter(pk=term_id).first()
        if obj is None:
            raise CommandError(f"Term #{term_id} not found.")
        return obj

    def _resolve_user(self, user_id: str):
        if user_id:
            user = User.objects.filter(pk=user_id).first()
            if user is None:
                raise CommandError(f"User #{user_id} not found.")
            return user
        return User.objects.filter(is_staff=True).order_by("pk").first()
