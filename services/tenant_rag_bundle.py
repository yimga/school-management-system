"""Signed, tenant-bound transport for the canonical AIEmbeddingStore."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from typing import Any, Iterable

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

BUNDLE_SCHEMA = "rmc.tenant-rag-bundle.v1"
SIGNING_ALGORITHM = "HMAC-SHA256"
MAX_BUNDLE_RECORDS = 100_000
MAX_VECTOR_DIMENSIONS = 16_384


class TenantRAGBundleError(ValueError):
    pass


@dataclass(frozen=True)
class ImportSummary:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    tombstoned: int = 0


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _signing_key(*, require_explicit: bool = True) -> bytes:
    explicit = (
        os.environ.get("TENANT_RAG_BUNDLE_SIGNING_KEY")
        or getattr(settings, "TENANT_RAG_BUNDLE_SIGNING_KEY", "")
        or ""
    ).strip()
    if explicit:
        return explicit.encode("utf-8")
    if not require_explicit and settings.DEBUG:
        return f"development-only:{settings.SECRET_KEY}".encode("utf-8")
    raise TenantRAGBundleError(
        "TENANT_RAG_BUNDLE_SIGNING_KEY is required for tenant RAG bundle signing."
    )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value.astimezone(datetime_timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any, *, field: str, required: bool = False) -> datetime | None:
    if value in (None, ""):
        if required:
            raise TenantRAGBundleError(f"{field} is required.")
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise TenantRAGBundleError(f"{field} must be an ISO-8601 datetime.")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, datetime_timezone.utc)
    return parsed


def _tenant_id(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise TenantRAGBundleError("tenant_id must be a valid UUID.") from exc


def _vector(value: Any, *, status: str) -> list[float]:
    if status == "tombstone":
        return []
    if not isinstance(value, list) or not value:
        raise TenantRAGBundleError("Active records require a non-empty embedding.")
    if len(value) > MAX_VECTOR_DIMENSIONS:
        raise TenantRAGBundleError("Embedding exceeds the maximum supported dimensions.")
    vector: list[float] = []
    for item in value:
        try:
            number = float(item)
        except (TypeError, ValueError) as exc:
            raise TenantRAGBundleError("Embedding values must be numeric.") from exc
        if not math.isfinite(number):
            raise TenantRAGBundleError("Embedding values must be finite.")
        vector.append(number)
    return vector


def _validated_record(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TenantRAGBundleError("Each bundle record must be an object.")
    scope = str(raw.get("scope") or "").strip()
    document_id = str(raw.get("document_id") or "").strip()
    text_hash = str(raw.get("text_hash") or "").strip().lower()
    status = str(raw.get("lifecycle_status") or "active").strip().lower()
    if not scope or len(scope) > 32:
        raise TenantRAGBundleError("Record scope is required and limited to 32 characters.")
    if not document_id or len(document_id) > 128:
        raise TenantRAGBundleError(
            "Record document_id is required and limited to 128 characters."
        )
    if len(text_hash) != 64 or any(c not in "0123456789abcdef" for c in text_hash):
        raise TenantRAGBundleError("Record text_hash must be a SHA-256 hex digest.")
    if status not in {"active", "tombstone"}:
        raise TenantRAGBundleError("Record lifecycle_status is invalid.")
    vector = _vector(raw.get("embedding"), status=status)
    dimensions = raw.get("embedding_dimensions")
    if dimensions in (None, ""):
        dimensions = len(vector) or None
    else:
        try:
            dimensions = int(dimensions)
        except (TypeError, ValueError) as exc:
            raise TenantRAGBundleError("embedding_dimensions must be an integer.") from exc
    if status == "active" and dimensions != len(vector):
        raise TenantRAGBundleError(
            "embedding_dimensions must match the embedding vector length."
        )
    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise TenantRAGBundleError("Record metadata must be an object.")
    source_updated_at = _parse_timestamp(
        raw.get("source_updated_at"),
        field="source_updated_at",
        required=True,
    )
    return {
        "conversation_id": str(raw.get("conversation_id") or "")[:64],
        "scope": scope,
        "document_id": document_id,
        "text_hash": text_hash,
        "embedding_model": str(raw.get("embedding_model") or "")[:128],
        "embedding_dimensions": dimensions,
        "embedding": vector,
        "lifecycle_status": status,
        "retention_until": _parse_timestamp(
            raw.get("retention_until"), field="retention_until"
        ),
        "source_updated_at": source_updated_at,
        "metadata": metadata,
    }


def sign_bundle_body(
    body: dict[str, Any],
    *,
    require_explicit_key: bool = True,
) -> dict[str, Any]:
    body_bytes = canonical_json_bytes(body)
    key = _signing_key(require_explicit=require_explicit_key)
    return {
        **body,
        "integrity": {
            "algorithm": SIGNING_ALGORITHM,
            "body_sha256": hashlib.sha256(body_bytes).hexdigest(),
            "signature": hmac.new(key, body_bytes, hashlib.sha256).hexdigest(),
        },
    }


def verify_bundle(
    envelope: dict[str, Any],
    *,
    expected_tenant_id: str,
    require_explicit_key: bool = True,
) -> dict[str, Any]:
    if not isinstance(envelope, dict):
        raise TenantRAGBundleError("Bundle envelope must be an object.")
    integrity = envelope.get("integrity")
    if not isinstance(integrity, dict):
        raise TenantRAGBundleError("Bundle integrity block is required.")
    if integrity.get("algorithm") != SIGNING_ALGORITHM:
        raise TenantRAGBundleError("Unsupported bundle signing algorithm.")
    body = {key: value for key, value in envelope.items() if key != "integrity"}
    body_bytes = canonical_json_bytes(body)
    expected_hash = hashlib.sha256(body_bytes).hexdigest()
    supplied_hash = str(integrity.get("body_sha256") or "")
    if not hmac.compare_digest(expected_hash, supplied_hash):
        raise TenantRAGBundleError("Bundle body checksum mismatch.")
    expected_signature = hmac.new(
        _signing_key(require_explicit=require_explicit_key),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(
        expected_signature, str(integrity.get("signature") or "")
    ):
        raise TenantRAGBundleError("Bundle signature verification failed.")
    if body.get("schema") != BUNDLE_SCHEMA:
        raise TenantRAGBundleError("Unsupported tenant RAG bundle schema.")
    tenant_id = _tenant_id(body.get("tenant_id"))
    if tenant_id != _tenant_id(expected_tenant_id):
        raise TenantRAGBundleError("Bundle tenant binding does not match import target.")
    records = body.get("records")
    if not isinstance(records, list):
        raise TenantRAGBundleError("Bundle records must be a list.")
    if len(records) > MAX_BUNDLE_RECORDS:
        raise TenantRAGBundleError("Bundle exceeds the maximum record count.")
    declared_count = body.get("record_count")
    if declared_count != len(records):
        raise TenantRAGBundleError("Bundle record_count does not match records.")
    _parse_timestamp(body.get("generated_at"), field="generated_at", required=True)
    return body


def export_tenant_rag_bundle(
    school_id: str,
    *,
    scopes: Iterable[str] | None = None,
    require_explicit_key: bool = True,
) -> dict[str, Any]:
    from apps.siteconfig.models import AIEmbeddingStore

    tenant_id = _tenant_id(school_id)
    qs = AIEmbeddingStore.objects.filter(school_id=tenant_id)
    normalized_scopes = sorted({str(scope).strip() for scope in scopes or [] if str(scope).strip()})
    if normalized_scopes:
        qs = qs.filter(scope__in=normalized_scopes)
    rows = qs.order_by("scope", "document_id", "text_hash", "id")
    records = []
    models: set[str] = set()
    dimensions: set[int] = set()
    for row in rows.iterator(chunk_size=1000):
        document_id = row.document_id or row.conversation_id or f"legacy:{row.pk}"
        model_id = row.embedding_model or ""
        vector = row.embedding if isinstance(row.embedding, list) else []
        dim = row.embedding_dimensions or (len(vector) or None)
        if model_id:
            models.add(model_id)
        if dim:
            dimensions.add(int(dim))
        records.append(
            {
                "conversation_id": row.conversation_id,
                "scope": row.scope,
                "document_id": document_id,
                "text_hash": row.text_hash,
                "embedding_model": model_id,
                "embedding_dimensions": dim,
                "embedding": vector if row.lifecycle_status == "active" else [],
                "lifecycle_status": row.lifecycle_status,
                "retention_until": _iso(row.retention_until),
                "source_updated_at": _iso(
                    row.source_updated_at or row.updated_at or row.created_at
                ),
                "metadata": row.metadata if isinstance(row.metadata, dict) else {},
            }
        )
    body = {
        "schema": BUNDLE_SCHEMA,
        "bundle_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "generated_at": _iso(timezone.now()),
        "record_count": len(records),
        "scopes": normalized_scopes,
        "embedding_contract": {
            "models": sorted(models),
            "dimensions": sorted(dimensions),
        },
        "records": records,
    }
    return sign_bundle_body(body, require_explicit_key=require_explicit_key)


@transaction.atomic
def import_tenant_rag_bundle(
    envelope: dict[str, Any],
    *,
    expected_school_id: str,
    require_explicit_key: bool = True,
) -> ImportSummary:
    from apps.siteconfig.models import AIEmbeddingStore

    body = verify_bundle(
        envelope,
        expected_tenant_id=expected_school_id,
        require_explicit_key=require_explicit_key,
    )
    tenant_id = _tenant_id(expected_school_id)
    created = updated = skipped = tombstoned = 0
    for raw in body["records"]:
        record = _validated_record(raw)
        document_rows = AIEmbeddingStore.objects.filter(
            school_id=tenant_id,
            scope=record["scope"],
            document_id=record["document_id"],
        )
        if record["lifecycle_status"] == "active":
            newer_tombstone = document_rows.filter(
                lifecycle_status="tombstone",
                source_updated_at__gte=record["source_updated_at"],
            ).exists()
            if newer_tombstone:
                skipped += 1
                continue
        identity_rows = document_rows.filter(text_hash=record["text_hash"]).order_by(
            "-source_updated_at", "-updated_at", "-id"
        )
        existing = identity_rows.first()
        if (
            existing
            and existing.source_updated_at
            and existing.source_updated_at > record["source_updated_at"]
        ):
            skipped += 1
            continue
        defaults = {
            "conversation_id": record["conversation_id"],
            "embedding_model": record["embedding_model"],
            "embedding_dimensions": record["embedding_dimensions"],
            "embedding": record["embedding"],
            "lifecycle_status": record["lifecycle_status"],
            "retention_until": record["retention_until"],
            "source_updated_at": record["source_updated_at"],
            "metadata": record["metadata"],
        }
        if existing:
            for field, value in defaults.items():
                setattr(existing, field, value)
            existing.save(update_fields=[*defaults.keys(), "updated_at"])
            updated += 1
        else:
            existing = AIEmbeddingStore.objects.create(
                school_id=tenant_id,
                scope=record["scope"],
                document_id=record["document_id"],
                text_hash=record["text_hash"],
                **defaults,
            )
            created += 1
        if record["lifecycle_status"] == "tombstone":
            affected = document_rows.filter(
                Q(source_updated_at__isnull=True)
                | Q(source_updated_at__lte=record["source_updated_at"])
            ).exclude(pk=existing.pk).update(
                lifecycle_status="tombstone",
                retention_until=record["retention_until"],
                source_updated_at=record["source_updated_at"],
            )
            tombstoned += affected + 1
    return ImportSummary(
        created=created,
        updated=updated,
        skipped=skipped,
        tombstoned=tombstoned,
    )
