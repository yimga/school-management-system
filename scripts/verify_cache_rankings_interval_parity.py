#!/usr/bin/env python3
"""Siteconfig slice (batch 1264/1265): cache_rankings_interval_minutes first-class parity.

No Django required. Ensures the field is on RuntimeDefaults first-class registry,
owned in domain_ownership, and evals rankings cache reads via get_cached_site_settings.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELD = "cache_rankings_interval_minutes"


def main() -> int:
    errors: list[str] = []

    fc = ROOT / "apps" / "platform_runtime" / "runtime_defaults_first_class.py"
    if FIELD not in fc.read_text(encoding="utf-8"):
        errors.append(f"{FIELD} missing from runtime_defaults_first_class.py")

    dom = ROOT / "apps" / "siteconfig" / "domain_ownership.py"
    dom_text = dom.read_text(encoding="utf-8")
    if f'"{FIELD}"' not in dom_text:
        errors.append(f"{FIELD} missing from domain_ownership.py")

    caching = ROOT / "apps" / "evals" / "caching.py"
    cache_src = caching.read_text(encoding="utf-8")
    if "get_cached_site_settings" not in cache_src:
        errors.append("apps/evals/caching.py must use get_cached_site_settings")
    if "SiteSettings.load(" in cache_src or "SiteSettings.objects" in cache_src:
        errors.append("apps/evals/caching.py must not call SiteSettings ORM directly")

    test = ROOT / "apps" / "platform_runtime" / "tests" / "test_cache_rankings_interval_resolver.py"
    if not test.is_file():
        errors.append("missing test_cache_rankings_interval_resolver.py")

    if errors:
        for e in errors:
            print(f"verify_cache_rankings_interval_parity: {e}", file=sys.stderr)
        return 1
    print("verify_cache_rankings_interval_parity: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
