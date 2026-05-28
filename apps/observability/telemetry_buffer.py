"""
Offline-safe telemetry buffer.

Accumulates redacted telemetry packets in-memory until flushed; flush yields a
canonical payload that can be uploaded later by online sync. Designed for
edge-runtime / offline-first deployment where a packet author cannot block on
the network.

No PII keys are accepted in payloads; sensitive keys are dropped on ingest.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Iterable


logger = logging.getLogger(__name__)


SCHEMA_VERSION = 1


class TelemetryBufferError(RuntimeError):
    pass


_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "private_key",
        "signature_text",
        "ssn",
        "dob",
        "email",
        "raw_prompt",
        "credential",
        "credentials",
    }
)


def _scrub(payload: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in _SENSITIVE_KEYS:
            continue
        if isinstance(value, dict):
            clean[key] = _scrub(value)
        elif isinstance(value, list):
            clean[key] = [_scrub(item) if isinstance(item, dict) else item for item in value]
        else:
            clean[key] = value
    return clean


@dataclass(frozen=True)
class TelemetryPacket:
    packet_id: str
    tenant_id_hash: str
    event_type: str
    schema_version: int
    payload: dict[str, Any]
    checksum: str


def _canonical_bytes(body: dict[str, Any]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_tenant(tenant_id: str) -> str:
    return hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:12]


class TelemetryBuffer:
    def __init__(self, *, capacity: int = 10_000) -> None:
        if capacity <= 0:
            raise TelemetryBufferError("capacity must be > 0")
        self._capacity = capacity
        self._packets: list[TelemetryPacket] = []
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._packets)

    def capacity(self) -> int:
        return self._capacity

    def record(
        self,
        *,
        tenant_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> TelemetryPacket:
        if not tenant_id:
            raise TelemetryBufferError("tenant_id required")
        if not event_type:
            raise TelemetryBufferError("event_type required")
        clean_payload = _scrub(dict(payload or {}))
        body = {
            "schema_version": SCHEMA_VERSION,
            "tenant_id_hash": _hash_tenant(tenant_id),
            "event_type": event_type,
            "payload": clean_payload,
        }
        checksum = hashlib.sha256(_canonical_bytes(body)).hexdigest()
        packet = TelemetryPacket(
            packet_id=str(uuid.uuid4()),
            tenant_id_hash=body["tenant_id_hash"],
            event_type=event_type,
            schema_version=SCHEMA_VERSION,
            payload=clean_payload,
            checksum=checksum,
        )
        with self._lock:
            if len(self._packets) >= self._capacity:
                self._packets.pop(0)
            self._packets.append(packet)
        return packet

    def peek(self) -> tuple[TelemetryPacket, ...]:
        with self._lock:
            return tuple(self._packets)

    def flush(self, *, sign_with: bytes = b"") -> dict[str, Any]:
        with self._lock:
            packets = list(self._packets)
            self._packets.clear()
        items = [
            {
                "packet_id": p.packet_id,
                "tenant_id_hash": p.tenant_id_hash,
                "event_type": p.event_type,
                "schema_version": p.schema_version,
                "payload": p.payload,
                "checksum": p.checksum,
            }
            for p in packets
        ]
        body = {
            "schema_version": SCHEMA_VERSION,
            "packet_count": len(items),
            "packets": items,
        }
        flush_checksum = hashlib.sha256(_canonical_bytes(body)).hexdigest()
        body["flush_checksum"] = flush_checksum
        if sign_with:
            body["signature"] = hmac.new(sign_with, _canonical_bytes({"flush_checksum": flush_checksum}), hashlib.sha256).hexdigest()
        logger.info(
            "telemetry_buffer.flush packets=%d checksum=%s signed=%s",
            len(items),
            flush_checksum[:12],
            bool(sign_with),
            extra={"scope": "telemetry_buffer.flush"},
        )
        return body


_DEFAULT_BUFFER: TelemetryBuffer | None = None


def default_buffer() -> TelemetryBuffer:
    global _DEFAULT_BUFFER
    if _DEFAULT_BUFFER is None:
        _DEFAULT_BUFFER = TelemetryBuffer()
    return _DEFAULT_BUFFER


def reset_default_buffer() -> None:
    global _DEFAULT_BUFFER
    _DEFAULT_BUFFER = None


def record(
    *,
    tenant_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> TelemetryPacket:
    return default_buffer().record(tenant_id=tenant_id, event_type=event_type, payload=payload)


def packets() -> Iterable[TelemetryPacket]:
    return default_buffer().peek()


__all__ = [
    "SCHEMA_VERSION",
    "TelemetryBuffer",
    "TelemetryBufferError",
    "TelemetryPacket",
    "default_buffer",
    "packets",
    "record",
    "reset_default_buffer",
]
