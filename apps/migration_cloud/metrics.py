"""Migration Cloud operational metrics emission (v3.38.0 Agent 4).

Thin typed helpers around the platform's metric backend. Six emission
sites — companion upload, MAA sign, key rotation, webhook delivery,
token mint, legacy hash decryption — each call exactly one helper here.
Every helper hashes the tenant id (sha256[:12]) before emission so
operator dashboards never accidentally label series with plaintext
tenant slugs.

Backend selection (introspected lazily on first call so the import
graph stays cheap):

* If ``services.observability`` (or any equivalent) exposes
  ``emit_counter`` / ``emit_gauge`` callables, we route through there.
* Otherwise we fall back to a structured-JSON line on
  ``logging.getLogger("migration_cloud.metrics")`` at INFO level. The
  operator's log shipper (Vector / Fluent Bit / etc.) reshapes the line
  into the metric backend of choice.

Logging discipline — every helper is wrapped in a try/except that
swallows the failure at WARNING and NEVER propagates. A metric backend
outage MUST NOT take down the production hot path (upload, sign,
rotate, etc.). The wrapped helpers (``record_*``) are the public
surface; the internal ``_emit_*`` callables are kept private so we can
add per-helper tag validation without breaking the call sites.

NEVER logged:

* raw payload bytes (only ``byte_size`` integer)
* signature bytes
* plaintext tenant slugs (only the 12-hex sha256 prefix)
* MAA signature_text bytes
* private key material

The byte_size argument to :func:`record_companion_upload` is an integer
count and is safe to emit; the helper asserts type-safety so a caller
accidentally passing the raw payload would surface a TypeError BEFORE
the bytes reached the logging sink.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger("migration_cloud.metrics")


# ─── Tenant id hashing ──────────────────────────────────────────────────

def _hash_tenant_id(tenant_id: Any) -> str:
    """Return the first 12 hex chars of sha256(str(tenant_id)).

    Stable across calls (same input → same output) but reveals nothing
    about the tenant's slug or pk to anyone who only sees the emitted
    metric series. Falls back to the string ``"unknown"`` when
    ``tenant_id`` is None — never raises.
    """
    if tenant_id is None:
        return "unknown"
    try:
        encoded = str(tenant_id).encode("utf-8")
    except (TypeError, ValueError):
        return "unknown"
    return hashlib.sha256(encoded).hexdigest()[:12]


# ─── Backend selection ──────────────────────────────────────────────────


def _resolve_backend() -> tuple[Any, Any]:
    """Return ``(emit_counter, emit_gauge)`` callables, or ``(None, None)``.

    Introspects ``services.observability`` and a couple of sibling
    modules so callers don't have to know which one is wired up in this
    deployment. Caller MUST treat ``(None, None)`` as "fall back to
    structured logging."
    """
    candidates = (
        "services.observability",
        "apps.observability.metrics",
    )
    for modname in candidates:
        try:
            mod = __import__(modname, fromlist=["emit_counter", "emit_gauge"])
        except ImportError:
            continue
        emit_counter = getattr(mod, "emit_counter", None)
        emit_gauge = getattr(mod, "emit_gauge", None)
        if callable(emit_counter) or callable(emit_gauge):
            return emit_counter, emit_gauge
    return None, None


def _emit_metric(
    name: str, kind: str, value: float, tags: dict[str, Any]
) -> None:
    """Send a metric to the resolved backend OR fall back to structured log.

    Wraps both code paths in defensive guards so a backend exception
    never propagates to the calling production hot path.
    """
    emit_counter, emit_gauge = _resolve_backend()
    if kind == "counter" and callable(emit_counter):
        emit_counter(name, value, tags=tags)
        logger.debug(
            "migration_cloud_metric_backend_emit metric=%s kind=%s tag_keys=%s",
            name, kind, sorted((tags or {}).keys()),
        )
        return
    if kind == "gauge" and callable(emit_gauge):
        emit_gauge(name, value, tags=tags)
        logger.debug(
            "migration_cloud_metric_backend_emit metric=%s kind=%s tag_keys=%s",
            name, kind, sorted((tags or {}).keys()),
        )
        return
    # Fallback: structured JSON line on the dedicated metrics logger.
    # Operators ship this to their metric backend via log forwarder.
    payload = {
        "metric": name,
        "kind": kind,
        "value": value,
        "tags": tags,
    }
    try:
        line = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        # Last-resort: serialize each tag value as str.
        safe_tags = {k: str(v) for k, v in (tags or {}).items()}
        line = json.dumps(
            {"metric": name, "kind": kind, "value": value, "tags": safe_tags},
            sort_keys=True, separators=(",", ":"),
        )
    logger.info("migration_cloud_metric %s", line)


# ─── Public record helpers ──────────────────────────────────────────────


def record_companion_upload(
    tenant_id: Any, byte_size: int, sealed_box_scheme: str
) -> None:
    """Counter + gauge for a successful Companion upload acceptance.

    ``byte_size`` is the ciphertext byte count (integer), NEVER the raw
    payload. ``sealed_box_scheme`` is the libsodium scheme identifier
    (e.g. ``"libsodium-secretbox-x25519-sealed"``).
    """
    try:
        # Defensive type-narrow so a caller accidentally passing the
        # bytes themselves trips the TypeError BEFORE we emit.
        size = int(byte_size or 0)
        scheme = str(sealed_box_scheme or "")[:64]
        tenant_hash = _hash_tenant_id(tenant_id)
        tags = {"tenant_id": tenant_hash, "sealed_box_scheme": scheme}
        _emit_metric(
            "migration_cloud.companion_uploads.count", "counter", 1, tags,
        )
        _emit_metric(
            "migration_cloud.companion_uploads.bytes_total", "gauge",
            float(size), {"tenant_id": tenant_hash},
        )
    except Exception as exc:  # noqa: BLE001 - metrics never break hot path
        logger.warning(
            "migration_cloud_metric_emit_failed metric=%s err=%s",
            "companion_uploads", type(exc).__name__,
        )


def record_maa_sign(
    tenant_id: Any, version: str, was_draft_attempt: bool
) -> None:
    """Counter for a MAA sign call (success OR draft-refusal)."""
    try:
        tags = {
            "tenant_id": _hash_tenant_id(tenant_id),
            "version": str(version or "")[:32],
            "was_draft_attempt": "true" if was_draft_attempt else "false",
        }
        _emit_metric(
            "migration_cloud.maa_signs.count", "counter", 1, tags,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud_metric_emit_failed metric=%s err=%s",
            "maa_signs", type(exc).__name__,
        )


def record_key_rotation(key_type: str, success: bool) -> None:
    """Counter for a key rotation attempt (companion / fernet / token)."""
    try:
        tags = {
            "key_type": str(key_type or "")[:32],
            "success": "true" if success else "false",
        }
        _emit_metric(
            "migration_cloud.key_rotations.count", "counter", 1, tags,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud_metric_emit_failed metric=%s err=%s",
            "key_rotations", type(exc).__name__,
        )


def record_webhook_delivery(
    subscription_id: Any, status: str, http_status: Any
) -> None:
    """Counter for one webhook delivery attempt outcome.

    ``subscription_id`` is emitted as a label as-is (subscription ids
    are non-PII platform identifiers). ``http_status`` may be ``None``
    when the network layer failed before a status code arrived; we
    emit ``"0"`` in that case.
    """
    try:
        try:
            http_label = str(int(http_status)) if http_status else "0"
        except (TypeError, ValueError):
            http_label = "0"
        tags = {
            "subscription_id": str(subscription_id),
            "status": str(status or "")[:32],
            "http_status": http_label,
        }
        _emit_metric(
            "migration_cloud.webhook_deliveries.count", "counter", 1, tags,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud_metric_emit_failed metric=%s err=%s",
            "webhook_deliveries", type(exc).__name__,
        )


def record_token_mint(scope: str, success: bool) -> None:
    """Counter for a scoped API token mint attempt."""
    try:
        tags = {
            "scope": str(scope or "")[:64],
            "success": "true" if success else "false",
        }
        _emit_metric(
            "migration_cloud.token_mints.count", "counter", 1, tags,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud_metric_emit_failed metric=%s err=%s",
            "token_mints", type(exc).__name__,
        )


def record_legacy_hash_decryption(vendor: str, success: bool) -> None:
    """Counter for a legacy foreign-vendor hash verification attempt."""
    try:
        tags = {
            "vendor": str(vendor or "")[:32],
            "success": "true" if success else "false",
        }
        _emit_metric(
            "migration_cloud.legacy_hash_decryptions.count", "counter", 1, tags,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud_metric_emit_failed metric=%s err=%s",
            "legacy_hash_decryptions", type(exc).__name__,
        )


__all__ = [
    "_hash_tenant_id",
    "record_companion_upload",
    "record_maa_sign",
    "record_key_rotation",
    "record_webhook_delivery",
    "record_token_mint",
    "record_legacy_hash_decryption",
]
