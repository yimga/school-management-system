#!/usr/bin/env python3
"""
Repository gate: every ``EXACT_FIELD_OWNERS`` key is either a RuntimeDefaults first-class
column or an explicitly registered virtual-only field (or row-metadata delete bucket).

No Django setup required (importlib loads plain modules).

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify domain ownership exact storage."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _relative(path: Path, base: Path) -> Path | str:
    try:
        return path.relative_to(base)
    except ValueError:
        return path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print("verify_domain_ownership_exact_storage: FAILED", file=sys.stderr)
        print(f"  - {exc}", file=sys.stderr)
        return 1

    domain_ownership = root / "apps" / "siteconfig" / "domain_ownership.py"
    runtime_defaults_first_class = (
        root / "apps" / "platform_runtime" / "runtime_defaults_first_class.py"
    )
    domain_ownership_storage = root / "apps" / "siteconfig" / "domain_ownership_storage.py"

    missing = [
        _relative(path, root)
        for path in (
            domain_ownership,
            runtime_defaults_first_class,
            domain_ownership_storage,
        )
        if not path.is_file()
    ]
    if missing:
        print("verify_domain_ownership_exact_storage: FAILED", file=sys.stderr)
        for path in missing:
            print(f"  - Missing {path}", file=sys.stderr)
        return 1

    do = _load("domain_ownership", domain_ownership)
    fc = _load(
        "runtime_defaults_first_class",
        runtime_defaults_first_class,
    )
    st = _load(
        "domain_ownership_storage",
        domain_ownership_storage,
    )

    first_class = frozenset(fc.RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES)
    errors = st.collect_exact_field_storage_errors(
        exact_field_owners=dict(do.EXACT_FIELD_OWNERS),
        first_class_field_names=first_class,
        virtual_only_exact=st.VIRTUAL_ONLY_EXACT_FIELDS,
    )

    # Every first-class column should appear in EXACT_FIELD_OWNERS (single classification source).
    exact_keys = frozenset(do.EXACT_FIELD_OWNERS.keys())
    for name in sorted(first_class):
        if name not in exact_keys:
            errors.append(
                f"RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES contains {name!r} "
                "missing from EXACT_FIELD_OWNERS — add explicit owner in domain_ownership.py."
            )

    if errors:
        print("verify_domain_ownership_exact_storage: FAILED", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "verify_domain_ownership_exact_storage: PASS "
        f"({len(do.EXACT_FIELD_OWNERS)} exact fields align with "
        f"{len(first_class)} first-class RuntimeDefaults columns + "
        f"{len(st.VIRTUAL_ONLY_EXACT_FIELDS)} virtual-only registrations)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
