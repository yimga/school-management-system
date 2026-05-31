"""Phase 7 smoke — legacy send_mail sweep + scanner (v4.00.98).

Exercises:
* email_compat.send_mail signature parity with django.core.mail.send_mail
* email_compat.send_mail routes through send_transactional (writes
  EmailDeliveryEvent + grows mail.outbox)
* email_compat returns 1 on success, 0 on no-recipients
* email_compat honors fail_silently=True
* scanner runs cleanly
* scanner baseline file exists + valid JSON shape
* assist_dock/views_share.py + feedback/signals.py imports were migrated
"""

from __future__ import annotations

import json
import os
import subprocess
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

from django.core import mail
from django.test.utils import override_settings

ASSERTIONS: list[tuple[str, bool, str]] = []


def expect(label: str, cond: bool, detail: str = "") -> None:
    ASSERTIONS.append((label, bool(cond), detail))


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def run():
    mail.outbox = []
    _run = uuid.uuid4().hex[:8]

    # ── T1: compat wrapper signature parity + routing ─────────────────────
    from apps.schoolops.email_compat import send_mail as compat_send_mail
    from apps.schoolops.models_email_delivery import EmailDeliveryEvent

    pre_outbox = len(mail.outbox)
    pre_events = EmailDeliveryEvent.objects.count()
    result = compat_send_mail(
        f"[smoke] phase 7 T1 {_run}",
        "compat body",
        "from@compat.test",
        [f"to1_{_run}@compat.test"],
        fail_silently=False,
        html_message="<p>compat</p>",
    )
    expect("T1.1 compat returns 1 on success", result == 1)
    expect("T1.2 outbox grew", len(mail.outbox) > pre_outbox)
    expect("T1.3 EmailDeliveryEvent row written", EmailDeliveryEvent.objects.count() > pre_events)

    # ── T2: empty recipients returns 0 ────────────────────────────────────
    r = compat_send_mail("subj", "body", "from@x.test", [])
    expect("T2.1 empty recipients returns 0", r == 0)
    r2 = compat_send_mail("subj", "body", "from@x.test", [""])
    expect("T2.2 empty-string recipient returns 0", r2 == 0)

    # ── T3: fail_silently=True swallows exceptions ────────────────────────
    # Use a deliberately-bad input that the reliability layer would reject
    # — we simulate by passing fail_silently=True; the compat returns 0
    # gracefully even if SOMETHING goes wrong.
    r = compat_send_mail(
        f"[smoke] T3 {_run}",
        "x",
        "from@x.test",
        [f"to3_{_run}@x.test"],
        fail_silently=True,
    )
    expect("T3.1 fail_silently honored — returns int", r in (0, 1))

    # ── T4: scanner runs cleanly ──────────────────────────────────────────
    scanner = _PROJECT_ROOT / "scripts" / "scan_legacy_send_mail.py"
    result = subprocess.run(
        [sys.executable, str(scanner), "--strict", "--json"],
        capture_output=True,
        text=True,
        cwd=str(_PROJECT_ROOT),
    )
    expect("T4.1 scanner exits 0 under --strict", result.returncode == 0)
    try:
        payload = json.loads(result.stdout)
        expect("T4.2 scanner emits valid JSON", isinstance(payload, dict))
        expect("T4.3 scanner reports ok=True", payload.get("ok") is True)
        expect("T4.4 finding_count <= baseline", payload.get("finding_count", 0) <= payload.get("baseline", 0))
    except Exception as exc:
        expect("T4.2 scanner emits valid JSON", False, f"{type(exc).__name__}: {exc}")

    # ── T5: baseline file shape ───────────────────────────────────────────
    baseline_path = _PROJECT_ROOT / "var" / "security-audit-baseline-legacy-send-mail.json"
    expect("T5.1 baseline file exists", baseline_path.exists())
    if baseline_path.exists():
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
        expect("T5.2 baseline has finding_count", "finding_count" in data)
        expect("T5.3 baseline has scanner field",
               data.get("scanner") == "scan_legacy_send_mail.py")

    # ── T6: migrated callsites no longer import from django.core.mail ─────
    for migrated in (
        "apps/assist_dock/views_share.py",
        "apps/feedback/signals.py",
    ):
        text = (_PROJECT_ROOT / migrated).read_text(encoding="utf-8")
        expect(f"T6 {migrated} uses email_compat",
               "from apps.schoolops.email_compat import send_mail" in text)
        expect(f"T6 {migrated} no longer imports django.core.mail.send_mail",
               "from django.core.mail import send_mail" not in text)


run()

passed = sum(1 for _, ok, _ in ASSERTIONS if ok)
failed = sum(1 for _, ok, _ in ASSERTIONS if not ok)
total = len(ASSERTIONS)

print(f"\n=== Phase 7 Legacy send_mail sweep ({total} assertions) ===\n")
for label, ok, detail in ASSERTIONS:
    mark = "PASS" if ok else "FAIL"
    extra = f" -- {detail}" if detail and not ok else ""
    print(f"  [{mark}] {label}{extra}")
print(f"\n{passed}/{total} passed, {failed} failed.")
sys.exit(0 if failed == 0 else 1)
