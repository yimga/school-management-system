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
    # Optional multi-domain history payload: {canonical_domain: [row, ...]}.
    # Omitted from the checksum body when empty so pre-existing single-record
    # envelopes keep verifying byte-for-byte.
    domain_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
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
        if self.domain_rows:
            body["domain_rows"] = self.domain_rows
        return body


_ENVELOPE_KINDS = frozenset({"student", "teacher", "academic_history"})


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _canonical_bytes(body: dict[str, Any]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _validate_domain_rows(domain_rows: dict[str, list[dict[str, Any]]]) -> None:
    """Schema-validate the multi-domain payload against the canonical headers.

    The canonical-domain registry is owned by migration_cloud (the apply side);
    validating here keeps a malformed envelope from ever being sealed.
    """
    from apps.migration_cloud.accelerators.runmycampus_canonical import (
        DOMAIN_CANONICAL_HEADERS,
    )

    for domain, rows in domain_rows.items():
        headers = DOMAIN_CANONICAL_HEADERS.get(domain)
        if headers is None:
            raise TransferEnvelopeError(
                f"domain_rows domain {domain!r} is not a canonical domain"
            )
        for row in rows:
            extra = set(row.keys()) - headers
            if extra:
                raise TransferEnvelopeError(
                    f"domain_rows[{domain!r}] row has non-canonical keys: {sorted(extra)}"
                )


def build_envelope(
    *,
    envelope_kind: str,
    source_tenant_id: str,
    target_tenant_id: str,
    canonical_data: dict[str, Any],
    custom_data: dict[str, Any] | None = None,
    consent_records: list[dict[str, Any]] | None = None,
    domain_rows: dict[str, list[dict[str, Any]]] | None = None,
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

    rows_payload = {k: list(v) for k, v in (domain_rows or {}).items() if v}
    if rows_payload:
        _validate_domain_rows(rows_payload)

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
    if rows_payload:
        body["domain_rows"] = rows_payload
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
        domain_rows=rows_payload,
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


def envelope_from_dict(payload: dict[str, Any]) -> TransferEnvelope:
    """Rehydrate an envelope received as JSON (checksum verified by the apply side)."""
    if not isinstance(payload, dict):
        raise TransferEnvelopeError("envelope payload must be a dict")
    kind = payload.get("envelope_kind") or ""
    if kind not in _ENVELOPE_KINDS:
        raise TransferEnvelopeError(f"unknown envelope_kind {kind!r}")
    return TransferEnvelope(
        envelope_kind=kind,
        schema_version=int(payload.get("schema_version") or ENVELOPE_VERSION),
        source_tenant_id_hash=str(payload.get("source_tenant_id_hash") or ""),
        target_tenant_id_hash=str(payload.get("target_tenant_id_hash") or ""),
        canonical_fields=dict(payload.get("canonical_fields") or {}),
        custom_fields=dict(payload.get("custom_fields") or {}),
        consent_records=list(payload.get("consent_records") or []),
        audit_metadata=dict(payload.get("audit_metadata") or {}),
        domain_rows=dict(payload.get("domain_rows") or {}),
        checksum=str(payload.get("checksum") or ""),
    )


__all__ = [
    "ENVELOPE_VERSION",
    "TransferEnvelope",
    "TransferEnvelopeError",
    "build_envelope",
    "build_student_envelope",
    "build_teacher_envelope",
    "envelope_from_dict",
]
