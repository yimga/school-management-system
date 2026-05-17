"""Wave 6 — portal-facing views for the AI/ML surfaces shipped in Waves 1-5.

Three operator surfaces:
    GET /portal/students/search/              — semantic search bar + results
    GET /portal/student/<id>/risk-drivers/    — per-student top contributions table
    GET /portal/student/<id>/grade-outlook/   — predicted-grade widget per subject

Permissioning: any authenticated user in the student's school can read.
We do NOT serve cross-tenant data — `request.school` is the hard scope.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

_SEARCH_TOP_K = 10
_SEARCH_MIN_QUERY_LEN = 2


def _get_school(request: HttpRequest):
    return getattr(request, "school", None)


def _hydrate_search_results(school, ranked: list[dict]) -> list[dict]:
    """Replace bare student_id with the actual StudentProfile row.

    Stays tenant-isolated: only students belonging to `school` are
    surfaced, even if the ranking accidentally returned a cross-tenant
    row (defence in depth — the search function already filters).
    """
    if not ranked:
        return []
    from apps.people.models import StudentProfile

    ids: list = []
    for r in ranked:
        sid = r.get("student_id")
        if sid:
            try:
                ids.append(int(sid))
            except (TypeError, ValueError):
                continue
    if not ids:
        return []
    # tenant-isolation-allow: scoped via school= below
    students = {
        s.pk: s for s in StudentProfile.objects.filter(
            school=school, pk__in=ids,
        ).select_related("user", "classroom")
    }
    hydrated = []
    for r in ranked:
        try:
            sid = int(r["student_id"])
        except (TypeError, ValueError, KeyError):
            continue
        student = students.get(sid)
        if not student:
            continue
        hydrated.append({
            "student": student,
            "score": r.get("score", 0.0),
            "summary": r.get("summary", ""),
        })
    return hydrated


@login_required
@require_http_methods(["GET"])
def semantic_student_search(request: HttpRequest) -> HttpResponse:
    """Render a search form and the ranked results when a query is present."""
    school = _get_school(request)
    if school is None:
        return render(
            request,
            "portal/ai_surfaces/no_tenant.html",
            status=400,
        )
    query = (request.GET.get("q") or "").strip()
    raw_results: list[dict] = []
    error_message = ""
    if query and len(query) >= _SEARCH_MIN_QUERY_LEN:
        try:
            from apps.analytics.semantic_search import search_students
            raw_results = search_students(
                query, school_id=school.id, top_k=_SEARCH_TOP_K,
            )
        except (ImportError, AttributeError, ValueError) as exc:
            logger.warning("semantic_student_search failed: %s", exc)
            error_message = (
                "Search is temporarily unavailable. Try again in a moment."
            )
    results = _hydrate_search_results(school, raw_results)
    return render(
        request,
        "portal/ai_surfaces/semantic_search.html",
        {
            "query": query,
            "results": results,
            "min_query_len": _SEARCH_MIN_QUERY_LEN,
            "top_k": _SEARCH_TOP_K,
            "error_message": error_message,
            "has_searched": bool(query and len(query) >= _SEARCH_MIN_QUERY_LEN),
        },
    )


def _resolve_student(request: HttpRequest, student_id: int):
    """Fetch a StudentProfile, tenant-scoped to request.school."""
    school = _get_school(request)
    if school is None:
        return None, None
    from apps.people.models import StudentProfile

    # tenant-isolation-allow: scoped via school= below
    student = get_object_or_404(
        StudentProfile.objects.select_related("user", "classroom"),
        school=school, pk=student_id,
    )
    return school, student


@login_required
@require_http_methods(["GET"])
def student_risk_drivers(
    request: HttpRequest, student_id: int,
) -> HttpResponse:
    """Show the latest RiskFactor.feature_contributions for one student."""
    school, student = _resolve_student(request, student_id)
    if school is None:
        return render(
            request, "portal/ai_surfaces/no_tenant.html", status=400,
        )
    from apps.analytics.models import RiskFactor

    # tenant-isolation-allow: student already school-scoped via _resolve_student
    rf = (
        RiskFactor.objects.filter(student=student, school=school)
        .order_by("-computed_at").first()
    )
    contributions: list[dict] = list(
        (rf.feature_contributions or []) if rf else []
    )
    return render(
        request,
        "portal/ai_surfaces/risk_drivers.html",
        {
            "student": student,
            "risk_factor": rf,
            "contributions": contributions,
            "has_ml_explanation": bool(contributions),
        },
    )


@login_required
@require_http_methods(["GET"])
def student_grade_outlook(
    request: HttpRequest, student_id: int,
) -> HttpResponse:
    """Show current grade predictions across enrolled subjects."""
    school, student = _resolve_student(request, student_id)
    if school is None:
        return render(
            request, "portal/ai_surfaces/no_tenant.html", status=400,
        )
    from apps.analytics.models import GradePrediction

    # tenant-isolation-allow: student already school-scoped via _resolve_student
    predictions = list(
        GradePrediction.objects.filter(student=student, school=school)
        .select_related("subject", "term", "academic_year")
        .order_by("-computed_at")[:20]
    )
    # Group by (academic_year, term, subject) — current view is just the most recent set.
    by_subject: dict[Any, dict] = {}
    for row in predictions:
        key = row.subject_id
        if key not in by_subject:
            by_subject[key] = {
                "subject": row.subject,
                "prediction": row,
            }
    return render(
        request,
        "portal/ai_surfaces/grade_outlook.html",
        {
            "student": student,
            "predictions_by_subject": list(by_subject.values()),
            "any_predictions": bool(by_subject),
        },
    )
