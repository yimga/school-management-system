"""Per-domain landers — persist canonical rows into the tenant schema.

Each domain in the canonical ontology has at most one ``Lander`` that
knows how to take canonical rows (dicts keyed by canonical field name)
and persist them under the tenant schema with full RLS scoping.

Landers are the *only* place in Migration Cloud that touches tenant
models. Everything upstream (intake, profiler, classifier, mapper,
transformers) operates on canonical, tenant-agnostic data. This keeps
the dangerous code (tenant writes) in one tightly-audited surface.

Landers shipped (23 first-class + 1 catch-all fallback, v3.27 —
up from 20 first-class in v3.26 with the three per-student
assignment landers below):

    * ``students``               → ``apps.people.StudentProfile``      (upsert on external_id)
    * ``guardians``              → ``apps.people.StudentGuardian``     (linked via student_external_id)
    * ``staff``                  → ``apps.people.TeacherProfile``      (upsert on external_id)
    * ``enrollment``             → updates StudentProfile grade_level / enrollment_status / section
    * ``sections``               → ``apps.academics.Classroom``        (upsert on code/slug)
    * ``attendance``             → ``apps.academics.Attendance``       (upsert on student+date)
    * ``grades``                 → ``apps.evals.Evaluation``           (upsert on student+term+subject)
    * ``behavior``               → ``apps.academics.Incident``         (upsert on student+date+hash)
    * ``finance``                → ``apps.finance.Invoice``            (upsert on reference)
    * ``transcripts``            → ``apps.people.TranscriptVaultItem`` (upsert on student+hash)
    * ``health``                 → ``apps.schoolops.HealthRecord``     (upsert on student+date+category)
    * ``payroll``                → ``apps.payroll.Payslip``            (upsert on employee+reference)
    * ``communications``         → ``apps.communication.Message``      (upsert on recipient+subject)
    * ``events``                 → ``apps.school_events.SchoolEvent``  (upsert on title+starts_at)
    * ``library``                → ``apps.schoolops.LibraryItem``      (upsert on isbn or title+author)
    * ``transport``              → ``apps.schoolops.Route``            (upsert on school+route name)
    * ``hostel``                 → ``apps.schoolops.HostelRoom``       (upsert on hostel+room name)
    * ``cafeteria``              → ``apps.schoolops.CanteenMeal``      (upsert on school+meal name)
    * ``transport_assignments``  → ``apps.metadata.DynamicFieldValue`` (upsert on student+route; v3.27 — first-class assignment model not yet shipped in schoolops)
    * ``hostel_assignments``     → ``apps.metadata.DynamicFieldValue`` (upsert on student+room+checkin_date; v3.27 — same rationale)
    * ``cafeteria_assignments``  → ``apps.metadata.DynamicFieldValue`` (upsert on student+meal_plan; v3.27 — same rationale; balance held as Decimal-str to satisfy scan_money_float)
    * ``alumni``                 → ``apps.people.StudentProfile`` w/ enrollment_status='graduated'
    * ``compliance``             → ``apps.compliance.ComplianceCheck`` (upsert on check_type+check_date)
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
from . import attendance_lander  # noqa: F401
from . import behavior_lander  # noqa: F401
from . import enrollment_lander  # noqa: F401
from . import finance_lander  # noqa: F401
from . import grades_lander  # noqa: F401
from . import sections_lander  # noqa: F401
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
from . import transcripts_lander  # noqa: F401
from . import transport_lander  # noqa: F401
# v3.27 — per-student assignment landers paired with the v3.26 catalog landers.
# Lands into apps.metadata.DynamicFieldValue until first-class assignment
# models ship in apps.schoolops.
from . import cafeteria_assignment_lander  # noqa: F401
from . import hostel_assignment_lander  # noqa: F401
from . import transport_assignment_lander  # noqa: F401

__all__ = [
    "Lander",
    "LanderError",
    "LanderResult",
    "get_lander",
    "register",
]
