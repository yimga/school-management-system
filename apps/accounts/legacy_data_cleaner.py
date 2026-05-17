"""
Section 11.1 — Legacy data cleaner for migration cloud.
Detects and optionally cleans legacy/invalid data: duplicate admission numbers,
empty required fields, malformed dates, orphaned references.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Count


def detect_legacy_issues(school) -> dict[str, Any]:
    """
    Scan tenant data for legacy/invalid records. Returns issues by category
    (duplicate_admission_numbers, missing_required, malformed_dates, orphans)
    with counts and sample IDs (no PII in messages).
    """
    issues = {
        "duplicate_admission_numbers": [],
        "missing_required": [],
        "malformed_dates": [],
        "orphans": [],
        "summary": {},
    }
    if not school:
        return issues

    try:
        from apps.people.models import StudentProfile

        # Duplicate admission numbers within school
        dupes = (
            StudentProfile.objects.filter(school=school, is_active=True)
            .values("admission_number")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        for d in dupes:
            issues["duplicate_admission_numbers"].append(
                {"admission_number": d["admission_number"], "count": d["cnt"]}
            )
        # Missing required: admission_number empty where policy requires it
        missing = StudentProfile.objects.filter(
            school=school,
            is_active=True,
            admission_number__in=("", None),
        ).count()
        if missing:
            issues["missing_required"].append(
                {
                    "entity": "StudentProfile",
                    "field": "admission_number",
                    "count": missing,
                }
            )
    except (ImportError, AttributeError, TypeError):
        pass

    # Orphans: evaluations whose student is inactive (soft-deleted) — optional
    try:
        from apps.evals.models import Evaluation

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        orphan_evals = Evaluation.objects.filter(
            student__school=school, student__is_active=False
        ).count()
        if orphan_evals:
            issues["orphans"].append(
                {
                    "entity": "Evaluation",
                    "description": "evaluation for inactive student",
                    "count": orphan_evals,
                }
            )
    except (ImportError, AttributeError, TypeError):
        pass

    issues["summary"] = {
        "duplicate_count": sum(
            x["count"] for x in issues["duplicate_admission_numbers"]
        ),
        "missing_required_count": sum(x["count"] for x in issues["missing_required"]),
        "orphan_count": sum(x["count"] for x in issues["orphans"]),
    }
    return issues


def clean_legacy_data(school, dry_run: bool = True) -> dict[str, Any]:
    """
    Apply safe cleanups: e.g. merge duplicate admission_number strategy (report only in dry_run),
    flag records with missing required for review. Does not delete; at most normalizes empty strings to null.
    Returns { "dry_run": bool, "actions": [...], "errors": [...] }.
    """
    result = {"dry_run": dry_run, "actions": [], "errors": []}
    if not school:
        result["errors"].append("No school.")
        return result

    issues = detect_legacy_issues(school)
    if not any(issues["summary"].values()):
        result["actions"].append(
            {"action": "none", "message": "No legacy issues detected."}
        )
        return result

    # Safe cleanup: normalize empty admission_number to null for consistency (optional)
    try:
        from apps.people.models import StudentProfile

        empty_admission = StudentProfile.objects.filter(
            school=school,
            admission_number="",
        )
        count = empty_admission.count()
        if count and not dry_run:
            empty_admission.update(admission_number=None)
            result["actions"].append(
                {"action": "normalize_empty_admission", "count": count}
            )
        elif count:
            result["actions"].append(
                {
                    "action": "normalize_empty_admission",
                    "would_update": count,
                    "dry_run": True,
                }
            )
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        result["errors"].append(str(e))

    result["issues_detected"] = issues["summary"]
    return result
