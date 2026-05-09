"""HMAC signing key rotation for the audit timeline.

The audit timeline is HMAC-bound (per ``apps/compliance/`` HMAC verifier).
Operators need a documented rotation path; this command supplies one.

Pattern: dual-sign window. After rotation, every new audit row is signed with
the NEW key, but verifiers still accept signatures produced by the OLD key
for ``settings.AUDIT_HMAC_DUAL_SIGN_WINDOW_DAYS`` (default 30) so historical
rows remain verifiable. After the window, the old key is retired.

Usage::

    python manage.py rotate_audit_hmac_key --dry-run            # preview
    python manage.py rotate_audit_hmac_key --apply --kid v3      # rotate

The command does NOT write secrets to disk — it generates a new key and
prints it to stdout (operator stores it in deployment secrets manager) plus
records a rotation event so the timeline records when the key changed.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from django.core.management.base import BaseCommand


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate a new audit-log HMAC key and record the rotation event."

    def add_arguments(self, parser):
        parser.add_argument(
            "--kid",
            type=str,
            default="",
            help="Key identifier (e.g. 'v2'); defaults to UTC timestamp.",
        )
        parser.add_argument(
            "--bytes",
            type=int,
            default=32,
            help="Random byte length (default 32 = 256 bits).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print preview only; do not log a rotation event.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Log the rotation event (recommended after distributing the new key).",
        )

    def handle(self, *args, **opts):
        nbytes = max(int(opts.get("bytes") or 32), 16)
        kid = (opts.get("kid") or "").strip() or _default_kid()
        dry_run = bool(opts.get("dry_run"))
        apply = bool(opts.get("apply"))

        new_key_hex = secrets.token_hex(nbytes)
        now = datetime.now(tz=timezone.utc).isoformat()

        # Print key + kid for the operator. Caller is responsible for setting
        # AUDIT_HMAC_KEY_<KID> in the deployment secret store before flipping
        # the active KID via AUDIT_HMAC_ACTIVE_KID.
        self.stdout.write(self.style.SUCCESS(
            f"New audit-HMAC key generated: kid={kid} bytes={nbytes} ({nbytes*8} bits)"
        ))
        self.stdout.write(f"AUDIT_HMAC_KEY_{kid.upper()}={new_key_hex}")
        self.stdout.write(self.style.WARNING(
            "Store this in your deployment secrets manager. Do NOT commit."
        ))

        if dry_run and not apply:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN — no rotation event recorded. Re-run with --apply once "
                "the new key is distributed."
            ))
            return

        if not apply:
            self.stdout.write(self.style.WARNING(
                "Pass --apply to record the rotation event in the audit timeline."
            ))
            return

        _record_rotation_event(kid=kid, key_bytes=nbytes, rotated_at=now)
        self.stdout.write(self.style.SUCCESS(
            f"Rotation event recorded for kid={kid} at {now}"
        ))


def _default_kid() -> str:
    return datetime.now(tz=timezone.utc).strftime("v%Y%m%dT%H%M%SZ")


def _record_rotation_event(*, kid: str, key_bytes: int, rotated_at: str) -> None:
    """Best-effort: write an AuditLog entry recording the rotation event.

    Safe when AuditLog model is unavailable — falls back to logger.
    """
    try:
        from apps.compliance.models import AuditLog  # type: ignore

        AuditLog.objects.create(
            action="audit.hmac_key_rotated",
            model_name="audit_hmac_key",
            object_id=kid,
            object_repr=f"kid={kid} bytes={key_bytes}",
            sensitivity="HIGH",
            new_values={
                "kid": kid,
                "key_bytes": key_bytes,
                "rotated_at": rotated_at,
            },
        )
    except Exception:
        logger.warning(
            "tenant_wind_down: AuditLog unavailable; rotation event logged via logger only "
            "(kid=%s bytes=%s rotated_at=%s)",
            kid,
            key_bytes,
            rotated_at,
        )
