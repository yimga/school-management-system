#!/usr/bin/env python3
"""
Ensure tenant resolution cache uses versioned keys (AWS pillar).

Fails when legacy unversioned ``tenant:host:`` keys are reintroduced in
apps/schools/middleware.py outside the delegation helper.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIDDLEWARE = ROOT / "apps" / "schools" / "middleware.py"
LEGACY_KEY_RE = re.compile(r'["\']tenant:(host|subdomain):')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    text = MIDDLEWARE.read_text(encoding="utf-8")
    if LEGACY_KEY_RE.search(text):
        print(
            "verify_tenant_resolution_cache_keys: legacy tenant:host: pattern in middleware",
            file=sys.stderr,
        )
        return 1
    if "tenant_resolution_cache_key" not in text:
        print(
            "verify_tenant_resolution_cache_keys: middleware must delegate to tenant_resolution_cache_key",
            file=sys.stderr,
        )
        return 1
    print("verify_tenant_resolution_cache_keys: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
