"""Remote Support P3 — diagnostics snapshot.

A PII-free, aggregate context bundle an operator needs to help a tenant WITHOUT
the tenant present: school identity, deployment/offline posture, provisioning
state, health score, and offline-queue depth. Every section is best-effort
(guarded) so a missing model or an off-tenant call never breaks the support
flow. The bundle is JSON-serialisable and stored on
``RemoteSupportSession.diagnostics`` — so it rides the existing OfflineAction
queue and reaches the operator on reconnect for offline/edge tenants.

Deliberately aggregate-only: it never reads student/guardian/staff PII (that is
the platform stance encoded in jit_operator_controller._OPERATOR_FORBIDDEN_FIELDS).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from apps.compliance.models_audit import AuditLog

logger = logging.getLogger(__name__)


def _school_identity(school) -> dict:
    try:
        return {
            "id": str(getattr(school, "id", "") or ""),
            "name": getattr(school, "name", "") or "",
            "slug": getattr(school, "slug", "") or "",
            "school_type": getattr(school, "school_type", "") or "",
            "country_code": getattr(school, "country_code", "") or "",
            "plan_id": getattr(school, "plan_id", None),
            "is_active": bool(getattr(school, "is_active", False)),
        }
    except Exception:  # noqa: BLE001 — diagnostics never break the flow
        logger.info("diagnostics school identity failed", exc_info=True)
        return {}


def _deployment(school) -> dict:
    try:
        features = getattr(school, "features", None) or {}
        offline = bool(
            features.get("offline_mode") or features.get("enable_offline_mode")
        )
        return {
            "profile": getattr(settings, "RMC_DEPLOYMENT_PROFILE", "online"),
            "offline_mode": offline,
        }
    except Exception:  # noqa: BLE001
        logger.info("diagnostics deployment failed", exc_info=True)
        return {}


def _provisioning(school) -> dict:
    try:
        prov = (getattr(school, "settings", None) or {}).get("provisioning") or {}
        return {
            "phase_a_complete": bool(prov.get("phase_a_complete")),
            "phase_b_complete": bool(prov.get("phase_b_complete")),
            "phase_b_failed_steps": list(prov.get("phase_b_failed_steps") or []),
        }
    except Exception:  # noqa: BLE001
        logger.info("diagnostics provisioning failed", exc_info=True)
        return {}


def _health(school) -> dict:
    try:
        from apps.customersuccess.models import TenantHealthScore

        row = (
            TenantHealthScore.objects.filter(school_id=school.id)
            .order_by("-created_at")
            .first()
        )
        if row is None:
            return {"score": None}
        return {"score": getattr(row, "score", None)}
    except Exception:  # noqa: BLE001
        logger.info("diagnostics health failed", exc_info=True)
        return {"score": None}


def _offline_queue(school) -> dict:
    try:
        from apps.platform_runtime.models import OfflineAction

        pending = OfflineAction.objects.filter(
            school_id=school.id, status="queued"
        ).count()
        return {"pending": int(pending)}
    except Exception:  # noqa: BLE001
        logger.info("diagnostics offline queue failed", exc_info=True)
        return {"pending": None}


def build_diagnostic_snapshot(*, school, now_iso=None) -> dict:
    """Assemble the PII-free diagnostics bundle for a school."""
    return {
        "captured_at": now_iso or timezone.now().isoformat(),
        "school": _school_identity(school),
        "deployment": _deployment(school),
        "provisioning": _provisioning(school),
        "health": _health(school),
        "offline_queue": _offline_queue(school),
    }


def attach_diagnostics(*, session, snapshot, actor=None):
    """Store a diagnostics bundle on the session (audited)."""
    session.diagnostics = snapshot or {}
    session.save(update_fields=["diagnostics", "updated_at"])
    session.record_lifecycle_audit(
        actor=actor,
        action=AuditLog.Action.UPDATE,
        reason="Diagnostics snapshot attached",
    )
    return session
