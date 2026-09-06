"""Year-ops preflight: can this school actually RUN the year it just set up?

``e2e_lifecycle`` proves a tenant can be PROVISIONED. Nothing proved it can be
OPERATED, and those are different questions with different failure modes:
provisioning fails loudly, while the academic year fails silently -- every step
reports success and the next one returns an empty list.

The chain a school actually depends on, in order, with what breaks when a link
is missing:

    active AcademicYear   -> no year: get_active_year_and_term returns
                             (None, None); roll call shows no classes at all
    active Term           -> no active term: teacher_marks_entry answers 403
                             "No active academic year/term set by admin yet."
                             and timetable generation bounces
    Term.school stamped   -> unstamped: provision_teaching_grid_for_school
                             filters school= and matches nothing, so the grid
                             is never built
    Department/Specialty  -> Classroom PROTECTs both; without them no class can
                             be created at all
    Classroom + Subject   -> nothing to teach, nothing to attend
    SubjectAssignment     -> the teaching grid; without it no teacher can be
                             assigned and no mark has anywhere to land
    TeacherAssignment     -> without it _attendance_visible_classrooms locks
                             the teacher to [] and marks entry 403s
    enrolled students     -> a class with no students saves an empty roll call
    resolvable mark scale -> resolve_school_score_scale raises, so the mark
                             workbench falls back to its NARROWEST bound

Every one of those is invisible from the admin's side: the setup pages all say
they succeeded. This command asks the same questions the runtime asks, in the
same way, and prints the next action for each gap rather than a status code.

    python manage.py year_ops_preflight --school buea-high
    python manage.py year_ops_preflight --all-active
    python manage.py year_ops_preflight --school buea-high --json

Read-only. It never writes, so it is safe to run against production.
Exit code is 1 when any BLOCKER is found, so it can gate a go-live script.
"""

from __future__ import annotations

import json

from django.core.exceptions import FieldError, ObjectDoesNotExist
from django.core.management.base import BaseCommand
from django.db import DatabaseError

BLOCKER = "BLOCKER"
WARN = "WARN"
OK = "OK"


class Check:
    __slots__ = ("key", "status", "detail", "next_action")

    def __init__(self, key: str, status: str, detail: str = "", next_action: str = ""):
        self.key = key
        self.status = status
        self.detail = detail
        self.next_action = next_action

    def as_dict(self) -> dict:
        return {
            "check": self.key,
            "status": self.status,
            "detail": self.detail,
            "next_action": self.next_action,
        }


class Command(BaseCommand):
    help = "Check that a school can actually operate its academic year (read-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            help="School slug or id. Omit with --all-active to sweep every active school.",
        )
        parser.add_argument(
            "--all-active",
            action="store_true",
            help="Run against every active school.",
        )
        parser.add_argument("--json", action="store_true", help="Emit JSON.")

    def handle(self, *args, **options):
        from apps.schools.models import School

        schools = []
        if options.get("all_active"):
            # tenant-isolation-allow: operator-preflight-sweeps-every-active-school-by-design
            schools = list(School.objects.filter(is_active=True).order_by("slug"))
        elif options.get("school"):
            from apps.schools.school_cli_resolution import resolve_school_arg

            school = resolve_school_arg(options["school"])
            if school is None:
                self.stderr.write(f"No school matched {options['school']!r}")
                return
            schools = [school]
        else:
            self.stderr.write("Pass --school <slug> or --all-active.")
            return

        payload = []
        worst_is_blocker = False
        for school in schools:
            checks = self.run_checks(school)
            payload.append(
                {
                    "school": school.slug,
                    "school_name": school.name,
                    "checks": [c.as_dict() for c in checks],
                }
            )
            if any(c.status == BLOCKER for c in checks):
                worst_is_blocker = True

        if options.get("json"):
            self.stdout.write(json.dumps(payload, indent=2))
        else:
            self._render(payload)

        if worst_is_blocker:
            # A non-zero exit lets a go-live script refuse to proceed.
            raise SystemExit(1)

    # -- rendering -----------------------------------------------------------
    def _render(self, payload):
        for entry in payload:
            self.stdout.write("")
            self.stdout.write(f"=== {entry['school_name']} ({entry['school']})")
            for c in entry["checks"]:
                mark = {OK: "  ok  ", WARN: " warn ", BLOCKER: "BLOCK "}[c["status"]]
                self.stdout.write(f"  [{mark}] {c['check']:<22} {c['detail']}")
                if c["next_action"]:
                    self.stdout.write(f"           -> {c['next_action']}")
            blockers = [c for c in entry["checks"] if c["status"] == BLOCKER]
            self.stdout.write(
                f"  {len(blockers)} blocker(s); "
                f"{sum(1 for c in entry['checks'] if c['status'] == WARN)} warning(s)"
            )

    # -- the checks ----------------------------------------------------------
    def run_checks(self, school) -> list[Check]:
        from apps.academics.models import (
            Classroom,
            Department,
            Specialty,
            Subject,
            SubjectAssignment,
            Term,
        )
        from apps.academics.services import get_active_year_and_term
        from apps.evals.models import TeacherAssignment
        from apps.people.models import StudentProfile, TeacherProfile

        checks: list[Check] = []
        year, term = get_active_year_and_term(school=school)

        # 1. Active academic year.
        if year is None:
            checks.append(
                Check(
                    "academic_year",
                    BLOCKER,
                    "no active academic year",
                    "Set up and ACTIVATE an academic year "
                    "(Settings > Academic years). Nothing below can be checked "
                    "until this exists.",
                )
            )
            return checks
        checks.append(Check("academic_year", OK, f"{year.name}"))

        # 2. Active term. The single most common silent dead end.
        if term is None:
            n_terms = Term.objects.filter(academic_year=year).count()
            checks.append(
                Check(
                    "active_term",
                    BLOCKER,
                    f"{n_terms} term(s) exist, none is active",
                    "Activate the current term. Until then teachers get "
                    "403 'No active academic year/term set by admin yet.' on "
                    "mark entry, and the timetable cannot be generated.",
                )
            )
        else:
            checks.append(Check("active_term", OK, f"{term.name}"))

        # 3. Terms stamped with the school. An unstamped term is invisible to
        #    the teaching-grid provisioner even though the admin can see it.
        unstamped = Term.objects.filter(academic_year=year, school__isnull=True).count()
        if unstamped:
            checks.append(
                Check(
                    "term_tenancy",
                    BLOCKER,
                    f"{unstamped} term(s) have no school_id",
                    "These terms are invisible to every school-scoped lookup, "
                    "so the teaching grid cannot be built from them. Re-run the "
                    "academic-year setup step to adopt them.",
                )
            )
        else:
            checks.append(Check("term_tenancy", OK, "all terms stamped"))

        unpositioned = Term.objects.filter(
            academic_year=year, position__isnull=True
        ).count()
        if unpositioned:
            checks.append(
                Check(
                    "term_position",
                    WARN,
                    f"{unpositioned} term(s) have no position",
                    "Term order is read from `position`; without it terms sort "
                    "arbitrarily and the third-term guard never fires.",
                )
            )

        # 4. Structure. Classroom PROTECTs department, so a missing department
        #    is not a warning -- no class can be created at all.
        n_dept = Department.objects.filter(school=school).count()
        n_spec = Specialty.objects.filter(school=school).count()
        if not n_dept:
            checks.append(
                Check(
                    "departments",
                    BLOCKER,
                    "no departments",
                    "A classroom requires a department (PROTECT). Create one "
                    "before any class can be added.",
                )
            )
        else:
            checks.append(Check("departments", OK, f"{n_dept} department(s), {n_spec} specialty(ies)"))

        classrooms = Classroom.objects.filter(academic_year=year)
        n_class = classrooms.count()
        if not n_class:
            checks.append(
                Check(
                    "classrooms",
                    BLOCKER,
                    "no classrooms in the active year",
                    "Create the year's classes. Roll call, the timetable and "
                    "the teaching grid all hang off these.",
                )
            )
        else:
            checks.append(Check("classrooms", OK, f"{n_class} in {year.name}"))

        orphan_classes = classrooms.filter(school__isnull=True).count()
        if orphan_classes:
            checks.append(
                Check(
                    "classroom_tenancy",
                    BLOCKER,
                    f"{orphan_classes} classroom(s) have no school_id",
                    "These do NOT appear on the classroom list page (it filters "
                    "school=), and uniq_classroom_school_code stops enforcing "
                    "for them because NULLs compare distinct.",
                )
            )

        n_subj = Subject.objects.filter(school=school).count()
        if not n_subj:
            checks.append(
                Check("subjects", BLOCKER, "no subjects", "Seed the subject list for the school.")
            )
        else:
            checks.append(Check("subjects", OK, f"{n_subj} subject(s)"))

        # 5. Teaching grid.
        grid = SubjectAssignment.objects.filter(academic_year=year)
        if term is not None:
            grid = grid.filter(term=term)
        n_grid = grid.count()
        if not n_grid:
            checks.append(
                Check(
                    "teaching_grid",
                    BLOCKER,
                    "no subject assignments for the active term",
                    "Nothing connects a subject to a class, so no teacher can "
                    "be assigned and marks have nowhere to land.",
                )
            )
        else:
            checks.append(Check("teaching_grid", OK, f"{n_grid} subject assignment(s)"))

        # 6. Teacher assignments -- the link roll call and mark entry read.
        teachers = TeacherProfile.objects.filter(school=school, is_active=True)
        n_teachers = teachers.count()
        assigned_teacher_ids = set(
            TeacherAssignment.objects.filter(
                academic_year=year, is_active=True, teacher__school=school
            ).values_list("teacher_id", flat=True)
        )
        unassigned = n_teachers - len(assigned_teacher_ids)
        if n_teachers and not assigned_teacher_ids:
            checks.append(
                Check(
                    "teacher_assignments",
                    BLOCKER,
                    f"0 of {n_teachers} teachers are assigned",
                    "Every teacher will see an empty class list on roll call "
                    "and a 403 on mark entry. Assign teachers to the teaching "
                    "grid.",
                )
            )
        elif unassigned:
            checks.append(
                Check(
                    "teacher_assignments",
                    WARN,
                    f"{unassigned} of {n_teachers} teachers have no assignment",
                    "Those teachers see an empty class list on roll call.",
                )
            )
        else:
            checks.append(
                Check("teacher_assignments", OK, f"all {n_teachers} teacher(s) assigned")
            )

        # 7. Students actually placed in a class.
        placed = StudentProfile.objects.filter(
            school=school, classroom__isnull=False
        ).count()
        unplaced = StudentProfile.objects.filter(
            school=school, classroom__isnull=True
        ).count()
        if not placed:
            checks.append(
                Check(
                    "enrollment",
                    BLOCKER,
                    f"no student is in a class ({unplaced} unplaced)",
                    "Roll call saves an empty register and every class list is "
                    "blank until students are placed.",
                )
            )
        elif unplaced:
            checks.append(
                Check("enrollment", WARN, f"{placed} placed, {unplaced} unplaced")
            )
        else:
            checks.append(Check("enrollment", OK, f"{placed} student(s) placed"))

        # 8. The mark scale must RESOLVE. It fails closed on purpose: a /20
        #    school that silently got /100 once accepted a mark of 25.
        checks.append(self._check_scale(school))
        return checks

    def _check_scale(self, school) -> Check:
        from apps.evals.grading_provisioning import resolve_school_score_scale

        # A preflight reports rather than crashes, but it still names what it
        # catches. Catching everything here would swallow an ordinary programming
        # error and report it to a head teacher as "mark scale unresolved",
        # sending them off to seed weights that were never the problem. These are
        # the ways a resolver legitimately fails: absent config, a missing related
        # row, a malformed profile.
        try:
            scale = resolve_school_score_scale(school)
        except (
            AttributeError,
            KeyError,
            LookupError,
            TypeError,
            ValueError,
            ObjectDoesNotExist,
            FieldError,
            DatabaseError,
        ) as exc:
            return Check(
                "mark_scale",
                BLOCKER,
                f"unresolved: {type(exc).__name__}: {exc}",
                "The mark workbench falls back to its narrowest bound and "
                "over-rejects valid marks. Seed AssessmentWeights for the "
                "school, or set the country grading profile.",
            )
        return Check("mark_scale", OK, f"marks are out of {scale}")
