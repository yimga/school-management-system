"""v4.00.14 — bulk-grade-entry surface on the rmc-bulk-actions primitive.

Closes the v4.00.13 follow-on opportunity: ``rmc-bulk-actions`` was a generic
primitive but no domain surface used it. This view ships a real bulk-action
flow — teachers select multiple Evaluation rows for one subject_assignment +
term, then apply the same score field (seq1/seq2/exam/mock/practical) to all
selected rows in a single POST.

Pure-Decimal arithmetic; never coerces money/marks through float. Validates the
score against the SCHOOL's resolved grading scale — the same
``resolve_school_score_scale`` bound ``Evaluation.clean()`` enforces — and
persists every row through ``Evaluation.save()`` so the denormalized columns,
the audit trail and the ranking-cache invalidation all fire.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.schools.mixins import require_school

logger = logging.getLogger(__name__)


# Score fields exposed to the bulk-entry UI. Matches Evaluation columns.
ALLOWED_SCORE_FIELDS: tuple[str, ...] = (
    "seq1_score",
    "seq2_score",
    "exam_score",
    "mock_score",
    "practical_score",
)


def _resolve_max_score(school) -> Decimal:
    """The upper bound a mark may carry at ``school``.

    This used to probe ``subject_assignment.grading_scale`` / ``.scale``.
    SubjectAssignment has NEITHER attribute, so the helper always fell through
    to a hardcoded ``Decimal("20")``: a teacher at a percentage school got
    ``value_out_of_range`` for 75 and the workbench was unusable, while a school
    on a 4.0 GPA scale had an 18 waved through. Resolve it the way
    ``Evaluation.clean()`` does so the view and the model agree, with the same
    fail-closed fallback — an unresolvable scale clamps to the NARROWEST bound,
    so the failure mode over-rejects (loud) rather than over-admits (silent).
    """
    from apps.evals.grading_provisioning import (
        UNRESOLVED_SCALE_FALLBACK_MAX,
        UnresolvedScoreScale,
        resolve_school_score_scale,
    )

    try:
        return resolve_school_score_scale(school)
    except UnresolvedScoreScale:
        return UNRESOLVED_SCALE_FALLBACK_MAX


@method_decorator(
    [
        login_required,
        role_required(
            User.Role.ADMIN, User.Role.HOD, User.Role.TEACHER, "HEAD_OF_ACADEMICS"
        ),
        # The tenant binding is MANDATORY, not best-effort. The previous guard
        # read ``request.user.active_school`` — an attribute that exists nowhere
        # in the codebase — so it silently resolved to None and the school
        # filter never applied, leaving the write queryset addressable by bare
        # pk. request.school is set by TenantSchemaSchoolBridgeMiddleware; with
        # no tenant there is nothing legitimate to bulk-edit, so refuse.
        require_school,
        csrf_protect,
    ],
    name="dispatch",
)
class BulkGradeEntryView(View):
    """GET renders the bulk grade entry workbench; POST applies a value to many rows.

    Mark-editing roles only (matches the marks-entry contract in evals/views.py):
    teacher / admin / HOD / head-of-academics. Without this gate a STUDENT or
    PARENT in the same school could bulk-mutate Evaluation scores.

    # rbac-allow: marks-editing-roles-bulk-grade-entry
    """

    template = "evals/bulk_grade_entry.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        school = request.school  # guaranteed by require_school
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
            subject_assignment = SubjectAssignment.objects.filter(
                pk=subject_assignment_id, school=school
            ).first()

        if term_id:
            term = Term.objects.filter(pk=term_id).first()  # tenant-isolation-allow: term-lookup-shared-vocab

        if subject_assignment is not None and term is not None:
            qs = (
                Evaluation.objects.filter(
                    school=school,
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

        max_score = _resolve_max_score(school)
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
        school = request.school  # guaranteed by require_school

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

        try:
            int_ids = [int(i) for i in ids]
        except (ValueError, TypeError):
            return JsonResponse({"error": "ids_must_be_integers"}, status=400)

        if value is not None:
            max_score = _resolve_max_score(school)
            if value < Decimal("0") or value > max_score:
                return JsonResponse({
                    "error": "value_out_of_range",
                    "min": "0",
                    "max": str(max_score),
                }, status=400)

        # The school predicate is unconditional — bulk update across tenants is
        # never legitimate, and a pk list arrives straight from the client.
        rows = list(
            Evaluation.objects.filter(pk__in=int_ids, school=school)
            .select_related("academic_year")
        )
        if not rows:
            return JsonResponse({"error": "no_matching_rows"}, status=404)

        # Soft/Hard Close is checked BEFORE anything is written, and once per
        # academic year (a pk list can in principle span years). The other three
        # evals write paths — views.py _update_evaluations_from_entries,
        # _apply_ocr_entries and the marks-entry POST — already refuse here.
        from apps.academics.year_close import assert_period_writable

        checked_years: set[Any] = set()
        for evaluation in rows:
            year = evaluation.academic_year
            if year is None or year.pk in checked_years:
                continue
            checked_years.add(year.pk)
            try:
                assert_period_writable(
                    year, domain="grades", actor=request.user, school=school
                )
            except ValidationError as exc:
                return JsonResponse({
                    "error": "period_not_writable",
                    "detail": "; ".join(exc.messages),
                }, status=409)

        updated = 0
        failures: list[dict[str, Any]] = []
        with transaction.atomic():
            for evaluation in rows:
                setattr(evaluation, field, value)
                try:
                    # Deliberately NOT a queryset .update() (see the app README):
                    # final_score / normalized_value are recomputed only inside
                    # save(), and .update() also skips full_clean()'s fail-closed
                    # score ceiling, the GradeAudit post_save receiver, and the
                    # ranking-cache invalidation.
                    evaluation.save()
                except ValidationError as exc:
                    # full_clean() raises before any SQL, so the row simply did
                    # not change — report it instead of failing the whole batch.
                    failures.append({
                        "id": evaluation.pk,
                        "errors": "; ".join(exc.messages),
                    })
                    continue
                updated += 1

        if updated == 0 and failures:
            return JsonResponse({
                "error": "no_rows_written",
                "applied": 0,
                "failed": failures,
            }, status=400)

        return JsonResponse({
            "applied": int(updated),
            "failed": failures,
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
