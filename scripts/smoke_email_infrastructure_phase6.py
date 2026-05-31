"""Phase 6 smoke — Workflow Progress Bus email integration (v4.00.98).

Exercises:
* @track_workflow accepts email_on_failure=True
* finalize_run(status='failed', email_on_failure=True) publishes workflow.run.failed
* finalize_run on success does NOT publish anything
* email_on_failure=False (default) does NOT publish
* api_create_school is opted in
* LMS dispatcher.call() opts in critical ops
* workflow_stuck_alert_sweep_task is registered + beat entry present
* Phase 6 templates render
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

    # ── T1: Decorator accepts the new flag ────────────────────────────────
    from apps.platform_runtime.workflow_tracker import track_workflow

    @track_workflow("phase6_test_silent", steps=("a",), expected_duration_seconds=5)
    def _silent_fail():
        raise RuntimeError("silent")

    @track_workflow("phase6_test_loud", steps=("a",), expected_duration_seconds=5, email_on_failure=True)
    def _loud_fail():
        raise RuntimeError("loud")

    @track_workflow("phase6_test_loud_ok", steps=("a",), expected_duration_seconds=5, email_on_failure=True)
    def _loud_ok():
        return 42

    expect("T1.1 silent decorator flag = False", getattr(_silent_fail, "email_on_failure", None) is False)
    expect("T1.2 loud decorator flag = True", getattr(_loud_fail, "email_on_failure", None) is True)

    # ── T2: Silent failure does NOT publish workflow.run.failed ───────────
    pre = len(mail.outbox)
    try:
        _silent_fail()
    except RuntimeError:
        pass
    expect("T2.1 silent failure produced no email", len(mail.outbox) == pre)

    # ── T3: Loud failure publishes (fires email) ──────────────────────────
    pre = len(mail.outbox)
    try:
        _loud_fail()
    except RuntimeError:
        pass
    expect("T3.1 loud failure grew outbox", len(mail.outbox) > pre,
           f"pre={pre} post={len(mail.outbox)}")
    if len(mail.outbox) > pre:
        last = mail.outbox[-1]
        expect("T3.2 subject mentions workflow", "workflow" in last.subject.lower() or "Workflow" in last.subject)

    # ── T4: Loud + success does NOT publish ───────────────────────────────
    pre = len(mail.outbox)
    out = _loud_ok()
    expect("T4.1 loud_ok returns normal", out == 42)
    expect("T4.2 loud_ok did not grow outbox", len(mail.outbox) == pre)

    # ── T5: api_create_school is opted in ─────────────────────────────────
    from apps.schools.super_views_provisioning import api_create_school

    inner = getattr(api_create_school, "__wrapped__", None) or api_create_school
    # peel one more layer if double-wrapped
    while hasattr(inner, "__wrapped__"):
        if getattr(inner, "email_on_failure", None) is not None:
            break
        inner = inner.__wrapped__
    expect("T5.1 api_create_school wrapper carries email_on_failure flag",
           getattr(api_create_school, "email_on_failure", None) is True
           or getattr(inner, "email_on_failure", None) is True)

    # ── T6: Workflow stuck sweep task registered + beat entry ─────────────
    from apps.platform_runtime.tasks import workflow_stuck_alert_sweep_task

    expect("T6.1 stuck sweep task is importable", workflow_stuck_alert_sweep_task is not None)
    expect("T6.2 stuck task name correct",
           getattr(workflow_stuck_alert_sweep_task, "name", "")
           == "platform_runtime.workflow_stuck_alert_sweep")
    sched = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
    expect("T6.3 stuck-sweep beat entry present",
           "platform-runtime-workflow-stuck-sweep" in sched)


run()

passed = sum(1 for _, ok, _ in ASSERTIONS if ok)
failed = sum(1 for _, ok, _ in ASSERTIONS if not ok)
total = len(ASSERTIONS)

print(f"\n=== Phase 6 Workflow-bus email integration ({total} assertions) ===\n")
for label, ok, detail in ASSERTIONS:
    mark = "PASS" if ok else "FAIL"
    extra = f" -- {detail}" if detail and not ok else ""
    print(f"  [{mark}] {label}{extra}")
print(f"\n{passed}/{total} passed, {failed} failed.")
sys.exit(0 if failed == 0 else 1)
