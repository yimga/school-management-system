#!/usr/bin/env python3
"""Consolidated repository gate for sovereign-platform optional completion."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "apps/compliance/audit_retention.py": [
        "verify_archive",
        "AUDIT_RETENTION_APPROVAL_TOKEN",
        "A legal hold now covers archived records",
    ],
    "apps/platform_runtime/browser_inference.py": [
        "same-origin path",
        "sha256",
        "BROWSER_AI_ENABLED",
    ],
    "apps/platform_runtime/views_local_ai.py": [
        "explicit_consent_required",
        "content_retained",
        "tenant_required",
    ],
    "services/local_voice.py": [
        "LOCAL_VOICE_ALLOWED_HOSTS",
        "_NoRedirect",
        "LOCAL_VOICE_MAX_AUDIO_BYTES",
    ],
    "services/ai_gateway.py": [
        "AI_GATEWAY_TASK_TIERS",
        "AI_PREMIUM_DAILY_CAP_PER_TENANT",
    ],
    "services/ai_deployment_posture.py": ["litellm_proxy_url"],
    "config/settings.py": [
        "DB_POOL_MODE",
        "BROWSER_AI_ENABLED",
        "LOCAL_VOICE_ENABLED",
        "AUDIT_ARCHIVE_SIGNING_KEY",
    ],
    "docs/PGBOUNCER_MULTI_SCHEMA.md": ["transaction"],
    "docs/MODULE_WORKFLOW_MAP.md": ["URL"],
    "apps/compliance/enterprise_audit.py": ["PERMISSION_GRANT"],
}


def _run(command: list[str]) -> str | None:
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode:
        return f"{' '.join(command)}\n{result.stdout[-4000:]}"
    return None


def main() -> int:
    errors: list[str] = []
    for relative, tokens in REQUIRED_TOKENS.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing required file: {relative}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in tokens:
            if token not in text:
                errors.append(f"{relative}: missing contract token {token!r}")

    catalog = json.loads(
        (ROOT / "config" / "intelligence_feature_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    experimental = {
        row["feature_id"]: row
        for row in catalog["features"]
        if row["feature_id"] in {"browser_slm", "voice_ai"}
    }
    if set(experimental) != {"browser_slm", "voice_ai"}:
        errors.append("browser and voice feature families are missing")
    for feature_id, row in experimental.items():
        if (
            row.get("implementation_status") != "implemented"
            or row.get("maximum_stage") != "repository_verified"
        ):
            errors.append(
                f"{feature_id}: must be implemented and capped at repository_verified"
            )

    commands = [
        [
            sys.executable,
            "manage.py",
            "test",
            "apps.platform_runtime.tests.test_local_ai_contracts",
            "services.tests.test_local_voice",
            "--settings=config.settings_test",
            "--noinput",
            "--verbosity=1",
        ],
        [sys.executable, "scripts/verify_audit_retention_minimal.py"],
        [
            sys.executable,
            "manage.py",
            "verify_intelligence_promotion",
            "--stage",
            "repository_verified",
            "--strict",
        ],
        [
            sys.executable,
            "manage.py",
            "makemigrations",
            "compliance",
            "--check",
            "--dry-run",
        ],
        [sys.executable, "manage.py", "check"],
        ["node", "--check", "static/js/rmc-browser-inference-worker.js"],
        ["node", "--check", "static/js/rmc-local-ai-accessibility.js"],
    ]
    for command in commands:
        failure = _run(command)
        if failure:
            errors.append(failure)

    if errors:
        print("SOVEREIGN_OPTIONALS_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "SOVEREIGN_OPTIONALS_PASS "
        "browser=repository_verified voice=repository_verified "
        "retention=archive_before_purge pooling=fail_closed_transaction"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
