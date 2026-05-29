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


_REFRESH_WINDOW_SECONDS = 60


def _maybe_proactive_refresh(row, provider: str) -> dict:
    """v4.00.52 — Proactive OAuth2 token refresh.

    If the row has a refresh_token + expires_at < now + 60s + client creds
    are configured in env, refreshes the token in-place and persists.

    Returns a dict with ``refreshed`` boolean + ``status_code``/``detail``
    for audit. Never raises.
    """
    if row is None or not getattr(row, "refresh_token", "") or not getattr(row, "expires_at", None):
        return {"refreshed": False, "reason": "not_eligible"}
    from django.utils import timezone as _tz

    if row.expires_at >= _tz.now() + _td_seconds(_REFRESH_WINDOW_SECONDS):
        return {"refreshed": False, "reason": "not_due"}

    import os as _os
    from django.conf import settings as _settings

    provider_upper = provider.upper()
    cid = (getattr(_settings, f"RMC_LMS_{provider_upper}_CLIENT_ID", "") or _os.environ.get(f"RMC_LMS_{provider_upper}_CLIENT_ID", "") or "").strip()
    csec = (getattr(_settings, f"RMC_LMS_{provider_upper}_CLIENT_SECRET", "") or _os.environ.get(f"RMC_LMS_{provider_upper}_CLIENT_SECRET", "") or "").strip()
    if not cid or not csec:
        return {"refreshed": False, "reason": "client_creds_missing"}

    kwargs: dict = {"refresh_token": row.refresh_token, "client_id": cid, "client_secret": csec}
    if provider == "canvas":
        kwargs["base_url"] = row.base_url or ""
    try:
        result = lms_adapters.refresh_token(provider, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"refreshed": False, "reason": f"adapter_raise: {exc}"}

    if not result.get("ok") or not result.get("access_token"):
        return {"refreshed": False, "reason": "refresh_failed", "status_code": result.get("status_code"), "detail": result.get("detail", "")}

    row.access_token = result["access_token"]
    exp = int(result.get("expires_in") or 0)
    if exp:
        from datetime import timedelta as _td

        row.expires_at = _tz.now() + _td(seconds=exp)
    row.save(update_fields=["access_token", "expires_at", "updated_at"])
    return {"refreshed": True, "expires_in": exp, "status_code": result.get("status_code")}


def _td_seconds(s: int):
    from datetime import timedelta

    return timedelta(seconds=s)


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
            refresh = _maybe_proactive_refresh(row, provider)
            try:
                courses = lms_adapters.dispatch(
                    provider, "list_courses",
                    token=row.access_token, base_url=row.base_url or "", limit=25,
                )
            except Exception as exc:  # noqa: BLE001 — adapter errors should always surface inline
                logger.warning("lms console %s list_courses failed school=%s err=%s", provider, school_id, exc)
                courses = [{"error": f"adapter_raise: {exc}"}]
            action_result = {"school": school_id, "courses": courses, "refresh": refresh}

    if school_id and action == "list_assignments":
        course_id = (request.GET.get("course") or "").strip()
        if not course_id:
            action_result = {"error": "missing_course"}
        else:
            row = _resolve_token_row(school_id, provider)
            if row is None or not row.access_token:
                action_result = {"error": "no_token_configured", "school": school_id}
            else:
                try:
                    assignments = lms_adapters.dispatch(
                        provider, "list_assignments",
                        course_id=course_id, token=row.access_token,
                        base_url=row.base_url or "", limit=25,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("lms console %s list_assignments failed school=%s err=%s", provider, school_id, exc)
                    assignments = [{"error": f"adapter_raise: {exc}"}]
                action_result = {"school": school_id, "course_id": course_id, "assignments": assignments}

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


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def lms_token_refresh(request: HttpRequest, provider: str):
    """v4.00.50 — OAuth2 token-refresh button.

    Reads the per-(school, provider) refresh_token + client_id/secret from
    the row + settings env, calls the LMS adapter refresh helper,
    persists the new access_token + expires_at on success.

    Settings keys (per provider): ``RMC_LMS_<PROVIDER>_CLIENT_ID``,
    ``RMC_LMS_<PROVIDER>_CLIENT_SECRET``. Failure surfaces as JSON.
    """
    if not _provider_supported(provider):
        return JsonResponse({"error": "unknown_provider", "provider": provider}, status=404)

    school_id_raw = (request.POST.get("school") or "").strip()
    if not school_id_raw:
        return JsonResponse({"error": "missing_school"}, status=400)
    row = _resolve_token_row(school_id_raw, provider)
    if row is None or not row.refresh_token:
        return JsonResponse({"error": "no_refresh_token", "school": school_id_raw}, status=412)

    import os as _os
    from django.conf import settings as _settings

    provider_upper = provider.upper()
    cid_key = f"RMC_LMS_{provider_upper}_CLIENT_ID"
    csec_key = f"RMC_LMS_{provider_upper}_CLIENT_SECRET"
    client_id = (getattr(_settings, cid_key, "") or _os.environ.get(cid_key, "") or "").strip()
    client_secret = (getattr(_settings, csec_key, "") or _os.environ.get(csec_key, "") or "").strip()
    if not client_id or not client_secret:
        return JsonResponse({"error": "client_credentials_missing", "needed": [cid_key, csec_key]}, status=412)

    kwargs: dict = {
        "refresh_token": row.refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if provider == "canvas":
        kwargs["base_url"] = row.base_url or ""

    try:
        result = lms_adapters.refresh_token(provider, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("lms console %s refresh_token failed school=%s err=%s", provider, school_id_raw, exc)
        result = {"ok": False, "status_code": 0, "detail": f"adapter_raise: {exc}"}

    persisted = False
    if result.get("ok") and result.get("access_token"):
        row.access_token = result["access_token"]
        expires_in = int(result.get("expires_in") or 0)
        if expires_in:
            from django.utils import timezone as _tz
            from datetime import timedelta as _td

            row.expires_at = _tz.now() + _td(seconds=expires_in)
        row.save(update_fields=["access_token", "expires_at", "updated_at"])
        persisted = True

    payload = {
        "success": bool(result.get("ok")),
        "provider": provider,
        "school": school_id_raw,
        "persisted": persisted,
        "expires_at": row.expires_at.isoformat() if row.expires_at else "",
        "masked_token": row.masked_token(),
        "result_status_code": result.get("status_code"),
        "result_detail": result.get("detail", ""),
    }
    if (request.GET.get("format") or "").lower() == "json" or (request.POST.get("format") or "").lower() == "json":
        return JsonResponse(payload)
    return HttpResponseRedirect(reverse("portal:lms_provider_detail", args=[provider]))


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def lms_push_grade(request: HttpRequest, provider: str):
    """v4.00.48 — Push a single grade through the LMS adapter SOT.

    POST body: ``school``, ``course_id``, ``assignment_id``, ``user_id``,
    ``score``. Resolves the per-(school, provider) token + base_url, then
    dispatches to the v4.00.46 adapter. Result is returned as JSON; the
    HTML caller can re-render the provider page on a 302 redirect.
    """
    if not _provider_supported(provider):
        return JsonResponse({"error": "unknown_provider", "provider": provider}, status=404)

    school_id_raw = (request.POST.get("school") or "").strip()
    if not school_id_raw:
        return JsonResponse({"error": "missing_school"}, status=400)
    row = _resolve_token_row(school_id_raw, provider)
    if row is None or not row.access_token:
        return JsonResponse({"error": "no_token_configured", "school": school_id_raw}, status=412)

    course_id = (request.POST.get("course_id") or "").strip()
    assignment_id = (request.POST.get("assignment_id") or "").strip()
    user_id = (request.POST.get("user_id") or "").strip()
    score_raw = (request.POST.get("score") or "").strip()
    if not course_id or not assignment_id or not user_id or score_raw == "":
        return JsonResponse({"error": "missing_field", "required": ["course_id", "assignment_id", "user_id", "score"]}, status=400)
    try:
        score = float(score_raw)  # money-float-allow: lms-score-not-money
    except (ValueError, TypeError):
        return JsonResponse({"error": "score_not_numeric"}, status=400)

    refresh = _maybe_proactive_refresh(row, provider)
    try:
        result = lms_adapters.dispatch(
            provider, "push_grade",
            course_id=course_id, assignment_id=assignment_id,
            user_id=user_id, score=score,
            token=row.access_token, base_url=row.base_url or "",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("lms console %s push_grade failed school=%s err=%s", provider, school_id_raw, exc)
        result = {"ok": False, "status_code": 0, "detail": f"adapter_raise: {exc}"}

    # v4.00.52 — audit the attempt (always; PII-safe via SHA-256[:16] of user_id).
    audit_pk = None
    try:
        from apps.integrations_marketplace.models import LMSPushGradeAudit
        from apps.integrations_marketplace.models_lms_audit import _hash16

        audit = LMSPushGradeAudit.objects.create(  # tenant-isolation-allow: audit-rows-keyed-by-school-staff-required
            school_id=row.school_id,
            provider=provider,
            course_id=course_id[:128],
            assignment_id=assignment_id[:128],
            user_hash=_hash16(user_id),
            score_text=f"{score:.2f}",  # money-float-allow: lms-score-not-money
            ok=bool(result.get("ok")),
            status_code=int(result.get("status_code") or 0),
            detail=str(result.get("detail") or "")[:255],
            actor_user_id=str(getattr(request.user, "pk", "") or ""),
        )
        audit_pk = audit.pk
    except Exception as exc:  # noqa: BLE001
        logger.warning("lms push_grade audit write failed school=%s err=%s", school_id_raw, exc)

    payload = {
        "success": bool(result.get("ok")),
        "provider": provider,
        "school": school_id_raw,
        "course_id": course_id,
        "assignment_id": assignment_id,
        "user_id": user_id,
        "score": score,
        "result": result,
        "refresh": refresh,
        "audit_id": audit_pk,
    }
    if (request.GET.get("format") or "").lower() == "json" or (request.POST.get("format") or "").lower() == "json":
        return JsonResponse(payload)
    return HttpResponseRedirect(
        reverse("portal:lms_provider_detail", args=[provider])
        + f"?school={school_id_raw}&action=list_assignments&course={course_id}"
    )
