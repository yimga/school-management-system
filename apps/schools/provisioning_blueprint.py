"""
Bind ``blueprint/school_templates/*.json`` metadata during tenant provisioning.

Full pack install remains platform-governed when ``tenant_safe_apply`` is false; we record
resolved catalog keys on the provisioning timeline for operators and Studio preview parity.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def record_school_template_blueprint(school) -> dict[str, Any]:
    """
    Load the selected school template (from policy provisioning.school_template_key),
    resolve pack keys against the on-disk platform catalog, and append a timeline event.
    """
    from apps.policies.policy_registry import get_effective_policy
    from apps.schools.models import SchoolProvisioningEvent

    out: dict[str, Any] = {"ok": True, "skipped": True}
    if school is None:
        return out

    policy = get_effective_policy(school) or {}
    prov = policy.get("provisioning") if isinstance(policy.get("provisioning"), dict) else {}
    key = str(prov.get("school_template_key") or "").strip()
    if not key:
        return out

    try:
        from apps.studio_os.school_infrastructure import (
            load_pack_catalog_from_disk,
            load_school_template,
        )
    except ImportError as e:
        logger.debug("record_school_template_blueprint import skip: %s", e)
        return {"ok": False, "skipped": True, "reason": "imports"}

    try:
        template = load_school_template(key)
    except (OSError, FileNotFoundError, ValueError) as e:
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.PROFILE_APPLIED,
            status=SchoolProvisioningEvent.Status.WARNING,
            message=f"School template '{key}' not found or invalid.",
            payload={"school_template_key": key, "error": str(e)},
        )
        return {"ok": False, "skipped": False, "error": str(e)}

    catalog = load_pack_catalog_from_disk()
    wf_keys = set()
    db_keys = set()
    tp_keys = set()
    for row in catalog.get("workflow_packs") or []:
        if isinstance(row, dict) and row.get("pack_key"):
            wf_keys.add(row["pack_key"])
    for row in catalog.get("dashboard_packs") or []:
        if isinstance(row, dict) and row.get("pack_key"):
            db_keys.add(row["pack_key"])
    for row in catalog.get("theme_packs") or []:
        if isinstance(row, dict) and row.get("pack_key"):
            tp_keys.add(row["pack_key"])

    want_wf = [k for k in (template.get("workflow_pack_keys") or []) if k]
    want_db = [k for k in (template.get("dashboard_pack_keys") or []) if k]
    want_tp = [k for k in (template.get("theme_pack_keys") or []) if k]

    unresolved = [
        *[f"workflow:{k}" for k in want_wf if k not in wf_keys],
        *[f"dashboard:{k}" for k in want_db if k not in db_keys],
        *[f"theme:{k}" for k in want_tp if k not in tp_keys],
    ]

    caps = template.get("capabilities") if isinstance(template.get("capabilities"), dict) else {}
    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.BLUEPRINT_TEMPLATE_RECORDED,
        status=(
            SchoolProvisioningEvent.Status.WARNING
            if unresolved
            else SchoolProvisioningEvent.Status.SUCCESS
        ),
        message=(
            f"Blueprint template '{key}' recorded ({len(unresolved)} unresolved catalog keys)."
            if unresolved
            else f"Blueprint template '{key}' recorded; catalog keys resolve."
        ),
        payload={
            "school_template_key": key,
            "template_version": template.get("version"),
            "display_name": template.get("display_name"),
            "workflow_pack_keys": want_wf,
            "dashboard_pack_keys": want_db,
            "theme_pack_keys": want_tp,
            "unresolved_pack_hints": unresolved,
            "tenant_safe_apply": bool(caps.get("tenant_safe_apply")),
            "notes": template.get("notes"),
        },
    )
    return {
        "ok": True,
        "skipped": False,
        "school_template_key": key,
        "unresolved": unresolved,
    }
