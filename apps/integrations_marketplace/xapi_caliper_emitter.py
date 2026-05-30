"""v4.00.91 Studio-OS-10X W1 Pillar B13 — xAPI / Caliper outbound emitter scaffold.

Two parallel statement formats for learning-analytics interop:

* **xAPI** (Experience API, ADL spec) — actor/verb/object triples shipped to
  an LRS (Learning Record Store) at ``<lrs_endpoint>/statements``.
* **IMS Caliper** (Caliper Analytics spec) — event envelopes shipped to a
  Caliper endpoint at ``<endpoint>/caliper``.

This scaffold lays in payload assembly + the outbound shape so callers can
unit-test payloads without hitting the network. Live outbound is gated
behind ``RMC_XAPI_LIVE_OUTBOUND`` and ``RMC_CALIPER_LIVE_OUTBOUND`` envs.

Honest contract: every emit returns ``{status, format, would_send | sent,
target_endpoint, statement_id}``.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _live(env_var: str) -> bool:
    return os.environ.get(env_var, "").strip().lower() in ("1", "true", "yes", "on")


def emit_xapi_statement(
    *,
    actor_mbox: str,
    verb_id: str,
    verb_display_en: str,
    object_id: str,
    object_name_en: str = "",
    object_type: str = "Activity",
    result: dict | None = None,
    lrs_endpoint: str = "",
) -> dict[str, Any]:
    """Emit an xAPI statement. Live outbound gated by RMC_XAPI_LIVE_OUTBOUND.

    Returns ``{status, format='xapi', target_endpoint, statement_id, would_send|sent}``.
    """
    if not actor_mbox or not actor_mbox.startswith("mailto:"):
        return {"status": "bad_request", "reason": "actor_mbox_must_start_with_mailto"}
    if not verb_id:
        return {"status": "bad_request", "reason": "missing_verb_id"}
    if not object_id:
        return {"status": "bad_request", "reason": "missing_object_id"}
    statement_id = str(uuid.uuid4())
    statement = {
        "id": statement_id,
        "actor": {"mbox": actor_mbox, "objectType": "Agent"},
        "verb": {"id": verb_id, "display": {"en-US": verb_display_en}},
        "object": {
            "id": object_id,
            "definition": {"name": {"en-US": object_name_en}, "type": "http://adlnet.gov/expapi/activities/" + object_type.lower()},
            "objectType": object_type,
        },
        "timestamp": _now_iso(),
        "stored": _now_iso(),
    }
    if result:
        statement["result"] = result
    target = f"{lrs_endpoint or '/xapi'}/statements"
    if not _live("RMC_XAPI_LIVE_OUTBOUND"):
        return {
            "status": "dry_run_scaffold", "format": "xapi",
            "target_method": "POST", "target_endpoint": target,
            "statement_id": statement_id, "would_send": statement,
            "live_env_var": "RMC_XAPI_LIVE_OUTBOUND",
        }
    try:
        import requests
        resp = requests.post(
            target,
            json=statement,
            headers={"X-Experience-API-Version": "1.0.3"},
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "network_error", "format": "xapi", "reason": str(exc)[:120],
                "statement_id": statement_id}
    if resp.status_code >= 400:
        return {"status": "upstream_error", "format": "xapi",
                "http_status": resp.status_code, "statement_id": statement_id}
    return {"status": "ok", "format": "xapi", "http_status": resp.status_code,
            "statement_id": statement_id, "target_endpoint": target}


def emit_caliper_event(
    *,
    actor_id: str,
    action: str,
    object_id: str,
    event_type: str = "Event",
    profile: str = "GeneralProfile",
    target_endpoint: str = "",
) -> dict[str, Any]:
    """Emit a Caliper event. Live outbound gated by RMC_CALIPER_LIVE_OUTBOUND."""
    if not actor_id:
        return {"status": "bad_request", "reason": "missing_actor_id"}
    if not action:
        return {"status": "bad_request", "reason": "missing_action"}
    if not object_id:
        return {"status": "bad_request", "reason": "missing_object_id"}
    event_id = "urn:uuid:" + str(uuid.uuid4())
    envelope = {
        "@context": "http://purl.imsglobal.org/ctx/caliper/v1p2",
        "id": event_id,
        "type": event_type,
        "profile": profile,
        "actor": {"id": actor_id, "type": "Person"},
        "action": action,
        "object": {"id": object_id, "type": "DigitalResource"},
        "eventTime": _now_iso(),
    }
    target = target_endpoint or "/caliper/events"
    if not _live("RMC_CALIPER_LIVE_OUTBOUND"):
        return {
            "status": "dry_run_scaffold", "format": "caliper",
            "target_method": "POST", "target_endpoint": target,
            "event_id": event_id, "would_send": envelope,
            "live_env_var": "RMC_CALIPER_LIVE_OUTBOUND",
        }
    try:
        import requests
        resp = requests.post(target, json=envelope, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return {"status": "network_error", "format": "caliper",
                "reason": str(exc)[:120], "event_id": event_id}
    if resp.status_code >= 400:
        return {"status": "upstream_error", "format": "caliper",
                "http_status": resp.status_code, "event_id": event_id}
    return {"status": "ok", "format": "caliper", "http_status": resp.status_code,
            "event_id": event_id, "target_endpoint": target}
