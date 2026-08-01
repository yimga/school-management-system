"""Operator per-tenant subscription manager.

Closes the operator-console gap where subscription lifecycle (change plan,
extend trial, suspend / reactivate / cancel) was only reachable via Django
admin. Wires the existing billing services + entitlement materialization behind
a single staff-gated, audited, BILLING_WRITE-scoped surface.

All mutations reuse canonical engines:
  * School.plan FK is the source the usage-limit middleware + entitlements read.
  * ensure_subscription_for_school() reconciles the TenantSubscription + account.
  * sync_subscription_entitlements() re-materializes Entitlement rows so feature
    gates + seat caps reflect the change immediately.
Every action writes a compliance AuditLog entry via log_control_plane_action.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.billing.models import PlatformLedgerEntry, SubscriptionGrant, TenantSubscription
from apps.billing.services import (
    apply_subscription_waiver,
    ensure_subscription_for_school,
    platform_account_balance,
    preview_subscription_commercial_terms,
    sync_subscription_entitlements,
)
from apps.compliance.models_audit import AuditLog
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_BILLING_WRITE,
    require_platform_scope,
)
from apps.schools.control_plane import (
    log_control_plane_action,
    require_super_access_with_host,
)
from apps.plans_entitlements.models import Plan

from .models import School

# Statuses an operator may set by hand. PAST_DUE is processor-driven (dunning),
# so it is intentionally excluded from the manual control.
_OPERATOR_SETTABLE_STATUSES = (
    TenantSubscription.Status.ACTIVE,
    TenantSubscription.Status.TRIALING,
    TenantSubscription.Status.SUSPENDED,
    TenantSubscription.Status.CANCELED,
)

_MAX_TRIAL_EXTENSION_DAYS = 365  # magic-number-allow: operator manual trial-extension ceiling = 1 year (days)
_MAX_WAIVER_DAYS = 3650  # magic-number-allow: operator commercial waiver ceiling = 10 years (days)

# How many recent ledger rows to surface inline so an operator can see a tenant's
# platform billing history without dropping to Django admin.
_LEDGER_HISTORY_LIMIT = 15  # magic-number-allow: inline ledger history rows shown on the manager surface


def _resolve_school(school_id: str):
    return School.objects.filter(pk=str(school_id)).select_related("plan").first()


def _operator_reason(request, base: str) -> str:
    """Combine the canonical action reason with an optional operator-supplied note.

    The note is free text from the form; it is appended to the fixed reason so the
    audit trail keeps a stable machine-readable prefix plus the human context. The
    AuditLog reason field caps at 255 chars, so the combined value is truncated.
    """
    note = (request.POST.get("reason") or "").strip()
    if not note:
        return base
    return f"{base} — {note}"[:255]


@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_BILLING_WRITE)
def tenant_subscription_manage(request, school_id):
    """Detail + lifecycle actions for one tenant's platform subscription."""
    school = _resolve_school(school_id)
    if school is None:
        messages.error(request, "School not found.")
        return redirect(reverse("super:billing_dashboard"))

    # ensure_subscription_for_school is idempotent + materializes the account /
    # subscription, so the detail view always has live records to show.
    billing_account, subscription, _created = ensure_subscription_for_school(school)

    if request.method == "POST":
        return _handle_action(request, school, subscription)

    plans = Plan.objects.filter(is_active=True).order_by("name")

    # Read-only platform billing history + current balance, so operators do not
    # have to fall back to Django admin to see what a tenant was charged.
    ledger_entries = []
    account_balance = None
    commercial_terms = preview_subscription_commercial_terms(subscription)
    active_grants = list(
        SubscriptionGrant.objects.select_related("promotion")
        .filter(school=school, status=SubscriptionGrant.Status.ACTIVE)
        .order_by("-starts_at", "-created_at")[:10]
    )
    if billing_account is not None:
        ledger_entries = list(
            PlatformLedgerEntry.objects.filter(
                billing_account=billing_account,
                school=school,
            ).order_by("-happened_at", "-created_at")[:_LEDGER_HISTORY_LIMIT]
        )
        account_balance = platform_account_balance(billing_account)

    context = {
        "school": school,
        "billing_account": billing_account,
        "subscription": subscription,
        "plans": plans,
        "settable_statuses": _OPERATOR_SETTABLE_STATUSES,
        "trial_end_date": getattr(school, "trial_end_date", None),
        "ledger_entries": ledger_entries,
        "account_balance": account_balance,
        "commercial_terms": commercial_terms,
        "active_grants": active_grants,
        "back_url": reverse("super:billing_dashboard"),
    }
    return render(request, "schools/super/tenant_subscription_manage.html", context)


def _handle_action(request, school, subscription):
    action = (request.POST.get("action") or "").strip()
    redirect_url = reverse(
        "super:tenant_subscription_manage", kwargs={"school_id": str(school.pk)}
    )

    if action == "change_plan":
        _action_change_plan(request, school, subscription)
    elif action == "extend_trial":
        _action_extend_trial(request, school, subscription)
    elif action == "set_status":
        _action_set_status(request, school, subscription)
    elif action == "apply_waiver":
        _action_apply_waiver(request, school, subscription)
    else:
        messages.error(request, "Unknown action.")
    return redirect(redirect_url)


def _action_change_plan(request, school, subscription):
    raw = (request.POST.get("plan_id") or "").strip()
    old_plan = school.plan
    new_plan = None
    if raw:
        new_plan = Plan.objects.filter(pk=raw, is_active=True).first()
        if new_plan is None:
            messages.error(request, "Selected plan was not found or is inactive.")
            return
    if (getattr(old_plan, "pk", None)) == (getattr(new_plan, "pk", None)):
        messages.info(request, "Plan unchanged.")
        return

    school.plan = new_plan
    school.save(update_fields=["plan", "updated_at"])
    # Re-reconcile the subscription + entitlements against the new plan.
    _account, subscription, _ = ensure_subscription_for_school(school)
    sync_subscription_entitlements(subscription)

    label = new_plan.name if new_plan else "(no plan)"
    log_control_plane_action(
        request,
        AuditLog.Action.UPDATE,
        "billing.TenantSubscription.plan",
        str(school.pk),
        object_repr=f"{school.name} plan -> {label}",
        reason=_operator_reason(request, "Operator changed tenant plan"),
        sensitivity=AuditLog.Sensitivity.HIGH,
        old_values={"plan": getattr(old_plan, "slug", None)},
        new_values={"plan": getattr(new_plan, "slug", None)},
        changed_fields=["plan"],
    )
    messages.success(request, f"Plan changed to {label}.")


def _action_extend_trial(request, school, subscription):
    raw_date = (request.POST.get("trial_end_date") or "").strip()
    raw_days = (request.POST.get("extend_days") or "").strip()
    old = getattr(school, "trial_end_date", None)
    new_date = None

    if raw_date:
        new_date = parse_date(raw_date)
        if new_date is None:
            messages.error(request, "Invalid date. Use YYYY-MM-DD.")
            return
    elif raw_days:
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            messages.error(request, "Extension days must be a whole number.")
            return
        if days <= 0 or days > _MAX_TRIAL_EXTENSION_DAYS:
            messages.error(
                request, f"Extension must be 1-{_MAX_TRIAL_EXTENSION_DAYS} days."
            )
            return
        base = old or timezone.now().date()
        new_date = base + timedelta(days=days)
    else:
        messages.error(request, "Provide a trial end date or a number of days.")
        return

    school.trial_end_date = new_date
    school.save(update_fields=["trial_end_date", "updated_at"])
    if hasattr(subscription, "trial_end_date"):
        subscription.trial_end_date = new_date
        subscription.save(update_fields=["trial_end_date", "updated_at"])

    log_control_plane_action(
        request,
        AuditLog.Action.UPDATE,
        "schools.School.trial_end_date",
        str(school.pk),
        object_repr=f"{school.name} trial -> {new_date.isoformat()}",
        reason=_operator_reason(request, "Operator set trial end date"),
        sensitivity=AuditLog.Sensitivity.MEDIUM,
        old_values={"trial_end_date": old.isoformat() if old else None},
        new_values={"trial_end_date": new_date.isoformat()},
        changed_fields=["trial_end_date"],
    )
    messages.success(request, f"Trial end date set to {new_date.isoformat()}.")


def _action_set_status(request, school, subscription):
    new_status = (request.POST.get("status") or "").strip().upper()
    valid = {s.value for s in _OPERATOR_SETTABLE_STATUSES}
    if new_status not in valid:
        messages.error(request, "Invalid or non-settable status.")
        return
    old_status = subscription.status
    if old_status == new_status:
        messages.info(request, "Status unchanged.")
        return

    subscription.status = new_status
    subscription.save(update_fields=["status", "updated_at"])
    # Status drives whether entitlements are enabled (CANCELED/SUSPENDED disable).
    sync_subscription_entitlements(subscription)

    log_control_plane_action(
        request,
        AuditLog.Action.UPDATE,
        "billing.TenantSubscription.status",
        str(school.pk),
        object_repr=f"{school.name} status {old_status} -> {new_status}",
        reason=_operator_reason(request, "Operator changed subscription status"),
        sensitivity=AuditLog.Sensitivity.HIGH,
        old_values={"status": old_status},
        new_values={"status": new_status},
        changed_fields=["status"],
    )
    messages.success(request, f"Subscription status set to {new_status}.")


def _aware_start_of_day(value):
    dt = datetime.combine(value, time.min)
    return timezone.make_aware(dt, timezone.get_current_timezone())


def _aware_end_of_day(value):
    dt = datetime.combine(value, time.max)
    return timezone.make_aware(dt, timezone.get_current_timezone())


def _action_apply_waiver(request, school, subscription):
    raw_days = (request.POST.get("waiver_days") or "").strip()
    raw_end_date = (request.POST.get("waiver_end_date") or "").strip()
    indefinite = bool(request.POST.get("waiver_indefinite"))
    include_addons = bool(request.POST.get("include_addons"))
    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        messages.error(request, "Waiver reason is required for audit.")
        return

    days = None
    ends_at = None
    if indefinite:
        ends_at = None
    elif raw_end_date:
        end_date = parse_date(raw_end_date)
        if end_date is None:
            messages.error(request, "Invalid waiver end date. Use YYYY-MM-DD.")
            return
        ends_at = _aware_end_of_day(end_date)
    else:
        try:
            days = int(raw_days or "365")
        except (TypeError, ValueError):
            messages.error(request, "Waiver days must be a whole number.")
            return
        if days <= 0 or days > _MAX_WAIVER_DAYS:
            messages.error(request, f"Waiver must be 1-{_MAX_WAIVER_DAYS} days.")
            return

    starts_at = _aware_start_of_day(timezone.now().date())
    grant = apply_subscription_waiver(
        school,
        starts_at=starts_at,
        ends_at=ends_at,
        days=days,
        include_addons=include_addons,
        reason=reason,
        user=request.user,
    )

    log_control_plane_action(
        request,
        AuditLog.Action.CREATE,
        "billing.SubscriptionGrant",
        str(grant.pk),
        object_repr=f"{school.name} waiver {grant.pk}",
        reason=_operator_reason(request, "Operator applied subscription waiver"),
        sensitivity=AuditLog.Sensitivity.HIGH,
        old_values={},
        new_values={
            "grant_type": grant.grant_type,
            "percent_off": str(grant.percent_off),
            "starts_at": grant.starts_at.isoformat(),
            "ends_at": grant.ends_at.isoformat() if grant.ends_at else None,
            "include_addons": grant.include_addons,
        },
        changed_fields=["subscription_grant"],
    )
    end_label = grant.ends_at.date().isoformat() if grant.ends_at else "indefinite"
    messages.success(request, f"Subscription waiver applied through {end_label}.")
