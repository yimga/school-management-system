#!/usr/bin/env python3
"""Verify Django URLconf and hot import paths load without circular ImportError.

Run before/after test-runner changes; fast (no DB migration).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main() -> int:
    import django

    django.setup()

    errors: list[str] = []

    def _check(label: str, fn) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")

    _check(
        "marketplace.WebhookDelivery",
        lambda: __import__(
            "apps.marketplace.models", fromlist=["WebhookDelivery"]
        ).WebhookDelivery,
    )
    _check(
        "orchestration.OrchestrationStepEvent",
        lambda: __import__(
            "apps.orchestration.models", fromlist=["OrchestrationStepEvent"]
        ).OrchestrationStepEvent,
    )
    _check(
        "marketplace.views_developer_platform",
        lambda: __import__("apps.marketplace.views_developer_platform"),
    )
    _check(
        "orchestration.api",
        lambda: __import__("apps.orchestration.api"),
    )
    _check(
        "root URLconf",
        lambda: __import__("django.urls", fromlist=["get_resolver"]).get_resolver(),
    )

    if errors:
        print("FAIL test import chain:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("OK test import chain (models + URLconf)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
