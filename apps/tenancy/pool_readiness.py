"""Configuration readiness for direct, session-pooled, and transaction-pooled DB endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from apps.tenancy.checks import SUPPORTED_DB_POOL_MODES


@dataclass(frozen=True)
class DatabasePoolReadiness:
    mode: str
    engine: str
    conn_max_age: int
    server_side_cursors_disabled: bool
    supported: bool
    reason: str
    live_interleaving_test_required: bool


def assess_database_pool_readiness() -> DatabasePoolReadiness:
    default_db = settings.DATABASES.get("default") or {}
    mode = str(getattr(settings, "DB_POOL_MODE", "direct") or "").strip().lower()
    engine = str(default_db.get("ENGINE") or "")
    conn_max_age = int(default_db.get("CONN_MAX_AGE") or 0)
    cursors_disabled = bool(default_db.get("DISABLE_SERVER_SIDE_CURSORS", False))
    if mode not in SUPPORTED_DB_POOL_MODES:
        return DatabasePoolReadiness(
            mode=mode,
            engine=engine,
            conn_max_age=conn_max_age,
            server_side_cursors_disabled=cursors_disabled,
            supported=False,
            reason="invalid DB_POOL_MODE",
            live_interleaving_test_required=False,
        )
    if mode == "transaction" and "postgresql" in engine:
        return DatabasePoolReadiness(
            mode=mode,
            engine=engine,
            conn_max_age=conn_max_age,
            server_side_cursors_disabled=cursors_disabled,
            supported=False,
            reason=(
                "transaction pooling cannot preserve the current session-level "
                "search_path/app.current_school_id tenant context"
            ),
            live_interleaving_test_required=True,
        )
    return DatabasePoolReadiness(
        mode=mode,
        engine=engine,
        conn_max_age=conn_max_age,
        server_side_cursors_disabled=cursors_disabled,
        supported=True,
        reason=(
            "direct endpoint"
            if mode == "direct"
            else "server sessions remain pinned for tenant session state"
        ),
        live_interleaving_test_required=False,
    )
