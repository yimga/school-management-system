"""
Read-only tenant billing / plan summary (GTM). Stripe checkout + portal when configured.
Shows the school's assigned Plan row plus live headcount vs plan limits when available.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required
from apps.billing.models import (
    PlatformLedgerEntry,
    StripePlanPrice,
    TenantSubscription,
    UsageMeter,
)
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
from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_stem,
)
from apps.siteconfig.models import Plan


def _plan_catalog_advanced_url(request: HttpRequest) -> str | None:
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


def _billing_plan_context(request: HttpRequest) -> dict:
    school = getattr(request, "school", None)
    plan = getattr(school, "plan", None) if school is not None else None
    addons = list(getattr(school, "addons", None) or []) if school is not None else []

    student_count = 0
    teacher_count = 0
    if school is not None:
        student_count = StudentProfile.objects.filter(
            school=school, is_active=True
        ).count()
        teacher_count = TeacherProfile.objects.filter(school=school).count()

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

    checkout_start_url = None
    customer_portal_url = None
    billing_stripe_connect_url = None
    try:
        checkout_start_url = reverse("siteconfig:billing_checkout_start")
        customer_portal_url = reverse("siteconfig:billing_customer_portal")
        billing_stripe_connect_url = reverse("siteconfig:billing_stripe_connect")
    except NoReverseMatch:
        pass

    billing_account = None
    platform_subscription = None
    usage_meters: list = []
    ledger_entries: list = []
    stripe_processor_configured = False
    stripe_customer_linked = False
    has_stripe_price_for_current_plan = False
    upgrade_checkout_plan_code = None

    if school is not None:
        cfg = get_active_stripe_processor_config()
        stripe_processor_configured = bool(cfg and stripe_secret_key(cfg))
        billing_account, platform_subscription, _ = ensure_subscription_for_school(school)
        stripe_customer_linked = bool(
            (billing_account.external_customer_ref or "").strip()
        )
        if plan is not None:
            slug = (plan.slug or "").strip()
            cyc = getattr(platform_subscription, "billing_cycle", None) or "MONTHLY"
            cur = (billing_account.currency_code or "USD").strip().upper()
            has_stripe_price_for_current_plan = (
                active_stripe_price_for_plan(slug, billing_cycle=cyc, currency=cur)
                is not None
                or active_stripe_price_for_plan(slug, billing_cycle=cyc) is not None
            )
        upgrade_checkout_plan_code = _suggested_upgrade_plan_slug_for_checkout(
            school, platform_subscription, billing_account
        )
        usage_meters = list(
            UsageMeter.objects.filter(school=school).order_by("-period_start")[:24]
        )
        # Billing history / receipts: the posted ledger (charges, grant credits,
        # and the tax line) so the tenant can read what they were billed and when.
        ledger_entries = list(
            PlatformLedgerEntry.objects.filter(school=school).order_by(
                "-happened_at", "-id"
            )[:24]
        )

    # Localized, plain-language pricing for the tenant's own country: current
    # terms + a plan comparison the tenant can actually read (prices, not codes).
    pricing_options: dict = {}
    if school is not None:
        try:
            from apps.billing.tenant_pricing import tenant_pricing_options

            pricing_options = tenant_pricing_options(school)
        except Exception:  # noqa: BLE001 - pricing display must never break the billing page
            pricing_options = {}

    return {
        "school": school,
        "plan": plan,
        "pricing_options": pricing_options,
        "addons": addons,
        "student_count": student_count,
        "teacher_count": teacher_count,
        "plan_tier_ctx": plan_tier_ctx,
        "upgrade_next_tier": upgrade_next_tier,
        "app_catalog_url": app_catalog_url,
        "console_url": console_url,
        "plan_catalog_advanced_url": _plan_catalog_advanced_url(request),
        "checkout_start_url": checkout_start_url,
        "customer_portal_url": customer_portal_url,
        "billing_account": billing_account,
        "platform_subscription": platform_subscription,
        "usage_meters": usage_meters,
        "ledger_entries": ledger_entries,
        "stripe_processor_configured": stripe_processor_configured,
        "stripe_customer_linked": stripe_customer_linked,
        "has_stripe_price_for_current_plan": has_stripe_price_for_current_plan,
        "upgrade_checkout_plan_code": upgrade_checkout_plan_code,
        "billing_stripe_connect_url": billing_stripe_connect_url,
    }


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET"])
def billing_plan_readonly(request: HttpRequest) -> HttpResponse:
    return render_siteconfig_stem(
        request,
        "billing_plan_readonly",
        _billing_plan_context(request),
        cp_title=_("Billing plan"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Billing plan"), active=True),
        ),
    )


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET"])
def billing_statement_pdf(request: HttpRequest) -> HttpResponse:
    """Downloadable platform billing statement (the school's posted ledger as a
    branded PDF document). Reuses the platform's WeasyPrint convention with a
    graceful 503 when the renderer is unavailable. Amounts carry their stored ISO
    currency code so a mixed-currency history reads unambiguously.
    """
    from django.utils import timezone
    from django.utils.html import escape

    school = getattr(request, "school", None)
    if school is None:
        return HttpResponse(_("No school in context."), status=404)

    entries = list(
        PlatformLedgerEntry.objects.filter(school=school).order_by(
            "-happened_at", "-id"
        )[:200]  # magic-number-allow: statement-row-cap
    )

    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        # ImportError: package absent. OSError: package present but native
        # libs (cairo/pango/GLib) unavailable — both mean "renderer offline".
        return HttpResponse(_("PDF export requires WeasyPrint."), status=503)

    def _fmt(entry) -> str:
        code = escape((entry.currency_code or "").strip())
        sign = "-" if entry.entry_type == PlatformLedgerEntry.EntryType.CREDIT else ""
        return f"{code} {sign}{entry.amount}".strip()

    rows_html = "".join(
        f"<tr><td>{escape(e.happened_at.strftime('%Y-%m-%d') if e.happened_at else '')}</td>"
        f"<td>{escape(e.description or e.reference or '')}</td>"
        f"<td>{escape(e.get_entry_type_display())}</td>"
        f"<td class='amt'>{_fmt(e)}</td></tr>"
        for e in entries
    )
    if not rows_html:
        rows_html = (
            f"<tr><td colspan='4'>{escape(str(_('No billing entries yet.')))}</td></tr>"
        )

    school_name = escape(getattr(school, "name", "") or "")
    title = escape(str(_("Billing statement")))
    generated = escape(timezone.now().strftime("%Y-%m-%d %H:%M UTC"))
    bill_to = escape(str(_("Account")))
    gen_label = escape(str(_("Generated")))
    th_date = escape(str(_("Date")))
    th_desc = escape(str(_("Description")))
    th_type = escape(str(_("Type")))
    th_amt = escape(str(_("Amount")))

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;font-size:10pt;margin:14mm;color:#1a1a2e;}}
h1{{font-size:16pt;margin:0 0 2px;}} .muted{{color:#555;font-size:9pt;}}
table{{width:100%;border-collapse:collapse;margin-top:14px;}}
th,td{{border:1px solid #ddd;padding:6px 8px;text-align:left;}}
th{{background:#f5f5f5;}} td.amt,th.amt{{text-align:right;white-space:nowrap;}}
.header{{margin-bottom:10px;border-bottom:2px solid #1a1a2e;padding-bottom:8px;}}</style></head>
<body><div class="header"><h1>{title}</h1>
<div class="muted">{bill_to}: {school_name}</div>
<div class="muted">{gen_label}: {generated}</div></div>
<table><thead><tr><th>{th_date}</th><th>{th_desc}</th><th>{th_type}</th><th class="amt">{th_amt}</th></tr></thead>
<tbody>{rows_html}</tbody></table></body></html>"""

    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="billing_statement.pdf"'
    return resp
