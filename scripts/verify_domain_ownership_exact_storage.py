#!/usr/bin/env python3
"""
Repository gate: every ``EXACT_FIELD_OWNERS`` key is either a RuntimeDefaults first-class
column or an explicitly registered virtual-only field (or row-metadata delete bucket).

No Django setup required (importlib loads plain modules).
"""

from __future__ import annotations

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


def main() -> int:
    do = _load("domain_ownership", ROOT / "apps" / "siteconfig" / "domain_ownership.py")
    fc = _load(
        "runtime_defaults_first_class",
        ROOT / "apps" / "platform_runtime" / "runtime_defaults_first_class.py",
    )
    st = _load(
        "domain_ownership_storage",
        ROOT / "apps" / "siteconfig" / "domain_ownership_storage.py",
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
    raise SystemExit(main())
