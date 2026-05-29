#!/usr/bin/env python3
"""Verify marketing site is 100% seeded (CMS DB + marketing_content JSON)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main() -> int:
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from apps.schools.marketing_content_seed import (
        validate_marketing_cms_db,
        validate_marketing_content_json_files,
        validate_marketing_loop_assets,
    )
    from apps.schools.marketing_i18n_gate import validate_marketing_i18n_seed_gate
    from apps.schools.marketing_personality import all_marketing_personality_ids
    from apps.schools.marketing_personality_seeds import seed_for_personality

    errors: list[str] = []
    errors.extend(validate_marketing_content_json_files())
    errors.extend(validate_marketing_cms_db())
    errors.extend(validate_marketing_i18n_seed_gate())
    errors.extend(validate_marketing_loop_assets())

    for pid in all_marketing_personality_ids():
        seed = seed_for_personality(pid)
        if not seed.get("metrics"):
            errors.append(f"personality seed missing metrics: {pid}")
        if not seed.get("viz_engine"):
            errors.append(f"personality seed missing viz_engine: {pid}")
        if not seed.get("json"):
            errors.append(f"personality seed missing json: {pid}")

    if errors:
        print("verify_marketing_site_seeded: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        "verify_marketing_site_seeded: OK "
        f"(CMS + {len(list((REPO / 'config' / 'marketing_content').glob('*.json')))} JSON "
        "+ fr review packet + loop assets + personalities)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
