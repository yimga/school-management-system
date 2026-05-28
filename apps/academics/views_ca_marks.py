"""v4.00.13 — CA-mark input UI for the certification export pipeline.

Closes the v4.00.12 follow-on gap: the export command reads
``CertificationCandidate.continuous_assessment`` but nothing wrote it.
This view ships a per-candidate JSON-shaped editor that writes to the
new ``continuous_assessment`` field added in migration 0050.

Wire format:
    {
        "total":    <number>,
        "subjects": { "<subject_code>": <number>, ... }
    }

UI accepts:
* per-subject decimals (form fields named ``subject_<code>``)
* a total decimal (form field ``total``)

Backend coerces empty/None to absence (no fake zeros).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)


def _coerce_decimal(raw: str):
    if raw is None:
        return None
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return float(Decimal(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None


@method_decorator([login_required, permission_required("academics.change_certificationcandidate", raise_exception=True)], name="dispatch")
class CAMarksInputView(View):
    """GET + POST ``/school/studio/certification/ca-marks/<candidate_id>/``.

    # rbac-allow: school-staff-ca-marks-input
    """

    template = "academics/ca_marks_input.html"

    def get(self, request: HttpRequest, candidate_id: int) -> HttpResponse:
        from apps.academics.models import CertificationCandidate

        candidate = get_object_or_404(
            CertificationCandidate.objects.select_related("student", "session"),
            pk=candidate_id,
        )
        ca = candidate.continuous_assessment if isinstance(candidate.continuous_assessment, dict) else {}
        return render(request, self.template, {
            "candidate": candidate,
            "ca_total": ca.get("total"),
            "ca_subjects": ca.get("subjects") or {},
        })

    def post(self, request: HttpRequest, candidate_id: int) -> HttpResponse:
        from apps.academics.models import CertificationCandidate

        candidate = get_object_or_404(CertificationCandidate, pk=candidate_id)
        new_subjects: dict[str, float] = {}
        for key, raw_value in request.POST.items():
            if not key.startswith("subject_"):
                continue
            code = key[len("subject_"):]
            if not code:
                continue
            value = _coerce_decimal(raw_value)
            if value is not None:
                new_subjects[code] = value
        new_total = _coerce_decimal(request.POST.get("total"))
        payload: dict = {}
        if new_total is not None:
            payload["total"] = new_total
        if new_subjects:
            payload["subjects"] = new_subjects
        candidate.continuous_assessment = payload
        candidate.save(update_fields=["continuous_assessment", "updated_at"])
        return redirect(reverse("academics:ca_marks_input", kwargs={"candidate_id": candidate.pk}))
