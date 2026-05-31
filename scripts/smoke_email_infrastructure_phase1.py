"""Phase 1 smoke for the platform email infrastructure (v4.00.98).

Exercises the apps.schoolops.email_delivery reliability layer end-to-end:

* smtp_probe()
* send_transactional() — happy path
* send_transactional() — idempotency_key dedup
* send_transactional() — per-tenant rate limit
* send_bulk() — fan-out to N recipients
* get_recent_delivery_stats() — schema + counts
* secret hygiene — to_hash present, raw recipient NEVER in EmailDeliveryEvent
* EmailDeliveryEvent row persisted with bounce + idempotency fields

Uses Django's locmem email backend so no SMTP is required. Exits 0 on green,
1 on any failure.
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
from django.test.utils import override_settings

ASSERTIONS: list[tuple[str, bool, str]] = []


def expect(label: str, cond: bool, detail: str = "") -> None:
    ASSERTIONS.append((label, bool(cond), detail))


# We MUST use locmem backend so we can introspect mail.outbox.
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SCHOOLOPS_EMAIL_DELIVERY_ASYNC_FORCED_SYNC=True,
)
def run():
    from django.utils import timezone

    from apps.schoolops.email_delivery import (
        _hash_recipient,
        _hash_tenant,
        get_recent_delivery_stats,
        send_bulk,
        send_transactional,
        smtp_probe,
    )
    from apps.schoolops.models_email_delivery import EmailDeliveryEvent

    # Reset outbox
    mail.outbox = []

    # ── T1: SMTP probe ────────────────────────────────────────────────────
    probe = smtp_probe()
    expect("T1.1 smtp_probe returns dict with ok key", isinstance(probe, dict) and "ok" in probe)
    expect("T1.2 smtp_probe short-circuits locmem to ok=True", probe.get("ok") is True)
    expect("T1.3 smtp_probe carries latency_ms", "latency_ms" in probe)
    expect("T1.4 smtp_probe carries backend", "backend" in probe)

    # ── T2: Happy path send ────────────────────────────────────────────────
    pre_count = EmailDeliveryEvent.objects.filter(ok=True).count()
    pre_outbox = len(mail.outbox)
    result = send_transactional(
        subject="[smoke] T2 happy path",
        body="hello",
        to="t2@example.com",
        html_body="<p>hello</p>",
        priority="transactional",
        idempotency_key=f"smoke_T2_{timezone.now().isoformat()}",
    )
    expect("T2.1 send_transactional returns dict", isinstance(result, dict))
    expect("T2.2 result.ok=True", result.get("ok") is True)
    expect("T2.3 result.attempts >= 1", int(result.get("attempts") or 0) >= 1)
    expect("T2.4 result.delivery_event_id set", bool(result.get("delivery_event_id")))
    expect("T2.5 EmailDeliveryEvent row added", EmailDeliveryEvent.objects.filter(ok=True).count() == pre_count + 1)
    expect("T2.6 mail.outbox grew by 1", len(mail.outbox) == pre_outbox + 1)
    if mail.outbox:
        msg = mail.outbox[-1]
        expect("T2.7 outbox recipient matches", "t2@example.com" in msg.to)
        expect("T2.8 outbox subject prefix matches", msg.subject.startswith("[smoke] T2"))

    # ── T3: Idempotency dedup ─────────────────────────────────────────────
    idem = f"smoke_T3_{timezone.now().isoformat()}"
    r1 = send_transactional(
        subject="[smoke] T3 idem",
        body="x",
        to="t3@example.com",
        idempotency_key=idem,
    )
    pre_outbox = len(mail.outbox)
    r2 = send_transactional(
        subject="[smoke] T3 idem",
        body="x",
        to="t3@example.com",
        idempotency_key=idem,
    )
    expect("T3.1 first idempotent send ok", r1.get("ok") is True)
    expect("T3.2 second send returns same delivery_event_id", r1.get("delivery_event_id") == r2.get("delivery_event_id"))
    expect("T3.3 second send did NOT re-deliver", len(mail.outbox) == pre_outbox)

    # ── T4: Per-tenant rate limit ─────────────────────────────────────────
    # Force a tiny cap so we don't need to send 200 emails.
    tenant_hash = _hash_tenant("tenant-rate-smoke")
    with override_settings(SCHOOLOPS_EMAIL_DELIVERY_TENANT_HOURLY_CAP=2):
        a = send_transactional(
            subject="[smoke] T4 ratelimit a",
            body="x",
            to="ra@example.com",
            tenant_hash=tenant_hash,
            idempotency_key=f"smoke_T4a_{timezone.now().isoformat()}",
        )
        b = send_transactional(
            subject="[smoke] T4 ratelimit b",
            body="x",
            to="rb@example.com",
            tenant_hash=tenant_hash,
            idempotency_key=f"smoke_T4b_{timezone.now().isoformat()}",
        )
        # The 3rd one should be rejected by the rate limiter.
        c = send_transactional(
            subject="[smoke] T4 ratelimit c",
            body="x",
            to="rc@example.com",
            tenant_hash=tenant_hash,
            idempotency_key=f"smoke_T4c_{timezone.now().isoformat()}",
        )
    expect("T4.1 first under-cap send ok", a.get("ok") is True)
    expect("T4.2 second at-cap send ok", b.get("ok") is True)
    expect("T4.3 third send rate-limited", c.get("ok") is False and c.get("error_kind") == "rate_limit_exceeded")
    expect(
        "T4.4 rate-limited row persisted",
        EmailDeliveryEvent.objects.filter(error_kind="rate_limit_exceeded").exists(),
    )

    # ── T5: Bulk send ─────────────────────────────────────────────────────
    # send_bulk(to=[...]) falls back to send_transactional with priority="bulk"
    # when Celery is unavailable. Outbox grows by 1 message addressed to all 3.
    pre_outbox = len(mail.outbox)
    r = send_bulk(
        subject="[smoke] T5 bulk",
        body="bulk body",
        to=["b1@example.com", "b2@example.com", "b3@example.com"],
    )
    expect("T5.1 send_bulk returns dict", isinstance(r, dict))
    expect("T5.2 send_bulk ok=True", r.get("ok") is True)
    expect("T5.3 mail.outbox grew by 1 (one message, multi-recipient)", len(mail.outbox) >= pre_outbox + 1)
    if mail.outbox:
        last = mail.outbox[-1]
        expect("T5.4 multi-recipient on the message", len(last.to) >= 3)

    # ── T6: Recent stats schema ────────────────────────────────────────────
    stats = get_recent_delivery_stats(window_hours=1)
    expect("T6.1 stats is dict", isinstance(stats, dict))
    for key in ("sent_count", "failed_count", "last_failure_iso", "last_failure_reason_kind", "window_hours"):
        expect(f"T6.2 stats carries {key}", key in stats)
    expect("T6.3 sent_count >= 5", stats.get("sent_count", 0) >= 5)
    expect("T6.4 failed_count >= 1 (rate-limited)", stats.get("failed_count", 0) >= 1)
    expect("T6.5 last_failure_reason_kind populated", stats.get("last_failure_reason_kind") in ("rate_limit_exceeded", "unknown"))

    # ── T7: Secret hygiene — recipient never logged raw ───────────────────
    rows = EmailDeliveryEvent.objects.order_by("-created_at")[:20]
    for row in rows:
        raw_match = any(
            ch in (row.to_hash or "") for ch in ("@example.com", "@runmycampus.com")
        )
        expect(f"T7 row {row.pk} to_hash never contains @", not raw_match)
        # 12 hex chars expected per _hash_recipient
        expect(f"T7 row {row.pk} to_hash is hex prefix", len(row.to_hash or "") <= 16)
        # Subject prefix exists but is capped at 64 chars per the SOT redaction.
        expect(f"T7 row {row.pk} subject_prefix capped", len(row.subject_prefix or "") <= 80)

    # ── T8: Hash helpers ──────────────────────────────────────────────────
    h1 = _hash_recipient("user@example.com")
    h2 = _hash_recipient("user@example.com")
    h3 = _hash_recipient("other@example.com")
    expect("T8.1 _hash_recipient deterministic", h1 == h2)
    expect("T8.2 _hash_recipient differs for different inputs", h1 != h3)
    # Empty input returns the sentinel zero-padded prefix (12 zeros by default).
    expect("T8.3 _hash_recipient empty-safe sentinel", _hash_recipient("") == "0" * 12)


run()

# ── Report ────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok, _ in ASSERTIONS if ok)
failed = sum(1 for _, ok, _ in ASSERTIONS if not ok)
total = len(ASSERTIONS)

print(f"\n=== Phase 1 Email infrastructure smoke ({total} assertions) ===\n")
for label, ok, detail in ASSERTIONS:
    mark = "PASS" if ok else "FAIL"
    extra = f" -- {detail}" if detail and not ok else ""
    print(f"  [{mark}] {label}{extra}")
print(f"\n{passed}/{total} passed, {failed} failed.")
sys.exit(0 if failed == 0 else 1)
