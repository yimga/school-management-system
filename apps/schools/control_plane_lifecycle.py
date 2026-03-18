from __future__ import annotations

from datetime import date

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.billing.models import BillingAccount, TenantSubscription
from apps.billing.services import (
    ensure_billing_account_for_school,
    ensure_subscription_for_school,
    reconcile_subscription_entitlements,
    sync_billing_incident_state,
)


def get_current_subscription(school):
    if school is None:
        return None
    return (
        TenantSubscription.objects.select_related("billing_account", "plan")
        .filter(school=school)
        .order_by("-updated_at", "-created_at")
        .first()
    )


def get_lifecycle_snapshot(school) -> dict:
    subscription = get_current_subscription(school)
    billing_account = getattr(subscription, "billing_account", None)
    if billing_account is None:
        try:
            billing_account = school.billing_account
        except (AttributeError, ObjectDoesNotExist):
            billing_account = None

    state = "inactive"
    tone = "muted"
    if getattr(school, "is_frozen", False):
        state = "frozen"
        tone = "danger"
    elif not getattr(school, "is_active", False):
        state = "inactive"
        tone = "muted"
    elif not getattr(school, "is_approved", True):
        state = "pending_approval"
        tone = "warning"
    elif getattr(school, "billing_type", "") == getattr(
        school.BillingType, "FREE_TRIAL", "FREE_TRIAL"
    ):
        state = "trialing"
        tone = "warning"
    elif subscription and getattr(subscription, "status", "") in {
        TenantSubscription.Status.PAST_DUE,
        TenantSubscription.Status.SUSPENDED,
    }:
        state = "billing_exception"
        tone = "danger"
    else:
        state = "active"
        tone = "success"

    available_actions: list[str] = []
    if not getattr(school, "is_approved", True):
        available_actions.append("approve")
    available_actions.append(
        "deactivate" if getattr(school, "is_active", False) else "activate"
    )
    available_actions.append(
        "unfreeze" if getattr(school, "is_frozen", False) else "freeze"
    )

    if getattr(school, "billing_type", "") == getattr(
        school.BillingType, "FREE_TRIAL", "FREE_TRIAL"
    ):
        available_actions.append("clear_trial")

    return {
        "state": state,
        "state_label": state.replace("_", " ").title(),
        "tone": tone,
        "is_active": bool(getattr(school, "is_active", False)),
        "is_approved": bool(getattr(school, "is_approved", False)),
        "is_frozen": bool(getattr(school, "is_frozen", False)),
        "frozen_reason": getattr(school, "frozen_reason", "") or "",
        "billing_type": getattr(school, "billing_type", "") or "",
        "trial_end_date": getattr(school, "trial_end_date", None),
        "subscription_status": getattr(subscription, "status", "") or "",
        "billing_account_status": getattr(billing_account, "status", "") or "",
        "available_actions": available_actions,
    }


def _normalized_action(action: str) -> str:
    a = str(action or "").strip().lower().replace("-", "_")
    if a == "suspend":
        return "freeze"  # Suspend is alias for freeze (TENANT_LIFECYCLE.md)
    return a


def _target_subscription_status_for_school(school) -> str:
    if getattr(school, "billing_type", "") == getattr(
        school.BillingType, "FREE_TRIAL", "FREE_TRIAL"
    ):
        return TenantSubscription.Status.TRIALING
    if getattr(school, "is_frozen", False):
        return TenantSubscription.Status.SUSPENDED
    return TenantSubscription.Status.ACTIVE


def _coerce_trial_end_date(raw_value) -> date:
    if isinstance(raw_value, date):
        return raw_value
    parsed = str(raw_value or "").strip()
    if not parsed:
        raise ValueError("trial_end_date is required.")
    try:
        return date.fromisoformat(parsed)
    except ValueError as exc:
        raise ValueError("trial_end_date must use YYYY-MM-DD.") from exc


@transaction.atomic
def apply_school_lifecycle_action(
    school, *, action: str, reason: str = "", trial_end_date=None
) -> dict:
    action = _normalized_action(action)
    if not action:
        raise ValueError("action is required.")

    old_values = get_lifecycle_snapshot(school)
    changed_fields: list[str] = []

    if action == "approve":
        if not school.is_approved:
            school.is_approved = True
            changed_fields.append("is_approved")
        message = "School approved."
    elif action == "unapprove":
        if school.is_approved:
            school.is_approved = False
            changed_fields.append("is_approved")
        message = "School moved back to pending approval."
    elif action == "activate":
        if not school.is_active:
            school.is_active = True
            changed_fields.append("is_active")
        message = "School activated."
    elif action == "deactivate":
        if school.is_active:
            school.is_active = False
            changed_fields.append("is_active")
        message = "School deactivated."
    elif action == "freeze":
        normalized_reason = str(reason or "").strip().upper() or "STORAGE"
        if normalized_reason not in {"STORAGE", "BILLING"}:
            raise ValueError("freeze reason must be STORAGE or BILLING.")
        if not school.is_frozen:
            school.is_frozen = True
            changed_fields.append("is_frozen")
        if school.frozen_reason != normalized_reason:
            school.frozen_reason = normalized_reason
            changed_fields.append("frozen_reason")
        message = f"School frozen ({normalized_reason.lower()})."
    elif action == "unfreeze":
        if school.frozen_reason == "BILLING":
            subscription = get_current_subscription(school)
            if (
                subscription
                and subscription.status == TenantSubscription.Status.SUSPENDED
            ):
                raise ValueError(
                    "Billing suspension must be cleared from the subscription before unfreezing the tenant."
                )
        if school.is_frozen:
            school.is_frozen = False
            changed_fields.append("is_frozen")
        if school.frozen_reason:
            school.frozen_reason = ""
            changed_fields.append("frozen_reason")
        message = "School unfrozen."
    elif action == "set_trial_end":
        target_date = _coerce_trial_end_date(trial_end_date)
        if getattr(school, "billing_type", "") != getattr(
            school.BillingType, "FREE_TRIAL", "FREE_TRIAL"
        ):
            school.billing_type = school.BillingType.FREE_TRIAL
            changed_fields.append("billing_type")
        if school.trial_end_date != target_date:
            school.trial_end_date = target_date
            changed_fields.append("trial_end_date")
        message = "Trial end date updated."
    elif action == "clear_trial":
        target_billing_type = getattr(school.BillingType, "REGULAR", "REGULAR")
        if getattr(school, "billing_type", "") != target_billing_type:
            school.billing_type = target_billing_type
            changed_fields.append("billing_type")
        if school.trial_end_date is not None:
            school.trial_end_date = None
            changed_fields.append("trial_end_date")
        message = "Trial cleared."
    else:
        raise ValueError(f"Unsupported lifecycle action: {action}")

    if changed_fields:
        school.save(update_fields=changed_fields + ["updated_at"])

    if action in {"freeze", "unfreeze", "set_trial_end", "clear_trial"}:
        account, subscription, _ = ensure_subscription_for_school(school)
        desired_subscription_status = _target_subscription_status_for_school(school)
        subscription_changed: list[str] = []
        if subscription.status != desired_subscription_status:
            subscription.status = desired_subscription_status
            subscription_changed.append("status")
        if subscription.trial_end_date != getattr(school, "trial_end_date", None):
            subscription.trial_end_date = getattr(school, "trial_end_date", None)
            subscription_changed.append("trial_end_date")
        desired_account_status = (
            BillingAccount.Status.TRIAL
            if desired_subscription_status == TenantSubscription.Status.TRIALING
            else BillingAccount.Status.SUSPENDED
            if desired_subscription_status == TenantSubscription.Status.SUSPENDED
            else BillingAccount.Status.ACTIVE
        )
        account_changed: list[str] = []
        if account.status != desired_account_status:
            account.status = desired_account_status
            account_changed.append("status")
        if account_changed:
            account.save(update_fields=account_changed + ["updated_at"])
        if subscription_changed:
            subscription.save(update_fields=subscription_changed + ["updated_at"])
        reconcile_subscription_entitlements(subscription)
        sync_billing_incident_state(subscription)
    elif action in {"activate", "deactivate"}:
        ensure_billing_account_for_school(school)

    school.refresh_from_db()
    return {
        "message": message,
        "changed_fields": changed_fields,
        "old_values": old_values,
        "new_values": get_lifecycle_snapshot(school),
    }
