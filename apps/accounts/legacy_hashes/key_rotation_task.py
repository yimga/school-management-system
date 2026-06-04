"""Celery task adapter for the v3.33.0 orphan-ciphertext audit.

Registered as ``accounts.audit_encryption_key_orphans``. Wired to
``CELERY_BEAT_SCHEDULE["accounts-key-rotation-monthly"]`` — first of
month 04:00 UTC.

The task is intentionally **read-only**: it calls
:func:`verify_no_orphan_ciphertexts` and emails the operator
distribution list when any orphan rows are found. Automatic rotation
is operator-driven (via ``python manage.py rotate_encryption_keys
--apply``) — the operator must always be in the loop on key
migrations.

Defensive invariants:

* Lazy-guarded import of ``celery.shared_task``: if Celery isn't
  installed (CI lanes), the task name is still importable as
  ``None`` so callers can branch safely.
* Email goes to a single address resolved from ``settings`` — falls
  back gracefully when no address is configured (logs the absence
  rather than raising).
* NEVER logs key material.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _operator_alert_email() -> Optional[str]:
    """Resolve the operator distribution address.

    Looks at, in order:
    ``settings.SECURITY_OPERATOR_EMAIL`` → ``settings.SERVER_EMAIL``
    → first entry of ``settings.ADMINS``. Returns ``None`` when no
    address is configured; the caller logs but does not raise.
    """
    try:
        from django.conf import settings
        for attr in ("SECURITY_OPERATOR_EMAIL", "SERVER_EMAIL"):
            val = getattr(settings, attr, None)
            if val:
                return str(val)
        admins = getattr(settings, "ADMINS", None)
        if admins:
            first = admins[0]
            if isinstance(first, (list, tuple)) and len(first) >= 2:
                return str(first[1])
            return str(first)
    except Exception:  # pragma: no cover
        return None
    return None


def audit_encryption_key_orphans(notify: bool = True) -> dict[str, Any]:
    """Read-only orphan-ciphertext audit. Returns the summary dict.

    Operator-driven entry point: callable from the management shell
    AND from the Celery beat task.

    Args:
        notify: when True (default) and orphans are found, emails the
            operator alert address with a count-only summary. NEVER
            includes ciphertext or key material in the email body.
    """
    # Local import keeps the module importable on systems without the
    # cryptography extra in their test path.
    from .key_rotation import verify_no_orphan_ciphertexts

    summary = verify_no_orphan_ciphertexts()
    totals = summary.get("totals", {})
    orphan_count = int(totals.get("orphan_count", 0))

    logger.info(
        "key_rotation_orphan_audit_complete",
        extra={"totals": totals, "notify": notify},
    )

    if orphan_count > 0 and notify:
        addr = _operator_alert_email()
        if not addr:
            logger.warning(
                "key_rotation_orphan_audit_no_operator_email",
                extra={"orphan_count": orphan_count},
            )
            return summary
        try:
            from apps.schoolops.email_compat import send_mail  # local: optional in CI
            body_lines = [
                "Orphan ciphertext audit found rows that cannot decrypt",
                "under any currently-active key in DJANGO_CRYPTOGRAPHY_KEYS.",
                "",
                f"Orphan rows: {orphan_count}",
                f"Models scanned: {totals.get('models_scanned', 0)}",
                f"Rows scanned: {totals.get('rows_scanned', 0)}",
                "",
                "Per-table breakdown:",
            ]
            for tbl in summary.get("tables", []):
                if tbl.get("orphan_count", 0) > 0:
                    body_lines.append(
                        f"  {tbl['model']}: {tbl['orphan_count']} orphan(s)"
                    )
            body_lines.append("")
            body_lines.append(
                "Action: do NOT rotate keys further. Triage the affected "
                "rows; the dropped key (if recoverable) must be reinstated "
                "to DJANGO_CRYPTOGRAPHY_KEYS so the rows can be re-encrypted."
            )
            send_mail(
                subject="[RunMyCampus] Encryption-key orphan audit found "
                f"{orphan_count} affected row(s)",
                message="\n".join(body_lines),
                from_email=None,
                recipient_list=[addr],
                fail_silently=True,
            )
        except Exception:  # noqa: BLE001 - email failure must not crash beat
            logger.exception(
                "key_rotation_orphan_audit_email_failed",
                extra={"orphan_count": orphan_count},
            )
    return summary


# Celery task adapter — only registered when celery is importable so the
# rotation module remains useful in environments without Celery.
try:
    from celery import shared_task

    @shared_task(name="accounts.audit_encryption_key_orphans")
    def audit_encryption_key_orphans_task() -> dict[str, Any]:
        """Celery wrapper around :func:`audit_encryption_key_orphans`."""
        return audit_encryption_key_orphans(notify=True)
except ImportError:  # pragma: no cover - celery is in requirements.txt
    audit_encryption_key_orphans_task = None  # type: ignore[assignment]


__all__ = [
    "audit_encryption_key_orphans",
]
