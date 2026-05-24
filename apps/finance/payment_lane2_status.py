"""
Lane 2 corridor status rollup for operator dashboards (SFDP Phase 2 — batch 1436).

Merges external_dependencies_register truth, PSP adapter registry, and tenant
Integration rows — never fabricates verified_live.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps.billing.psp_adapter_registry import get_psp
from apps.finance.payment_lane2_checklist import LANE2_PILOT_CORRIDORS
from apps.finance.services import get_payment_integration_by_slug

_REGISTER_PATH = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "external_dependencies_register.json"
)


def _load_register_statuses() -> dict[str, str]:
    if not _REGISTER_PATH.is_file():
        return {}
    data = json.loads(_REGISTER_PATH.read_text(encoding="utf-8"))
    payments = next(
        (s for s in data.get("sections", []) if s.get("id") == "payments_psp_settlement"),
        {},
    )
    return {
        str(entry.get("id", "")): str(entry.get("status", "unknown"))
        for entry in payments.get("entries", [])
        if entry.get("id")
    }


def build_lane2_corridor_rows(*, school=None) -> list[dict[str, Any]]:
    """
    Operator-facing rows for payment readiness UI.

    ``live_proof`` is True only when register status is verified_live (Lane 2 evidence filed).
    """
    register = _load_register_statuses()
    rows: list[dict[str, Any]] = []
    for checklist in LANE2_PILOT_CORRIDORS:
        psp = get_psp(checklist.psp_slug)
        adapter_status = psp.adapter_status if psp else "unknown"
        reg_status = register.get(checklist.register_id, "unknown")
        integration = get_payment_integration_by_slug(checklist.psp_slug)
        if school is not None and integration is not None:
            school_id = getattr(school, "pk", None)
            integ_school = getattr(integration, "school_id", None)
            if integ_school is not None and school_id is not None and integ_school != school_id:
                integration = None

        rows.append(
            {
                "register_id": checklist.register_id,
                "psp_slug": checklist.psp_slug,
                "label": psp.label if psp else checklist.psp_slug,
                "corridors": list(checklist.corridors),
                "register_status": reg_status,
                "adapter_status": adapter_status,
                "integration_configured": integration is not None,
                "verification_mode": checklist.verification_mode,
                "verification_command": checklist.verification_command,
                "evidence_path": f"{checklist.evidence_dir}/{checklist.evidence_filename}",
                "live_proof": reg_status == "verified_live",
                "engine": "platform" if checklist.register_id.startswith("stripe") else "tuition",
            }
        )
    return rows


def stripe_connect_summary(*, school) -> dict[str, Any]:
    """Engine 1 Connect posture for readiness sidebar."""
    if school is None:
        return {"connected": False, "charges_enabled": False, "account_id": ""}
    try:
        from apps.schools.stripe_connect_settings import get_stripe_connect_payload, is_stripe_connected

        payload = get_stripe_connect_payload(school)
        return {
            "connected": is_stripe_connected(school),
            "charges_enabled": bool(payload.get("charges_enabled")),
            "account_id": str(payload.get("account_id") or "")[:12] + "…"
            if payload.get("account_id")
            else "",
        }
    except Exception:
        return {"connected": False, "charges_enabled": False, "account_id": ""}
