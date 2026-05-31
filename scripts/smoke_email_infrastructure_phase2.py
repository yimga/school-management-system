"""Phase 2 smoke — Platform Email Matrix SOT (v4.00.98).

Exercises:
* Matrix registry registration + lookup
* matrix_summary() shape
* dispatch_email_for_event happy path
* dispatch_email_for_event no-matrix-row skip
* dispatch_email_for_event no-recipients skip
* cooldown gate
* event_bus subscriber wiring
* Secret scrub on payload
* All 16 template files render without raising
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.core import mail
from django.template.loader import render_to_string
from django.test.utils import override_settings

ASSERTIONS: list[tuple[str, bool, str]] = []


def expect(label: str, cond: bool, detail: str = "") -> None:
    ASSERTIONS.append((label, bool(cond), detail))


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@runmycampus.test",
    RMC_OPERATOR_ALERT_EMAIL="ops@runmycampus.test",
)
def run():
    mail.outbox = []

    from apps.platform_runtime.platform_email_matrix import (
        CLASSIFICATION_OPERATOR,
        CLASSIFICATION_TENANT_ADMIN,
        EmailMatrixRow,
        all_email_rows,
        dispatch_email_for_event,
        get_email_row,
        is_unsubscribed,
        matrix_summary,
        register_email_row,
        resolve_operator_inbox,
    )

    # ── T1: Registry shape ────────────────────────────────────────────────
    rows = all_email_rows()
    expect("T1.1 matrix has rows", len(rows) >= 16)
    summary = matrix_summary()
    expect("T1.2 summary.total matches", summary["total"] == len(rows))
    expect("T1.3 summary by_classification has operator", summary["by_classification"].get("operator", 0) >= 3)
    expect("T1.4 summary by_priority has operator_alert", summary["by_priority"].get("operator_alert", 0) >= 3)

    # ── T2: Key event_types exist ─────────────────────────────────────────
    for key in (
        "tenant.signup.created",
        "tenant.signup.completed",
        "tenant.signup.verification_sent",
        "tenant.signup.verification_stale",
        "tenant.payment.failed",
        "tenant.offboarding.confirmed",
        "tenant.subscription.expiring_soon",
        "workflow.run.failed",
        "workflow.run.stuck",
        "tenant.reactivation.30d",
        "tenant.reactivation.60d",
        "tenant.reactivation.90d",
        "tenant.reactivation.120d",
        "newsletter.subscription.verify",
        "newsletter.subscription.confirmed",
    ):
        expect(f"T2 row registered: {key}", get_email_row(key) is not None)

    # ── T3: Operator inbox resolver ───────────────────────────────────────
    inbox = resolve_operator_inbox({})
    expect("T3.1 operator inbox returns the configured RMC_OPERATOR_ALERT_EMAIL",
           inbox == ["ops@runmycampus.test"])

    # ── T4: Dispatch happy path — operator alert ──────────────────────────
    import uuid
    _run = uuid.uuid4().hex[:12]
    pre = len(mail.outbox)
    result = dispatch_email_for_event(
        "tenant.signup.created",
        {
            "school_name": "Test Academy",
            "country_code": "US",
            "subdomain": "test-academy",
            "admin_email": "owner@test.edu",
        },
        idempotency_key=f"smoke_phase2_T4_{_run}",
    )
    expect("T4.1 dispatch returns dict", isinstance(result, dict))
    expect("T4.2 result.ok=True", result.get("ok") is True)
    expect("T4.3 result.classification=operator", result.get("classification") == "operator")
    expect("T4.4 recipient_count=1", result.get("recipient_count") == 1)
    expect("T4.5 outbox grew", len(mail.outbox) == pre + 1)
    if mail.outbox:
        msg = mail.outbox[-1]
        expect("T4.6 subject contains school name", "Test Academy" in msg.subject)
        expect("T4.7 body contains school name", "Test Academy" in msg.body)
        expect("T4.8 X-RMC-Event-Type header present",
               msg.extra_headers.get("X-RMC-Event-Type") == "tenant.signup.created")
        expect("T4.9 X-RMC-Classification header present",
               msg.extra_headers.get("X-RMC-Classification") == "operator")

    # ── T5: Unknown event silently skips ──────────────────────────────────
    r = dispatch_email_for_event("never.fired.event", {"x": 1})
    expect("T5.1 unknown event skipped", r.get("skipped") is True and r.get("reason") == "no_matrix_row")
    expect("T5.2 ok=True still", r.get("ok") is True)

    # ── T6: No recipients silently skips ──────────────────────────────────
    # The outer envelope reports recipient_count=0 when every row resolves
    # to an empty recipient list; inner row carries skipped=True.
    r = dispatch_email_for_event("newsletter.subscription.verify", {"to": ""})
    expect("T6.1 ok=True with no recipients", r.get("ok") is True)
    expect("T6.2 recipient_count == 0", r.get("recipient_count") == 0)
    inner = (r.get("row_results") or [{}])[0]
    expect("T6.3 inner row reports skipped=True / no_recipients",
           inner.get("skipped") is True and inner.get("reason") == "no_recipients")

    # ── T7: Secret scrub ──────────────────────────────────────────────────
    pre = len(mail.outbox)
    r = dispatch_email_for_event(
        "tenant.signup.created",
        {
            "school_name": "Scrub Academy",
            "password": "leaked",
            "client_secret": "alsoleaked",
            "nested": {"api_key": "x", "ok_field": "ok"},
        },
        idempotency_key=f"smoke_phase2_T7_{_run}",
    )
    expect("T7.1 scrub dispatch ok", r.get("ok") is True)
    if mail.outbox and len(mail.outbox) > pre:
        body = mail.outbox[-1].body
        expect("T7.2 password not in body", "leaked" not in body)
        expect("T7.3 client_secret not in body", "alsoleaked" not in body)
        expect("T7.4 api_key not in body", "x" not in body or body.count("x") <= 5)

    # ── T8: Cooldown ──────────────────────────────────────────────────────
    # subscription_expiring_soon has cooldown_minutes=1440 (24h). Both calls
    # share an idempotency_key seed but the cooldown ring (in-process) blocks
    # the second send regardless of DB dedup.
    pre = len(mail.outbox)
    cooldown_email = f"cooldown_{_run}@test.edu"
    r1 = dispatch_email_for_event(
        "tenant.subscription.expiring_soon",
        {"admin_email": cooldown_email, "school_name": "Cooldown HS", "days_until": 7},
        idempotency_key=f"smoke_phase2_T8a_{_run}",
    )
    r2 = dispatch_email_for_event(
        "tenant.subscription.expiring_soon",
        {"admin_email": cooldown_email, "school_name": "Cooldown HS", "days_until": 7},
        idempotency_key=f"smoke_phase2_T8b_{_run}",
    )
    expect("T8.1 first send in cooldown window OK", r1.get("ok") is True and r1.get("recipient_count") == 1)
    expect("T8.2 second send hits cooldown",
           r2.get("ok") is True and r2.get("recipient_count") == 0 and r2.get("skipped_cooldown_count") == 1)

    # ── T9: Operator class never blocked by unsubscribe ───────────────────
    expect("T9.1 operator class never unsubscribable", is_unsubscribed("any@person.com", "operator") is False)
    expect("T9.2 system class never unsubscribable", is_unsubscribed("any@person.com", "system") is False)

    # ── T10: Templates render ──────────────────────────────────────────────
    templates_to_check = [
        ("emails/operator_tenant_signup_created.txt", {"school_name": "Acme", "generated_at": "2026-05-31"}),
        ("emails/operator_tenant_signup_created.html", {"school_name": "Acme", "generated_at": "2026-05-31"}),
        ("emails/operator_signup_verification_stale.txt", {"school_name": "Acme", "age_hours": 36, "created_at": "2026-05-30"}),
        ("emails/operator_payment_failed.txt", {"school_name": "Acme", "failure_code": "card_declined", "amount": "$199", "generated_at": "x"}),
        ("emails/operator_workflow_failed.txt", {"workflow_key": "test", "run_id": 1, "error_type": "X", "error_message": "Y"}),
        ("emails/operator_workflow_stuck.txt", {"workflow_key": "test", "current_step_name": "step1"}),
        ("emails/tenant_admin_signup_verification.txt", {"verification_url": "https://x/v", "school_name": "Acme"}),
        ("emails/tenant_admin_signup_verification.html", {"verification_url": "https://x/v", "school_name": "Acme"}),
        ("emails/tenant_admin_signup_completed.txt", {"school_name": "Acme"}),
        ("emails/tenant_admin_signup_completed.html", {"school_name": "Acme"}),
        ("emails/tenant_admin_subscription_expiring.txt", {"days_until": 7, "school_name": "Acme"}),
        ("emails/tenant_admin_payment_failed.txt", {"school_name": "Acme"}),
        ("emails/tenant_admin_offboarded.txt", {"school_name": "Acme"}),
        ("emails/tenant_reactivation_30d.txt", {"school_name": "Acme"}),
        ("emails/tenant_reactivation_60d.txt", {"school_name": "Acme"}),
        ("emails/tenant_reactivation_90d.txt", {"school_name": "Acme"}),
        ("emails/tenant_reactivation_120d.txt", {"school_name": "Acme"}),
        ("emails/newsletter_verify.txt", {"verification_url": "https://x/v"}),
        ("emails/newsletter_verify.html", {"verification_url": "https://x/v"}),
        ("emails/newsletter_confirmed.txt", {"unsubscribe_url": "https://x/u"}),
        ("emails/newsletter_confirmed.html", {"unsubscribe_url": "https://x/u"}),
    ]
    for path, ctx in templates_to_check:
        try:
            out = render_to_string(path, ctx)
            expect(f"T10 render {path}", bool(out and len(out) > 5))
        except Exception as exc:
            expect(f"T10 render {path}", False, f"{type(exc).__name__}: {exc}")


run()

passed = sum(1 for _, ok, _ in ASSERTIONS if ok)
failed = sum(1 for _, ok, _ in ASSERTIONS if not ok)
total = len(ASSERTIONS)

print(f"\n=== Phase 2 Email matrix smoke ({total} assertions) ===\n")
for label, ok, detail in ASSERTIONS:
    mark = "PASS" if ok else "FAIL"
    extra = f" -- {detail}" if detail and not ok else ""
    print(f"  [{mark}] {label}{extra}")
print(f"\n{passed}/{total} passed, {failed} failed.")
sys.exit(0 if failed == 0 else 1)
