"""Edge outbox core — build delta bundles + mint/resolve the edge machine credential.

Shared by the export/mint/post management commands and the receiver's credential
auth (Tier 3 Slices 2-3). The edge machine credential reuses the existing
``accounts.OfflineCapabilityToken`` (sha256-fingerprinted, revocable via both the
token and its ``DeviceRegistration``, with an expiry) tagged with ``EDGE_SYNC_SCOPE``
so an ordinary mobile offline token can never be used to drive server->server sync.
No new model / migration — a sovereign box registers as a device.

Direction is edge-initiated / outbound-only: the box POSTs its bundle UP to the
operator; the operator never needs to reach a box behind a private LAN.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import urllib.error
import urllib.request
from datetime import timedelta

from django.utils import timezone

BUNDLE_CONTENT_TYPE = "application/x-rmc-sync-bundle+ndjson"

# Marker stamped into an edge credential's permission_bitmap. resolve_edge_credential
# REQUIRES it, so a plain offline capability token can't authenticate the sync POST.
EDGE_SYNC_SCOPE = "edge-sync-machine"


# --------------------------------------------------------------------------- #
# Bundle building (shared by export_edge_delta_bundle + post_edge_outbox)
# --------------------------------------------------------------------------- #
def build_edge_delta_bundle(school, *, since=None, entities=None, device_id="edge"):
    """Package the school's records changed since ``since`` into a signed delta bundle.

    Returns ``(bundle_bytes, meta)`` where ``meta`` is
    ``{"counts", "row_count", "high_water_iso"}``. UPDATE-only rows for the
    ``apply_changes`` entity set (identity holds because the clone is pk-preserving).
    Raises ``ValueError('unknown_entities:...')`` for an unknown entity filter.
    """
    from apps.api.sync_services import _get_entity_config  # SOT: (model, allowed fields)
    from apps.sync_engine.delta_bundle import export_delta_bundle

    config = _get_entity_config()
    want = {str(e).strip().lower() for e in (entities or []) if str(e).strip()}
    unknown = want - set(config)
    if unknown:
        raise ValueError(f"unknown_entities:{sorted(unknown)}")

    rows: list[dict] = []
    counts: dict[str, int] = {}
    high_water = None
    for entity_type, (model, allowed) in config.items():
        if want and entity_type not in want:
            continue
        qs = model._default_manager.filter(school=school)  # school= is the tenant-isolation kwarg
        if since is not None:
            qs = qs.filter(updated_at__gt=since)
        n = 0
        for instance in qs.order_by("updated_at").iterator():
            changes = {f: getattr(instance, f) for f in sorted(allowed) if hasattr(instance, f)}
            updated_at = getattr(instance, "updated_at", None)
            rows.append(
                {
                    "entity_type": entity_type,
                    "id": instance.pk,
                    "changes": changes,
                    "updated_at": updated_at.isoformat() if updated_at else None,
                }
            )
            if updated_at and (high_water is None or updated_at > high_water):
                high_water = updated_at
            n += 1
        if n:
            counts[entity_type] = n

    data = export_delta_bundle(school_id=str(school.id), rows=rows, device_id=device_id or "edge")
    meta = {
        "counts": counts,
        "row_count": len(rows),
        "high_water_iso": high_water.isoformat() if high_water else None,
    }
    return data, meta


# --------------------------------------------------------------------------- #
# Machine credential (mint on the operator, resolve on the receiver)
# --------------------------------------------------------------------------- #
def _fingerprint(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def mint_edge_credential(school, user, *, device_id="", days=365, public_key_fingerprint=""):
    """Register the box as a device + mint a long-lived edge machine credential.

    Returns ``(raw_token, token_obj)``. The raw token is shown ONCE; only its sha256
    is persisted. Refuses to re-mint for a REVOKED device (reinstatement must be an
    explicit operator action), mirroring OfflineTokenMintView's online-boundary rule.
    """
    from apps.accounts.models_offline_device import DeviceRegistration, OfflineCapabilityToken

    device_id = (device_id or f"edge-{getattr(school, 'slug', '') or school.pk}").strip()[:128]
    if DeviceRegistration.objects.filter(
        school=school, user=user, device_id=device_id, revoked_at__isnull=False
    ).exists():
        raise ValueError("device_revoked")

    device, _created = DeviceRegistration.objects.update_or_create(
        school=school,
        user=user,
        device_id=device_id,
        defaults={
            "public_key_fingerprint": public_key_fingerprint or "",
            "permission_bitmap": [EDGE_SYNC_SCOPE],
            "last_seen_at": timezone.now(),
        },
    )
    raw_token = secrets.token_urlsafe(32)
    token = OfflineCapabilityToken.objects.create(
        device=device,
        school=school,
        user=user,
        token_fingerprint=_fingerprint(raw_token),
        permission_bitmap=[EDGE_SYNC_SCOPE],
        expires_at=timezone.now() + timedelta(days=max(1, int(days))),
    )
    return raw_token, token


def resolve_edge_credential(raw_token: str):
    """Resolve a raw edge bearer token to ``(user, school)``, or ``None`` if invalid.

    Requires the ``EDGE_SYNC_SCOPE`` marker, a non-revoked non-expired token, and a
    non-revoked device. Touches ``last_seen_at`` on success. Never raises — an
    unrecognised/expired/revoked token simply resolves to ``None``.
    """
    from apps.accounts.models_offline_device import OfflineCapabilityToken

    if not raw_token:
        return None
    token = (
        OfflineCapabilityToken.objects.select_related("device", "school", "user")
        # tenant-isolation-allow: credential-resolution-is-intentionally-cross-tenant-the-sha256-fingerprint-resolves-which-school
        .filter(token_fingerprint=_fingerprint(raw_token))
        .first()
    )
    if token is None or not token.is_valid:
        return None
    if EDGE_SYNC_SCOPE not in (token.permission_bitmap or []):
        return None
    device = token.device
    if device is not None and device.revoked_at is not None:
        return None
    if device is not None:
        device.touch_seen()
    return token.user, token.school


# --------------------------------------------------------------------------- #
# Transport (box side) — POST a bundle to the operator receiver
# --------------------------------------------------------------------------- #
def post_bundle(endpoint: str, token: str, data: bytes, *, timeout: float = 30.0):
    """POST a signed bundle to the operator's receiver with a bearer credential.

    Returns ``(status_code, body_dict)``. A 4xx/5xx is a real HTTP RESPONSE (returned,
    not raised) so the caller can distinguish "operator rejected the bundle" from
    "couldn't reach the operator". A connectivity failure (``URLError``/``OSError``,
    e.g. offline) PROPAGATES — the caller queues the bundle and retries later.
    """
    req = urllib.request.Request(
        endpoint,
        data=data,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": BUNDLE_CONTENT_TYPE},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator URL, not user input
            status = resp.getcode()
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:  # a response with a 4xx/5xx status, not a connectivity failure
        status = exc.code
        try:
            body = exc.read().decode("utf-8", "replace")
        except (OSError, AttributeError):
            body = ""
    try:
        parsed = json.loads(body) if body else {}
    except ValueError:
        parsed = {"raw": body}
    return status, parsed


__all__ = [
    "EDGE_SYNC_SCOPE",
    "BUNDLE_CONTENT_TYPE",
    "build_edge_delta_bundle",
    "mint_edge_credential",
    "resolve_edge_credential",
    "post_bundle",
]
