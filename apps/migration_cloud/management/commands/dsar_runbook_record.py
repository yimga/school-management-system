"""v3.40.0 Agent 13 — DSAR runbook recorder.

Operator runs this after completing a DSAR (Data Subject Access
Request) fulfillment. The command:

  1. Validates inputs (request_id non-empty, completed_at parseable as
     ISO-UTC).
  2. Writes a structured row to ``var/dsar-runs/<utc-iso>.json`` (one
     file per DSAR run — append-only by virtue of unique filenames).
  3. Updates ``var/dsar-last-run.txt`` with just the latest UTC ISO
     timestamp (one-line file the command center reads).
  4. Emits a ``migration.dsar.runbook_recorded`` audit event with
     payload ``{request_id_sha256_prefix, completed_at, has_notes}``.
     NEVER logs the notes content (could contain PII / FERPA-protected
     identifiers).

CLI::

    python manage.py dsar_runbook_record \\
        --request-id <opaque>      # required
        --completed-at <iso-utc>   # required; e.g. 2026-05-19T13:00:00Z
        --notes "..."              # optional; NEVER logged

The notes content is persisted ONLY in the per-run JSON file (operator
context, not audit-log material). The audit row records ``has_notes``
boolean and nothing more.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


def _var_dir() -> Path:
    """Resolve the ``var/`` directory under ``BASE_DIR``."""
    base = getattr(settings, "BASE_DIR", None)
    if base is None:
        return Path("var")
    return Path(base) / "var"


def _parse_iso_utc(value: str) -> datetime:
    """Parse a permissive ISO-8601 string and normalize to UTC.

    Accepts the trailing ``Z`` shorthand (Python's fromisoformat
    rejects it pre-3.11; we substitute ``+00:00``).
    """
    if not value:
        raise ValueError("empty completed_at")
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    dt = datetime.fromisoformat(candidate)
    if dt.tzinfo is None:
        # Naive → assume UTC (operator gave a bare ISO date-time).
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(dt_timezone.utc)


def _utc_iso_filename_stamp() -> str:
    """Compact UTC-ISO stamp safe as a filename component (no colons)."""
    return datetime.now(tz=dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_iso_now() -> str:
    """ISO-8601 UTC with explicit ``Z`` suffix (Django-compatible)."""
    return datetime.now(tz=dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_dsar_run(
    *,
    request_id: str,
    completed_at: str,
    notes: str = "",
) -> dict:
    """Pure function: record one DSAR fulfillment.

    Returns the dict that was written. Raises ``ValueError`` on bad
    input. NEVER logs the notes content; emits a structured audit row
    carrying ONLY the request-id SHA-256 prefix + has_notes boolean.

    Shared between the CLI ``Command`` and the ``DSARRunbookView`` POST
    handler so both paths produce byte-identical artifacts.
    """
    request_id = (request_id or "").strip()
    if not request_id:
        raise ValueError("--request-id must be non-empty")
    completed_dt = _parse_iso_utc(completed_at)
    completed_iso = completed_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    notes_str = notes or ""
    has_notes = bool(notes_str.strip())

    # Hashed request id — 12-char prefix for the audit row, full sha256
    # in the file row (file lives on the operator's box; never streamed
    # to a logger).
    request_id_full_sha = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    request_id_prefix = request_id_full_sha[:12]

    var_dir = _var_dir()
    runs_dir = var_dir / "dsar-runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    filename_stamp = _utc_iso_filename_stamp()
    run_file = runs_dir / f"{filename_stamp}.json"
    # Guard against collisions inside the same second.
    suffix_n = 0
    while run_file.exists():
        suffix_n += 1
        run_file = runs_dir / f"{filename_stamp}-{suffix_n}.json"

    row = {
        "recorded_at_utc_iso": _utc_iso_now(),
        "completed_at_utc_iso": completed_iso,
        "request_id_sha256": request_id_full_sha,
        "request_id_prefix": request_id_prefix,
        "has_notes": has_notes,
        "notes": notes_str,  # persisted ONLY in the local var/ file
    }
    with run_file.open("w", encoding="utf-8") as fh:
        json.dump(row, fh, sort_keys=True, indent=2)

    # Update last-run pointer.
    last_run_file = var_dir / "dsar-last-run.txt"
    last_run_file.parent.mkdir(parents=True, exist_ok=True)
    with last_run_file.open("w", encoding="utf-8") as fh:
        fh.write(row["recorded_at_utc_iso"] + "\n")

    # Audit emission — NEVER carries the notes content. Falls back to
    # the closest registered event_type when the dedicated one isn't
    # yet in the TextChoices set.
    try:
        from apps.migration_cloud.models_audit import (
            MigrationCloudAuditEvent,
            MigrationCloudAuditEventType,
        )
        valid_choices = {c.value for c in MigrationCloudAuditEventType}
        event_type = "migration.dsar.runbook_recorded"
        payload = {
            "dsar_marker": "migration.dsar.runbook_recorded",
            "request_id_sha256_prefix": request_id_prefix,
            "completed_at": completed_iso,
            "has_notes": has_notes,
        }
        if event_type not in valid_choices:
            payload["registered_choice_fallback"] = "dsar_event_type_unregistered"
            # Closest existing registered choice: AUDIT_RETENTION_PURGE_APPLIED
            # is the audit-housekeeping event most semantically adjacent.
            event_type = MigrationCloudAuditEventType.AUDIT_RETENTION_PURGE_APPLIED.value
        MigrationCloudAuditEvent.objects.record(
            tenant_slug="",  # DSAR is platform-level, not per-tenant
            event_type=event_type,
            actor=None,
            subject=request_id_prefix,
            payload_summary=payload,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud.dsar_runbook_record: audit_emit_failed err=%s",
            type(exc).__name__,
        )

    logger.info(
        "migration_cloud.dsar_runbook_record: recorded "
        "request_id_prefix=%s completed_at=%s has_notes=%s",
        request_id_prefix, completed_iso, has_notes,
    )
    return row


class Command(BaseCommand):
    """Record a completed DSAR fulfillment + update the command-center pointer."""

    help = (
        "Record a completed DSAR run. Writes var/dsar-runs/<utc-iso>.json "
        "and updates var/dsar-last-run.txt. Audit-emits a structured "
        "event carrying only sha256 prefixes (never the notes content)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--request-id",
            required=True,
            type=str,
            help="Opaque DSAR request identifier (operator-issued).",
        )
        parser.add_argument(
            "--completed-at",
            required=True,
            type=str,
            help="ISO-8601 UTC timestamp the DSAR was fulfilled.",
        )
        parser.add_argument(
            "--notes",
            default="",
            type=str,
            help="Free-form operator notes (NEVER logged or audit-emitted).",
        )

    def handle(self, *args, **options):
        try:
            row = record_dsar_run(
                request_id=options["request_id"],
                completed_at=options["completed_at"],
                notes=options.get("notes") or "",
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Recorded DSAR run: request_id_prefix={row['request_id_prefix']} "
            f"completed_at={row['completed_at_utc_iso']} has_notes={row['has_notes']}"
        ))


__all__ = ["Command", "record_dsar_run"]
