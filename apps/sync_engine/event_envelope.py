"""Canonical offline event envelope (batch 1532) — queued sync, not CRDT."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

MAX_ENVELOPE_BYTES = 1024


class OfflineEnvelopeError(ValueError):
    """Invalid or oversized offline payload."""


@dataclass(frozen=True)
class OfflineEventEnvelope:
    entity: str
    entity_id: str
    op: str
    attribute_key: str
    attribute_value: Any
    deterministic_timestamp: str
    client_id: str
    bytes_estimate: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "entity_id": self.entity_id,
            "op": self.op,
            "attribute_key": self.attribute_key,
            "attribute_value": self.attribute_value,
            "deterministic_timestamp": self.deterministic_timestamp,
            "client_id": self.client_id,
            "bytes_estimate": self.bytes_estimate,
        }


def _estimate_bytes(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"))


def validate_envelope_dict(data: dict[str, Any], *, allow_oversize: bool = False) -> OfflineEventEnvelope:
    if not isinstance(data, dict):
        raise OfflineEnvelopeError("envelope must be a dict")
    entity = str(data.get("entity") or "").strip()
    entity_id = str(data.get("entity_id") or "").strip()
    op = str(data.get("op") or "upsert").strip().lower()
    attribute_key = str(data.get("attribute_key") or "").strip()
    if not entity or not entity_id:
        raise OfflineEnvelopeError("entity and entity_id required")
    ts = str(data.get("deterministic_timestamp") or "").strip()
    if not ts:
        ts = datetime.now(timezone.utc).isoformat()
    client_id = str(data.get("client_id") or "").strip()[:128]
    env = OfflineEventEnvelope(
        entity=entity,
        entity_id=entity_id,
        op=op,
        attribute_key=attribute_key,
        attribute_value=data.get("attribute_value"),
        deterministic_timestamp=ts,
        client_id=client_id,
    )
    size = _estimate_bytes(env.to_dict())
    if size > MAX_ENVELOPE_BYTES and not allow_oversize:
        raise OfflineEnvelopeError(f"envelope exceeds {MAX_ENVELOPE_BYTES} bytes ({size})")
    return OfflineEventEnvelope(
        entity=env.entity,
        entity_id=env.entity_id,
        op=env.op,
        attribute_key=env.attribute_key,
        attribute_value=env.attribute_value,
        deterministic_timestamp=env.deterministic_timestamp,
        client_id=env.client_id,
        bytes_estimate=size,
    )


def build_envelope(
    *,
    entity: str,
    entity_id: str,
    attribute_key: str,
    attribute_value: Any,
    client_id: str = "",
    op: str = "upsert",
) -> dict[str, Any]:
    """Build a validated envelope dict for API enqueue."""
    return validate_envelope_dict(
        {
            "entity": entity,
            "entity_id": entity_id,
            "op": op,
            "attribute_key": attribute_key,
            "attribute_value": attribute_value,
            "deterministic_timestamp": datetime.now(timezone.utc).isoformat(),
            "client_id": client_id,
        }
    ).to_dict()


__all__ = [
    "MAX_ENVELOPE_BYTES",
    "OfflineEnvelopeError",
    "OfflineEventEnvelope",
    "build_envelope",
    "validate_envelope_dict",
]
