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

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

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
