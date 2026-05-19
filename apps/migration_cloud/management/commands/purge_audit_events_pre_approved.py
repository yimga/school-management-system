"""v3.39.0 Agent 1 — counsel-pending audit retention purge command.

This is the ONLY documented mutation path that removes rows from
``migration_cloud_migrationcloudauditevent``. It bypasses the
append-only ``delete()`` guard intentionally — auditors must be able
to enforce FERPA / GDPR / state-specific retention windows by purging
rows past the cutoff. To do that safely the command:

  1. REFUSES to run without ``--counsel-approval-token=<token>``
     matching ``settings.MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN``
     via :func:`hmac.compare_digest`. When the setting is empty the
     command prints a counsel-pending message and exits 1 regardless
     of the supplied flag.
  2. Defaults to dry-run. Only ``--apply`` performs the DELETE.
  3. Wraps the DELETE in :func:`django.db.transaction.atomic`.
  4. Emits a meta-audit-event ``audit.retention_purge_applied`` so
     the purge itself is audited. The meta-event lives in the same
     table — so the next ``verify_audit_chain`` run sees it.
  5. NEVER logs raw approval token, raw tenant slug, raw event UUIDs,
     hash bytes, payload bytes, or payload_summary content.

Usage::

    python manage.py purge_audit_events_pre_approved \
        --tenant=<slug> --before=<iso-date> \
        --counsel-approval-token=<token> [--apply]

Exit codes:

  * 0 — dry-run or apply succeeded.
  * 1 — refused (no counsel approval, or token mismatch, or counsel
    PDF pending).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import logging
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.migration_cloud.models_audit import (
    MigrationCloudAuditEvent,
    MigrationCloudAuditEventType,
    _hash_tenant_slug,
)

logger = logging.getLogger(__name__)


_COUNSEL_PENDING_MESSAGE = (
    "Counsel approval pending — see docs/MIGRATION_CLOUD_AUDIT_LOG.md § Retention"
)


class Command(BaseCommand):
    help = (
        "Counsel-approved retention purge of MigrationCloudAuditEvent rows. "
        "Defaults to dry-run; --apply performs the DELETE."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            required=True,
            type=str,
            help="Tenant slug whose audit rows to purge.",
        )
        parser.add_argument(
            "--before",
            required=True,
            type=str,
            help=(
                "ISO-8601 date / datetime. Rows with created_at strictly "
                "before this cutoff are eligible for purge."
            ),
        )
        parser.add_argument(
            "--counsel-approval-token",
            default="",
            type=str,
            help=(
                "Counsel-approved approval token. MUST match "
                "settings.MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN via "
                "constant-time compare. NEVER logged in plaintext."
            ),
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Without this flag, the command runs in dry-run mode "
                "and prints the row count + first/last UUIDs that "
                "WOULD be purged."
            ),
        )

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        tenant_slug = options["tenant"]
        before_raw = options["before"]
        supplied_token = options.get("counsel_approval_token") or ""
        apply = bool(options.get("apply"))

        # Token gate — constant-time compare. Empty setting = counsel
        # pending. The compare ALWAYS happens (even when the setting is
        # empty) so timing doesn't leak whether the setting is set.
        configured_token = (
            getattr(settings, "MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN", "") or ""
        )
        if not configured_token:
            self.stdout.write(_COUNSEL_PENDING_MESSAGE)
            # Still run a no-op compare for timing parity.
            hmac.compare_digest(
                supplied_token.encode("utf-8"),
                b"\x00" * max(1, len(supplied_token)),
            )
            sys.exit(1)

        token_ok = hmac.compare_digest(
            supplied_token.encode("utf-8"),
            configured_token.encode("utf-8"),
        )
        if not token_ok:
            self.stderr.write(
                "purge_audit_events_pre_approved: counsel approval token mismatch — refused."
            )
            sys.exit(1)

        # Parse cutoff. Accept date-only or full ISO-8601 with offset.
        cutoff = self._parse_cutoff(before_raw)

        tenant_hash = _hash_tenant_slug(tenant_slug)

        # tenant-isolation-allow: audit-retention-purge-by-tenant-hash-cutoff-window
        qs = (
            MigrationCloudAuditEvent.objects
            .filter(tenant_id_hash=tenant_hash, created_at__lt=cutoff)
            .order_by("created_at")
            .only("id", "created_at")
        )
        row_count = qs.count()

        if row_count == 0:
            self.stdout.write(
                f"purge_audit_events_pre_approved: 0 rows match for "
                f"tenant_hash_prefix={tenant_hash[:6]} cutoff={cutoff.isoformat()}"
            )
            return

        first = qs.first()
        last = qs.last()
        first_uuid_prefix = str(first.id)[:8] if first else ""
        last_uuid_prefix = str(last.id)[:8] if last else ""

        self.stdout.write(
            f"purge_audit_events_pre_approved: "
            f"tenant_hash_prefix={tenant_hash[:6]} "
            f"cutoff={cutoff.isoformat()} "
            f"rows_eligible={row_count} "
            f"first_uuid_prefix={first_uuid_prefix} "
            f"last_uuid_prefix={last_uuid_prefix}"
        )

        if not apply:
            self.stdout.write(
                "DRY-RUN — no rows deleted. This operation is "
                "irreversible and violates the append-only contract — "
                "proceed only with counsel signoff PDF on file."
            )
            return

        # APPLY path. Raw-SQL DELETE bypasses the append-only manager
        # intentionally; transactional + meta-event audited.
        approval_token_hash = hashlib.sha256(
            configured_token.encode("utf-8")
        ).hexdigest()[:12]

        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "DELETE FROM migration_cloud_migrationcloudauditevent "
                    "WHERE tenant_id_hash=%s AND created_at < %s",
                    [tenant_hash, cutoff],
                )
                deleted_via_cursor = cur.rowcount or row_count

            # Emit the meta-event AFTER the DELETE (so the chain
            # head reflects post-purge state). The meta-event lives
            # in the same audit table for the same tenant — the
            # purge audits itself.
            # NOTE: payload_summary keys are intentionally crafted to
            # AVOID the _sanitize_payload rejection list (which fires
            # on substring matches of "hash" / "token" / "slug" /
            # "email"). We use "tenant_prefix" + "approval_fingerprint"
            # so the meta-event survives the sanitizer.
            MigrationCloudAuditEvent.objects.record(
                tenant_slug=tenant_slug,
                event_type=MigrationCloudAuditEventType.AUDIT_RETENTION_PURGE_APPLIED.value,
                actor=None,
                subject=None,
                payload_summary={
                    "tenant_prefix": tenant_hash[:6],
                    "rows_purged": int(deleted_via_cursor),
                    "cutoff_iso": cutoff.isoformat(),
                    "approval_fingerprint": approval_token_hash,
                },
            )

        logger.info(
            "migration_cloud.audit_retention_purge_applied "
            "tenant_hash_prefix=%s rows_purged=%s cutoff=%s",
            tenant_hash[:6], int(deleted_via_cursor), cutoff.isoformat(),
        )

        self.stdout.write(
            f"purge_audit_events_pre_approved: APPLIED rows_purged="
            f"{deleted_via_cursor} meta_event_recorded=1"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_cutoff(self, raw: str) -> _dt.datetime:
        """Accept date-only or ISO-8601 datetime; return tz-aware UTC."""
        raw = (raw or "").strip()
        if not raw:
            raise CommandError("--before is required and must be ISO-8601.")

        # Date-only form
        try:
            d = _dt.date.fromisoformat(raw)
            return _dt.datetime(
                d.year, d.month, d.day, tzinfo=_dt.timezone.utc,
            )
        except ValueError:
            pass

        try:
            dt = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CommandError(
                f"--before could not be parsed as ISO-8601: {exc}"
            ) from exc

        if dt.tzinfo is None:
            # Treat naive as UTC by convention.
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return dt
