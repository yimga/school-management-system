"""Phase 5 smoke — platform events wired to publish_event (v4.00.98).

Exercises:
* EVENT_CATALOG contains all 15 platform email events
* publish_event(tenant.signup.created, ...) flows through subscriber and
  fires an email
* publish_event(tenant.signup.completed, ...) fires a tenant welcome
* publish_event(workflow.run.failed, ...) fires operator alert
* signup_verification_stale_sweep_task name + beat entry registered
* Catalog publish for unknown event still rejects (strict_catalog=True)
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

import logging as _logging
for _name in ("django.db.backends", "django.db", "django.security", "celery"):
    _logging.getLogger(_name).setLevel(_logging.WARNING)

from django.conf import settings
from django.core import mail
from django.test.utils import override_settings

ASSERTIONS: list[tuple[str, bool, str]] = []


def expect(label: str, cond: bool, detail: str = "") -> None:
    ASSERTIONS.append((label, bool(cond), detail))


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    RMC_OPERATOR_ALERT_EMAIL="ops@runmycampus.test",
)
def run():
    mail.outbox = []
    _run = uuid.uuid4().hex[:10]

    # ── T1: EVENT_CATALOG contains all 15 platform email events ───────────
    from apps.platform_runtime.events import EVENT_CATALOG

    expected_events = (
        "tenant.signup.created",
        "tenant.signup.verification_sent",
        "tenant.signup.verification_stale",
        "tenant.signup.completed",
        "tenant.offboarding.confirmed",
        "tenant.payment.failed",
        "tenant.subscription.expiring_soon",
        "tenant.reactivation.30d",
        "tenant.reactivation.60d",
        "tenant.reactivation.90d",
        "tenant.reactivation.120d",
        "workflow.run.failed",
        "workflow.run.stuck",
        "newsletter.subscription.verify",
        "newsletter.subscription.confirmed",
    )
    for ev in expected_events:
        expect(f"T1 catalog has {ev}", ev in EVENT_CATALOG)

    # ── T2: publish_event(tenant.signup.created) flows through matrix ─────
    from apps.platform_runtime.event_bus import publish_event

    pre = len(mail.outbox)
    try:
        publish_event(
            "tenant.signup.created",
            {
                "school_id": f"smoke_{_run}",
                "school_name": "Smoke Phase 5 Academy",
                "country_code": "US",
                "subdomain": f"smoke-{_run}",
                "admin_email": f"owner_{_run}@phase5.test",
            },
            school_id=f"smoke_{_run}",
            strict_catalog=True,
            source="smoke_phase5",
        )
        expect("T2.1 publish_event tenant.signup.created OK", True)
    except Exception as exc:
        expect("T2.1 publish_event tenant.signup.created OK", False, f"{type(exc).__name__}: {exc}")
    expect("T2.2 outbox grew after operator-alert event",
           len(mail.outbox) > pre,
           f"pre={pre} post={len(mail.outbox)}")
    if len(mail.outbox) > pre:
        sub = mail.outbox[-1].subject
        expect("T2.3 operator alert subject contains school name",
               "Smoke Phase 5 Academy" in sub)

    # ── T3: publish_event(tenant.signup.completed) → tenant welcome ────────
    pre = len(mail.outbox)
    publish_event(
        "tenant.signup.completed",
        {
            "school_id": f"smoke_{_run}",
            "school_name": "Smoke Phase 5 Academy",
            "admin_email": f"owner_complete_{_run}@phase5.test",
            "portal_url": "https://manager.runmycampus.com/",
        },
        school_id=f"smoke_{_run}",
        strict_catalog=True,
        source="smoke_phase5",
    )
    expect("T3.1 publish completed grew outbox", len(mail.outbox) > pre)

    # ── T4: publish_event(workflow.run.failed) → operator alert ───────────
    pre = len(mail.outbox)
    publish_event(
        "workflow.run.failed",
        {
            "run_id": 9999,
            "workflow_key": "smoke_workflow",
            "workflow_label": "Smoke Workflow",
            "error_type": "RuntimeError",
            "error_message": "synthetic",
            "tenant_schema": "smoke",
        },
        strict_catalog=True,
        source="smoke_phase5",
    )
    expect("T4.1 publish workflow.run.failed grew outbox", len(mail.outbox) > pre)

    # ── T5: Celery task registered + beat entry present ───────────────────
    from apps.platform_runtime.tasks import signup_verification_stale_sweep_task

    expect("T5.1 stale sweep task importable", signup_verification_stale_sweep_task is not None)
    expect("T5.2 stale sweep task name correct",
           getattr(signup_verification_stale_sweep_task, "name", "")
           == "platform_runtime.signup_verification_stale_sweep")
    sched = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
    expect("T5.3 beat entry registered",
           "platform-runtime-signup-verification-stale" in sched)

    # ── T6: strict_catalog=True still rejects unknown events ──────────────
    # The platform behavior is "soft reject": persist_platform_event returns
    # None when require_catalog=True and the event_type isn't in the catalog.
    # The wrapper publish_event surfaces that as a None return.
    result = publish_event(
        "never.fired.event_smoke",
        {"x": 1},
        strict_catalog=True,
    )
    expect("T6.1 strict_catalog returns None for unknown", result is None)


run()

passed = sum(1 for _, ok, _ in ASSERTIONS if ok)
failed = sum(1 for _, ok, _ in ASSERTIONS if not ok)
total = len(ASSERTIONS)

print(f"\n=== Phase 5 Platform-event wiring smoke ({total} assertions) ===\n")
for label, ok, detail in ASSERTIONS:
    mark = "PASS" if ok else "FAIL"
    extra = f" -- {detail}" if detail and not ok else ""
    print(f"  [{mark}] {label}{extra}")
print(f"\n{passed}/{total} passed, {failed} failed.")
sys.exit(0 if failed == 0 else 1)
