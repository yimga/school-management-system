"""Per-tenant policy: what grade/result data students see on their dashboard."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

STUDENT_RESULTS_VISIBILITY_OFF = "off"
STUDENT_RESULTS_VISIBILITY_PUBLISHED = "published"
STUDENT_RESULTS_VISIBILITY_ENTERED = "entered"

DEFAULT_STUDENT_RESULTS_VISIBILITY = STUDENT_RESULTS_VISIBILITY_PUBLISHED

STUDENT_RESULTS_VISIBILITY_CHOICES: tuple[tuple[str, str], ...] = (
    (
        STUDENT_RESULTS_VISIBILITY_OFF,
        _("Hidden — no grades on student dashboard"),
    ),
    (
        STUDENT_RESULTS_VISIBILITY_PUBLISHED,
        _("Published term results only"),
    ),
    (
        STUDENT_RESULTS_VISIBILITY_ENTERED,
        _("Show entered marks as teachers save them"),
    ),
)

_VALID_MODES = frozenset(
    {
        STUDENT_RESULTS_VISIBILITY_OFF,
        STUDENT_RESULTS_VISIBILITY_PUBLISHED,
        STUDENT_RESULTS_VISIBILITY_ENTERED,
    }
)


def normalize_student_results_visibility(raw: object | None) -> str:
    """Return a canonical mode; unknown/blank values fall back to published."""
    if raw is None:
        return DEFAULT_STUDENT_RESULTS_VISIBILITY
    val = str(raw).strip().lower()
    if val in _VALID_MODES:
        return val
    return DEFAULT_STUDENT_RESULTS_VISIBILITY


def get_student_results_visibility_from_site(site) -> str:
    if site is None:
        return DEFAULT_STUDENT_RESULTS_VISIBILITY
    return normalize_student_results_visibility(
        getattr(site, "student_results_visibility", None)
    )


def resolve_student_grade_dashboard_access(
    *,
    visibility_mode: str,
    term_published: bool,
    has_grade_data: bool,
) -> dict[str, object]:
    """
    Decide whether the student dashboard may show grade panels.

    Returns keys: can_view_results (bool), results_locked (bool), visibility_mode (str).
    """
    mode = normalize_student_results_visibility(visibility_mode)
    if mode == STUDENT_RESULTS_VISIBILITY_OFF:
        return {
            "can_view_results": False,
            "results_locked": False,
            "visibility_mode": mode,
        }
    if mode == STUDENT_RESULTS_VISIBILITY_ENTERED:
        return {
            "can_view_results": bool(has_grade_data),
            "results_locked": False,
            "visibility_mode": mode,
        }
    if term_published and has_grade_data:
        return {
            "can_view_results": True,
            "results_locked": False,
            "visibility_mode": mode,
        }
    if not term_published and has_grade_data:
        return {
            "can_view_results": False,
            "results_locked": True,
            "visibility_mode": mode,
        }
    return {
        "can_view_results": False,
        "results_locked": False,
        "visibility_mode": mode,
    }


def _parent_grade_signals(students, year, term, widget_data) -> tuple[bool, bool]:
    """Aggregate grade presence and publish state for guardian dashboards."""
    perf = widget_data.get("performance") or {}
    has_grade_data = (
        perf.get("average") is not None
        or bool(widget_data.get("grade_trend"))
        or any(
            row.get("average") is not None for row in (perf.get("per_student") or [])
        )
    )
    term_published = False
    if year and term:
        from apps.reports.services import is_term_published

        for student in students:
            classroom_id = getattr(student, "classroom_id", None)
            try:
                if is_term_published(year.id, term.id, classroom_id):
                    term_published = True
                    break
            except (AttributeError, TypeError, ValueError):
                pass
    if not has_grade_data and year and term and students:
        try:
            from apps.evals.models import Evaluation

            student_ids = [s.id for s in students]
            has_grade_data = Evaluation.objects.filter(
                student_id__in=student_ids,
                academic_year=year,
                term=term,
            ).exists()
        except Exception:
            pass
    return has_grade_data, term_published


def resolve_parent_grade_dashboard_access(
    *,
    site,
    students,
    year,
    term,
    widget_data,
    has_guardian_results_links: bool,
) -> dict[str, object]:
    """
    Apply ``student_results_visibility`` to guardian home surfaces.

    Requires guardian links with results permission; then uses the same
    off / published / entered policy as the student dashboard.
    """
    visibility_mode = get_student_results_visibility_from_site(site)
    if not has_guardian_results_links or not students:
        return {
            "can_view_results": False,
            "results_locked": False,
            "visibility_mode": visibility_mode,
        }
    if visibility_mode == STUDENT_RESULTS_VISIBILITY_OFF:
        return {
            "can_view_results": False,
            "results_locked": False,
            "visibility_mode": visibility_mode,
        }
    has_grade_data, term_published = _parent_grade_signals(
        students, year, term, widget_data or {}
    )
    return resolve_student_grade_dashboard_access(
        visibility_mode=visibility_mode,
        term_published=term_published,
        has_grade_data=has_grade_data,
    )
