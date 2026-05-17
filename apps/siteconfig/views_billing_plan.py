"""
Read-only tenant billing / plan summary (GTM). No payment capture or Stripe.
Shows the school's assigned Plan row plus live headcount vs plan limits when available.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_stem,
)
from django.utils.translation import gettext as _

from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required
from apps.billing.models import StripePlanPrice, TenantSubscription, UsageMeter
from apps.billing.price_map import active_stripe_price_for_plan
from apps.billing.services import ensure_subscription_for_school
from apps.billing.stripe_checkout import (
    get_active_stripe_processor_config,
    stripe_secret_key,
)
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.tenant_url import build_manager_absolute_url
from apps.siteconfig.commercial_tiers import (
    next_commercial_tier,
    plan_display_context,
    plan_slug_candidates_for_commercial_tier,
)
from apps.siteconfig.models import Plan


def _plan_catalog_advanced_url(request: HttpRequest) -> str | None:
    """
    Break-glass plan catalog: Django admin changelist when registered; otherwise
    control-plane plans list (Plan CRUD is not on tenant/platform admin).
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_superuser", False):
        return None
    try:
        return reverse("admin:siteconfig_plan_changelist")
    except NoReverseMatch:
        pass
    try:
        rel = reverse("super:plans_list", urlconf="config.manager_urls")
    except NoReverseMatch:
        return None
    return build_manager_absolute_url(request, path=rel)


def _suggested_upgrade_plan_slug_for_checkout(
    school, subscription, account
) -> str | None:
    """Pick a plan slug that has an active Stripe price row for the next commercial tier."""
    ctx = plan_display_context(school)
    nxt = next_commercial_tier(ctx.get("tier_key"))
    if not nxt:
        return None
    candidates = plan_slug_candidates_for_commercial_tier(nxt)
    if not candidates:
        return None
    cycle = (
        getattr(subscription, "billing_cycle", None)
        or TenantSubscription.BillingCycle.MONTHLY
    )
    curr = (getattr(account, "currency_code", None) or "USD").strip().upper()
    priced = list(
        StripePlanPrice.objects.filter(
            is_active=True,
            plan_code__in=list(candidates),
            billing_cycle=cycle,
            currency=curr,
        ).values_list("plan_code", flat=True)
    )
    if not priced:
        priced = list(
            StripePlanPrice.objects.filter(
                is_active=True,
                plan_code__in=list(candidates),
                billing_cycle=cycle,
            ).values_list("plan_code", flat=True)
        )
    for code in priced:
        if Plan.objects.filter(slug=code, is_active=True).exists():
            return code
    return priced[0] if priced else None


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET"])
def billing_plan_readonly(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    plan = getattr(school, "plan", None) if school is not None else None
    addons: list = []
    if school is not None:
        addons = list(getattr(school, "addons", None) or [])

    student_count = 0
    teacher_count = 0
    if school is not None:
        student_count = StudentProfile.objects.filter(
            school=school, is_active=True
        ).count()
        teacher_count = TeacherProfile.objects.filter(school=school).count()

    plan_catalog_advanced_url = _plan_catalog_advanced_url(request)

    console_url = None
    try:
        console_url = reverse("siteconfig:console_domains_hub")
    except NoReverseMatch:
        pass

    plan_tier_ctx = plan_display_context(school)
    upgrade_next_tier = next_commercial_tier(plan_tier_ctx.get("tier_key"))
    app_catalog_url = None
    try:
        app_catalog_url = reverse("tenant_app_catalog")
    except NoReverseMatch:
        pass

    billing_account = None
    platform_subscription = None
    usage_meters: list = []
    stripe_processor_configured = False
    stripe_customer_linked = False
    has_stripe_price_for_current_plan = False
    upgrade_checkout_plan_code: str | None = None
    checkout_start_url = None
    customer_portal_url = None
    try:
        checkout_start_url = reverse("siteconfig:billing_checkout_start")
        customer_portal_url = reverse("siteconfig:billing_customer_portal")
    except NoReverseMatch:
        pass

    if school is not None:
        cfg = get_active_stripe_processor_config()
        stripe_processor_configured = bool(cfg and stripe_secret_key(cfg))
        account, subscription, _ = ensure_subscription_for_school(school)
        billing_account = account
        platform_subscription = subscription
        stripe_customer_linked = bool((account.external_customer_ref or "").strip())
        if plan is not None:
            slug = (plan.slug or "").strip()
            cyc = getattr(subscription, "billing_cycle", None) or "MONTHLY"
            cur = (account.currency_code or "USD").strip().upper()
            has_stripe_price_for_current_plan = (
                active_stripe_price_for_plan(
                    slug, billing_cycle=cyc, currency=cur
                )
                is not None
                or active_stripe_price_for_plan(slug, billing_cycle=cyc) is not None
            )
        upgrade_checkout_plan_code = _suggested_upgrade_plan_slug_for_checkout(
            school, subscription, account
        )
        usage_meters = list(
            UsageMeter.objects.filter(school=school).order_by("-period_start")[:24]
        )

    return render_siteconfig_stem(
        request,
        "billing_plan_readonly",
        None,
        cp_title=_("Billing plan"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Billing plan"), active=True),
        ),
    )
