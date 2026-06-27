"""Default rows for the Platform Email Matrix (v4.00.98 Phase 2).

These are the platform events that ship emails out of the box. Add new
rows here when wiring a new event into the matrix. Each event_type MUST
match the value used at the ``publish_event(event_type=...)`` callsite.
"""

from __future__ import annotations

import logging

from apps.platform_runtime.platform_email_matrix import (
    CLASSIFICATION_MARKETING,
    CLASSIFICATION_OPERATOR,
    CLASSIFICATION_TENANT_ADMIN,
    PRIORITY_BULK,
    PRIORITY_OPERATOR_ALERT,
    PRIORITY_TRANSACTIONAL,
    EmailMatrixRow,
    register_email_row,
    resolve_from_payload_to_field,
    resolve_operator_inbox,
    resolve_tenant_admin_from_payload,
)

logger = logging.getLogger(__name__)


def _register_default_email_rows() -> int:
    """Register every default matrix row. Returns the count registered.

    Idempotent — re-running overrides existing rows with the same
    event_type, so AppConfig.ready re-runs in tests are safe.
    """

    rows = (
        # ── Operator alerts ────────────────────────────────────────────────
        EmailMatrixRow(
            event_type="tenant.signup.created",
            classification=CLASSIFICATION_OPERATOR,
            subject_template="[RMC] New school signup: {{ school_name|default:'(unknown)' }}",
            body_template="emails/operator_tenant_signup_created.txt",
            html_template="emails/operator_tenant_signup_created.html",
            recipient_resolver=resolve_operator_inbox,
            priority=PRIORITY_OPERATOR_ALERT,
            cooldown_minutes=0,
            user_unsubscribable=False,
            description="Alert operators when a new school signs up. Always fires.",
        ),
        EmailMatrixRow(
            event_type="tenant.signup.verification_stale",
            classification=CLASSIFICATION_OPERATOR,
            subject_template="[RMC] Signup verification stale: {{ school_name|default:'(unknown)' }}",
            body_template="emails/operator_signup_verification_stale.txt",
            recipient_resolver=resolve_operator_inbox,
            priority=PRIORITY_OPERATOR_ALERT,
            cooldown_minutes=60 * 24,
            user_unsubscribable=False,
            description="Signup created 24h+ ago with no verification click.",
        ),
        EmailMatrixRow(
            event_type="tenant.signup.provisioning_failed",
            classification=CLASSIFICATION_OPERATOR,
            subject_template="[RMC] Signup provisioning failed: {{ school_name|default:'(unknown)' }}",
            body_template="emails/operator_signup_provisioning_failed.txt",
            recipient_resolver=resolve_operator_inbox,
            priority=PRIORITY_OPERATOR_ALERT,
            cooldown_minutes=30,
            user_unsubscribable=False,
            description="Provisioning failed after email verification — operator action required.",
        ),
        EmailMatrixRow(
            event_type="tenant.payment.failed",
            classification=CLASSIFICATION_OPERATOR,
            subject_template="[RMC] Payment failed for tenant {{ school_name|default:'(unknown)' }}",
            body_template="emails/operator_payment_failed.txt",
            recipient_resolver=resolve_operator_inbox,
            priority=PRIORITY_OPERATOR_ALERT,
            cooldown_minutes=60,
            user_unsubscribable=False,
        ),
        EmailMatrixRow(
            event_type="workflow.run.failed",
            classification=CLASSIFICATION_OPERATOR,
            subject_template="[RMC] Workflow failed: {{ workflow_label|default:workflow_key }}",
            body_template="emails/operator_workflow_failed.txt",
            recipient_resolver=resolve_operator_inbox,
            priority=PRIORITY_OPERATOR_ALERT,
            cooldown_minutes=15,
            user_unsubscribable=False,
            description="Workflow Progress Bus signaled a failed run with email_on_failure=True.",
        ),
        EmailMatrixRow(
            event_type="workflow.run.stuck",
            classification=CLASSIFICATION_OPERATOR,
            subject_template="[RMC] Workflow stuck: {{ workflow_label|default:workflow_key }}",
            body_template="emails/operator_workflow_stuck.txt",
            recipient_resolver=resolve_operator_inbox,
            priority=PRIORITY_OPERATOR_ALERT,
            cooldown_minutes=60,
            user_unsubscribable=False,
        ),
        EmailMatrixRow(
            event_type="workflow.sla.breached",
            classification=CLASSIFICATION_OPERATOR,
            subject_template="[RMC] Workflow SLA exceeded: {{ workflow_label|default:workflow_key }}",
            body_template="emails/operator_workflow_sla_breached.txt",
            recipient_resolver=resolve_operator_inbox,
            priority=PRIORITY_OPERATOR_ALERT,
            cooldown_minutes=30,
            user_unsubscribable=False,
            description="Workflow exceeded registry slo_seconds while running or on finalize.",
        ),
        # ── Tenant admin transactional ─────────────────────────────────────
        EmailMatrixRow(
            event_type="tenant.signup.verification_sent",
            classification=CLASSIFICATION_TENANT_ADMIN,
            subject_template="Verify your RunMyCampus signup",
            body_template="emails/tenant_admin_signup_verification.txt",
            html_template="emails/tenant_admin_signup_verification.html",
            recipient_resolver=resolve_tenant_admin_from_payload,
            priority=PRIORITY_TRANSACTIONAL,
            cooldown_minutes=10,
            user_unsubscribable=False,
            description="Transactional double-opt-in verification email.",
        ),
        EmailMatrixRow(
            event_type="tenant.signup.completed",
            classification=CLASSIFICATION_TENANT_ADMIN,
            subject_template="Welcome to RunMyCampus, {{ school_name|default:'your school' }}!",
            body_template="emails/tenant_admin_signup_completed.txt",
            html_template="emails/tenant_admin_signup_completed.html",
            recipient_resolver=resolve_tenant_admin_from_payload,
            priority=PRIORITY_TRANSACTIONAL,
            user_unsubscribable=False,
        ),
        EmailMatrixRow(
            event_type="tenant.subscription.expiring_soon",
            classification=CLASSIFICATION_TENANT_ADMIN,
            subject_template="Your RunMyCampus subscription expires {{ days_until }} day(s)",
            body_template="emails/tenant_admin_subscription_expiring.txt",
            recipient_resolver=resolve_tenant_admin_from_payload,
            priority=PRIORITY_TRANSACTIONAL,
            cooldown_minutes=60 * 24,
            user_unsubscribable=False,
        ),
        EmailMatrixRow(
            event_type="tenant.subscription.trial_ending",
            classification=CLASSIFICATION_TENANT_ADMIN,
            subject_template="Your RunMyCampus trial ends in {{ days_until }} day(s)",
            body_template="emails/tenant_admin_trial_ending.txt",
            recipient_resolver=resolve_tenant_admin_from_payload,
            priority=PRIORITY_TRANSACTIONAL,
            cooldown_minutes=60 * 24,
            user_unsubscribable=False,
        ),
        EmailMatrixRow(
            event_type="tenant.payment.failed",  # tenant side
            classification=CLASSIFICATION_TENANT_ADMIN,
            subject_template="Payment failed — please update your billing details",
            body_template="emails/tenant_admin_payment_failed.txt",
            recipient_resolver=resolve_tenant_admin_from_payload,
            priority=PRIORITY_TRANSACTIONAL,
            cooldown_minutes=60 * 2,
            user_unsubscribable=False,
        ),
        EmailMatrixRow(
            event_type="tenant.offboarding.confirmed",
            classification=CLASSIFICATION_TENANT_ADMIN,
            subject_template="Your RunMyCampus tenant has been offboarded",
            body_template="emails/tenant_admin_offboarded.txt",
            recipient_resolver=resolve_tenant_admin_from_payload,
            priority=PRIORITY_TRANSACTIONAL,
            user_unsubscribable=False,
        ),
        # Win-back / reactivation is MARKETING under CASL/GDPR (no longer
        # transactional). Classifying it as marketing routes it through the
        # matrix suppression gate centrally + makes it user-unsubscribable
        # (audit) — the reactivation engine's own opt-out pre-check stays as
        # defence in depth.
        EmailMatrixRow(
            event_type="tenant.reactivation.30d",
            classification=CLASSIFICATION_MARKETING,
            subject_template="We miss you at RunMyCampus",
            body_template="emails/tenant_reactivation_30d.txt",
            recipient_resolver=resolve_tenant_admin_from_payload,
            priority=PRIORITY_BULK,
            cooldown_minutes=60 * 24 * 30,
            user_unsubscribable=True,
        ),
        EmailMatrixRow(
            event_type="tenant.reactivation.60d",
            classification=CLASSIFICATION_MARKETING,
            subject_template="Your RunMyCampus account has been quiet",
            body_template="emails/tenant_reactivation_60d.txt",
            recipient_resolver=resolve_tenant_admin_from_payload,
            priority=PRIORITY_BULK,
            cooldown_minutes=60 * 24 * 30,
            user_unsubscribable=True,
        ),
        EmailMatrixRow(
            event_type="tenant.reactivation.90d",
            classification=CLASSIFICATION_MARKETING,
            subject_template="Coming back to RunMyCampus? Here's what's new.",
            body_template="emails/tenant_reactivation_90d.txt",
            recipient_resolver=resolve_tenant_admin_from_payload,
            priority=PRIORITY_BULK,
            cooldown_minutes=60 * 24 * 30,
            user_unsubscribable=True,
        ),
        EmailMatrixRow(
            event_type="tenant.reactivation.120d",
            classification=CLASSIFICATION_MARKETING,
            subject_template="Final reactivation reminder",
            body_template="emails/tenant_reactivation_120d.txt",
            recipient_resolver=resolve_tenant_admin_from_payload,
            priority=PRIORITY_BULK,
            cooldown_minutes=60 * 24 * 90,
            user_unsubscribable=True,
        ),
        # ── Marketing ──────────────────────────────────────────────────────
        EmailMatrixRow(
            event_type="newsletter.subscription.confirmed",
            classification=CLASSIFICATION_MARKETING,
            subject_template="Welcome to the RunMyCampus newsletter",
            body_template="emails/newsletter_confirmed.txt",
            html_template="emails/newsletter_confirmed.html",
            recipient_resolver=resolve_from_payload_to_field,
            priority=PRIORITY_BULK,
            user_unsubscribable=True,
        ),
        EmailMatrixRow(
            event_type="newsletter.subscription.verify",
            classification=CLASSIFICATION_MARKETING,
            subject_template="Confirm your RunMyCampus newsletter signup",
            body_template="emails/newsletter_verify.txt",
            html_template="emails/newsletter_verify.html",
            recipient_resolver=resolve_from_payload_to_field,
            priority=PRIORITY_TRANSACTIONAL,
            user_unsubscribable=False,
            description="Double-opt-in verification with timed token.",
        ),
    )

    for row in rows:
        register_email_row(row)

    return len(rows)
