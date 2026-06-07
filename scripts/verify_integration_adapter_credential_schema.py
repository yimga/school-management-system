#!/usr/bin/env python3
"""
Verify integration adapters in the catalog have operator credential schemas.

Usage: python scripts/verify_integration_adapter_credential_schema.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from apps.marketplace.integration_adapter_credentials import (  # noqa: E402
    adapter_schema_validation_errors,
)


def main() -> int:
    errors = adapter_schema_validation_errors()
    if errors:
        print("INTEGRATION_ADAPTER_CREDENTIAL_SCHEMA_FAIL", file=sys.stderr)
        for line in errors[:30]:
            print(f"  - {line}", file=sys.stderr)
        if len(errors) > 30:
            print(f"  ... and {len(errors) - 30} more", file=sys.stderr)
        return 1

    print("INTEGRATION_ADAPTER_CREDENTIAL_SCHEMA_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
