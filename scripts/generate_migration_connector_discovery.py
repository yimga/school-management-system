#!/usr/bin/env python3
"""Generate Migration Cloud connector discovery artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "docs" / "generated" / "migration_cloud_connector_discovery.json"
OUT_MD = ROOT / "docs" / "generated" / "migration_cloud_connector_discovery.md"
REG_JSON = ROOT / "docs" / "generated" / "migration_connector_registry.json"
REG_MD = ROOT / "docs" / "generated" / "migration_connector_registry.md"


def main() -> int:
    discovery = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "existing_primitives": {
            "bundle_lifecycle": "apps.migration_cloud.models.MigrationBundle + MigrationArtifact",
            "intake_adapters": "apps.migration_cloud.intake.* (file, archive, url, oauth, pdf, access, sql_dump)",
            "accelerators": "apps.migration_cloud.accelerators.* (6 SIS vendors + OneRoster + canonical)",
            "landers": "apps.migration_cloud.landers.* (24+ domains)",
            "preview_mapping": "apps.platform_runtime.migration_center",
            "audit_chain": "apps.migration_cloud.models_audit.MigrationCloudAuditEvent",
            "customer_intake": "apps.migration_cloud.models_intake.MigrationIntakeRequest",
            "companion": "companion-extension/ + companion_receiver.py",
        },
        "new_connector_layer": {
            "models": "apps.migration_cloud.models_connectors",
            "services": [
                "connector_credentials",
                "connector_discovery",
                "connector_mapping",
                "connector_import",
                "connector_bundle_bridge",
                "connector_rollback",
                "connector_audit",
            ],
            "intake": ["api_pull_intake", "database_intake (sqlite)"],
            "adapters": "apps.migration_cloud.connectors",
            "tenant_routes": "/school/setup/migration-cloud/",
            "operator_routes": "/super/migration/connectors/",
        },
        "missing_pieces_deferred": [
            "Live vendor API pull (IntakeMethod.API_PULL Phase U9)",
            "DatabaseIntakeAdapter / EmailIntakeAdapter (Phase U7)",
            "OAuth Google Classroom connector (planned)",
            "Ed-Fi production connector (planned)",
            "FACTS/Skyward write paths (counsel-blocked in companion)",
        ],
        "recommended_architecture": "Authorized connection → verify → discover → stage → map → validate → quarantine → import via MigrationBundle; credentials memory-only default; audit dual-write.",
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(discovery, indent=2), encoding="utf-8")

    md = [
        "# Migration Cloud connector discovery",
        "",
        f"Generated: {discovery['generated_at']}",
        "",
        "## Existing primitives (reuse)",
        "",
    ]
    for k, v in discovery["existing_primitives"].items():
        md.append(f"- **{k}:** `{v}`")
    md.extend(["", "## New connector layer", ""])
    for k, v in discovery["new_connector_layer"].items():
        md.append(f"- **{k}:** `{v}`")
    md.extend(["", "## Deferred", ""])
    for item in discovery["missing_pieces_deferred"]:
        md.append(f"- {item}")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    # Registry — introspect live adapters when Django is importable.
    connectors: list[dict] = []
    try:
        import os
        import sys

        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        import django

        django.setup()
        from apps.migration_cloud.connectors import list_connectors
        from apps.migration_cloud.connectors.base import get_connector

        for key in sorted(list_connectors()):
            adapter = get_connector(key)
            if adapter is None:
                continue
            row = {
                "key": key,
                "certification_status": adapter.certification,
                "supported_methods": list(
                    getattr(adapter, "supported_methods", None) or ["file_export"]
                ),
                "test_evidence": "apps.migration_cloud.tests.test_connector_registry",
            }
            if key in ("powerschool", "blackbaud", "veracross"):
                row["test_evidence"] = "apps.migration_cloud.tests.test_vendor_connectors"
            connectors.append(row)
    except Exception as exc:  # pragma: no cover - fallback for doc-only generation
        connectors = [
            {
                "key": "generic_csv_export",
                "name": "Generic CSV / Excel export",
                "certification_status": "production_ready",
                "supported_methods": ["file_export", "manual_template"],
                "test_evidence": "apps.migration_cloud.tests.test_connector_registry",
                "owner": "migration_cloud",
                "fallback_reason": str(exc),
            },
        ]
    registry = {
        "generated_at": discovery["generated_at"],
        "connectors": connectors,
        "canonical_school_payload": "apps.platform_runtime.migration_center.MIGRATION_TEMPLATES",
    }
    REG_JSON.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    REG_MD.write_text(
        "# Migration connector registry\n\nSee `migration_connector_registry.json` for machine-readable rows.\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {REG_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
