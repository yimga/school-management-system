"""Runtime-configurable defaults for the Migration Cloud (no hardcoding).

Every value an operator or tenant might want to tune (MIME whitelist, size
caps, parallel-worker count, SLA targets, confidence thresholds, retention
windows) lives in ``RuntimeDefaults.payload`` under a stable key and is read
through the helpers below. The constants in this module are *seeded
fallbacks* — the value returned when the cascade has no override yet. They
are the bottom of the 7-layer configurability contract, never the top.

Cascade order applied at read time:
    tenant SiteSettings → env override → RuntimeDefaults.payload → seed fallback

If a key changes shape (e.g. add a new MIME type), update the seed below
**and** ship a RuntimeDefaults data migration so existing tenants see the
new value without code-path regressions.
"""

from __future__ import annotations

import os
from typing import Any

# --- Seed fallbacks (bottom of the cascade) ---------------------------------
# Keep in sync with: docs/MIGRATION_UNIVERSAL_INTAKE.md (operator-visible)
# and any data migration that seeds RuntimeDefaults for these keys.

_SEED: dict[str, Any] = {
    # Formats we accept at intake. Anything else is registered as UNKNOWN and
    # quarantined for operator review — never silently dropped.
    "migration_cloud.intake.allowed_mime_types": [
        "text/csv",
        "text/tab-separated-values",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
        "application/vnd.ms-excel",
        "application/vnd.ms-excel.sheet.macroenabled.12",
        "application/json",
        "application/x-ndjson",
        "application/xml",
        "text/xml",
        "application/sql",
        "application/x-sqlite3",
        "application/vnd.apache.parquet",
        "application/zip",
        "application/x-tar",
        "application/gzip",
        "application/x-7z-compressed",
        "application/pdf",
        "application/x-msaccess",
        "application/vnd.ms-access",
        "application/msaccess",
        "image/png",
        "image/jpeg",
        "image/tiff",
        "application/octet-stream",  # fall-through; the profiler sniffs the bytes
    ],
    "migration_cloud.intake.allowed_extensions": [
        ".csv", ".tsv", ".xlsx", ".xls", ".json", ".jsonl", ".ndjson",
        ".xml", ".sql", ".db", ".sqlite", ".sqlite3", ".parquet",
        ".zip", ".tar", ".gz", ".tgz", ".7z", ".bz2",
        ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
        ".mdb", ".accdb", ".bak", ".dump",
    ],
    # Per-bundle byte caps by SLA tier.
    "migration_cloud.intake.max_bundle_bytes_small": 200 * 1024 * 1024,
    "migration_cloud.intake.max_bundle_bytes_mid": 2 * 1024 * 1024 * 1024,
    "migration_cloud.intake.max_bundle_bytes_large": 20 * 1024 * 1024 * 1024,
    # Per-artifact caps (single file inside the bundle).
    "migration_cloud.intake.max_artifact_bytes": 5 * 1024 * 1024 * 1024,
    # Archive expansion safety.
    "migration_cloud.intake.max_archive_members": 50_000,
    "migration_cloud.intake.max_archive_depth": 8,
    # SLO wall-clock targets in seconds per tier (asserted as soft alerts).
    "migration_cloud.slo.small_seconds": 60 * 60,           # 1h
    "migration_cloud.slo.mid_seconds": 4 * 60 * 60,         # 4h
    "migration_cloud.slo.large_seconds": 12 * 60 * 60,      # 12h
    # Worker fan-out for parallel domain ingest (Phase U5).
    "migration_cloud.orchestrator.worker_count": 8,
    # Classifier confidence thresholds (Phase U3/U4). Below these the
    # operator is asked to review; never auto-applied.
    "migration_cloud.classifier.source_min_confidence": 0.65,
    "migration_cloud.classifier.domain_min_confidence": 0.70,
    "migration_cloud.mapper.field_min_confidence": 0.80,
    # Retention for raw bundle storage after RECONCILED, in days.
    "migration_cloud.retention.raw_bundle_days": 90,
    # sms-v3.7 — Tier 1 / Tier 2 / Tier 3 tunables.
    # Financial guardrail (Tier 1 #1): absolute + relative tolerance for control totals.
    "migration_cloud.guardrail.tolerance_abs": "0.01",
    "migration_cloud.guardrail.tolerance_rel": "0.001",
    # Asset pipeline (Tier 1 #2): per-batch ceiling for fetch_pending_assets.
    "migration_cloud.assets.max_batch": 100,
    "migration_cloud.assets.http_timeout_seconds": 30,
    # Cost predictor (Tier 3 #18): heuristic AI-call token cost.
    "migration_cloud.cost.avg_tokens_per_call": 800,
    "migration_cloud.cost.usd_per_1k_tokens": 0.002,
    # Pre-flight capacity ceilings per SLA tier (Tier 2 #11).
    "migration_cloud.preflight.capacity": {
        "small": {"max_students": 1500, "max_bytes": 524288000, "max_rows": 250000},
        "mid": {"max_students": 15000, "max_bytes": 5368709120, "max_rows": 5000000},
        "large": {"max_students": 75000, "max_bytes": 26843545600, "max_rows": 50000000},
        "state": {"max_students": 1000000, "max_bytes": 268435456000, "max_rows": 1000000000},
    },
    # SLA tier targets in minutes (Tier 3 #23).
    "migration_cloud.sla.targets": {
        "small": {"target_minutes": 60, "escalate_minutes": 120},
        "mid": {"target_minutes": 240, "escalate_minutes": 480},
        "large": {"target_minutes": 720, "escalate_minutes": 1440},
        "state": {"target_minutes": 4320, "escalate_minutes": 7200},
    },
    # OCR confidence warning thresholds (Tier 3 #22).
    "migration_cloud.ocr.min_chars_for_decision": 40,
    "migration_cloud.ocr.low_confidence_threshold": 0.5,
    # Network resilience (Tier 2 #14).
    "migration_cloud.network.max_retries": 5,
    "migration_cloud.network.fetch_timeout_seconds": 30,
}


def get(key: str) -> Any:
    """Read a Migration Cloud setting from the cascade.

    Lookup order:
      1. Environment variable ``MIGRATION_CLOUD__<KEY_UPPER>`` (operator override).
      2. ``RuntimeDefaults.payload[key]`` if the row exists (platform default).
      3. Seed fallback from this module.

    The env-var rung is included so the platform team can hotfix a value in
    production without a deploy. The seed fallback is only reached during
    bootstrap before the first ``RuntimeDefaults`` row has been written.
    """
    env_key = "MIGRATION_CLOUD__" + key.replace(".", "__").upper()
    if env_key in os.environ:
        return _coerce(os.environ[env_key], _SEED.get(key))

    try:
        from apps.platform_runtime.models import RuntimeDefaults

        rd = RuntimeDefaults.objects.first()
        if rd is not None:
            payload = rd.payload or {}
            if key in payload:
                return payload[key]
    except Exception:  # noqa: BLE001 — bootstrap / unmigrated DBs return seed
        pass

    if key not in _SEED:
        raise KeyError(f"Unknown migration_cloud default: {key!r}")
    return _SEED[key]


def _coerce(raw: str, reference: Any) -> Any:
    """Best-effort coercion of an env-var string to match the seed's shape."""
    if isinstance(reference, bool):
        return raw.lower() in ("1", "true", "yes", "on")
    if isinstance(reference, int):
        return int(raw)
    if isinstance(reference, float):
        return float(raw)
    if isinstance(reference, list):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


def seed_payload_patch() -> dict[str, Any]:
    """Return the keys/values a data migration should seed into RuntimeDefaults.

    Called by the ``RuntimeDefaults`` seed migration so the cascade has every
    Migration Cloud key materialized at install time. Re-running this is safe;
    callers should merge over existing payload, not replace.
    """
    return dict(_SEED)
