"""v3.39.0 Agent 1 — Celery beat task for the weekly audit-chain verifier.

The task wraps ``manage.py verify_audit_chain --all-tenants`` and is
scheduled by ``config/settings.py::CELERY_BEAT_SCHEDULE`` under the
``accounts-verify-audit-chain`` entry (Mondays 02:00 UTC).

Failure path: try/except wraps the entire body. On exception, logs
ERROR but NEVER propagates — a broken verifier is itself an alertable
event but must not break the beat queue. When
``settings.MIGRATION_CLOUD_AUDIT_OPS_EMAIL`` is empty, the task logs
WARNING and exits without invoking the verifier with an email arg.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# Lazy-imported shared_task — the test harness imports
# ``verify_audit_chain_weekly_task`` as a plain callable, while
# Celery beat dispatches via the registered task name. Both paths
# resolve to the same body.
try:
    from celery import shared_task as _shared_task  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - celery is in requirements.txt
    _shared_task = None  # type: ignore[assignment]


def verify_audit_chain_weekly_task() -> dict:
    """Run the verifier across all active tenants once a week.

    Returns a small status dict (used by tests + manual invocation).
    NEVER raises — caller is the Celery beat, which must not see
    transient verifier errors as task failures.
    """
    # Lazy-import to keep beat loading cheap. Django settings + the
    # management-command machinery should NEVER be imported at module
    # load time inside a Celery task module — beat must be able to
    # introspect the schedule without booting half the ORM.
    try:
        from django.conf import settings
        from django.core.management import call_command
    except Exception:  # pragma: no cover - defensive
        logger.error(
            "migration_cloud.audit.weekly: failed to import django bootstrap"
        )
        return {"status": "import_failed"}

    ops_email = (getattr(settings, "MIGRATION_CLOUD_AUDIT_OPS_EMAIL", "") or "").strip()
    if not ops_email:
        logger.warning(
            "migration_cloud.audit.weekly: MIGRATION_CLOUD_AUDIT_OPS_EMAIL "
            "is unset; verifier will run but no notification will be sent"
        )

    try:
        if ops_email:
            call_command(
                "verify_audit_chain",
                "--all-tenants",
                f"--email-on-broken={ops_email}",
            )
        else:
            call_command("verify_audit_chain", "--all-tenants")
    except SystemExit as exc:
        # call_command propagates the verifier's sys.exit(1) — that's
        # not a task failure; the broken-chain email already went out.
        logger.info(
            "migration_cloud.audit.weekly: verifier exited with code=%s",
            getattr(exc, "code", "?"),
        )
        return {"status": "completed_with_breaks", "exit_code": getattr(exc, "code", None)}
    except Exception as exc:  # pylint: disable=broad-except
        # NEVER propagate. Beat retries are not the right recovery
        # mechanism for verifier errors — the operator should see the
        # ERROR log and investigate by hand.
        logger.error(
            "migration_cloud.audit.weekly: verifier raised %s: %s",
            type(exc).__name__, exc,
        )
        return {"status": "raised", "exc_type": type(exc).__name__}

    return {"status": "clean"}


# Celery-discoverable wrapper. The beat schedule entry references
# "migration_cloud.verify_audit_chain_weekly" by task name.
if _shared_task is not None:  # pragma: no cover - thin shim
    @_shared_task(
        name="migration_cloud.verify_audit_chain_weekly",
        ignore_result=True,
    )
    def _celery_verify_audit_chain_weekly() -> dict:
        return verify_audit_chain_weekly_task()


__all__ = ["verify_audit_chain_weekly_task"]
