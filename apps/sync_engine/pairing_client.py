"""The BOX half of pairing: open a request, show a code, wait to be adopted.

Runs on the sovereign appliance. Talks outbound only — the same direction, over the
same transport, to the same host as an ordinary sync cycle. That is not an accident:
if pairing completes, the sync network path is proven working, and if pairing fails
the operator learns it BEFORE any credential exists, with an error about reaching the
cloud rather than one about a credential being wrong. The failure that started all of
this — a wrong path reported as "RMC_EDGE_OPERATOR_BASE is probably wrong" four days
after the fact — is exactly what this ordering prevents.

The pending request (its id and poll secret) is held on disk rather than in memory, so
the screen a technician is watching survives the worker restarting, and a poll started
on Friday can be collected on Monday.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path

from django.conf import settings

from apps.sync_engine.cloud_endpoints import cloud_endpoint

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 20


def _state_path() -> Path:
    """Where the in-flight request is parked.

    Under the media root by default because that is the one directory the compose
    file mounts as a volume — anything written elsewhere in the container is lost on
    the next rebuild, which is the failure mode this whole feature exists to remove.
    """
    override = (os.getenv("RMC_EDGE_PAIRING_STATE_PATH") or "").strip()
    if override:
        return Path(override)
    root = getattr(settings, "MEDIA_ROOT", "") or "."
    return Path(root) / "edge_pairing_request.json"


def _load_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        # The poll secret is a credential-equivalent for the duration of the request.
        try:
            os.chmod(path, 0o600)
        except OSError:
            # Windows / some volume drivers do not support chmod. Not fatal — the
            # file still sits inside the container's own volume.
            pass
    except OSError:
        logger.warning("pairing_client: could not persist pairing state", exc_info=True)


def clear_state() -> None:
    try:
        _state_path().unlink()
    except OSError:
        pass


def _post(url: str, payload: dict) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw or "{}")
            except ValueError:
                # An HTML body here means we hit something that is not the API —
                # the signature of a wrong base or a path that does not exist.
                return resp.status, {"error": "non_json_response", "body": raw[:400]}
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        try:
            return exc.code, json.loads(raw or "{}")
        except ValueError:
            return exc.code, {"error": "non_json_response", "body": raw[:400]}
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        return 0, {"error": "unreachable", "detail": str(exc)}


def _box_identity() -> dict:
    from apps.sync_engine.edge_binding import school_slug

    return {
        "school_slug": school_slug(),
        "device_id": (os.getenv("RMC_EDGE_DEVICE_ID") or "").strip()
        or f"edge-{school_slug() or socket.gethostname()}",
        "box_label": (os.getenv("RMC_EDGE_BOX_LABEL") or "").strip(),
        "hostname": socket.gethostname(),
        "version": (getattr(settings, "RMC_RELEASE_VERSION", "") or "").strip(),
    }


def start(*, base: str = "", claim_ticket: str = "") -> dict:
    """Open a pairing request against the cloud and remember it.

    Returns a dict with ``user_code`` for the screen, or ``error`` describing why the
    cloud could not be reached — which is a diagnosis, not a failure to be retried
    silently.
    """
    from apps.sync_engine.edge_binding import operator_base

    base = (base or operator_base() or "").rstrip("/")
    if not base:
        return {
            "ok": False,
            "error": "no_cloud_address",
            "message": (
                "This box does not know where its cloud is. Set RMC_EDGE_SCHOOL_SLUG "
                "so the address can be derived, or RMC_EDGE_OPERATOR_BASE directly."
            ),
        }
    url = cloud_endpoint(base, "api:sync-pair-start")
    identity = _box_identity()
    if claim_ticket:
        identity["claim_ticket"] = claim_ticket
    status, body = _post(url, identity)
    if status != 200 or not body.get("ok"):
        return {
            "ok": False,
            "error": body.get("error") or f"http_{status}",
            "message": _explain_failure(status, body, base),
            "endpoint": url,
        }
    state = {
        "request_id": body.get("request_id"),
        "poll_secret": body.get("poll_secret"),
        "user_code": body.get("user_code"),
        "expires_at": body.get("expires_at"),
        "operator_base": base,
        "school_resolved": bool(body.get("school_resolved")),
        "poll_interval_seconds": int(body.get("poll_interval_seconds") or 5),
        "pre_approved": bool(body.get("pre_approved")),
        "claim_ticket_error": body.get("claim_ticket_error") or "",
    }
    _save_state(state)
    logger.info("pairing_client: request opened, code %s", state["user_code"])
    return {"ok": True, **{k: v for k, v in state.items() if k != "poll_secret"}}


def poll() -> dict:
    """Ask whether the request has been approved; bind the box when it has."""
    from apps.sync_engine.edge_binding import save_binding

    state = _load_state()
    if not state.get("request_id") or not state.get("poll_secret"):
        return {"ok": False, "status": "no_request"}
    base = (state.get("operator_base") or "").rstrip("/")
    url = cloud_endpoint(base, "api:sync-pair-poll")
    status, body = _post(
        url,
        {"request_id": state["request_id"], "poll_secret": state["poll_secret"]},
    )
    if status == 0:
        return {"ok": False, "status": "unreachable", "message": body.get("detail", "")}
    if status == 429:
        return {"ok": False, "status": "rate_limited"}
    if status != 200:
        return {"ok": False, "status": f"http_{status}"}

    protocol_status = body.get("status")
    if protocol_status == "approved" and body.get("credential"):
        from django.utils.dateparse import parse_datetime

        save_binding(
            operator_base=base,
            credential=body["credential"],
            school_slug=body.get("school_slug") or state.get("school_slug") or "",
            school_name=body.get("school_name") or "",
            device_id=_box_identity()["device_id"],
            credential_expires_at=parse_datetime(body.get("expires_at") or "") or None,
            via="pairing",
        )
        clear_state()
        logger.info("pairing_client: paired with %s", body.get("school_slug"))
        return {
            "ok": True,
            "status": "paired",
            "school_slug": body.get("school_slug"),
            "school_name": body.get("school_name"),
        }
    if protocol_status in ("denied", "expired", "already_redeemed", "unknown"):
        # Terminal. Drop the parked request so the screen offers a fresh start rather
        # than polling forever against something that will never approve.
        clear_state()
        return {"ok": False, "status": protocol_status, "reason": body.get("reason", "")}
    return {"ok": True, "status": "pending", "user_code": state.get("user_code")}


def current_request() -> dict:
    """What the pairing screen should display. Never includes the poll secret."""
    state = _load_state()
    if not state.get("user_code"):
        return {}
    return {
        "user_code": state.get("user_code"),
        "expires_at": state.get("expires_at"),
        "operator_base": state.get("operator_base"),
        "school_resolved": state.get("school_resolved", True),
        "poll_interval_seconds": state.get("poll_interval_seconds", 5),
    }


def _explain_failure(status: int, body: dict, base: str) -> str:
    """Say what to DO, and never blame a setting without evidence."""
    if status == 0:
        return (
            f"Could not reach {base}. Check the box's internet connection and that "
            f"the address is right — nothing has been configured, so it is safe to "
            f"try again."
        )
    if status == 429:
        return "The cloud is rate-limiting pairing requests from this address. Wait a minute and try again."
    if body.get("error") == "non_json_response":
        return (
            f"{base} answered with a web page instead of the pairing API. That "
            f"address is reachable but is not a RunMyCampus cloud tenant — check the "
            f"school subdomain."
        )
    if status == 404:
        return (
            f"{base} has no pairing endpoint. The cloud is reachable but is running a "
            f"build older than box pairing."
        )
    return f"The cloud refused the pairing request (HTTP {status})."


__all__ = ["clear_state", "current_request", "poll", "start"]
