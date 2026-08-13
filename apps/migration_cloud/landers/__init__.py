"""Per-domain landers — persist canonical rows into the tenant schema.

Each domain in the canonical ontology has at most one ``Lander`` that
knows how to take canonical rows (dicts keyed by canonical field name)
and persist them under the tenant schema with full RLS scoping.

Landers are the *only* place in Migration Cloud that touches tenant
models. Everything upstream (intake, profiler, classifier, mapper,
transformers) operates on canonical, tenant-agnostic data. This keeps
the dangerous code (tenant writes) in one tightly-audited surface.

Landers shipped (24 first-class + 1 catch-all fallback, v3.29 —
up from 23 first-class in v3.27 with the three per-student
assignment landers below now promoted to first-class schoolops
models, with DFV fallback retained for out-of-order bundles):

    * ``students``               → ``apps.people.StudentProfile``      (upsert on external_id)
    * ``guardians``              → ``apps.people.StudentGuardian``     (linked via student_external_id)
    * ``staff``                  → ``apps.people.TeacherProfile``      (upsert on external_id)
    * ``enrollment``             → updates StudentProfile grade_level / enrollment_status / section
    * ``structure``              → provisions the academic scaffold (AcademicYear/Term/Department/Classroom/Specialty/Subject/SubjectAssignment + a target-scoped teacher) for a SPLIT into an empty target, in wave 0 so enrollment+grades resolve
    * ``academics``              → ``apps.academics.Subject``          (upsert on name; Subject catalog for grades)
    * ``specialties``            → ``apps.academics.Specialty`` (+ required ``Department``) (2026-08-13 — trades/streams catalog; dedup on (school, name); keeps the source code when globally free else mints one; wave 0 so enrollment can place students on a specialty)
    * ``sections``               → ``apps.academics.Classroom``        (upsert on code/slug)
    * ``attendance``             → ``apps.academics.Attendance``       (upsert on student+date)
    * ``grades``                 → ``apps.evals.Evaluation``           (upsert on student+term+subject)
    * ``behavior``               → ``apps.academics.Incident``         (upsert on student+date+hash)
    * ``finance``                → ``apps.finance.Invoice``            (upsert on reference)
    * ``transcripts``            → ``apps.people.TranscriptVaultItem`` (upsert on student+hash)
    * ``health``                 → ``apps.schoolops.HealthRecord``     (upsert on student+date+category)
    * ``payroll``                → DFV custom records (Payslip needs PayrollRun/Employee FKs — see payroll_lander honesty note)
    * ``communications``         → ``apps.communication.Message``      (upsert on recipient+subject)
    * ``events``                 → ``apps.school_events.SchoolEvent``  (upsert on title+starts_at)
    * ``library``                → ``apps.schoolops.LibraryItem``      (upsert on isbn or title+author)
    * ``transport``              → ``apps.schoolops.Route``            (upsert on school+route name)
    * ``hostel``                 → ``apps.schoolops.HostelRoom``       (upsert on hostel+room name)
    * ``cafeteria``              → ``apps.schoolops.CanteenMeal``      (upsert on school+meal name)
    * ``transport_assignments``  → ``apps.schoolops.TransportAssignment`` (v3.29 — upsert on student+route+effective_from; falls back to ``apps.metadata.DynamicFieldValue`` when the Route catalog row hasn't landed yet so out-of-order bundles never drop data)
    * ``hostel_assignments``     → ``apps.schoolops.HostelAssignment`` (v3.29 — upsert on student+room+effective_from; same DFV fallback when HostelRoom hasn't landed)
    * ``cafeteria_assignments``  → ``apps.schoolops.MealPlanBalance`` (v3.29 — upsert on student+meal_plan, meal_plan FK nullable for generic credit; last-wins balance with ``last_topup_amount/_at`` audit trail; Decimal end-to-end to satisfy scan_money_float)
    * ``alumni``                 → ``apps.people.StudentProfile`` w/ enrollment_status='graduated'
    * ``compliance``             → DFV custom records (no first-class ComplianceCheck land path — see compliance_lander)
    * ``athletics_teams``        → ``apps.athletics.Team`` (2026-07-09 — upsert on season+name; provisions Sport+Season school-scoped on the fly; optional home_venue skip-when-unresolved)
    * ``athletics_memberships``  → ``apps.athletics.TeamMembership`` (2026-07-09 — upsert on team+student; quarantines on unresolved student/team)
    * ``athletics_fixtures``     → ``apps.athletics.Fixture`` (+ ``FixtureResult`` when a score is present; 2026-07-09 — upsert on team+opponent_name+scheduled_start; optional venue skip-when-unresolved)
    * ``custom_fields`` (fallback) → ``apps.metadata.DynamicFieldValue``

Catch-all invariant: any canonical domain without a registered lander
falls through to ``custom_fields`` so no data is ever dropped. Tail
domains lost their pre-v3.26 dynamic_field fallback as the 11 landers
listed above earned first-class status.

FK dependency ordering lives in
``apps.migration_cloud.orchestrator._DEPENDENCY_WAVES``:
roots (students/staff/sections) → enrollment+guardians+schedule →
attendance+grades+behavior+finance+others → custom_fields. Workers
parallel within a wave, serial across waves.

Add a domain-specific lander by subclassing :class:`Lander` and
registering with ``register("<domain>", MyLander())``.
"""

from __future__ import annotations

from .base import Lander, LanderError, LanderResult, get_lander, register
from . import dynamic_field_lander  # noqa: F401 — generic fallback
from . import guardian_lander  # noqa: F401
from . import staff_lander  # noqa: F401
from . import student_lander  # noqa: F401
# Phase U5 expansion — domain-specific landers.
from . import academic_sessions_lander  # noqa: F401 — OneRoster academicSessions → AcademicYear/Term (D-3)
from . import academics_lander  # noqa: F401 — courses/subjects → apps.academics.Subject
from . import specialty_lander  # noqa: F401 — trades/streams → apps.academics.Specialty (+ Department)
from . import attendance_lander  # noqa: F401
from . import behavior_lander  # noqa: F401
from . import enrollment_lander  # noqa: F401
from . import finance_lander  # noqa: F401
from . import grades_lander  # noqa: F401
from . import sections_lander  # noqa: F401
from . import structure_lander  # noqa: F401 — SPLIT academic scaffold (wave 0)
# v3.26 — long-tail closure: the 11 remaining canonical domains
# graduate from dynamic_field fallback to first-class landers.
from . import alumni_lander  # noqa: F401
from . import cafeteria_lander  # noqa: F401
from . import communications_lander  # noqa: F401
from . import compliance_lander  # noqa: F401
from . import events_lander  # noqa: F401
from . import health_lander  # noqa: F401
from . import hostel_lander  # noqa: F401
from . import library_lander  # noqa: F401
from . import payroll_lander  # noqa: F401
from . import schedule_lander  # noqa: F401 — timetable rows preserved as DFV (ScheduleEntry needs the solver graph)
from . import transcripts_lander  # noqa: F401
from . import transport_lander  # noqa: F401
# v3.27 — per-student assignment landers paired with the v3.26 catalog
# landers. v3.29 — promoted to first-class apps.schoolops models
# (TransportAssignment / HostelAssignment / MealPlanBalance) with DFV
# fallback retained for out-of-order bundles where the catalog row
# hasn't landed yet.
from . import cafeteria_assignment_lander  # noqa: F401
from . import hostel_assignment_lander  # noqa: F401
from . import transport_assignment_lander  # noqa: F401
# Athletics module round-trip (2026-07-09) — teams/roster/fixtures land
# into apps.athletics (Sport/Season/Team/TeamMembership/Fixture/FixtureResult).
from . import athletics_teams_lander  # noqa: F401
from . import athletics_memberships_lander  # noqa: F401
from . import athletics_fixtures_lander  # noqa: F401

__all__ = [
    "Lander",
    "LanderError",
    "LanderResult",
    "get_lander",
    "register",
]
