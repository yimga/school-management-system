#!/usr/bin/env python3
"""SODP depth gate — conflict policy wiring, platform shell adoption, CI presence."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _text(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def main() -> int:
    findings: list[str] = []

    queue = _text("apps/platform_runtime/offline_queue.py")
    if "conflict_resolver" not in queue:
        findings.append("offline_queue must import conflict_resolver for grade apply")
    if "_grading_payload_conflicts_row" not in queue:
        findings.append("offline_queue missing grading conflict helper")
    if "_apply_support_ticket" not in queue:
        findings.append("offline_queue missing support ticket apply path")
    if "_apply_provision_signup" not in queue:
        findings.append("offline_queue missing provision.signup apply path")

    draft = _text("static/js/form-draft-save.js")
    if "data-rmc-offline-action" not in draft:
        findings.append("form-draft-save missing data-rmc-offline-action typed enqueue")
    if "postTypedEnqueue" not in draft:
        findings.append("form-draft-save missing typed pending flush to enqueue API")

    bootstrap = _text("static/js/rmc-offline-auth-bootstrap.js")
    if "provision.signup" not in bootstrap:
        findings.append("rmc-offline-auth-bootstrap missing provision.signup enqueue")

    oqc = _text("static/js/offline-queue-client.js")
    if "runProcessQueue" not in oqc or "rmc-offline-conflicts-updated" not in oqc:
        findings.append("offline-queue-client must refresh conflict count after process")
    if "offlineConflictsUrl" not in _text("templates/portal_base.html"):
        findings.append("portal_base SMS_OFFLINE_CONFIG missing offlineConflictsUrl")

    status_js = _text("static/js/offline-status-bar.js")
    if "conflictsPortalUrl" not in status_js:
        findings.append("offline-status-bar missing portal conflicts bridge")

    services = _text("apps/sync_engine/services.py")
    if "resolve_one" not in services:
        findings.append("apply_remote must use conflict_resolver.resolve_one")

    form_hits = 0
    templates_root = ROOT / "templates"
    if templates_root.is_dir():
        for path in templates_root.rglob("*.html"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if 'data-rmc-offline-form="' in text:
                form_hits += 1
    if form_hits < 14:
        findings.append(f"expected >=14 templates with data-rmc-offline-form (found {form_hits})")

    portal = _text("templates/portal_base.html")
    for needle in (
        "form-draft-save.js",
        "rmc-offline-auth-vault.js",
        "rmc-offline-auth-bootstrap.js",
        "rmc-lan-mule-sync.js",
    ):
        if needle not in portal:
            findings.append(f"portal_base missing {needle}")

    forms = _text("static/js/rmc-offline-portal-forms.js")
    if 'support_ticket' not in forms:
        findings.append("rmc-offline-portal-forms missing support_ticket wiring")

    ci = ROOT / ".github/workflows/sodp-gates.yml"
    if not ci.is_file():
        findings.append("missing .github/workflows/sodp-gates.yml")

    test = ROOT / "apps/platform_runtime/tests/test_offline_grading_manual_review.py"
    if not test.is_file():
        findings.append("missing test_offline_grading_manual_review.py")

    notify = _text("apps/schoolops/notification_intent.py")
    if "fee_reminder" not in notify or "transport_delay" not in notify:
        findings.append("notification_intent missing expanded template copy")

    if findings:
        print("verify_sovereign_offline_depth: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_sovereign_offline_depth: SOVEREIGN_OFFLINE_DEPTH_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
