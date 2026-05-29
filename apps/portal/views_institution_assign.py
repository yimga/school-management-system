"""v4.00.39 — Per-tenant institution-type assignment endpoint.

Backs the Wedge 16 / 17 / 18 detail-page workflow: an operator picks a
charter authorizer / IB programmes / faith tradition from the SOT and
this view persists the value onto the requesting tenant's School row.

Stable URL: ``POST /portal/configure/institution-type/save/`` — body
keys ``{charter_authorizer_code, ib_programmes (csv or list),
faith_tradition_code}``. Only fields present in the body are updated.
Per-tenant: writes to ``request.school`` (admin role + staff bypass).

Companion GET ``/portal/configure/institution-type/`` renders the form
for the current tenant.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


def _user_is_admin(request: HttpRequest) -> bool:
    user = getattr(request, "user", None)
    if user is None:
        return False
    if getattr(user, "is_staff", False):
        return True
    try:
        getter = getattr(user, "has_role", None)
        if callable(getter):
            return bool(getter("ADMIN"))
        return str(getattr(user, "role", "")).upper() == "ADMIN"  # role-string-allow: institution-type-admin-fallback
    except Exception:  # noqa: BLE001
        return False


def _allowed_values() -> dict[str, set[str]]:
    try:
        from apps.siteconfig._institution_types import (
            CHARTER_AUTHORIZERS,
            FAITH_TRADITIONS,
            IB_PROGRAMMES,
            CAMBRIDGE_PROGRAMMES,
        )
    except Exception:  # noqa: BLE001
        return {"charter": set(), "faith": set(), "ib": set()}
    return {
        "charter": {r["code"] for r in CHARTER_AUTHORIZERS},
        "faith": {r["code"] for r in FAITH_TRADITIONS},
        "ib": {r["code"] for r in (list(IB_PROGRAMMES) + list(CAMBRIDGE_PROGRAMMES))},
    }


@login_required
@require_http_methods(["GET"])
def assignment_view(request):
    school = getattr(request, "school", None)
    state = {
        "charter_authorizer_code": getattr(school, "charter_authorizer_code", "") if school else "",
        "ib_programmes": list(getattr(school, "ib_programmes", []) or []) if school else [],
        "faith_tradition_code": getattr(school, "faith_tradition_code", "") if school else "",
    }
    try:
        from apps.siteconfig._institution_types import (
            CHARTER_AUTHORIZERS,
            FAITH_TRADITIONS,
            IB_PROGRAMMES,
            CAMBRIDGE_PROGRAMMES,
            INSTITUTION_TYPES,
        )
    except Exception:  # noqa: BLE001
        CHARTER_AUTHORIZERS = FAITH_TRADITIONS = IB_PROGRAMMES = CAMBRIDGE_PROGRAMMES = []
        INSTITUTION_TYPES = {}
    return render(request, "portal/institution_type_assign.html", {
        "state": state,
        "authorizers": CHARTER_AUTHORIZERS,
        "traditions": FAITH_TRADITIONS,
        "ib_programmes": IB_PROGRAMMES,
        "cambridge_programmes": CAMBRIDGE_PROGRAMMES,
        "institution_types": INSTITUTION_TYPES,
        "is_admin_user": _user_is_admin(request),
    })


@login_required
@require_http_methods(["POST"])
@csrf_protect
def assignment_save(request):
    school = getattr(request, "school", None)
    if school is None:
        return JsonResponse({"success": False, "error": "no_tenant"}, status=400)
    if not _user_is_admin(request):
        return JsonResponse({"success": False, "error": "forbidden"}, status=403)

    # Accept either JSON body OR form-encoded POST.
    payload: dict[str, Any]
    if "application/json" in (request.META.get("CONTENT_TYPE") or ""):
        try:
            payload = json.loads(request.body or b"{}")
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "bad_json"}, status=400)
    else:
        payload = {
            "charter_authorizer_code": request.POST.get("charter_authorizer_code") or "",
            "faith_tradition_code": request.POST.get("faith_tradition_code") or "",
            "ib_programmes": request.POST.getlist("ib_programmes") or request.POST.get("ib_programmes") or "",
        }

    allowed = _allowed_values()
    update_fields: list[str] = []

    if "charter_authorizer_code" in payload:
        raw = str(payload.get("charter_authorizer_code") or "").strip()[:40]
        if raw and raw not in allowed["charter"]:
            return JsonResponse({"success": False, "error": "invalid_authorizer_code", "value": raw}, status=400)
        if raw != getattr(school, "charter_authorizer_code", ""):
            school.charter_authorizer_code = raw
            update_fields.append("charter_authorizer_code")

    if "faith_tradition_code" in payload:
        raw = str(payload.get("faith_tradition_code") or "").strip()[:40]
        if raw and raw not in allowed["faith"]:
            return JsonResponse({"success": False, "error": "invalid_faith_tradition", "value": raw}, status=400)
        if raw != getattr(school, "faith_tradition_code", ""):
            school.faith_tradition_code = raw
            update_fields.append("faith_tradition_code")

    if "ib_programmes" in payload:
        raw = payload.get("ib_programmes")
        if isinstance(raw, str):
            programmes = [p.strip() for p in raw.split(",") if p.strip()]
        elif isinstance(raw, list):
            programmes = [str(p).strip() for p in raw if str(p).strip()]
        else:
            programmes = []
        invalid = [p for p in programmes if p not in allowed["ib"]]
        if invalid:
            return JsonResponse({"success": False, "error": "invalid_ib_programmes", "invalid": invalid}, status=400)
        programmes = programmes[:8]
        if programmes != list(getattr(school, "ib_programmes", []) or []):
            school.ib_programmes = programmes
            update_fields.append("ib_programmes")

    if update_fields:
        try:
            school.save(update_fields=update_fields)
        except Exception as exc:  # noqa: BLE001
            logger.warning("institution assignment save failed: %s", exc)
            return JsonResponse({"success": False, "error": "save_failed"}, status=500)

    return JsonResponse({
        "success": True,
        "updated_fields": update_fields,
        "state": {
            "charter_authorizer_code": school.charter_authorizer_code,
            "ib_programmes": list(school.ib_programmes or []),
            "faith_tradition_code": school.faith_tradition_code,
        },
    })
