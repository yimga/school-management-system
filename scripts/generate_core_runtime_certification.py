#!/usr/bin/env python3
"""Core runtime certification artifact from audit + in-repo gate checks.

Writes:
  docs/generated/core_runtime_certification.json
  docs/generated/core_runtime_certification.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT_JSON = ROOT / "docs" / "generated" / "core_runtime_dependency_audit.json"
CERT_JSON = ROOT / "docs" / "generated" / "core_runtime_certification.json"
CERT_MD = ROOT / "docs" / "generated" / "core_runtime_certification.md"


def _bootstrap_django() -> None:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _gate_checks() -> list[dict]:
    from django.conf import settings
    from django.urls import NoReverseMatch, reverse

    gates: list[dict] = []

    def add(gate_id: str, ok: bool, note: str) -> None:
        gates.append({"id": gate_id, "ok": ok, "note": note})

    add(
        "cors_no_allow_all",
        not bool(getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False)),
        "CORS_ALLOW_ALL_ORIGINS must remain disabled",
    )
    add(
        "drf_default_authenticated",
        "IsAuthenticated"
        in str(
            (getattr(settings, "REST_FRAMEWORK", {}) or {}).get(
                "DEFAULT_PERMISSION_CLASSES", ()
            )
        ),
        "DRF default permission is IsAuthenticated",
    )
    add(
        "jwt_simple_jwt_configured",
        bool(getattr(settings, "SIMPLE_JWT", None)),
        "SIMPLE_JWT settings block present",
    )
    add(
        "mfa_middleware_present",
        "apps.accounts.middleware.RequireMFAMiddleware"
        in list(getattr(settings, "MIDDLEWARE", [])),
        "RequireMFAMiddleware wired",
    )
    add(
        "celery_eager_in_tests",
        not getattr(settings, "RUNNING_TESTS", False)
        or bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)),
        "CELERY_TASK_ALWAYS_EAGER when RUNNING_TESTS",
    )

    jwt_routes = ("api:token_obtain_pair", "api:token_refresh", "api:ai-support-assistant")
    for name in jwt_routes:
        try:
            reverse(name)
            add(f"route_{name.replace(':', '_')}", True, "resolves")
        except NoReverseMatch as exc:
            add(f"route_{name.replace(':', '_')}", False, str(exc))

    return gates


def build_certification(audit: dict) -> dict:
    gates = _gate_checks()
    failed = [g for g in gates if not g["ok"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "CORE RUNTIME READY — REPO SCOPE"
        if not failed
        else "CORE RUNTIME NOT READY — REPO SCOPE",
        "repo_scope_only": True,
        "external_blockers": [
            "live_render_celery_worker_health",
            "production_redis_channel_layer_proof",
        ],
        "audit_ref": str(AUDIT_JSON.relative_to(ROOT)).replace("\\", "/"),
        "audit_generated_at": audit.get("generated_at"),
        "gates": gates,
        "failed_gate_count": len(failed),
        "focused_test_modules": [
            "apps.security.tests.test_cors_csrf_tenant_runtime",
            "apps.accounts.tests.test_mfa_jwt_runtime_contracts",
            "apps.platform_runtime.tests.test_core_runtime_integrity",
            "apps.security.tests.test_auth_runtime_boundaries",
            "apps.observability.tests.test_async_runtime_contracts",
        ],
    }


def _write_md(data: dict) -> str:
    lines = [
        "# Core runtime certification",
        "",
        f"**Generated:** {data['generated_at']}",
        f"**Verdict:** {data['verdict']}",
        "",
        f"Audit reference: `{data['audit_ref']}`",
        "",
        "## Gates",
        "",
        "| Gate | OK | Note |",
        "|------|----|------|",
    ]
    for g in data["gates"]:
        lines.append(f"| {g['id']} | {g['ok']} | {g['note']} |")
    lines.extend(["", "## External (not repo-proven)", ""])
    for item in data["external_blockers"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not args.write:
        args.write = True

    if not AUDIT_JSON.is_file():
        import subprocess

        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts/generate_core_runtime_dependency_audit.py"), "--write"],
            cwd=str(ROOT),
        )

    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    _bootstrap_django()
    data = build_certification(audit)
    CERT_JSON.parent.mkdir(parents=True, exist_ok=True)
    CERT_JSON.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    CERT_MD.write_text(_write_md(data), encoding="utf-8")
    print(f"Wrote {CERT_JSON.relative_to(ROOT)}")
    print(f"Verdict: {data['verdict']}")
    return 1 if data["failed_gate_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
