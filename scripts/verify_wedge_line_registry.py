#!/usr/bin/env python3
"""
Verify apps/platform_runtime/wedge_line_registry.py: 45 wedges, phases, manager URLs,
and beachhead blueprint slugs present in seed command source.

Run: python scripts/verify_wedge_line_registry.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []

    import os

    os.chdir(REPO)
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from apps.platform_runtime.wedge_line_registry import (
        BEACHHEAD_BLUEPRINT_PACKS,
        WEDGE_LINES,
        assert_wedge_lines_complete,
        wedge_phase,
    )

    try:
        assert_wedge_lines_complete()
    except ValueError as e:
        errors.append(str(e))

    ids = [int(row["id"]) for row in WEDGE_LINES]
    if sorted(ids) != list(range(1, 46)):
        errors.append(f"Wedge ids must be 1..45 exactly, got {ids!r}")

    for row in WEDGE_LINES:
        wid = int(row["id"])
        if int(row["phase"]) != wedge_phase(wid):
            errors.append(f"Wedge {wid}: phase field mismatch vs wedge_phase()")

    from django.test.utils import override_settings
    from django.urls import NoReverseMatch, reverse

    seen_urls: set[str] = set()
    with override_settings(ROOT_URLCONF="config.manager_urls"):
        for row in WEDGE_LINES:
            for name in row["urls"]:
                seen_urls.add(name)
                try:
                    reverse(name)
                except NoReverseMatch as e:
                    errors.append(f"Wedge {row['id']}: URL {name!r} NoReverseMatch: {e}")
        for wid in range(1, 46):
            try:
                reverse("super:wedge_operator_detail", kwargs={"wedge_id": wid})
            except NoReverseMatch as e:
                errors.append(
                    f"Canonical wedge URL wedge_id={wid} NoReverseMatch: {e}"
                )

    seed_py = REPO / "apps" / "policies" / "management" / "commands" / "seed_blueprint_policy_packs.py"
    if not seed_py.is_file():
        errors.append(f"Missing seed file: {seed_py}")
    else:
        seed_text = seed_py.read_text(encoding="utf-8", errors="replace")
        for pack in BEACHHEAD_BLUEPRINT_PACKS:
            slug = pack["slug"]
            needle = f'"slug": "{slug}"'
            if needle not in seed_text and f"'slug': '{slug}'" not in seed_text:
                if f'"{slug}"' not in seed_text:
                    errors.append(
                        f"Beachhead blueprint slug {slug!r} not found in seed_blueprint_policy_packs.py"
                    )

    if errors:
        print("verify_wedge_line_registry FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "verify_wedge_line_registry: PASS (45 wedges, phases, "
        f"{len(seen_urls)} unique manager URL patterns, {len(BEACHHEAD_BLUEPRINT_PACKS)} beachhead slugs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
