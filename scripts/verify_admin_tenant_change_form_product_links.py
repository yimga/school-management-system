#!/usr/bin/env python3
"""
P3 discipline: tenant Unfold admin change_form templates under templates/admin/
must expose at least one product-surface link (or explicit exempt marker).

Fails fast when a new high-churn change_form is added without escape links.

``--base`` scopes the template glob to the given repository root (default: this repository root).

Run: ``raise SystemExit(main(None))``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ADMIN_CHANGE_FORM_GLOB = "templates/admin/**/change_form.html"

# {% url 'namespace:...' %} — tenant urlconf-safe namespaces (no super: on school hosts).
_URL_TOKEN = re.compile(
    r"\{%\s*url\s+['\"]([a-z0-9_]+):",
    re.IGNORECASE,
)
_EXEMPT = re.compile(
    r"admin-change-form-escape-exempt",
    re.IGNORECASE,
)
_ALLOWED_PREFIXES = frozenset(
    {
        "siteconfig",
        "studio_os",
        "portal",
        "accounts",
        "apicenter",
        "communication",
        "kb",
    }
)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify tenant admin change_form templates expose product-surface links."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_admin_tenant_change_form_product_links: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    paths = sorted(root.glob(ADMIN_CHANGE_FORM_GLOB))
    if not paths:
        errors.append(f"no files matched {ADMIN_CHANGE_FORM_GLOB}")
        print("verify_admin_tenant_change_form_product_links: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    for path in paths:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if _EXEMPT.search(text):
            continue
        namespaces = {m.group(1).lower() for m in _URL_TOKEN.finditer(text)}
        if namespaces & _ALLOWED_PREFIXES:
            continue
        errors.append(
            f"{rel}: add a product url tag (allowed namespaces: {sorted(_ALLOWED_PREFIXES)}) "
            "or comment 'admin-change-form-escape-exempt' for rare exceptions"
        )

    if errors:
        print("verify_admin_tenant_change_form_product_links: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(
        f"verify_admin_tenant_change_form_product_links: PASS (files={len(paths)})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
