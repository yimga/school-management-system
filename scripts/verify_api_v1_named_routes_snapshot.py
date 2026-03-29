#!/usr/bin/env python3
"""
Drift guard for ``apps.api.urls_v1`` named routes (batch 2 #13 / SOT §11.4).

When a new ``path(..., name=...)`` is added under ``api_v1``, run with ``--write``
to refresh ``scripts/generated/api_v1_named_routes.json`` and
``scripts/generated/api_v1_non_curated_route_names.json`` (names not in
``MANIFEST_CURATED_API_V1_URL_NAMES``). CI / ``pre_deploy_gate`` uses ``--check``
so renames, appendix drift, or accidental drops fail the train.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "generated" / "api_v1_named_routes.json"
NON_CURATED_OUT = ROOT / "scripts" / "generated" / "api_v1_non_curated_route_names.json"


def _curated_api_v1_url_names() -> set[str]:
    from apps.api.api_v1_manifest import MANIFEST_CURATED_API_V1_URL_NAMES

    return {url_name for _key, url_name in MANIFEST_CURATED_API_V1_URL_NAMES}


def _collect_names() -> list[str]:
    root_s = str(ROOT)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from apps.api.urls_v1 import urlpatterns

    names: list[str] = []
    for p in urlpatterns:
        n = getattr(p, "name", None)
        if n:
            names.append(n)
    return sorted(names)


def _write_non_curated(names: list[str]) -> None:
    curated = _curated_api_v1_url_names()
    non_curated = sorted(n for n in names if n not in curated)
    payload = {
        "version": 1,
        "source": "apps.api.api_v1_manifest.MANIFEST_CURATED_API_V1_URL_NAMES",
        "curated_url_name_count": len(curated),
        "snapshot_name_count": len(names),
        "non_curated": non_curated,
    }
    NON_CURATED_OUT.parent.mkdir(parents=True, exist_ok=True)
    NON_CURATED_OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _non_curated_matches(names: list[str]) -> tuple[bool, str]:
    if not NON_CURATED_OUT.is_file():
        return True, ""
    curated = _curated_api_v1_url_names()
    expected = sorted(n for n in names if n not in curated)
    try:
        blob = json.loads(NON_CURATED_OUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"invalid JSON in {NON_CURATED_OUT}: {e}"
    got = blob.get("non_curated")
    if not isinstance(got, list) or got != expected:
        return (
            False,
            f"{NON_CURATED_OUT.name} non_curated drift (run --write to refresh appendix)",
        )
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--check",
        action="store_true",
        help="Fail if snapshot differs from live urlpattern names",
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="Write scripts/generated/api_v1_named_routes.json",
    )
    args = ap.parse_args()

    current = _collect_names()
    payload = {"version": 1, "source": "apps.api.urls_v1", "names": current}

    if args.check:
        if not OUT.is_file():
            print(
                f"verify_api_v1_named_routes_snapshot: missing {OUT}; "
                "run: python scripts/verify_api_v1_named_routes_snapshot.py --write",
                file=sys.stderr,
            )
            return 1
        existing = json.loads(OUT.read_text(encoding="utf-8"))
        old = existing.get("names")
        if not isinstance(old, list):
            print(
                "verify_api_v1_named_routes_snapshot: snapshot 'names' must be a list",
                file=sys.stderr,
            )
            return 1
        if old != current:
            old_set, new_set = set(old), set(current)
            added = sorted(new_set - old_set)
            removed = sorted(old_set - new_set)
            print(
                "verify_api_v1_named_routes_snapshot: FAIL (drift).\n"
                f"  added:   {added!r}\n"
                f"  removed: {removed!r}\n"
                "  run: python scripts/verify_api_v1_named_routes_snapshot.py --write",
                file=sys.stderr,
            )
            return 1
        ok_nc, msg_nc = _non_curated_matches(current)
        if not ok_nc:
            print(
                f"verify_api_v1_named_routes_snapshot: FAIL ({msg_nc})",
                file=sys.stderr,
            )
            return 1
        print("verify_api_v1_named_routes_snapshot: PASS (snapshot matches urls_v1)")
        return 0

    if args.write or not args.check:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        _write_non_curated(current)
        print(f"verify_api_v1_named_routes_snapshot: wrote {OUT}")
        print(f"verify_api_v1_named_routes_snapshot: wrote {NON_CURATED_OUT}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
