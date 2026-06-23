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
