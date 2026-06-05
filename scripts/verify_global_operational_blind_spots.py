#!/usr/bin/env python3
"""Audit seven global blind spots + granular ops gaps (honest scaffold)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated" / "global_operational_blind_spots_audit.json"


def _exists(rel: str) -> bool:
    return (REPO / rel).is_file()


def main() -> int:
    parser = argparse.ArgumentParser(description="Global operational blind spots verifier")
    parser.add_argument("--granular-ops", action="store_true", help="Phase 4E — require granular ops artifacts")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--allow-pending", action="store_true", help="Structural audit only (Phase 0B)")
    args = parser.parse_args()

    checks = {
        "blind_spot_1_calendars": _exists("apps/siteconfig/country_formats_service.py"),
        "blind_spot_2_family_graph": _exists("apps/people/models.py"),
        "blind_spot_3_offline_pwa": _exists("static/js/service-worker.js"),
        "blind_spot_4_names": _exists("apps/siteconfig/country_formats_service.py"),
        "blind_spot_5_residency": _exists("apps/schools/middleware_residency.py"),
        "blind_spot_6_ledger": _exists("apps/finance/services.py"),
        "blind_spot_7_grading": _exists("apps/evals/grading.py"),
        "granular_sms_router": _exists("apps/communication/sms_router.py"),
        "granular_fast_switch": _exists("apps/governance/fast_switch.py"),
        "granular_fractional_capacity": _exists("apps/academics/fractional_capacity.py"),
        "granular_instruction_day": _exists("apps/academics/instruction_day_ledger.py"),
        "granular_operational_time": _exists("apps/siteconfig/operational_time.py"),
        "granular_scheduling": _exists("apps/academics/scheduling.py"),
    }

    failures: list[str] = []
    for key, ok in checks.items():
        if not ok:
            failures.append(f"missing kernel for {key}")

    if checks.get("granular_fractional_capacity"):
        try:
            if str(REPO) not in sys.path:
                sys.path.insert(0, str(REPO))
            from apps.academics.fractional_capacity import effective_room_capacity  # noqa: F401
        except Exception as exc:
            failures.append(f"fractional_capacity import failed: {exc}")

    if args.granular_ops and not args.allow_pending:
        required = (
            "granular_sms_router",
            "granular_fast_switch",
            "granular_fractional_capacity",
            "granular_instruction_day",
            "granular_operational_time",
            "granular_scheduling",
        )
        for key in required:
            if not checks.get(key):
                failures.append(f"Phase 4E requires {key}")

    # Language regression (Phase 1 fix target)
    try:
        import os

        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        import django

        django.setup()
        from apps.siteconfig.country_localization_service import get_languages

        if len(get_languages("CM")) < 2:
            if not args.allow_pending:
                failures.append("language overlay regression: get_languages('CM') < 2")
    except Exception as exc:
        if not args.allow_pending:
            failures.append(f"language overlay check failed: {exc}")

    verdict = "GLOBAL_OPERATIONAL_BLIND_SPOTS_PASS" if not failures else "GLOBAL_OPERATIONAL_BLIND_SPOTS_FAIL"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "finding_count": len(failures),
        "checks": checks,
        "failures": failures,
    }
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(f"verify_global_operational_blind_spots: {verdict}", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_global_operational_blind_spots: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
