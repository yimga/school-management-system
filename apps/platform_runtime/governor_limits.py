"""
Governor limits (plan H5 / Codex §10).
Enforceable limits for workflow, API, migration, bulk, AI, dynamic fields, pack complexity.
"""
from __future__ import annotations

# Default limits; override via settings.PLATFORM_GOVERNOR_LIMITS or env.
DEFAULT_LIMITS = {
    "workflow_runs_per_tenant_per_hour": 1000,
    "api_requests_per_minute_per_tenant": 300,
    "migration_concurrent_runs": 2,
    "bulk_export_max_rows": 50_000,
    "ai_invocations_per_tenant_per_day": 500,
    "dynamic_fields_per_entity": 100,
    "pack_dependency_depth": 5,
}


def get_limit(key: str) -> int:
    """Return effective limit for key (from settings or DEFAULT_LIMITS)."""
    from django.conf import settings
    custom = getattr(settings, "PLATFORM_GOVERNOR_LIMITS", None) or {}
    return int(custom.get(key, DEFAULT_LIMITS.get(key, 0)))
