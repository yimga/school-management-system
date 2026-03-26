#!/usr/bin/env python
"""Verify runtime environment contract for deploy profiles."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass


PLACEHOLDER_FRAGMENTS = (
    "change-me",
    "from_render",
    "your-shared-secret",
    "example",
    "localhost",
)


@dataclass(frozen=True)
class CheckItem:
    key: str
    required: bool = True
    secret: bool = False


PROFILES: dict[str, list[CheckItem]] = {
    "render-core": [
        CheckItem("DATABASE_URL"),
        CheckItem("SECRET_KEY", secret=True),
        CheckItem("ALLOWED_HOSTS"),
        CheckItem("MULTI_TENANT_BASE_DOMAIN"),
        CheckItem("USE_DJANGO_TENANTS"),
        CheckItem("DEBUG"),
    ],
    "render-collabora": [
        CheckItem("COLLABORA_BASE_URL"),
        CheckItem("WOPI_SHARED_SECRET", secret=True),
    ],
}


def _is_placeholder(value: str) -> bool:
    lower = value.lower()
    return any(fragment in lower for fragment in PLACEHOLDER_FRAGMENTS)


def validate_profile(profile: str) -> list[str]:
    issues: list[str] = []
    checks = PROFILES.get(profile, [])
    for item in checks:
        value = (os.getenv(item.key) or "").strip()
        if item.required and not value:
            issues.append(f"missing required env: {item.key}")
            continue
        if value and _is_placeholder(value):
            issues.append(f"placeholder-like value detected: {item.key}")
        if item.key == "DEBUG" and value not in {"0", "false", "False"}:
            issues.append("DEBUG must be 0/false in render-core profile")
        if item.key == "USE_DJANGO_TENANTS" and value not in {"1", "true", "True"}:
            issues.append("USE_DJANGO_TENANTS must be 1/true for render-core profile")
        if item.key == "COLLABORA_BASE_URL" and not value.startswith("https://"):
            issues.append("COLLABORA_BASE_URL must be https URL")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate deployment environment contract.")
    parser.add_argument(
        "--profile",
        action="append",
        choices=sorted(PROFILES.keys()),
        help="One or more profiles to validate. Defaults to render-core.",
    )
    args = parser.parse_args()
    profiles = args.profile or ["render-core"]
    failures: list[str] = []
    for profile in profiles:
        failures.extend(f"[{profile}] {msg}" for msg in validate_profile(profile))

    if failures:
        print("ENV CONTRACT: FAIL")
        for item in failures:
            print(f" - {item}")
        return 1

    print("ENV CONTRACT: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
