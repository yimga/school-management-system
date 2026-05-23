"""Tenant Stripe Connect Express onboarding — /siteconfig/billing-stripe/."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.accounts.decorators import permission_required
from apps.billing.stripe_checkout import get_active_stripe_processor_config, stripe_secret_key
from apps.billing.stripe_connect_onboarding import (
    connect_is_configured,
    create_account_link,
    create_express_account,
    fetch_connect_account,
    platform_connect_config,
)
from apps.schools.stripe_connect_settings import (
    get_stripe_connect_payload,
    is_stripe_connected,
    merge_stripe_account_object,
    set_stripe_connect_payload,
    tenant_stripe_connect_allowed,
)


def _billing_stripe_connect_url(request, view_name: str = "siteconfig:billing_stripe_connect") -> str:
    try:
        path = reverse(view_name, urlconf="config.tenant_urls")
    except Exception:  # noqa: BLE001
        path = reverse(view_name)
    return request.build_absolute_uri(path)


@login_required
@permission_required("settings.manage")
@require_GET
def billing_stripe_connect(request):
    school = getattr(request, "school", None)
    if not school:
        messages.warning(
            request,
            "No active school context. Open Stripe Connect on a tenant host.",
        )
        return redirect(reverse("siteconfig:billing_plan_readonly"))

    cfg = get_active_stripe_processor_config()
    processor_ready = bool(cfg and stripe_secret_key(cfg))
    connect_cfg = platform_connect_config(cfg) if cfg else {"enabled": False}

    from apps.siteconfig.models import SiteSettings

    site_row = SiteSettings.objects.first()
    allow_tenant = tenant_stripe_connect_allowed(site_row)

    payload = get_stripe_connect_payload(school)
    if payload.get("account_id") and processor_ready:
        ok, err, account = fetch_connect_account(config=cfg, account_id=payload["account_id"])
        if ok and isinstance(account, dict):
            payload = merge_stripe_account_object(school, account)
            school.save(update_fields=["settings"])
        elif err:
            messages.info(request, f"Could not refresh Connect status: {err}")

    return render(
        request,
        "siteconfig/billing_stripe_connect.html",
        {
            "school": school,
            "stripe_connect": payload,
            "stripe_connected": is_stripe_connected(school),
            "processor_ready": processor_ready,
            "connect_enabled": connect_is_configured(cfg),
            "allow_tenant_connect": allow_tenant,
            "connect_account_type": connect_cfg.get("account_type") or "express",
        },
    )


@login_required
@permission_required("settings.manage")
@require_GET
def billing_stripe_connect_start(request):
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "No active school context.")
        return redirect(reverse("siteconfig:billing_plan_readonly"))

    from apps.siteconfig.models import SiteSettings

    if not tenant_stripe_connect_allowed(SiteSettings.objects.first()):
        messages.error(request, "Platform operator has disabled tenant Stripe Connect onboarding.")
        return redirect(reverse("siteconfig:billing_stripe_connect"))

    cfg = get_active_stripe_processor_config()
    if not connect_is_configured(cfg):
        messages.warning(
            request,
            "Stripe Connect is not enabled. Your platform operator must enable Connect on the billing processor.",
        )
        return redirect(reverse("siteconfig:billing_stripe_connect"))

    payload = get_stripe_connect_payload(school)
    account_id = payload.get("account_id") or ""

    if not account_id:
        ok, err, body = create_express_account(config=cfg, school=school)
        if not ok:
            messages.error(request, err or "Could not create Stripe Connect account.")
            return redirect(reverse("siteconfig:billing_stripe_connect"))
        account_id = str(body.get("id") or "").strip()
        set_stripe_connect_payload(
            school,
            {
                "account_id": account_id,
                "account_type": str(body.get("type") or platform_connect_config(cfg).get("account_type")),
            },
        )
        school.save(update_fields=["settings"])

    refresh_url = _billing_stripe_connect_url(request, "siteconfig:billing_stripe_connect_start")
    return_url = _billing_stripe_connect_url(request, "siteconfig:billing_stripe_connect_return")
    ok, err, link_url, _body = create_account_link(
        config=cfg,
        account_id=account_id,
        refresh_url=refresh_url,
        return_url=return_url,
    )
    if not ok or not link_url:
        messages.error(request, err or "Could not start Stripe onboarding.")
        return redirect(reverse("siteconfig:billing_stripe_connect"))
    return redirect(link_url)


@login_required
@permission_required("settings.manage")
@require_GET
def billing_stripe_connect_return(request):
    school = getattr(request, "school", None)
    if not school:
        return redirect(reverse("siteconfig:billing_plan_readonly"))

    cfg = get_active_stripe_processor_config()
    payload = get_stripe_connect_payload(school)
    account_id = payload.get("account_id") or ""
    if cfg and account_id:
        ok, _err, account = fetch_connect_account(config=cfg, account_id=account_id)
        if ok and isinstance(account, dict):
            merge_stripe_account_object(school, account)
            school.save(update_fields=["settings"])
            if is_stripe_connected(school):
                messages.success(request, "Stripe Connect onboarding complete. Payouts can flow to your school.")
            else:
                messages.info(
                    request,
                    "Stripe onboarding saved. Complete any remaining steps in Stripe if prompted.",
                )
    return redirect(reverse("siteconfig:billing_stripe_connect"))
