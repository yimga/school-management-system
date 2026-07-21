"""
Platform billing console (BR-12 split from super_views).
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import (
    BillingAccount,
    BillingProcessorSyncEvent,
    PlatformLedgerEntry,
    RevenueSharePayout,
    TenantSubscription,
)
from apps.billing.services import ensure_subscription_for_school
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_BILLING_READ,
    require_platform_scope,
)
from apps.platform_runtime.operational_center_nav import billing_command_frame_context
from apps.platform_runtime.page_status_tags import (
    STATUS_ATTENTION,
    STATUS_HEALTHY,
    build_masthead,
    chip,
    sparkline_from_count,
)
from apps.schools.control_plane import require_super_access_with_host

from .models import School, TenantApiUsage


@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_BILLING_READ)
def billing_dashboard(request):
    """Platform billing console: subscriptions, usage, and recent platform ledger activity."""
    trial_schools = list(
        School.objects.filter(
            is_active=True, billing_type=School.BillingType.FREE_TRIAL
        )
        .select_related("plan", "default_region")
        .annotate(student_count=Count("student_profiles", distinct=True))
        .order_by("trial_end_date", "name")[:100]
    )
    for school in trial_schools:
        ensure_subscription_for_school(school)
    school_ids = [s.pk for s in trial_schools]
    usage_agg = {}
    if school_ids:
        for r in (
            TenantApiUsage.objects.filter(school_id__in=school_ids)
            .values("school_id")
            .annotate(total=Sum("request_count"))
        ):
            usage_agg[r["school_id"]] = r["total"]
    for school in trial_schools:
        school.api_requests = usage_agg.get(school.pk, 0)
        school.trial_expired = (
            school.trial_end_date and school.trial_end_date < timezone.now().date()
        )
    account_summary = (
        BillingAccount.objects.values("status")
        .annotate(total=Count("id"))
        .order_by("status")
    )
    subscription_summary = (
        TenantSubscription.objects.values("status")
        .annotate(total=Count("id"))
        .order_by("status")
    )
    billing_account_count = BillingAccount.objects.count()
    subscription_count = TenantSubscription.objects.count()
    active_subscriptions = list(
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        TenantSubscription.objects.filter(
            status__in=[
                TenantSubscription.Status.TRIALING,
                TenantSubscription.Status.ACTIVE,
                TenantSubscription.Status.PAST_DUE,
                TenantSubscription.Status.SUSPENDED,
            ]
        )
        .select_related("school", "plan", "billing_account")
        .order_by("-updated_at", "school__name")[:30]
    )
    recent_ledger = list(
        PlatformLedgerEntry.objects.select_related(
            "school", "billing_account"
        ).order_by("-happened_at", "-created_at")[:20]
    )
    total_posted_charges = (
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        PlatformLedgerEntry.objects.filter(
            status=PlatformLedgerEntry.Status.POSTED,
            entry_type=PlatformLedgerEntry.EntryType.CHARGE,
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    total_posted_credits = (
        PlatformLedgerEntry.objects.filter(
            status=PlatformLedgerEntry.Status.POSTED,
            entry_type__in=[
                PlatformLedgerEntry.EntryType.CREDIT,
                PlatformLedgerEntry.EntryType.WRITE_OFF,
            ],
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )
    stale_processor_accounts = (
        BillingAccount.objects.exclude(processor_code="")
        .filter(
            Q(last_processor_sync_at__isnull=True)
            | Q(last_processor_sync_at__lt=timezone.now() - timedelta(days=3))
        )
        .count()
    )
    processor_event_count = BillingProcessorSyncEvent.objects.count()
    recent_processor_events = list(
        BillingProcessorSyncEvent.objects.select_related(
            "school", "billing_account", "subscription"
        ).order_by("-happened_at", "-created_at")[:12]
    )
    scheduled_payouts = list(
        RevenueSharePayout.objects.select_related("source_school")
        .filter(
            status__in=[
                RevenueSharePayout.Status.SCHEDULED,
                RevenueSharePayout.Status.IN_TRANSIT,
            ]
        )
        .order_by("scheduled_for", "-created_at")[:12]
    )
    scheduled_payout_total = (
        RevenueSharePayout.objects.filter(
            status__in=[
                RevenueSharePayout.Status.SCHEDULED,
                RevenueSharePayout.Status.IN_TRANSIT,
            ]
        )
        .aggregate(total=Sum("net_amount"))
        .get("total")
        or 0
    )
    past_due = 0
    try:
        past_due = sum(
            int(row.get("total") or 0)
            for row in subscription_summary
            if str(row.get("status", "")).lower() in {"past_due", "past-due", "delinquent"}
        )
    except Exception:
        past_due = 0
    stale_n = int(stale_processor_accounts or 0)
    chips = [
        chip(
            label=f"{billing_account_count} accounts",
            tone="success",
            sparkline=sparkline_from_count(billing_account_count),
        ),
        chip(
            label=f"{subscription_count} subscriptions",
            tone="success",
            sparkline=sparkline_from_count(subscription_count),
        ),
    ]
    if past_due:
        chips.append(
            chip(
                label=f"{past_due} past due",
                tone="warning",
                sparkline=sparkline_from_count(past_due),
            )
        )
    if stale_n:
        chips.append(chip(label=f"{stale_n} PSP sync issues", tone="danger"))
    elif processor_event_count:
        chips.append(chip(label="PSP healthy", tone="success"))
    chips.append(chip(label="Updated just now", tone="fresh"))
    masthead = build_masthead(
        archetype="money",
        host="operator",
        eyebrow="Money · fleet",
        title="Platform billing",
        purpose=(
            "Posted charges, credits, accounts, and subscriptions across the fleet. "
            "PSP posture stays honest — no fake live collection."
        ),
        chips=chips,
        primary_url=reverse("super:usage"),
        primary_label="Usage API",
        secondary_url=reverse("super:dashboard"),
        secondary_label="Back to dashboard",
        status_key=STATUS_ATTENTION if (past_due or stale_n) else STATUS_HEALTHY,
        why_items=[
            {
                "title": "Posted charges",
                "body": "Sum of posted platform ledger charge rows.",
                "source": "Platform ledger",
                "freshness": "Live on page load",
            },
            {
                "title": "Past due",
                "body": "Subscriptions in past-due / delinquent status.",
                "source": "TenantSubscription",
                "freshness": "Live on page load",
            },
        ],
    )
    return render(
        request,
        "schools/billing_dashboard.html",
        {
            **billing_command_frame_context(),
            **masthead,
            "trial_schools": trial_schools,
            "account_summary": list(account_summary),
            "subscription_summary": list(subscription_summary),
            "billing_account_count": billing_account_count,
            "subscription_count": subscription_count,
            "active_subscriptions": active_subscriptions,
            "recent_ledger": recent_ledger,
            "total_posted_charges": total_posted_charges,
            "total_posted_credits": total_posted_credits,
            "stale_processor_accounts": stale_processor_accounts,
            "processor_event_count": processor_event_count,
            "recent_processor_events": recent_processor_events,
            "scheduled_payouts": scheduled_payouts,
            "scheduled_payout_total": scheduled_payout_total,
            "usage_url": reverse("super:usage"),
        },
    )
