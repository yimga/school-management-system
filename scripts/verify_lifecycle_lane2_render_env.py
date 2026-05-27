#!/usr/bin/env python3
"""Verify render.yaml documents Lane 2 tenant lifecycle / offboarding env defaults."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RENDER_YAML = ROOT / "render.yaml"

# Explicit defaults on web + worker (beat needs purge flag when Celery schedules purges).
WEB_WORKER_KEYS = (
    "TENANT_SELF_SERVICE_OFFBOARDING_ENABLED",
    "TENANT_AUTO_PURGE_ENABLED",
    "TENANT_AUTO_PURGE_GRACE_DAYS",
    "TENANT_OFFBOARDING_EMAIL_ENABLED",
    "TENANT_OFFBOARDING_NOTIFY_TENANT_ADMINS",
    "TENANT_OFFBOARDING_S3_CLEANUP_ENABLED",
)

BEAT_KEYS = (
    "TENANT_AUTO_PURGE_ENABLED",
    "TENANT_AUTO_PURGE_GRACE_DAYS",
)

EMAIL_KEYS = (
    "EMAIL_BACKEND",
    "DEFAULT_FROM_EMAIL",
)


def _service_blocks(text: str) -> dict[str, str]:
    """Return {service_name: block_text} for each ``- type:`` service entry."""
    blocks: dict[str, str] = {}
    for match in re.finditer(
        r"- type: (\w+)\s+name: ([^\n]+)\n(.*?)(?=\n  - type: |\ndatabases:|\Z)",
        text,
        re.DOTALL,
    ):
        kind, name, body = match.group(1), match.group(2).strip(), match.group(3)
        if kind in ("web", "worker"):
            blocks[name] = body
    return blocks


def _keys_in_block(block: str) -> set[str]:
    return set(re.findall(r"- key: (\w+)", block))


def main() -> int:
    failures: list[str] = []
    if not RENDER_YAML.is_file():
        failures.append("missing render.yaml")
        print("verify_lifecycle_lane2_render_env: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    text = RENDER_YAML.read_text(encoding="utf-8")
    blocks = _service_blocks(text)

    web = blocks.get("school-management-system", "")
    worker = blocks.get("school-management-system-worker", "")
    beat = blocks.get("school-management-system-beat", "")

    for label, block, keys in (
        ("web", web, WEB_WORKER_KEYS),
        ("worker", worker, WEB_WORKER_KEYS),
    ):
        if not block:
            failures.append(f"render.yaml: missing {label} service block")
            continue
        present = _keys_in_block(block)
        for key in keys:
            if key not in present:
                failures.append(f"render.yaml {label}: missing env key {key}")
        for email_key in EMAIL_KEYS:
            if email_key not in present:
                failures.append(f"render.yaml {label}: missing {email_key} (Lane 2 signup/offboarding mail)")

    if not beat:
        failures.append("render.yaml: missing beat service block")
    else:
        present = _keys_in_block(beat)
        for key in BEAT_KEYS:
            if key not in present:
                failures.append(f"render.yaml beat: missing env key {key}")

    if 'TENANT_AUTO_PURGE_ENABLED\n        value: "0"' not in text.replace("\r\n", "\n"):
        failures.append(
            'render.yaml: TENANT_AUTO_PURGE_ENABLED must default to "0" until legal signoff'
        )

    if failures:
        print("verify_lifecycle_lane2_render_env: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print("verify_lifecycle_lane2_render_env: LIFECYCLE_LANE2_RENDER_ENV_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
