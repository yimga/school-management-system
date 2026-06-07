#!/usr/bin/env python3
"""Verify marketplace integration credential editor is wired (finance route + template)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from django.urls import reverse  # noqa: E402


def main() -> int:
    errors: list[str] = []
    try:
        reverse("finance:marketplace_integration_credentials")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"finance:marketplace_integration_credentials: {exc}")

    template = REPO / "templates/finance/marketplace_integration_credentials.html"
    if not template.is_file():
        errors.append("missing marketplace_integration_credentials.html")
    else:
        text = template.read_text(encoding="utf-8")
        for marker in ("csrf_token", "integration-credentials", "Save credentials"):
            if marker not in text:
                errors.append(f"template missing {marker!r}")

    setup = REPO / "templates/finance/payment_readiness_setup.html"
    if setup.is_file():
        if "marketplace_integration_credentials" not in setup.read_text(encoding="utf-8"):
            errors.append("payment_readiness_setup missing credential editor link")

    if errors:
        print("MARKETPLACE_INTEGRATION_CREDENTIALS_UI_FAIL", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print("MARKETPLACE_INTEGRATION_CREDENTIALS_UI_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
