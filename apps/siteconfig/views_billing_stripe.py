"""
Tenant Stripe Checkout and Customer Portal entry points.

Real Stripe API calls only when an active ``PlatformBillingProcessorConfig`` (code=stripe)
exists with a secret key in metadata. Never fabricates checkout or portal URLs.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.accounts.decorators import permission_required
from apps.schools.security_enforcer import enforce_tenant_security
from apps.billing.price_map import active_stripe_price_for_plan
from apps.billing.services import ensure_subscription_for_school
from apps.billing.stripe_checkout import (
    absolute_urls_for_billing,
    create_billing_portal_session,
    create_checkout_session,
    get_active_stripe_processor_config,
    stripe_secret_key,
)
from apps.marketplace.manifest_schema import normalize_platform_manifest
from apps.marketplace.models import MarketplaceApp, MarketplaceListing


def _redirect_billing_plan():
    return redirect(reverse("siteconfig:billing_plan_readonly"))


@login_required
@permission_required("settings.manage")
@require_GET
def billing_checkout_start(request):
    school = getattr(request, "school", None)
    if not school:
        messages.warning(
            request,
            "No active school context. Open Plan & entitlements on a tenant host.",
        )
        return _redirect_billing_plan()

    cfg = get_active_stripe_processor_config()
    if not cfg or not stripe_secret_key(cfg):
        messages.warning(
            request,
            "Billing processor is not configured for online checkout. "
            "Your platform operator must enable Stripe with valid credentials.",
        )
        return _redirect_billing_plan()

    account, subscription, _ = ensure_subscription_for_school(school)

    marketplace_raw = str(request.GET.get("marketplace_app_id") or "").strip()
    if marketplace_raw:
        try:
            app_pk = int(marketplace_raw)
        except ValueError:
            messages.error(request, "Invalid marketplace app.")
            return _redirect_billing_plan()

        app = get_object_or_404(
            MarketplaceApp.objects.select_related("publisher"), pk=app_pk
        )
        lst = getattr(app, "listing", None)
        if lst is None or lst.status != MarketplaceListing.Status.APPROVED:
            messages.error(request, "That marketplace listing is not approved.")
            return _redirect_billing_plan()
        if getattr(lst, "kill_switch_active", False):
            messages.error(
                request,
                "This marketplace listing is temporarily unavailable for purchase.",
            )
            return _redirect_billing_plan()

        publisher_slug = getattr(app.publisher, "slug", "") if app.publisher_id else ""
        mf = normalize_platform_manifest(
            dict(app.manifest or {}),
            app_slug=app.slug,
            app_name=app.name,
            version=app.version or "",
            publisher_slug=publisher_slug or "",
        )
        sku_code = str(mf.get("billing_sku") or "").strip()
        if not sku_code:
            messages.error(
                request,
                "Paid marketplace apps must declare a billing_sku mapped to Stripe prices.",
            )
            return _redirect_billing_plan()

        cycle = (
            request.GET.get("billing_cycle")
            or getattr(subscription, "billing_cycle", None)
            or ""
        ).strip().upper()
        if cycle not in ("MONTHLY", "ANNUAL"):
            cycle = "MONTHLY"
        currency = (getattr(account, "currency_code", None) or "USD").strip().upper()
        row = active_stripe_price_for_plan(
            sku_code, billing_cycle=cycle, currency=currency
        )
        if row is None:
            row = active_stripe_price_for_plan(sku_code, billing_cycle=cycle)
        if row is None:
            messages.error(
                request,
                "No Stripe price is mapped for this marketplace billing SKU. "
                "Your operator must configure Stripe prices for the app's billing_sku.",
            )
            return _redirect_billing_plan()

        plan_slug = ""
        pl = getattr(school, "plan", None)
        if pl is not None:
            plan_slug = (getattr(pl, "slug", "") or "").strip()

        success_url, cancel_url = absolute_urls_for_billing(request)
        ok, err, checkout_url, _body = create_checkout_session(
            config=cfg,
            stripe_price_id=row.stripe_price_id,
            success_url=success_url,
            cancel_url=cancel_url,
            customer_id=(account.external_customer_ref or "").strip(),
            customer_email=(getattr(request.user, "email", None) or "").strip(),
            metadata={
                "school_id": str(school.pk),
                "marketplace_app_id": str(app.pk),
                "billing_sku": sku_code,
                "billing_context": "marketplace_addon",
                "plan_code": plan_slug or sku_code,
                "billing_cycle": cycle,
            },
        )
        if not ok or not checkout_url:
            messages.error(request, err or "Checkout could not be started with Stripe.")
            return _redirect_billing_plan()
        return redirect(checkout_url)

    plan = getattr(school, "plan", None)
    plan_code = (request.GET.get("plan_code") or "").strip()
    if not plan_code and plan is not None:
        plan_code = (getattr(plan, "slug", "") or "").strip()
    if not plan_code:
        messages.error(
            request,
            "No plan was selected for checkout. Choose an upgrade target or contact support.",
        )
        return _redirect_billing_plan()

    cycle = (
        request.GET.get("billing_cycle")
        or getattr(subscription, "billing_cycle", None)
        or ""
    ).strip().upper()
    if cycle not in ("MONTHLY", "ANNUAL"):
        cycle = "MONTHLY"

    currency = (getattr(account, "currency_code", None) or "USD").strip().upper()
    row = active_stripe_price_for_plan(
        plan_code, billing_cycle=cycle, currency=currency
    )
    if row is None:
        row = active_stripe_price_for_plan(plan_code, billing_cycle=cycle)
    if row is None:
        messages.error(
            request,
            "No Stripe price is mapped for this plan and billing cycle. "
            "Your operator must configure Stripe plan prices in platform billing settings.",
        )
        return _redirect_billing_plan()

    success_url, cancel_url = absolute_urls_for_billing(request)
    ok, err, checkout_url, _body = create_checkout_session(
        config=cfg,
        stripe_price_id=row.stripe_price_id,
        success_url=success_url,
        cancel_url=cancel_url,
        customer_id=(account.external_customer_ref or "").strip(),
        customer_email=(getattr(request.user, "email", None) or "").strip(),
        metadata={
            "school_id": str(school.pk),
            "plan_code": plan_code,
            "billing_cycle": cycle,
        },
    )
    if not ok or not checkout_url:
        messages.error(request, err or "Checkout could not be started with Stripe.")
        return _redirect_billing_plan()
    return redirect(checkout_url)


@login_required
@permission_required("settings.manage")
@enforce_tenant_security(action="admin", require_school=False)
@require_GET
def billing_customer_portal(request):
    school = getattr(request, "school", None)
    if not school:
        messages.warning(
            request,
            "No active school context. Open Plan & entitlements on a tenant host.",
        )
        return _redirect_billing_plan()

    cfg = get_active_stripe_processor_config()
    if not cfg or not stripe_secret_key(cfg):
        messages.warning(
            request,
            "Billing processor is not configured. "
            "Your platform operator must enable Stripe with valid credentials.",
        )
        return _redirect_billing_plan()

    account, _subscription, _ = ensure_subscription_for_school(school)
    customer_id = (account.external_customer_ref or "").strip()
    if not customer_id:
        messages.warning(
            request,
            "Stripe customer is not linked to this tenant yet. "
            "Complete checkout once, or ask your operator to link billing records.",
        )
        return _redirect_billing_plan()

    return_path = reverse("siteconfig:billing_plan_readonly")
    return_url = request.build_absolute_uri(return_path)
    ok, err, portal_url, _body = create_billing_portal_session(
        config=cfg,
        customer_id=customer_id,
        return_url=return_url,
    )
    if not ok or not portal_url:
        messages.error(
            request,
            err or "Could not open the billing portal. Try again or contact support.",
        )
        return _redirect_billing_plan()
    return redirect(portal_url)
