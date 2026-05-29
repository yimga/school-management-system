"""v4.00.32 — admissions intake schema API.

Returns the country/system-type-aware admissions intake schema for the
requesting tenant so the applicant-intake form can render the right
exam-score fields (WASSCE/KCSE/CSEE/Thanaweya/NSC/Bac/…).

GET ``/api/v1/admissions/intake-schema/`` — uses request.school.
GET ``?country=GH&type=shs`` — operator override (preview).

Response:
    {
      "success": true,
      "schema": {"code": "waec-wassce", "label": "WASSCE …", …},
      "field_specs": [{"name": "score_english", "label": "English",
                       "type": "select", "choices": [...], "score_kind": "letter"}, …]
    }
"""
from __future__ import annotations

import logging
from typing import Any

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_http_methods

logger = logging.getLogger(__name__)


def _resolve_school_context(request) -> tuple[str, list[str]]:
    """Return (country_code, system_type_codes) from the request's tenant."""
    country = ""
    system_codes: list[str] = []
    school = getattr(request, "school", None)
    try:
        if school is not None:
            country = (getattr(school, "country_code", "") or "").upper()
            m2m = getattr(school, "education_system_types", None)
            if m2m is not None:
                system_codes = list(m2m.values_list("code", flat=True))
            elif getattr(school, "school_type", ""):
                system_codes = [school.school_type]
    except Exception as exc:  # noqa: BLE001
        logger.debug("admissions-intake school introspect failed: %s", exc)
    return country, system_codes


@require_GET
@login_required
def api_admissions_intake_schema(request):
    """Return the resolved intake schema + field specs for the tenant."""
    try:
        from apps.siteconfig._admissions_intake_schemas import (
            applicant_field_specs,
            intake_schema_for_school,
        )
    except ImportError as exc:
        logger.warning("admissions-intake schema module missing: %s", exc)
        return JsonResponse({"success": False, "error": "module_missing"}, status=500)

    country, system_codes = _resolve_school_context(request)
    # Allow operator preview override.
    override_country = (request.GET.get("country") or "").strip()
    override_type = (request.GET.get("type") or "").strip()
    if override_country:
        country = override_country.upper()
    if override_type:
        system_codes = [override_type] + system_codes

    schema = intake_schema_for_school(country_code=country, system_type_codes=system_codes)
    specs: list[dict[str, Any]] = applicant_field_specs(schema)
    return JsonResponse({
        "success": True,
        "country_code": country,
        "system_type_codes": system_codes,
        "schema": schema,
        "field_specs": specs,
    })


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_admissions_applicant_scores(request):
    """v4.00.34 — capture exam scores into an existing Applicant.

    Body: ``{"applicant_id": 123, "exam_schema_code": "waec-wassce",
            "exam_marker": "WASSCE",
            "scores": {"english": "A1", "mathematics": "B2", …}}``

    Tenant-isolation: only updates the applicant when its school matches
    ``request.school`` (or the user is staff).
    """
    # Accept either JSON body OR multipart/form-data (the form auto-POST
    # hook in rmc-admissions-intake.js posts FormData so keepalive fetch /
    # sendBeacon stays simple).
    content_type = (request.META.get("CONTENT_TYPE") or "").lower()
    body: dict
    if "application/json" in content_type:
        try:
            body = json.loads(request.body) if request.body else {}
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "bad_json"}, status=400)
    else:
        body = {
            "applicant_id": request.POST.get("applicant_id"),
            "exam_schema_code": request.POST.get("exam_schema_code") or "",
            "exam_marker": request.POST.get("exam_marker") or "",
        }
        scores_raw = request.POST.get("exam_scores_json") or "{}"
        try:
            body["scores"] = json.loads(scores_raw)
        except (ValueError, TypeError):
            body["scores"] = {}

    applicant_id = body.get("applicant_id")
    schema_code = (body.get("exam_schema_code") or "").strip()[:40]
    marker = (body.get("exam_marker") or "").strip()[:80]
    scores = body.get("scores") or {}
    if not applicant_id or not isinstance(scores, dict):
        return JsonResponse({"success": False, "error": "applicant_id_and_scores_required"}, status=400)

    try:
        from apps.people.models import Applicant
    except ImportError:
        return JsonResponse({"success": False, "error": "applicant_model_missing"}, status=500)

    school = getattr(request, "school", None)
    qs = Applicant.objects.all()  # tenant-isolation-allow: filtered-immediately-by-request-school-below
    if school is not None and not getattr(request.user, "is_staff", False):
        qs = qs.filter(school=school)  # tenant-isolation-allow: explicit-tenant-scope-via-request-school

    try:
        applicant = qs.filter(pk=applicant_id).first()
    except (ValueError, TypeError):
        applicant = None
    if applicant is None:
        return JsonResponse({"success": False, "error": "applicant_not_found"}, status=404)

    # Sanitize scores: keys stripped to 64 chars, values to 16 chars.
    sanitized = {
        str(k)[:64]: str(v)[:16]
        for k, v in scores.items()
        if k and v not in (None, "")
    }
    applicant.exam_scores = sanitized
    if schema_code:
        applicant.exam_schema_code = schema_code
    if marker:
        applicant.exam_marker = marker
    applicant.save(update_fields=["exam_scores", "exam_schema_code", "exam_marker", "updated_at"])

    return JsonResponse({
        "success": True,
        "applicant_id": applicant.pk,
        "exam_schema_code": applicant.exam_schema_code,
        "exam_marker": applicant.exam_marker,
        "score_count": len(sanitized),
    })
