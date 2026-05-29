"""v4.00.47 — LMS connector operator console (Wedge 2 item — operator UI for adapters).

Surfaces the v4.00.46 ``apps.api.lms_adapters`` SOT + v4.00.47
``LMSConnectorToken`` storage to a staff-only operator console:

* ``GET /portal/super/integrations/lms/`` — provider × school index.
* ``GET /portal/super/integrations/lms/<provider>/`` — token list +
  per-school course-fetch button (``?school=<id>&action=list_courses``).
* ``POST /portal/super/integrations/lms/<provider>/save/`` — upsert the
  per-school token (CSRF-protected).
"""
from __future__ import annotations

import logging
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.api import lms_adapters

logger = logging.getLogger(__name__)


def _resolve_token_row(school_id, provider: str):
    """Return the LMSConnectorToken row for (school, provider), or None."""
    from apps.integrations_marketplace.models import LMSConnectorToken

    return LMSConnectorToken.objects.filter(  # tenant-isolation-allow: operator-console-platform-scope-staff-required
        school_id=school_id, provider=provider
    ).first()


def _provider_supported(provider: str) -> bool:
    return provider in lms_adapters.supported_providers()


@staff_member_required
@require_http_methods(["GET"])
def lms_index(request: HttpRequest):
    """Provider × school index — one row per configured token."""
    from apps.integrations_marketplace.models import LMSConnectorToken

    rows = LMSConnectorToken.objects.select_related("school")[:500]  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    providers = lms_adapters.supported_providers()
    return render(request, "super/integrations/lms_index.html", {
        "rows": rows,
        "providers": providers,
    })


@staff_member_required
@require_http_methods(["GET"])
def lms_provider_detail(request: HttpRequest, provider: str):
    """Per-provider view with optional inline course fetch.

    ``?school=<id>&action=list_courses`` triggers a live HTTP call against
    the configured token + base_url. Result is rendered alongside the
    token list; errors are surfaced inline (never raised).
    """
    if not _provider_supported(provider):
        return JsonResponse({"error": "unknown_provider", "provider": provider}, status=404)

    from apps.integrations_marketplace.models import LMSConnectorToken

    rows = LMSConnectorToken.objects.filter(provider=provider).select_related("school")[:500]  # tenant-isolation-allow: operator-console-platform-scope-staff-required

    action_result: dict[str, Any] = {}
    school_id = (request.GET.get("school") or "").strip()
    action = (request.GET.get("action") or "").strip()

    if school_id and action == "list_courses":
        row = _resolve_token_row(school_id, provider)
        if row is None:
            action_result = {"error": "no_token_configured", "school": school_id}
        elif not row.access_token:
            action_result = {"error": "token_empty", "school": school_id}
        else:
            try:
                courses = lms_adapters.dispatch(
                    provider, "list_courses",
                    token=row.access_token, base_url=row.base_url or "", limit=25,
                )
            except Exception as exc:  # noqa: BLE001 — adapter errors should always surface inline
                logger.warning("lms console %s list_courses failed school=%s err=%s", provider, school_id, exc)
                courses = [{"error": f"adapter_raise: {exc}"}]
            action_result = {"school": school_id, "courses": courses}

    if (request.GET.get("format") or "").lower() == "json":
        payload = {
            "provider": provider,
            "rows": [
                {
                    "school_id": r.school_id,
                    "school_name": getattr(r.school, "name", ""),
                    "base_url": r.base_url,
                    "is_configured": r.is_configured,
                    "masked_token": r.masked_token(),
                    "scope": r.scope,
                    "expires_at": r.expires_at.isoformat() if r.expires_at else "",
                }
                for r in rows
            ],
            "action_result": action_result,
        }
        return JsonResponse({"success": True, **payload})

    return render(request, "super/integrations/lms_provider.html", {
        "provider": provider,
        "provider_label": dict(lms_adapters.ADAPTERS).get(provider, {}).get("label", provider),
        "rows": rows,
        "action_result": action_result,
    })


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def lms_token_save(request: HttpRequest, provider: str):
    """Upsert the per-(school, provider) token row."""
    if not _provider_supported(provider):
        return JsonResponse({"error": "unknown_provider", "provider": provider}, status=404)

    from apps.integrations_marketplace.models import LMSConnectorToken
    from apps.schools.models import School

    school_id_raw = (request.POST.get("school") or "").strip()
    if not school_id_raw:
        return JsonResponse({"error": "missing_school"}, status=400)
    school = School.objects.filter(pk=school_id_raw).first()  # tenant-isolation-allow: operator-console-resolve-school-by-pk-staff-required
    if school is None:
        return JsonResponse({"error": "school_not_found"}, status=404)
    school_id = school.pk

    base_url = (request.POST.get("base_url") or "").strip()
    access_token = (request.POST.get("access_token") or "").strip()
    refresh_token = (request.POST.get("refresh_token") or "").strip()
    scope = (request.POST.get("scope") or "").strip()
    clear = (request.POST.get("clear") or "").strip().lower() in ("1", "true", "on", "yes")

    row, created = LMSConnectorToken.objects.get_or_create(  # tenant-isolation-allow: operator-console-upsert-token-by-school-provider
        school=school, provider=provider, defaults={"base_url": base_url}
    )

    if clear:
        row.access_token = ""
        row.refresh_token = ""
        row.scope = ""
        row.expires_at = None
        row.save(update_fields=["access_token", "refresh_token", "scope", "expires_at", "updated_at"])
        return JsonResponse({"success": True, "action": "cleared", "school": school_id, "provider": provider})

    if base_url:
        row.base_url = base_url
    if access_token:
        row.access_token = access_token
    if refresh_token:
        row.refresh_token = refresh_token
    if scope:
        row.scope = scope
    row.save(update_fields=["base_url", "access_token", "refresh_token", "scope", "updated_at"])

    if (request.GET.get("format") or "").lower() == "json" or (request.POST.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": True,
            "action": "created" if created else "updated",
            "school": school_id,
            "provider": provider,
            "is_configured": row.is_configured,
            "masked_token": row.masked_token(),
        })
    return HttpResponseRedirect(reverse("portal:lms_provider_detail", args=[provider]))
