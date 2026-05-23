"""Verifier — every ExperienceTemplate carries accessibility_level >= AA."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap() -> None:
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    sys.path.insert(0, str(repo_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def main() -> int:
    _bootstrap()
    from apps.brand_experience import experience_templates as et

    floor = {"AA", "AAA"}
    failures = [o.key for o in et.OVERLAYS if o.accessibility_level not in floor]
    if failures:
        print(f"FAIL: {len(failures)} templates below WCAG AA floor: {failures[:5]}")
        return 1
    counts = {"AA": 0, "AAA": 0}
    for o in et.OVERLAYS:
        counts[o.accessibility_level] = counts.get(o.accessibility_level, 0) + 1
    print(f"TEMPLATE_A11Y_FLOOR_PASS (AA: {counts.get('AA', 0)} / AAA: {counts.get('AAA', 0)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
