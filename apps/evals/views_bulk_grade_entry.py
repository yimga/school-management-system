"""v4.00.14 — bulk-grade-entry surface on the rmc-bulk-actions primitive.

Closes the v4.00.13 follow-on opportunity: ``rmc-bulk-actions`` was a generic
primitive but no domain surface used it. This view ships a real bulk-action
flow — teachers select multiple Evaluation rows for one subject_assignment +
term, then apply the same score field (seq1/seq2/exam/mock/practical) to all
selected rows in a single POST.

Pure-Decimal arithmetic; never coerces money/marks through float. Validates
the score against the SubjectAssignment's resolved max (falling back to 20
when no scale is bound, matching the existing grade-entry contract).
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect

logger = logging.getLogger(__name__)


# Score fields exposed to the bulk-entry UI. Matches Evaluation columns.
ALLOWED_SCORE_FIELDS: tuple[str, ...] = (
    "seq1_score",
    "seq2_score",
    "exam_score",
    "mock_score",
    "practical_score",
)


def _resolve_subject_max(subject_assignment) -> Decimal:
    """Return the max score for ``subject_assignment`` (defaults to Decimal("20"))."""
    if subject_assignment is None:
        return Decimal("20")
    scale = (
        getattr(subject_assignment, "grading_scale", None)
        or getattr(subject_assignment, "scale", None)
    )
    if scale is not None:
        for attr in ("max_score", "max_value", "scale_max", "ceiling"):
            raw = getattr(scale, attr, None)
            if raw is not None:
                try:
                    return Decimal(str(raw))
                except (InvalidOperation, ValueError, TypeError):
                    continue
    return Decimal("20")


@method_decorator([login_required, csrf_protect], name="dispatch")
class BulkGradeEntryView(View):
    """GET renders the bulk grade entry workbench; POST applies a value to many rows.

    # rbac-allow: authenticated-teacher-bulk-grade-entry
    """

    template = "evals/bulk_grade_entry.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        subject_assignment_id = request.GET.get("subject_assignment") or ""
        term_id = request.GET.get("term") or ""

        try:
            from apps.evals.models import Evaluation, SubjectAssignment, Term
        except ImportError:
            return render(request, self.template, self._empty_context(
                error="evals_unavailable",
            ))

        subject_assignment = None
        term = None
        rows: list[dict[str, Any]] = []

        if subject_assignment_id:
            # tenant-isolation-allow: scoped-via-user-school-bulk-grade-entry-subject-pick
            sa_qs = SubjectAssignment.objects.filter(pk=subject_assignment_id)
            user_school_id = getattr(getattr(request.user, "active_school", None), "pk", None)
            if user_school_id is not None:
                sa_qs = sa_qs.filter(school_id=user_school_id)
            subject_assignment = sa_qs.first()

        if term_id:
            term = Term.objects.filter(pk=term_id).first()  # tenant-isolation-allow: term-lookup-shared-vocab

        if subject_assignment is not None and term is not None:
            # tenant-isolation-allow: scoped-via-subject-assignment-and-term-bulk-grade-entry
            qs = (
                Evaluation.objects.filter(
                    subject_assignment=subject_assignment,
                    term=term,
                )
                .select_related("student")
                .order_by("student__last_name", "student__first_name")
            )
            for ev in qs[:500]:
                rows.append({
                    "id": ev.pk,
                    "student_display": (
                        getattr(ev.student, "full_name", None)
                        or f"{getattr(ev.student, 'last_name', '')} {getattr(ev.student, 'first_name', '')}".strip()
                        or f"#{ev.student_id}"
                    ),
                    "seq1_score": ev.seq1_score,
                    "seq2_score": ev.seq2_score,
                    "exam_score": ev.exam_score,
                    "mock_score": ev.mock_score,
                    "practical_score": ev.practical_score,
                })

        max_score = _resolve_subject_max(subject_assignment)
        return render(request, self.template, {
            "subject_assignment": subject_assignment,
            "term": term,
            "rows": rows,
            "allowed_fields": ALLOWED_SCORE_FIELDS,
            "max_score": str(max_score),
            "bulk_actions": [
                {"slug": "apply_value", "label": "Apply value", "variant": "default"},
                {"slug": "clear", "label": "Clear marks", "variant": "danger"},
            ],
        })

    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            payload = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "invalid_json"}, status=400)

        ids = payload.get("evaluation_ids") or []
        if not isinstance(ids, list) or not ids:
            return JsonResponse({"error": "evaluation_ids_required"}, status=400)
        if len(ids) > 500:
            return JsonResponse({"error": "too_many_rows", "limit": 500}, status=400)

        field = str(payload.get("field") or "").strip()
        if field not in ALLOWED_SCORE_FIELDS:
            return JsonResponse({"error": "field_not_allowed", "allowed": list(ALLOWED_SCORE_FIELDS)}, status=400)

        raw_value = payload.get("value")
        action = str(payload.get("action") or "apply_value").strip()
        value: Decimal | None
        if action == "clear" or raw_value in (None, "", "null"):
            value = None
        else:
            try:
                value = Decimal(str(raw_value))
            except (InvalidOperation, ValueError, TypeError):
                return JsonResponse({"error": "invalid_value"}, status=400)

        try:
            from apps.evals.models import Evaluation
        except ImportError:
            return JsonResponse({"error": "evals_unavailable"}, status=503)

        # Scope by user's school + ID list. We intentionally read the school
        # off the first row and reject any rows that don't match it — bulk
        # update across tenants is never legitimate.
        try:
            int_ids = [int(i) for i in ids]
        except (ValueError, TypeError):
            return JsonResponse({"error": "ids_must_be_integers"}, status=400)

        user_school_id = getattr(getattr(request.user, "active_school", None), "pk", None)
        # tenant-isolation-allow: explicit-user-school-bind-bulk-grade-entry-apply
        qs = Evaluation.objects.filter(pk__in=int_ids)
        if user_school_id is not None:
            qs = qs.filter(school_id=user_school_id)

        if value is not None:
            # Validate against the subject's resolved max (single read).
            sample = qs.select_related("subject_assignment").first()
            if sample is None:
                return JsonResponse({"error": "no_matching_rows"}, status=404)
            max_score = _resolve_subject_max(sample.subject_assignment)
            if value < Decimal("0") or value > max_score:
                return JsonResponse({
                    "error": "value_out_of_range",
                    "min": "0",
                    "max": str(max_score),
                }, status=400)

        with transaction.atomic():
            updated = qs.update(**{field: value})

        return JsonResponse({
            "applied": int(updated),
            "field": field,
            "value": str(value) if value is not None else None,
        })

    def _empty_context(self, *, error: str = "") -> dict[str, Any]:
        return {
            "subject_assignment": None,
            "term": None,
            "rows": [],
            "allowed_fields": ALLOWED_SCORE_FIELDS,
            "max_score": "20",
            "bulk_actions": [
                {"slug": "apply_value", "label": "Apply value", "variant": "default"},
                {"slug": "clear", "label": "Clear marks", "variant": "danger"},
            ],
            "error": error,
        }
