#!/usr/bin/env python3
"""
Drift guard for ``apps.api.urls_v1`` named routes (batch 2 #13 / SOT §11.4).

When a new ``path(..., name=...)`` is added under ``api_v1``, run with ``--write``
to refresh ``scripts/generated/api_v1_named_routes.json`` and
``scripts/generated/api_v1_non_curated_route_names.json`` (names not in
``MANIFEST_CURATED_API_V1_URL_NAMES``). CI / ``pre_deploy_gate`` uses ``--check``
so renames, appendix drift, or accidental drops fail the train.

[--base REPO_ROOT] selects the repository root for imports, snapshots, and generated
paths (default: directory containing this script's parent).

Run (from repo root):
  python scripts/verify_api_v1_named_routes_snapshot.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def _curated_api_v1_url_names() -> set[str]:
    from apps.api.api_v1_manifest import MANIFEST_CURATED_API_V1_URL_NAMES

    return {url_name for _key, url_name in MANIFEST_CURATED_API_V1_URL_NAMES}


def _collect_names(root: Path) -> list[str]:
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from apps.api.urls_v1 import urlpatterns

    names: list[str] = []

    def _walk(patterns) -> None:
        for pattern in patterns:
            n = getattr(pattern, "name", None)
            if n:
                names.append(n)
            nested = getattr(pattern, "url_patterns", None)
            if nested:
                _walk(nested)

    _walk(urlpatterns)
    return sorted(set(names))


def _write_non_curated(names: list[str], non_curated_out: Path) -> None:
    curated = _curated_api_v1_url_names()
    non_curated = sorted(n for n in names if n not in curated)
    payload = {
        "version": 1,
        "source": "apps.api.api_v1_manifest.MANIFEST_CURATED_API_V1_URL_NAMES",
        "curated_url_name_count": len(curated),
        "snapshot_name_count": len(names),
        "non_curated": non_curated,
    }
    non_curated_out.parent.mkdir(parents=True, exist_ok=True)
    non_curated_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _non_curated_matches(
    names: list[str], non_curated_out: Path
) -> tuple[bool, str]:
    if not non_curated_out.is_file():
        return True, ""
    curated = _curated_api_v1_url_names()
    expected = sorted(n for n in names if n not in curated)
    try:
        blob = json.loads(non_curated_out.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"invalid JSON in {non_curated_out}: {e}"
    got = blob.get("non_curated")
    if not isinstance(got, list) or got != expected:
        return (
            False,
            f"{non_curated_out.name} non_curated drift (run --write to refresh appendix)",
        )
    return True, ""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (default: directory containing this script's parent).",
    )
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
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_api_v1_named_routes_snapshot: {exc}", file=sys.stderr)
        return 1

    out = root / "scripts" / "generated" / "api_v1_named_routes.json"
    non_curated_out = (
        root / "scripts" / "generated" / "api_v1_non_curated_route_names.json"
    )

    current = _collect_names(root)
    payload = {"version": 1, "source": "apps.api.urls_v1", "names": current}

    if args.check:
        if not out.is_file():
            print(
                f"verify_api_v1_named_routes_snapshot: missing {out}; "
                "run: python scripts/verify_api_v1_named_routes_snapshot.py --write",
                file=sys.stderr,
            )
            return 1
        existing = json.loads(out.read_text(encoding="utf-8"))
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
        ok_nc, msg_nc = _non_curated_matches(current, non_curated_out)
        if not ok_nc:
            print(
                f"verify_api_v1_named_routes_snapshot: FAIL ({msg_nc})",
                file=sys.stderr,
            )
            return 1
        print("verify_api_v1_named_routes_snapshot: PASS (snapshot matches urls_v1)")
        return 0

    if args.write or not args.check:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        _write_non_curated(current, non_curated_out)
        print(f"verify_api_v1_named_routes_snapshot: wrote {out}")
        print(f"verify_api_v1_named_routes_snapshot: wrote {non_curated_out}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
