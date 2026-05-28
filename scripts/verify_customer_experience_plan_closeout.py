#!/usr/bin/env python3
"""CEZGP plan v2 phase-8 hooks not covered by per-phase verifiers (batches 1514–1522)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _contains(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    failures: list[str] = []

    if not _contains("docs/ROADMAPS_IMPLEMENTATION_STATUS.md", "CEZGP batch 1522"):
        failures.append("ROADMAPS_IMPLEMENTATION_STATUS.md missing CEZGP 1522 honesty gate")
    if not _contains("apps/api/roadmap_due_today_views.py", "code_presence_stub"):
        failures.append("roadmap_due_today_views missing code_presence_stub honesty")
    if not _contains("templates/studio_os/partials/launch_school_infrastructure_body.html", "Preview API"):
        failures.append("Launch Studio missing Preview API badge")

    geos = ROOT / "docs/generated/greatest_education_os_matrix.json"
    if not geos.is_file():
        failures.append("greatest_education_os_matrix.json missing")
    else:
        try:
            data = json.loads(geos.read_text(encoding="utf-8"))
            pillars = {p.get("pillar_id") for p in data.get("pillars", []) if isinstance(p, dict)}
            if "customer_experience" not in pillars:
                failures.append("GEOS matrix missing customer_experience pillar")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            failures.append(f"GEOS matrix JSON invalid: {exc}")

    if (ROOT / "templates/siteconfig/feedback_roadmap.html").is_file():
        failures.append(
            "orphan templates/siteconfig/feedback_roadmap.html "
            "(feedback_roadmap view redirects; remove dead template)"
        )

    if not _contains("apps/siteconfig/views.py", 'redirect("feedback:product_feedback")'):
        failures.append("siteconfig feedback_roadmap must redirect to feedback:product_feedback")

    for script, token in (
        ("scripts/verify_email_delivery_surface.py", "EMAIL_DELIVERY_SURFACE_PASS"),
        ("scripts/verify_greatest_education_os_matrix.py", "GEOS_99_MATRIX_PASS"),
        ("scripts/generate_platform_inventory.py", "committed inventory is up to date"),
        ("scripts/verify_customer_experience_phase_h_subset.py", "CUSTOMER_EXPERIENCE_PHASE_H_SUBSET_PASS"),
        ("scripts/verify_parent_mobile_first.py", "PARENT_MOBILE_FIRST_PASS"),
        ("scripts/verify_marketing_glocal_visual_engine.py", "MARKETING_GLOCAL_VISUAL_ENGINE_PASS"),
    ):
        argv = [sys.executable, str(ROOT / script)]
        if script.endswith("generate_platform_inventory.py"):
            argv.append("--check")
        proc = subprocess.run(
            argv,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0 or token not in out:
            failures.append(f"{script} failed (need {token})")

    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1

    print("CUSTOMER_EXPERIENCE_PLAN_CLOSEOUT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
