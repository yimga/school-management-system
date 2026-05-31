"""Phase 3 smoke — NewsletterSubscription double-opt-in (v4.00.98).

Exercises the end-to-end newsletter flow:
* model + migration
* request_subscription() → pending + verification email fired
* invalid email rejected
* confirm_subscription() with valid token → confirmed
* confirm_subscription() replay (already confirmed) → idempotent
* confirm_subscription() with bad token → bad_token
* unsubscribe() → status=unsubscribed
* unsubscribe() replay → idempotent
* re-subscribe after unsubscribe → back to pending
* URLs resolvable
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.core import mail
from django.test.utils import override_settings

ASSERTIONS: list[tuple[str, bool, str]] = []


def expect(label: str, cond: bool, detail: str = "") -> None:
    ASSERTIONS.append((label, bool(cond), detail))


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def run():
    mail.outbox = []

    from django.urls import NoReverseMatch, reverse

    from apps.platform_runtime.models import (
        NewsletterSubscription,
        NewsletterSubscriptionStatus,
    )
    from apps.platform_runtime.newsletter_service import (
        _build_confirm_url,
        _build_unsubscribe_url,
        confirm_subscription,
        request_subscription,
        unsubscribe,
    )

    suffix = uuid.uuid4().hex[:8]

    # ── T1: Model basics ─────────────────────────────────────────────────
    expect(
        "T1.1 NewsletterSubscriptionStatus.PENDING exists",
        NewsletterSubscriptionStatus.PENDING == "pending",
    )

    # ── T2: request_subscription happy path ──────────────────────────────
    email = f"alice_{suffix}@example.com"
    pre = len(mail.outbox)
    result = request_subscription(
        email=email,
        source="smoke_phase3",
        ip="203.0.113.7",
        utm_source="smoke",
        utm_medium="cli",
        utm_campaign="phase3_validation",
    )
    expect("T2.1 request_subscription ok", result.get("ok") is True)
    expect("T2.2 created=True for new email", result.get("created") is True)
    expect("T2.3 status returned = pending", result.get("status") == "pending")
    row = NewsletterSubscription.objects.get(email=email)
    expect("T2.4 row persisted with PENDING", row.status == "pending")
    expect("T2.5 ip_hash is sha256[:16]", len(row.ip_hash) == 16)
    expect("T2.6 utm_source captured", row.utm_source == "smoke")
    expect("T2.7 verification email sent (outbox)", len(mail.outbox) > pre)
    if len(mail.outbox) > pre:
        last = mail.outbox[-1]
        expect("T2.8 verification subject contains 'Confirm'", "Confirm" in last.subject)
        expect("T2.9 verification body contains the confirm URL", "/newsletter/confirm/" in last.body)

    # ── T3: Invalid email rejected ───────────────────────────────────────
    r = request_subscription(email="not-an-email")
    expect("T3.1 invalid email rejected", r.get("ok") is False and r.get("reason") == "invalid_email")
    r2 = request_subscription(email="   ")
    expect("T3.2 blank email rejected", r2.get("ok") is False)

    # ── T4: Confirm happy path ───────────────────────────────────────────
    confirm_url = _build_confirm_url(email)
    token = confirm_url.rstrip("/").rsplit("/", 1)[-1]
    pre = len(mail.outbox)
    r = confirm_subscription(token)
    expect("T4.1 confirm ok", r.get("ok") is True)
    expect("T4.2 confirm.email matches", r.get("email") == email)
    row.refresh_from_db()
    expect("T4.3 status flipped to confirmed", row.status == "confirmed")
    expect("T4.4 confirmation_token cleared", row.confirmation_token == "")
    expect("T4.5 welcome email fired", len(mail.outbox) > pre)

    # ── T5: Confirm replay is idempotent ─────────────────────────────────
    r2 = confirm_subscription(token)
    expect("T5.1 replay ok", r2.get("ok") is True)
    expect("T5.2 already_confirmed flag set", r2.get("already_confirmed") is True)

    # ── T6: Confirm bad token ────────────────────────────────────────────
    r = confirm_subscription("bogus-token")
    expect("T6.1 bad_token reason", r.get("ok") is False and r.get("reason") == "bad_token")

    # ── T7: Unsubscribe ──────────────────────────────────────────────────
    unsub_url = _build_unsubscribe_url(email)
    unsub_token = unsub_url.rstrip("/").rsplit("/", 1)[-1]
    r = unsubscribe(unsub_token)
    expect("T7.1 unsubscribe ok", r.get("ok") is True)
    expect("T7.2 unsubscribe.email matches", r.get("email") == email)
    row.refresh_from_db()
    expect("T7.3 status = unsubscribed", row.status == "unsubscribed")
    expect("T7.4 unsubscribed_at set", row.unsubscribed_at is not None)

    # ── T8: Unsubscribe replay idempotent ────────────────────────────────
    r2 = unsubscribe(unsub_token)
    expect("T8.1 replay ok", r2.get("ok") is True)
    expect("T8.2 already_unsubscribed flag", r2.get("already_unsubscribed") is True)

    # ── T9: Re-subscribe after unsub → back to pending ───────────────────
    r = request_subscription(email=email, source="smoke_resub")
    expect("T9.1 resubscribe ok", r.get("ok") is True)
    expect("T9.2 created=False (existing row)", r.get("created") is False)
    expect("T9.3 status = pending", r.get("status") == "pending")
    row.refresh_from_db()
    expect("T9.4 row status flipped back to pending", row.status == "pending")
    expect("T9.5 unsubscribed_at cleared", row.unsubscribed_at is None)

    # ── T10: URL routes resolvable ───────────────────────────────────────
    for name, kwargs in (
        ("newsletter_subscribe", {}),
        ("newsletter_confirm", {"token": "fake"}),
        ("newsletter_unsubscribe", {"token": "fake"}),
    ):
        try:
            reverse(f"platform_runtime:{name}", kwargs=kwargs)
            expect(f"T10 reverse {name}", True)
        except NoReverseMatch as e:
            expect(f"T10 reverse {name}", False, str(e))


run()

passed = sum(1 for _, ok, _ in ASSERTIONS if ok)
failed = sum(1 for _, ok, _ in ASSERTIONS if not ok)
total = len(ASSERTIONS)

print(f"\n=== Phase 3 Newsletter smoke ({total} assertions) ===\n")
for label, ok, detail in ASSERTIONS:
    mark = "PASS" if ok else "FAIL"
    extra = f" -- {detail}" if detail and not ok else ""
    print(f"  [{mark}] {label}{extra}")
print(f"\n{passed}/{total} passed, {failed} failed.")
sys.exit(0 if failed == 0 else 1)
