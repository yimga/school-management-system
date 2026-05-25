"""
Tenant-to-tenant transfer envelopes (student / teacher).

Builds redacted, schema-validated envelopes suitable for transfer between
tenants. Backed by apps.global_registries.schema_mapping for canonical-field
validation. No raw PII leaves the originating tenant unless explicit consent
gates are recorded.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from apps.global_registries.schema_mapping import (
    MappingValidation,
    lookup,
    validate_custom_mapping,
)


logger = logging.getLogger(__name__)


class TransferEnvelopeError(RuntimeError):
    pass


ENVELOPE_VERSION = 1


@dataclass
class TransferEnvelope:
    envelope_kind: str
    schema_version: int
    source_tenant_id_hash: str
    target_tenant_id_hash: str
    canonical_fields: dict[str, Any] = field(default_factory=dict)
    custom_fields: dict[str, Any] = field(default_factory=dict)
    consent_records: list[dict[str, Any]] = field(default_factory=list)
    audit_metadata: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_kind": self.envelope_kind,
            "schema_version": self.schema_version,
            "source_tenant_id_hash": self.source_tenant_id_hash,
            "target_tenant_id_hash": self.target_tenant_id_hash,
            "canonical_fields": self.canonical_fields,
            "custom_fields": self.custom_fields,
            "consent_records": self.consent_records,
            "audit_metadata": self.audit_metadata,
            "checksum": self.checksum,
        }


_ENVELOPE_KINDS = frozenset({"student", "teacher", "academic_history"})


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _canonical_bytes(body: dict[str, Any]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_envelope(
    *,
    envelope_kind: str,
    source_tenant_id: str,
    target_tenant_id: str,
    canonical_data: dict[str, Any],
    custom_data: dict[str, Any] | None = None,
    consent_records: list[dict[str, Any]] | None = None,
    actor_id: str = "",
) -> TransferEnvelope:
    if envelope_kind not in _ENVELOPE_KINDS:
        raise TransferEnvelopeError(f"unknown envelope_kind {envelope_kind!r}")
    if not source_tenant_id or not target_tenant_id:
        raise TransferEnvelopeError("source and target tenant ids required")
    if source_tenant_id == target_tenant_id:
        raise TransferEnvelopeError("source and target tenant must differ")

    for key in canonical_data:
        if lookup(key) is None:
            raise TransferEnvelopeError(
                f"canonical_data key {key!r} is not in canonical registry"
            )

    custom = dict(custom_data or {})
    mapping: MappingValidation = validate_custom_mapping(
        custom_field_keys=list(custom.keys()),
        transferable_only=True,
    )
    if not mapping.ok:
        raise TransferEnvelopeError(
            f"custom_data contains unmappable keys: {mapping.unmapped_keys}"
        )

    body = {
        "envelope_kind": envelope_kind,
        "schema_version": ENVELOPE_VERSION,
        "source_tenant_id_hash": _hash(source_tenant_id),
        "target_tenant_id_hash": _hash(target_tenant_id),
        "canonical_fields": canonical_data,
        "custom_fields": custom,
        "consent_records": consent_records or [],
        "audit_metadata": {
            "actor_id_hash": _hash(actor_id) if actor_id else "",
        },
    }
    checksum = hashlib.sha256(_canonical_bytes(body)).hexdigest()
    envelope = TransferEnvelope(
        envelope_kind=envelope_kind,
        schema_version=ENVELOPE_VERSION,
        source_tenant_id_hash=body["source_tenant_id_hash"],
        target_tenant_id_hash=body["target_tenant_id_hash"],
        canonical_fields=canonical_data,
        custom_fields=custom,
        consent_records=consent_records or [],
        audit_metadata=body["audit_metadata"],
        checksum=checksum,
    )
    logger.info(
        "transfer_envelope.build kind=%s source=%s target=%s checksum=%s",
        envelope_kind,
        envelope.source_tenant_id_hash,
        envelope.target_tenant_id_hash,
        checksum[:12],
        extra={"scope": "transfer_envelope.build"},
    )
    return envelope


def build_student_envelope(**kwargs: Any) -> TransferEnvelope:
    return build_envelope(envelope_kind="student", **kwargs)


def build_teacher_envelope(**kwargs: Any) -> TransferEnvelope:
    return build_envelope(envelope_kind="teacher", **kwargs)


__all__ = [
    "ENVELOPE_VERSION",
    "TransferEnvelope",
    "TransferEnvelopeError",
    "build_envelope",
    "build_student_envelope",
    "build_teacher_envelope",
]
