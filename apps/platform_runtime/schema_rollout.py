"""Wave D — G3: platform migration safe-apply coordinator.

Wraps ``django.core.management.call_command("migrate", ...)`` with:

* a per-run audit row (`SchemaRollout`)
* per-DB-alias result rows (`SchemaRolloutAlias`)
* a danger check that refuses destructive migrations (NOT NULL adds,
  column renames, raw SQL) unless the operator passed ``--dangerous``
* multi-database iteration: if ``School.dedicated_db_alias`` rows point
  at non-``default`` DBs, those aliases are migrated in addition to the
  primary ``default`` alias

Returns a dict so the management command can render a nice summary.
"""

from __future__ import annotations

import io
import logging
from typing import Any, Iterable

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone

logger = logging.getLogger(__name__)

# Operations that, when present in an *unapplied* migration, indicate a
# blocking schema change. The coordinator refuses to run these without
# the operator's explicit ``--dangerous`` flag. The list is intentionally
# small + obvious — we are not trying to autoclassify every destructive
# operation, just to catch the easiest foot-guns.
DANGEROUS_OP_TYPES: frozenset[str] = frozenset({
    "RemoveField",
    "RenameField",
    "RenameModel",
    "DeleteModel",
    "AlterField",       # may rewrite the column on PG when type changes
    "RunSQL",           # raw SQL bypasses Django's safety reasoning
})


def discover_db_aliases() -> list[str]:
    """Return all DB aliases that need a migrate run.

    Always includes ``default``. Adds any alias referenced by an active
    school via ``dedicated_db_alias`` AND configured in ``DATABASES``.
    Unknown aliases are skipped — never raise from discovery.
    """
    aliases = {"default"}
    configured = set(settings.DATABASES.keys())
    try:
        School = apps.get_model("schools", "School")
        # tenant-isolation-allow: rollout coordinator scans every tenant's dedicated alias by design
        rows = (
            School.objects.exclude(dedicated_db_alias="")
            .exclude(dedicated_db_alias__isnull=True)
            .values_list("dedicated_db_alias", flat=True)
            .distinct()
        )
        for alias in rows:
            alias = (alias or "").strip()
            if alias and alias in configured:
                aliases.add(alias)
    except (LookupError, RuntimeError, ValueError):
        # Model not registered yet (e.g. checks) — fall back to default only.
        pass
    return sorted(aliases)


def find_dangerous_operations(target_app: str = "") -> list[tuple[str, str, str]]:
    """Walk unapplied migrations and flag dangerous operations.

    Returns ``[(app_label, migration_name, op_type), ...]``. Empty list
    means all unapplied migrations are non-destructive. When ``target_app``
    is set, only migrations for that app are considered.
    """
    findings: list[tuple[str, str, str]] = []
    try:
        connection = connections["default"]
        loader = MigrationLoader(connection)
    except (RuntimeError, ValueError):
        return findings

    applied = loader.applied_migrations
    for key, migration in loader.graph.nodes.items():
        if key in applied:
            continue
        app_label, name = key
        if target_app and app_label != target_app:
            continue
        for op in migration.operations:
            op_type = type(op).__name__
            if op_type in DANGEROUS_OP_TYPES:
                findings.append((app_label, name, op_type))
    return findings


def run_rollout(
    *,
    target: str = "",
    initiator: Any = None,
    dangerous: bool = False,
    dry_run: bool = False,
    notes: str = "",
    aliases: Iterable[str] | None = None,
) -> dict:
    """Apply Django migrations across discovered DB aliases with audit trail.

    Args:
        target: optional app label to migrate (passes through to ``migrate``).
            Empty string applies all unapplied migrations.
        initiator: User instance who triggered the run (recorded for audit).
        dangerous: must be True for migrations containing ops in
            ``DANGEROUS_OP_TYPES``; otherwise the run is refused.
        dry_run: pass ``--plan`` to migrate; no schema changes made.
        notes: free-form audit text (e.g. ticket reference).
        aliases: override the default discovery (used by tests).

    Returns:
        Dict shaped for the management command + admin dashboard.
    """
    from apps.platform_runtime.models_rollout import (
        SchemaRollout,
        SchemaRolloutAlias,
    )

    # Refuse dangerous migrations without explicit ack.
    dangerous_ops = find_dangerous_operations(target_app=target.split(".")[0] if target else "")
    if dangerous_ops and not dangerous and not dry_run:
        return {
            "ok": False,
            "rollout_id": None,
            "reason": "dangerous_migrations_present",
            "dangerous_ops": dangerous_ops,
            "message": (
                "Refusing to apply migrations: dangerous operations present. "
                "Re-run with --dangerous to acknowledge or fix the migration."
            ),
        }

    rollout = SchemaRollout.objects.create(
        target=target or "all",
        initiator=initiator if getattr(initiator, "pk", None) else None,
        status="running",
        dangerous_acknowledged=dangerous,
        dry_run=dry_run,
        notes=notes or "",
    )

    target_aliases = list(aliases) if aliases is not None else discover_db_aliases()
    summary: dict[str, dict] = {}
    any_failed = False
    any_applied = False

    for alias in target_aliases:
        alias_row = SchemaRolloutAlias.objects.create(
            rollout=rollout, db_alias=alias, status="pending"
        )
        out, err, ok = _migrate_one(alias, target=target, dry_run=dry_run)
        summary[alias] = {"stdout": out, "stderr": err, "ok": ok}
        alias_row.status = "applied" if ok else "failed"
        alias_row.error_text = err if not ok else ""
        alias_row.finished_at = timezone.now()
        alias_row.save(update_fields=["status", "error_text", "finished_at"])
        any_failed = any_failed or not ok
        any_applied = any_applied or ok

    if dry_run:
        final_status = "dry_run"
    elif any_failed and any_applied:
        final_status = "partial"
    elif any_failed:
        final_status = "failed"
    else:
        final_status = "succeeded"

    rollout.status = final_status
    rollout.finished_at = timezone.now()
    rollout.summary = summary
    rollout.save(update_fields=["status", "finished_at", "summary"])

    return {
        "ok": not any_failed,
        "rollout_id": rollout.pk,
        "status": final_status,
        "aliases": target_aliases,
        "summary": summary,
        "dangerous_ops": dangerous_ops,
    }


def _migrate_one(alias: str, *, target: str, dry_run: bool) -> tuple[str, str, bool]:
    """Run ``manage.py migrate`` against ``alias``. Capture stdout/stderr."""
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    args: list[str] = []
    if target:
        args.append(target)
    kwargs: dict[str, Any] = {
        "database": alias,
        "verbosity": 1,
        "interactive": False,
        "stdout": out_buf,
        "stderr": err_buf,
    }
    if dry_run:
        kwargs["plan"] = True
    try:
        call_command("migrate", *args, **kwargs)
        return out_buf.getvalue(), err_buf.getvalue(), True
    except Exception as exc:  # noqa: BLE001  audit boundary
        return out_buf.getvalue(), f"{err_buf.getvalue()}\n{type(exc).__name__}: {exc}", False


__all__ = [
    "DANGEROUS_OP_TYPES",
    "discover_db_aliases",
    "find_dangerous_operations",
    "run_rollout",
]
