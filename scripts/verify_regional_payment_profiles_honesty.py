#!/usr/bin/env python
"""
verify_regional_payment_profiles_honesty.py — lock the payment-corridor honesty contract.

The content gap is real and cannot be honestly fabricated: regional_payment_profiles.json
carries 250 country rows but only ~15 are researched corridors; the other ~235 are
placeholder stubs (fake USD/EUR currency + generic CARD/BANK rails). The honest engine
(apps/finance/country_readiness_register.py) already classifies those placeholders into the
``corridor_undefined`` tier so they never inflate the readiness picture.

This verifier is the CI guard that keeps it that way. It fails if a future data/code edit
ever lets a placeholder corridor masquerade as ready, introduces an unclassified rail token,
or silently DROPS below the researched-corridor floor (a regression of honest coverage).
Adding real corridors is celebrated — raise MIN_DEFINED_CORRIDORS when the floor moves up.

Exit 0 = contract held. Exit 1 = a violation that must be fixed (not baselined away).

Usage:
    python scripts/verify_regional_payment_profiles_honesty.py [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# The researched-corridor floor. 15 corridors are defined today
# (BR CD CI CM EU GB GH KE NG RW SN TZ UG US ZA). This is a RATCHET: coverage may only
# grow. Raise this number when you research and define a new corridor — never lower it.
MIN_DEFINED_CORRIDORS = 15

# Tiers that imply a tenant could collect money / is launch-ready. A placeholder corridor
# must NEVER resolve to one of these — its rails/currency are not real.
_READY_IMPLYING_TIERS = frozenset(
    {"config_only", "adapter_in_progress", "manual_only", "platform_build"}
)


def _setup_django() -> None:
    import pathlib

    repo_root = str(pathlib.Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def run() -> tuple[bool, dict]:
    _setup_django()
    from apps.finance.country_readiness_register import (
        TIER_CORRIDOR_UNDEFINED,
        all_assessments,
        summary,
        unclassified_rails,
    )

    violations: list[str] = []
    rows = all_assessments()
    s = summary()

    # 1. Every rail token in the SOT must be classified (electronic / manual / native).
    #    An unclassified token silently routes a whole country family to platform_build.
    unclassified = unclassified_rails()
    if unclassified:
        for rail, ccs in sorted(unclassified.items()):
            violations.append(
                f"unclassified rail token {rail!r} used by {len(ccs)} countries "
                f"(e.g. {', '.join(ccs[:5])}) — classify it in country_readiness_register"
            )

    # 2. No placeholder corridor may resolve to a ready-implying tier.
    masquerading: list[str] = []
    for cc, row in rows.items():
        if row.get("data_state") == "placeholder" and row.get("overall_tier") != TIER_CORRIDOR_UNDEFINED:
            masquerading.append(f"{cc}->{row.get('overall_tier')}")
    if masquerading:
        violations.append(
            "placeholder corridors masquerading as ready (must be corridor_undefined): "
            + ", ".join(sorted(masquerading))
        )

    # 3. A defined corridor claiming config_only (tenant self-serve) must actually have a
    #    live PSP behind it — otherwise it is overclaiming "just add an API key".
    overclaimed: list[str] = []
    for cc, row in rows.items():
        if row.get("data_state") == "defined" and row.get("overall_tier") == "config_only":
            findings = row.get("rail_findings") or []
            has_live = any(f.get("status") == "live" for f in findings)
            wallet_native = any(f.get("kind") == "platform_native" for f in findings)
            if not (has_live or wallet_native):
                overclaimed.append(cc)
    if overclaimed:
        violations.append(
            "config_only corridors without a live PSP or native wallet: " + ", ".join(sorted(overclaimed))
        )

    # 4. Researched-corridor coverage must not regress below the ratchet floor.
    defined = int(s.get("defined_corridors", 0))
    if defined < MIN_DEFINED_CORRIDORS:
        violations.append(
            f"defined corridors dropped to {defined}, below the ratchet floor "
            f"{MIN_DEFINED_CORRIDORS} — honest coverage regressed (lost a researched corridor?)"
        )

    report = {
        "total_countries": s.get("total_countries"),
        "defined_corridors": defined,
        "placeholder_corridors": s.get("placeholder_corridors"),
        "min_defined_floor": MIN_DEFINED_CORRIDORS,
        "by_tier": s.get("by_tier"),
        "unclassified_rails": unclassified,
        "violations": violations,
        "ok": not violations,
    }
    return (not violations), report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    ok, report = run()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"regional payment corridor honesty: "
            f"{report['defined_corridors']} defined / {report['placeholder_corridors']} placeholder "
            f"(floor {report['min_defined_floor']})"
        )
        if report["violations"]:
            print("VIOLATIONS:")
            for v in report["violations"]:
                print(f"  - {v}")
        else:
            print("OK — placeholders never masquerade as ready; rails fully classified.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
