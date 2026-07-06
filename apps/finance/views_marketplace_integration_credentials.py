"""Operator UI for marketplace integration adapter credentials (Paystack, SMS, SIS)."""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from apps.accounts.decorators import require_permission
from apps.accounts.step_up import require_step_up
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.marketplace.integration_adapter_credentials import (
    apply_credential_field_values,
    list_credential_entries,
    mask_secret_value,
)

from services.post_delete_navigation import redirect_after_save

from .views_common import _active_profile


@require_permission("finance.manage")
@require_step_up()
@require_http_methods(["GET", "POST"])
def marketplace_integration_credentials(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseForbidden("School context required.")

    school_settings = dict(school.settings or {})
    adapter_key = (request.GET.get("adapter") or request.POST.get("adapter") or "").strip()
    entries = list_credential_entries(school_settings)
    active = next((e for e in entries if e["adapter_key"] == adapter_key), None)

    if request.method == "POST" and adapter_key:
        field_values = {}
        for key, value in request.POST.items():
            if key.startswith("field_"):
                field_values[key[6:]] = value
        school_settings, changed = apply_credential_field_values(
            school_settings,
            adapter_key=adapter_key,
            field_values=field_values,
        )
        if changed:
            school.settings = school_settings
            school.save(update_fields=["settings", "updated_at"])
            messages.success(request, f"Saved credentials for {adapter_key}.")
        else:
            messages.info(request, "No credential changes detected.")
        target = (
            reverse("finance:marketplace_integration_credentials")
            + f"?adapter={adapter_key}"
        )
        return redirect_after_save(request, target, list_url=target)

    if not active and entries:
        active = entries[0]
        adapter_key = active["adapter_key"]

    display_fields: list[dict] = []
    if active:
        for field_key, spec in (active.get("fields") or {}).items():
            if not isinstance(spec, dict):
                continue
            value = str(spec.get("value") or "")
            display_fields.append(
                {
                    "key": field_key,
                    "label": spec.get("label") or field_key,
                    "required": bool(spec.get("required")),
                    "value": value,
                    "masked": mask_secret_value(value) if value else "",
                    "input_type": "password" if "secret" in field_key or "token" in field_key or "key" in field_key else "text",
                }
            )

    return render(
        request,
        "finance/marketplace_integration_credentials.html",
        {
            "profile": profile,
            "entries": entries,
            "active": active,
            "adapter_key": adapter_key,
            "display_fields": display_fields,
            "payment_setup_url": reverse("finance:payment_readiness_setup"),
        },
    )
