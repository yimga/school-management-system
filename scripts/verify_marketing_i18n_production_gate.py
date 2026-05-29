#!/usr/bin/env python3
"""
Marketing i18n gates: seed completeness (default) vs production native-review.

Default (dev/CI seed path):
  MARKETING_I18N_SEED_GATE_PASS — fr anchors + review ledger + fr.md packet

Production deploy:
  python scripts/verify_marketing_i18n_production_gate.py --production
  MARKETING_I18N_PRODUCTION_GATE_PASS — fr/es/pt-br production-ready in ledger
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main() -> int:
    parser = argparse.ArgumentParser(description="Marketing i18n seed vs production gate")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Fail unless fr/es/pt-br are production-ready (native-reviewed).",
    )
    args = parser.parse_args()

    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from apps.schools.marketing_i18n_gate import (
        validate_marketing_i18n_production_gate,
        validate_marketing_i18n_seed_gate,
    )

    if args.production:
        errors = validate_marketing_i18n_production_gate()
        label = "verify_marketing_i18n_production_gate"
        ok_msg = "MARKETING_I18N_PRODUCTION_GATE_PASS"
    else:
        errors = validate_marketing_i18n_seed_gate()
        label = "verify_marketing_i18n_production_gate"
        ok_msg = "MARKETING_I18N_SEED_GATE_PASS"

    if errors:
        print(f"{label}: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"{label}: {ok_msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
