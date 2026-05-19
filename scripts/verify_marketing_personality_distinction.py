#!/usr/bin/env python3
"""Verify marketing personalities are distinct (accent + viz_engine) and seeds exist."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from apps.schools.marketing_personality import (  # noqa: E402
    all_marketing_personality_ids,
    personality_accent_signature,
    resolve_marketing_personality,
)
from apps.schools.marketing_personality_seeds import seed_for_personality  # noqa: E402

REQUIRED_FILES = (
    "apps/schools/marketing_personality.py",
    "apps/schools/marketing_personality_seeds.py",
    "templates/marketing/components/_personality_viz_panel.html",
    "static/marketing/css/marketing-personality-viz.css",
    "static/marketing/js/mkt-personality-viz.js",
)

REQUIRED_SNIPPETS = (
    ("templates/marketing/base_marketing.html", "data-mkt-personality-os", "OS matrix on html"),
    ("templates/marketing/base_marketing.html", "marketing-personality-viz.css", "viz CSS in shell"),
    ("templates/marketing/base_marketing.html", "mkt-personality-viz.js", "viz JS in shell"),
    ("templates/marketing/pages/type_platform_generic.html", "_personality_viz_panel.html", "viz on platform pages"),
    ("templates/marketing/pages/type_view_layer.html", "_personality_viz_panel.html", "viz on view-layer pages"),
    ("templates/marketing/partials/marketing_inner_head.html", "_personality_viz_panel.html", "viz on default inner pages"),
)


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    errors: list[str] = []

    for rel in REQUIRED_FILES:
        if not (REPO / rel).is_file():
            errors.append(f"missing file: {rel}")

    for rel, needle, label in REQUIRED_SNIPPETS:
        if needle not in _read(rel):
            errors.append(f"{label}: expected `{needle}` in {rel}")

    signatures: dict[str, list[str]] = {}
    for pid in all_marketing_personality_ids():
        p = resolve_marketing_personality(pid)
        sig = personality_accent_signature(p)
        signatures.setdefault(sig, []).append(pid)
        seed = seed_for_personality(pid)
        if not seed.get("metrics"):
            errors.append(f"seed missing metrics: {pid}")
        if not seed.get("viz_engine"):
            errors.append(f"seed missing viz_engine: {pid}")
        if not seed.get("json"):
            errors.append(f"seed missing json: {pid}")

    collisions = {sig: ids for sig, ids in signatures.items() if len(ids) > 1}
    if collisions:
        for sig, ids in sorted(collisions.items()):
            errors.append(f"personality collision (same accent|viz): {ids} -> {sig}")

    view_layer = _read("apps/schools/marketing_personality.py")
    for token in ("run", "teach", "pay", "communicate"):
        if f'os_matrix=_OS_{token.upper()}' not in view_layer and f'os_matrix="{token}"' not in view_layer:
            if f'"{token}"' not in view_layer:
                errors.append(f"os_matrix {token} not referenced in personality registry")

    if errors:
        print("verify_marketing_personality_distinction: FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(
        f"verify_marketing_personality_distinction: OK ({len(all_marketing_personality_ids())} personalities, "
        f"{len(signatures)} unique signatures)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
