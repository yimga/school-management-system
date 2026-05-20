#!/usr/bin/env python3
"""Policy / entitlement / metadata / registry runtime discovery audit.

Writes:
  docs/generated/policy_entitlement_runtime_audit.json
  docs/generated/policy_entitlement_runtime_audit.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_OUT = ROOT / "docs" / "generated" / "policy_entitlement_runtime_audit.json"
MD_OUT = ROOT / "docs" / "generated" / "policy_entitlement_runtime_audit.md"


def _bootstrap_django() -> None:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _module_exists(rel: str) -> bool:
    return (ROOT / rel.replace("/", os.sep)).is_file()


def build_audit() -> dict:
    _bootstrap_django()
    from apps.platform_runtime.administration_catalog import REGISTRIES
    from apps.platform_runtime.registry_health import evaluate_registry_health

    now = datetime.now(timezone.utc)
    registry_rows = []
    for entry in REGISTRIES:
        proof = str(entry.get("proof") or "").lstrip("/")
        test = str(entry.get("test") or "").lstrip("/")
        registry_rows.append(
            {
                **dict(entry),
                "proof_exists": _module_exists(proof) if proof.startswith("apps/") else (ROOT / proof).is_file(),
                "test_exists": _module_exists(test) if test else False,
                "generated_at": now.isoformat(),
            }
        )
    route_inventory = {str(r.get("route") or "") for r in REGISTRIES}
    health = evaluate_registry_health(
        [
            {
                **dict(row),
                "generated_at": now,
            }
            for row in REGISTRIES
        ],
        route_inventory=route_inventory,
    )

    gates = {
        "entitlement_gates": _module_exists("apps/platform_runtime/entitlement_gates.py"),
        "billing_entitlements": _module_exists("apps/billing/entitlements.py"),
        "policy_pdp": _module_exists("apps/policies/pdp.py"),
        "policy_registry": _module_exists("apps/policies/policy_registry.py"),
        "metadata_ddl_safety": _module_exists("apps/metadata/ddl_safety.py"),
        "metadata_governance": _module_exists("apps/platform_runtime/metadata_governance.py"),
        "setup_studio_tenant_guard": _module_exists("apps/setup_studio/tenant_guard.py"),
        "registry_health_engine": _module_exists("apps/platform_runtime/registry_health.py"),
    }

    return {
        "generated_at": now.isoformat(),
        "metadata_only": True,
        "pii_free": True,
        "target_apps": [
            "billing",
            "plans_entitlements",
            "policies",
            "metadata",
            "packages",
            "runtime_blueprints",
            "registries",
            "global_registries",
            "brand_experience",
            "setup_studio",
        ],
        "central_gate_modules": gates,
        "registry_count": len(REGISTRIES),
        "registry_health": health,
        "registry_rows": registry_rows,
        "focused_test_modules": [
            "apps.platform_runtime.tests.test_entitlement_policy_runtime",
            "apps.metadata.tests.test_metadata_no_ddl_safety",
            "apps.registries.tests.test_registry_health_contracts",
            "apps.setup_studio.tests.test_setup_studio_configuration_flow",
        ],
        "ok": all(gates.values()) and health.get("ok"),
    }


def _write_md(data: dict) -> str:
    lines = [
        "# Policy entitlement runtime audit",
        "",
        f"**Generated:** {data['generated_at']}",
        f"**OK:** {data['ok']}",
        "",
        "## Central gates",
        "",
    ]
    for key, ok in sorted(data["central_gate_modules"].items()):
        lines.append(f"- {key}: {'PASS' if ok else 'FAIL'}")
    lines.extend(
        [
            "",
            f"## Registries ({data['registry_count']})",
            "",
            f"Health OK: {data['registry_health'].get('ok')}",
            f"High severity: {data['registry_health'].get('high_count', 0)}",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not args.write:
        args.write = True

    data = build_audit()
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MD_OUT.write_text(_write_md(data), encoding="utf-8")
    print(f"Wrote {JSON_OUT.relative_to(ROOT)}")
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
