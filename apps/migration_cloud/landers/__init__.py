"""Per-domain landers — persist canonical rows into the tenant schema.

Each domain in the canonical ontology has at most one ``Lander`` that
knows how to take canonical rows (dicts keyed by canonical field name)
and persist them under the tenant schema with full RLS scoping.

Landers are the *only* place in Migration Cloud that touches tenant
models. Everything upstream (intake, profiler, classifier, mapper,
transformers) operates on canonical, tenant-agnostic data. This keeps
the dangerous code (tenant writes) in one tightly-audited surface.

Landers shipped (10 first-class + 1 catch-all fallback, v2.7):

    * ``students``    → ``apps.people.StudentProfile``  (upsert on external_id)
    * ``guardians``   → ``apps.people.StudentGuardian`` (linked via student_external_id)
    * ``staff``       → ``apps.people.TeacherProfile``  (upsert on external_id)
    * ``enrollment``  → updates StudentProfile grade_level / enrollment_status / section
    * ``sections``    → ``apps.academics.Classroom``     (upsert on code/slug)
    * ``attendance``  → ``apps.academics.Attendance``    (upsert on student+date)
    * ``grades``      → ``apps.evals.Evaluation``        (upsert on student+term+subject)
    * ``behavior``    → ``apps.academics.Incident``      (upsert on student+date+hash)
    * ``finance``     → ``apps.finance.Invoice``         (upsert on reference)
    * ``custom_fields`` (fallback) → ``apps.metadata.DynamicFieldValue``

Catch-all invariant: any canonical domain without a registered lander
falls through to ``custom_fields`` so no data is ever dropped. Tail
domains (transcripts / health / library / transport / hostel /
cafeteria / etc.) land as DynamicFields today; per-domain hand-tuning
is incremental.

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

__all__ = [
    "Lander",
    "LanderError",
    "LanderResult",
    "get_lander",
    "register",
]
