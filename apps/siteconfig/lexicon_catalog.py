"""Canonical lexicon registry (Wave A — G1).

A tenant can rename any term in this registry (e.g. "Student" → "Scholar",
"Class" → "Cohort", "Teacher" → "Sensei") and have it reflected platform-wide
without code edits. Anything not in this registry is intentionally
untranslatable at runtime — keeps the surface area finite and auditable.

The four legacy keys from `terminology_service.DEFAULT_TERMINOLOGY`
(``grade``, ``gpa``, ``term``, ``report_card``) remain as aliases so existing
templates and curriculum templates keep working unchanged.

Cascade (most-specific wins):
    school -> ancestor schools (district/group walk via parent_school)
    -> curriculum template terminology_map
    -> country profile lexicon overlay
    -> registry default below

Override shapes accepted from JSON storage:
    "Scholar"                                      # singular only
    {"singular": "Scholar", "plural": "Scholars"}  # explicit plural
    {"singular": "Scholar"}                        # singular only, plural auto

Scope hints (``ui`` / ``email`` / ``all``) reserved for future filtering — for
now every term is treated as scope=``all``.
"""

from __future__ import annotations

from typing import Iterable

# --- Term registry ---------------------------------------------------------

# Shape: key -> (default_singular, default_plural, category, description)
# Category drives the settings-UI grouping; description is operator-facing.
LEXICON_REGISTRY: dict[str, tuple[str, str, str, str]] = {
    # People ------------------------------------------------------------
    "student": ("Student", "Students", "people", "Primary learner."),
    "teacher": ("Teacher", "Teachers", "people", "Subject instructor."),
    "parent": ("Parent", "Parents", "people", "Family contact."),
    "guardian": ("Guardian", "Guardians", "people", "Non-parent legal contact."),
    "principal": ("Principal", "Principals", "people", "School head."),
    "head_teacher": ("Head teacher", "Head teachers", "people", "Department or year lead."),
    "administrator": ("Administrator", "Administrators", "people", "Operations staff."),
    "staff": ("Staff member", "Staff", "people", "Any school employee."),
    "alumnus": ("Alumnus", "Alumni", "people", "Former student."),
    "counsellor": ("Counsellor", "Counsellors", "people", "Guidance role."),
    # Academic units ----------------------------------------------------
    "class": ("Class", "Classes", "academic", "Scheduled group meeting."),
    "course": ("Course", "Courses", "academic", "Curriculum unit (multi-term)."),
    "subject": ("Subject", "Subjects", "academic", "Discipline area."),
    "lesson": ("Lesson", "Lessons", "academic", "Single session of instruction."),
    "module": ("Module", "Modules", "academic", "Sub-unit of a course."),
    "assignment": ("Assignment", "Assignments", "academic", "Graded student work."),
    "exam": ("Exam", "Exams", "academic", "Formal assessment."),
    "quiz": ("Quiz", "Quizzes", "academic", "Short assessment."),
    "project": ("Project", "Projects", "academic", "Extended student work."),
    "homework": ("Homework", "Homework", "academic", "At-home assignment."),
    "sequence": ("Sequence", "Sequences", "academic", "Continuous-assessment unit (Cameroon system says 'sequence'; elsewhere 'test', 'CA', or 'assessment')."),
    # Organisation ------------------------------------------------------
    "school": ("School", "Schools", "organisation", "Top-level tenant unit."),
    "campus": ("Campus", "Campuses", "organisation", "Physical site."),
    "department": ("Department", "Departments", "organisation", "Academic division."),
    "classroom": ("Classroom", "Classrooms", "organisation", "Physical room."),
    "dormitory": ("Dormitory", "Dormitories", "organisation", "Residential block."),
    "library": ("Library", "Libraries", "organisation", "Resource centre."),
    # Time --------------------------------------------------------------
    "term": ("Term", "Terms", "time", "Academic period (term/semester)."),
    "semester": ("Semester", "Semesters", "time", "Half-year period."),
    "academic_year": ("Academic year", "Academic years", "time", "Full school year."),
    "period": ("Period", "Periods", "time", "Single scheduled slot."),
    "session": ("Session", "Sessions", "time", "Daily attendance block."),
    # Records -----------------------------------------------------------
    "grade": ("Grade", "Grades", "records", "Achievement mark."),
    "gpa": ("GPA", "GPAs", "records", "Grade-point average."),
    "report_card": ("Report card", "Report cards", "records", "Periodic results summary."),
    "transcript": ("Transcript", "Transcripts", "records", "Cumulative records."),
    "attendance": ("Attendance", "Attendance", "records", "Presence record."),
    # Communication -----------------------------------------------------
    "announcement": ("Announcement", "Announcements", "communication", "Broadcast notice."),
    "message": ("Message", "Messages", "communication", "Direct communication."),
    "notice": ("Notice", "Notices", "communication", "Posted alert."),
    # Finance -----------------------------------------------------------
    "fee": ("Fee", "Fees", "finance", "School-charged amount."),
    "invoice": ("Invoice", "Invoices", "finance", "Billable document."),
}

# Tone hints reserved for the AI gateway (e.g. CommunicationTemplate rendering).
TONE_CHOICES: tuple[str, ...] = ("warm", "formal", "playful")
DEFAULT_TONE: str = "warm"

# Categories (stable order for the settings UI).
LEXICON_CATEGORIES: tuple[str, ...] = (
    "people",
    "academic",
    "organisation",
    "time",
    "records",
    "communication",
    "finance",
)


def lexicon_keys() -> tuple[str, ...]:
    """Stable, sorted view of canonical keys."""
    return tuple(sorted(LEXICON_REGISTRY.keys()))


def default_singular(key: str) -> str:
    entry = LEXICON_REGISTRY.get(key)
    return entry[0] if entry else key


def default_plural(key: str) -> str:
    entry = LEXICON_REGISTRY.get(key)
    if entry:
        return entry[1]
    return auto_plural(key)


def category_for(key: str) -> str:
    entry = LEXICON_REGISTRY.get(key)
    return entry[2] if entry else "other"


def description_for(key: str) -> str:
    entry = LEXICON_REGISTRY.get(key)
    return entry[3] if entry else ""


def is_known_key(key: str) -> bool:
    return key in LEXICON_REGISTRY


def grouped_by_category() -> dict[str, list[str]]:
    """Stable category -> sorted keys map for the settings UI."""
    out: dict[str, list[str]] = {cat: [] for cat in LEXICON_CATEGORIES}
    for key, (_, _, cat, _) in LEXICON_REGISTRY.items():
        out.setdefault(cat, []).append(key)
    for cat in out:
        out[cat].sort()
    return out


def auto_plural(singular: str) -> str:
    """Last-resort English plural when no override supplies one.

    Only used as a fallback for unknown keys; the registry hand-curates the
    plural for every canonical key so this rule never fires in production
    rendering of canonical terms.
    """
    if not singular:
        return singular
    last = singular[-1].lower()
    if last == "s":
        return singular  # already plural-ish
    if last == "y" and len(singular) >= 2 and singular[-2].lower() not in "aeiou":
        return singular[:-1] + "ies"
    return singular + "s"


def normalise_override(raw: object) -> dict[str, str]:
    """Turn a JSON override value into ``{"singular": ..., "plural": ...}``.

    Tolerant of these shapes:
        - non-empty string                 → singular only
        - {"singular": "...", "plural": "..."}
        - {"singular": "..."}              → plural auto-derived
        - empty / None / wrong type        → returns {}
    """
    if isinstance(raw, str):
        s = raw.strip()
        return {"singular": s} if s else {}
    if isinstance(raw, dict):
        out: dict[str, str] = {}
        sing = raw.get("singular")
        plur = raw.get("plural")
        if isinstance(sing, str) and sing.strip():
            out["singular"] = sing.strip()
        if isinstance(plur, str) and plur.strip():
            out["plural"] = plur.strip()
        return out
    return {}


def merge_overrides(target: dict[str, dict[str, str]], src: object) -> None:
    """Mutating merge: apply ``src`` (a terminology dict from JSON storage)
    on top of ``target``. Non-empty values win per key; empty values pass.

    ``src`` may be the same flat-string shape used by the legacy
    `terminology_service` (``{"grade": "Note"}``) — that resolves to
    ``{"grade": {"singular": "Note"}}`` here.
    """
    if not isinstance(src, dict):
        return
    for key, raw in src.items():
        norm = normalise_override(raw)
        if not norm:
            continue
        slot = target.setdefault(key, {})
        slot.update(norm)


def known_categories() -> tuple[str, ...]:
    """All distinct categories actually used in the registry, stable order."""
    seen: list[str] = []
    for cat in LEXICON_CATEGORIES:
        if any(c == cat for _, _, c, _ in LEXICON_REGISTRY.values()):
            seen.append(cat)
    return tuple(seen)


def iter_registry() -> Iterable[tuple[str, str, str, str, str]]:
    """Yield (key, default_singular, default_plural, category, description)."""
    for key, (sing, plur, cat, desc) in LEXICON_REGISTRY.items():
        yield key, sing, plur, cat, desc


__all__ = [
    "DEFAULT_TONE",
    "LEXICON_CATEGORIES",
    "LEXICON_REGISTRY",
    "TONE_CHOICES",
    "auto_plural",
    "category_for",
    "default_plural",
    "default_singular",
    "description_for",
    "grouped_by_category",
    "is_known_key",
    "iter_registry",
    "known_categories",
    "lexicon_keys",
    "merge_overrides",
    "normalise_override",
]
