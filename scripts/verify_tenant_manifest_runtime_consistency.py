from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(ROOT))

    import django

    django.setup()

    failures: list[str] = []

    from apps.schools.models import School
    from apps.sync_engine.tenant_manifest_compiler import SCHEMA_VERSION
    from apps.sync_engine.tenant_manifest_resolver import (
        build_school_offline_manifest,
        school_offline_manifest_dict,
    )

    compiler_text = (ROOT / "apps/sync_engine/tenant_manifest_compiler.py").read_text(
        encoding="utf-8"
    )
    if SCHEMA_VERSION < 2:
        failures.append(f"SCHEMA_VERSION must be >= 2 (got {SCHEMA_VERSION})")
    if "operational_context" not in compiler_text:
        failures.append("tenant_manifest_compiler missing operational_context")

    school = School.objects.filter(slug="demo-school", is_active=True).first()
    if school is None:
        school = School.objects.filter(is_active=True).order_by("created_at").first()
    if school is None:
        failures.append("no active school available for manifest consistency check")
    else:
        live = build_school_offline_manifest(school)
        stored_settings = getattr(school, "settings", None) or {}
        snapshot = (
            stored_settings.get("tenant_manifest_snapshot")
            if isinstance(stored_settings, dict)
            else None
        )

        if live.schema_version < 2:
            failures.append("compiled manifest schema_version < 2")
        if not live.operational_context.get("schema_contract"):
            failures.append("operational_context missing schema_contract")
        if not live.operational_context.get("operational_state"):
            failures.append("operational_context missing operational_state")

        live_dict = live.to_dict()
        resolver_dict = school_offline_manifest_dict(school)
        for key in ("schema_version", "tenant_id_hash", "checksum"):
            if live_dict.get(key) != resolver_dict.get(key):
                failures.append(f"manifest dict mismatch on {key}")

        if snapshot and isinstance(snapshot, dict):
            if snapshot.get("schema_version", 0) < 2:
                failures.append(
                    "school.settings tenant_manifest_snapshot schema_version < 2 "
                    "(run apply_tenant_seed_blueprint)"
                )

    if failures:
        print("verify_tenant_manifest_runtime_consistency: FAIL")
        for f in failures:
            print(f"- {f}")
        return 1

    print(
        "verify_tenant_manifest_runtime_consistency: "
        "TENANT_MANIFEST_RUNTIME_CONSISTENCY_PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
