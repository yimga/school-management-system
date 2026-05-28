#!/usr/bin/env python3
"""CEZGP batch 1514 — Infrastructure baseline gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ok(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    failures: list[str] = []

    if not _ok("templates/portal_base.html", "rmc-friction.js"):
        failures.append("portal_base must load rmc-friction.js")
    if not _ok("apps/feedback/models.py", "class Category"):
        failures.append("FeedbackSubmission.Category required")
    for cat in ("LOGIN", "MOBILE", "OFFLINE_SYNC", "DATA_IMPORT", "BILLING"):
        if not _ok("apps/feedback/models.py", cat):
            failures.append(f"Feedback category {cat} missing")
    if not _ok("config/manager_feedback_loop.py", "operator_help_signal_bundle"):
        failures.append("manager_feedback_loop must use operator_help_signal_bundle")
    if not _ok("templates/schools/partials/manager_feedback_loop_body.html", "friction.by_view"):
        failures.append("manager_feedback_loop_body must show friction aggregates")
    if not (ROOT / "apps/observability/management/commands/digest_friction.py").is_file():
        failures.append("digest_friction management command missing")
    if not (ROOT / "scripts/audit_customer_experience_research_matrix.py").is_file():
        failures.append("audit_customer_experience_research_matrix.py missing")

    email = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_email_delivery_surface.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if email.returncode != 0 or "EMAIL_DELIVERY_SURFACE_PASS" not in (
        (email.stdout or "") + (email.stderr or "")
    ):
        failures.append("verify_email_delivery_surface.py failed")

    audit = subprocess.run(
        [sys.executable, str(ROOT / "scripts/audit_customer_experience_research_matrix.py"), "--write"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if audit.returncode != 0:
        failures.append(f"audit matrix failed: {audit.stderr or audit.stdout}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("CUSTOMER_EXPERIENCE_BASELINE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
