#!/usr/bin/env python3
"""Offline manifest capability taxonomy — schema v2 + honest payment posture."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

# Capability tiers consumed by edge/PWA planners (batch 1726 cycle 11).
OFFLINE_CAPABILITY_TIERS: dict[str, frozenset[str]] = {
    "OFFLINE_SAFE_READ": frozenset(
        {
            "routes_allowlist",
            "locale_default",
            "operational_context",
            "pwa_cache_hints",
        }
    ),
    "OFFLINE_QUEUED_WRITE": frozenset(
        {
            "enable_offline_form_queue",
            "enable_offline_attendance_sync",
            "enable_offline_grade_sync",
            "enable_offline_homework_sync",
            "enable_offline_fee_payment_sync",
            "enable_offline_migration_cloud_upload",
        }
    ),
    "OFFLINE_BACKGROUND_SYNC": frozenset(
        {
            "enable_offline_background_sync",
            "offline_entity_sync",
            "offline_requests_sync",
        }
    ),
    "ONLINE_ONLY_PAYMENT": frozenset({"live_collection"}),
}


def main() -> int:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from apps.sync_engine.feature_flag_registry import known_feature_flags
    from apps.sync_engine.tenant_manifest_compiler import SCHEMA_VERSION
    from apps.sync_engine.tenant_manifest_resolver import build_school_offline_manifest

    failures: list[str] = []

    school = SimpleNamespace(
        id=99,
        schema_name="tenant_demo_school",
        country_code="BF",
        slug="demo-school",
    )
    manifest = build_school_offline_manifest(school)
    payload = manifest.to_dict()

    if payload.get("schema_version") != SCHEMA_VERSION:
        failures.append(
            f"schema_version expected {SCHEMA_VERSION}, got {payload.get('schema_version')}"
        )

    for key in OFFLINE_CAPABILITY_TIERS["OFFLINE_SAFE_READ"]:
        if key not in payload or payload[key] in (None, "", [], {}):
            failures.append(f"missing or empty manifest field: {key}")

    flags = payload.get("feature_flags") or {}
    if not isinstance(flags, dict) or not flags:
        failures.append("feature_flags missing or empty")
    else:
        unknown = sorted(set(flags) - set(known_feature_flags()))
        if unknown:
            failures.append(f"manifest feature_flags unknown keys: {unknown[:5]}")
        queued = OFFLINE_CAPABILITY_TIERS["OFFLINE_QUEUED_WRITE"]
        if not queued.intersection(flags.keys()):
            failures.append("no OFFLINE_QUEUED_WRITE flags present in manifest")

    payment = (payload.get("data_policies") or {}).get("payment") or {}
    if payment.get("live_collection") is True and payment.get("data_state") != "defined":
        failures.append("live_collection true without defined payment corridor")
    allowed_states = {"placeholder", "defined", "unknown"}
    if payment.get("data_state") not in allowed_states:
        failures.append(f"unexpected payment data_state: {payment.get('data_state')}")

    op_ctx = payload.get("operational_context") or {}
    if "operational_state" not in op_ctx:
        failures.append("operational_context missing operational_state")

    routes = payload.get("routes_allowlist") or []
    if not routes or not all(str(r).startswith("/") for r in routes):
        failures.append("routes_allowlist must be non-empty absolute paths")

    if failures:
        print("verify_offline_manifest_taxonomy: FAIL")
        for item in failures:
            print(f"- {item}")
        return 1

    print(
        "verify_offline_manifest_taxonomy: "
        f"OFFLINE_MANIFEST_TAXONOMY_PASS (tiers={len(OFFLINE_CAPABILITY_TIERS)}, "
        f"flags={len(flags)}, routes={len(routes)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
