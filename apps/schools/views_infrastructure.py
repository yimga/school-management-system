"""Tenant Studio infrastructure — email + offline (SODP batches 1406–1407)."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.schools.email_delivery_settings import (
    get_email_delivery_payload,
    set_email_delivery_payload,
    tenant_email_override_allowed,
)
from apps.schools.offline_delivery_settings import (
    get_offline_delivery_payload,
    set_offline_delivery_payload,
)
from apps.schools.views_domains import _require_school_admin


@login_required
@require_GET
def infrastructure_email_page(request):
    if not _require_school_admin(request):
        return JsonResponse({"error": "Forbidden"}, status=403)
    school = request.school
    payload = get_email_delivery_payload(school)
    from apps.platform_runtime.helpers import get_platform_site_settings_record

    # config-resolver-allow: settings row object passed whole to tenant_email_override_allowed()
    site_row = get_platform_site_settings_record(create=False)
    allow_override = tenant_email_override_allowed(site_row) if site_row else True
    return render(
        request,
        "schools/studio/infrastructure_email.html",
        {
            "email_delivery": payload,
            "allow_tenant_override": allow_override,
            "school": school,
        },
    )


@login_required
@require_POST
def infrastructure_email_save(request):
    if not _require_school_admin(request):
        return JsonResponse({"error": "Forbidden"}, status=403)
    school = request.school
    from apps.platform_runtime.helpers import get_platform_site_settings_record

    # config-resolver-allow: settings row object passed whole to tenant_email_override_allowed()
    site_row = get_platform_site_settings_record(create=False)
    if site_row is not None and not tenant_email_override_allowed(site_row):
        return JsonResponse({"error": "tenant_override_disabled"}, status=403)
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid_json"}, status=400)
    from apps.schoolops.email_delivery import encrypt_password_for_storage

    pwd_enc = ""
    raw_pwd = (body.get("host_password") or "").strip()
    if raw_pwd:
        pwd_enc = encrypt_password_for_storage(raw_pwd)
    set_email_delivery_payload(school, body, password_encrypted_b64=pwd_enc)
    school.save(update_fields=["settings"])
    safe = get_email_delivery_payload(school)
    return JsonResponse({"ok": True, "email_delivery": safe})


@login_required
@require_POST
def infrastructure_email_probe(request):
    if not _require_school_admin(request):
        return JsonResponse({"error": "Forbidden"}, status=403)
    from apps.schoolops.email_delivery import get_resolved_smtp_config, smtp_probe

    cfg = get_resolved_smtp_config(school=request.school)
    safe_cfg = {k: v for k, v in cfg.items() if k != "host_password"}
    result = smtp_probe(timeout=5.0)
    return JsonResponse({"ok": bool(result.get("ok")), "config": safe_cfg, "probe": result})


@login_required
@require_GET
def infrastructure_offline_page(request):
    if not _require_school_admin(request):
        return JsonResponse({"error": "Forbidden"}, status=403)
    return render(
        request,
        "schools/studio/infrastructure_offline.html",
        {
            "offline_delivery": get_offline_delivery_payload(request.school),
            "school": request.school,
        },
    )


@login_required
@require_POST
def infrastructure_offline_save(request):
    if not _require_school_admin(request):
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid_json"}, status=400)
    school = request.school
    set_offline_delivery_payload(school, body)
    school.save(update_fields=["settings"])
    return JsonResponse({"ok": True, "offline_delivery": get_offline_delivery_payload(school)})
