#!/usr/bin/env python3
"""Generate Playwright P0 menu sweep surfaces from portal sidebar baselines (batch 1728 D1)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "generated" / "tenant_p0_menu_sweep_surfaces.json"

ROLE_USER = {
    "TEACHER": "demo.teacher",
    "PARENT": "demo.parent",
    "STUDENT": "demo.student",
}


def _surface_index(surfaces):
    """Key surfaces by (role, item_id) so a delta survives reordering."""
    return {(s.get("role"), s.get("item_id")): s for s in (surfaces or [])}


def _describe_drift(existing_text, payload):
    """Explain a drift as added / removed / changed surfaces.

    The bare word "DRIFT" is why this ledger rotted: the only instruction was
    "run --write", which accepts a surface DISAPPEARING (a URL deleted, a
    baseline nav spec removed, a reverse that stopped resolving) exactly as
    readily as one appearing. A shrinking sweep ledger is a silent Playwright
    coverage loss that leaves every gate green, so name the shape of the drift
    and put the removal warning where a 3-line log tail still shows it.
    """
    try:
        old = json.loads(existing_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return ["committed ledger is not valid JSON", "DRIFT summary: unreadable ledger - run with --write"]
    old_idx = _surface_index(old.get("surfaces"))
    new_idx = _surface_index(payload.get("surfaces"))
    lines = []
    for key, row in new_idx.items():
        if key not in old_idx:
            lines.append(f"+ {key[0]}/{key[1]} {row.get('url_name')} {row.get('url')} (NEW surface, coverage grows)")
    removed = [key for key in old_idx if key not in new_idx]
    for key in removed:
        row = old_idx[key]
        lines.append(f"- {key[0]}/{key[1]} {row.get('url_name')} {row.get('url')} (surface GONE)")
    changed = 0
    for key, row in old_idx.items():
        other = new_idx.get(key)
        if other is None or other == row:
            continue
        changed += 1
        for field in sorted(set(row) | set(other)):
            if row.get(field) != other.get(field):
                lines.append(f"~ {key[0]}/{key[1]} {field}: {row.get(field)!r} -> {other.get(field)!r}")
    added = sum(1 for line in lines if line.startswith("+"))
    if not lines:
        lines.append("no surface changed - formatting or metadata only")
    if removed:
        lines.append(
            f"REMOVAL: {len(removed)} swept surface(s) disappeared - establish why before --write; "
            "writing here SHRINKS the Playwright sweep and every gate goes green."
        )
    lines.append(f"DRIFT summary: +{added} added / -{len(removed)} removed / ~{changed} changed - run with --write to accept")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write JSON artifact")
    parser.add_argument("--check", action="store_true", help="Fail if artifact drift")
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(ROOT))

    import django

    django.setup()

    from apps.siteconfig import portal_sidebar_items as psi

    surfaces: list[dict] = []
    unresolved: list[str] = []

    def add(role_key: str, item_id: str, url_name: str, user: str) -> None:
        path = psi._baseline_reverse(url_name)
        if not path:
            # A baseline nav item whose target no longer reverses is dropped from
            # the sweep. Silently, before this line: the ledger just got smaller.
            unresolved.append(f"{role_key}/{item_id} ({url_name})")
            return
        label = f"{role_key.lower()}-{item_id}"
        surfaces.append(
            {
                "label": label,
                "url": path,
                "user": user,
                "role": role_key,
                "url_name": url_name,
                "item_id": item_id,
            }
        )

    for role, specs in psi._BASELINE_BY_ROLE.items():
        user = ROLE_USER.get(role, f"demo.{role.lower()}")
        for item_id, _label, url_name, _icon, _section in specs:
            add(role, item_id, url_name, user)

    for item_id, _label, url_name, _icon, _section, _perm in psi._BASELINE_ADMIN:
        add("ADMIN", item_id, url_name, "demo.admin")

    payload = {
        "generated_by": "scripts/generate_tenant_p0_menu_sweep_surfaces.py",
        "schema_version": 1,
        "surface_count": len(surfaces),
        "surfaces": surfaces,
    }
    canonical = json.dumps(payload, indent=2, sort_keys=True) + "\n"

    for target in unresolved:
        print(
            f"generate_tenant_p0_menu_sweep_surfaces: WARNING {target} did not reverse - NOT swept",
            file=sys.stderr,
        )

    if args.write or not OUT.is_file():
        existing = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        OUT.parent.mkdir(parents=True, exist_ok=True)
        # Bytes, not write_text: on Windows write_text turns every "\n" into
        # "\r\n" while .gitattributes pins docs/generated/*.json to eol=lf, so a
        # text-mode write rewrote all 159 lines on one platform and none on the other.
        OUT.write_bytes(canonical.encode("utf-8"))
        print(f"generate_tenant_p0_menu_sweep_surfaces: wrote {OUT} ({len(surfaces)} surfaces)")
        if existing and existing != canonical:
            for line in _describe_drift(existing, payload):
                print(f"  {line}")
        return 0

    if args.check:
        existing = OUT.read_text(encoding="utf-8")
        if existing != canonical:
            print("generate_tenant_p0_menu_sweep_surfaces: DRIFT — run with --write")
            for line in _describe_drift(existing, payload):
                print(f"  {line}")
            return 1
        print("generate_tenant_p0_menu_sweep_surfaces: OK (no drift)")
        return 0

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
