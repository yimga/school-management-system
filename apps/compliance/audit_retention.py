"""Archive-before-purge retention for compliance records."""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connections, transaction
from django.db.models import Model, Q, QuerySet
from django.utils import timezone

from apps.compliance.models_audit import AuditArchiveRecord, AuditLegalHold
from apps.platform_runtime.append_only import AppendOnlyManager


@dataclass(frozen=True)
class ArchiveResult:
    archive: AuditArchiveRecord | None
    eligible_count: int
    held_count: int


def _archive_root() -> Path:
    configured = getattr(settings, "AUDIT_ARCHIVE_ROOT", "")
    return Path(configured or (Path(settings.BASE_DIR) / "var" / "audit-archives"))


def _signing_key() -> bytes:
    value = getattr(settings, "AUDIT_ARCHIVE_SIGNING_KEY", "")
    if not value:
        raise ImproperlyConfigured(
            "AUDIT_ARCHIVE_SIGNING_KEY is required for audit retention archives."
        )
    return str(value).encode("utf-8")


def _model_label(model: type[Model]) -> str:
    return model._meta.label


def _active_holds(model: type[Model], *, using: str = "default") -> QuerySet:
    return AuditLegalHold.objects.using(using).filter(is_active=True).filter(
        Q(model_label="") | Q(model_label=_model_label(model))
    )


def _legal_hold_filter(holds: Iterable[AuditLegalHold], timestamp_field: str) -> Q:
    combined = None
    for hold in holds:
        if not hold.object_id and not hold.starts_at and not hold.ends_at:
            return Q()
        scoped = Q()
        if hold.object_id:
            scoped &= Q(pk=hold.object_id)
        if hold.starts_at:
            scoped &= Q(**{f"{timestamp_field}__gte": hold.starts_at})
        if hold.ends_at:
            scoped &= Q(**{f"{timestamp_field}__lte": hold.ends_at})
        combined = scoped if combined is None else combined | scoped
    return combined if combined is not None else Q(pk__in=[])


def retention_queryset(
    model: type[Model], timestamp_field: str, cutoff_at, *, using: str = "default"
) -> tuple[QuerySet, int]:
    base = model.objects.using(using).filter(
        **{f"{timestamp_field}__lt": cutoff_at}
    )
    holds = list(_active_holds(model, using=using))
    if not holds:
        return base, 0
    held = base.filter(_legal_hold_filter(holds, timestamp_field))
    held_count = held.count()
    return base.exclude(pk__in=held.values("pk")), held_count


def _json_line(value: dict) -> bytes:
    return (
        json.dumps(
            value,
            cls=DjangoJSONEncoder,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _row_payload(row: Model) -> dict:
    fields = {}
    for field in row._meta.concrete_fields:
        fields[field.attname] = getattr(row, field.attname)
    return {"pk": str(row.pk), "fields": fields}


def _signature_payload(
    archive_id: uuid.UUID,
    model_label: str,
    timestamp_field: str,
    cutoff_at,
    record_count: int,
    sha256: str,
) -> bytes:
    return "|".join(
        (
            str(archive_id),
            model_label,
            timestamp_field,
            cutoff_at.isoformat(),
            str(record_count),
            sha256,
        )
    ).encode("utf-8")


def create_archive(
    model: type[Model],
    timestamp_field: str,
    cutoff_at,
    *,
    batch_size: int = 1000,
    using: str = "default",
) -> ArchiveResult:
    queryset, held_count = retention_queryset(
        model, timestamp_field, cutoff_at, using=using
    )
    record_count = queryset.count()
    if not record_count:
        return ArchiveResult(None, 0, held_count)

    archive_id = uuid.uuid4()
    model_label = _model_label(model)
    relative_path = Path(model._meta.app_label) / model._meta.model_name
    relative_path /= f"{archive_id}.jsonl.gz"
    destination = _archive_root() / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)

    first_record_at = None
    last_record_at = None
    digest = hashlib.sha256()
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{archive_id}-", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    try:
        with open(temporary_name, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
                header = {
                    "archive_id": str(archive_id),
                    "cutoff_at": cutoff_at,
                    "format": "gilead.audit-archive.v1",
                    "model_label": model_label,
                    "record_count": record_count,
                    "timestamp_field": timestamp_field,
                }
                compressed.write(_json_line({"manifest": header}))
                for row in queryset.order_by(timestamp_field, "pk").iterator(
                    chunk_size=batch_size
                ):
                    value = getattr(row, timestamp_field)
                    first_record_at = first_record_at or value
                    last_record_at = value
                    compressed.write(_json_line(_row_payload(row)))
        with open(temporary_name, "rb") as archived:
            for chunk in iter(lambda: archived.read(1024 * 1024), b""):
                digest.update(chunk)
        sha256 = digest.hexdigest()
        signature = hmac.new(
            _signing_key(),
            _signature_payload(
                archive_id,
                model_label,
                timestamp_field,
                cutoff_at,
                record_count,
                sha256,
            ),
            hashlib.sha256,
        ).hexdigest()
        os.replace(temporary_name, destination)
        archive = AuditArchiveRecord.objects.using(using).create(
            archive_id=archive_id,
            model_label=model_label,
            timestamp_field=timestamp_field,
            cutoff_at=cutoff_at,
            record_count=record_count,
            first_record_at=first_record_at,
            last_record_at=last_record_at,
            relative_path=relative_path.as_posix(),
            sha256=sha256,
            signature=signature,
        )
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise

    verify_archive(archive)
    return ArchiveResult(archive, record_count, held_count)


def _archive_path(archive: AuditArchiveRecord) -> Path:
    root = _archive_root().resolve()
    path = (root / archive.relative_path).resolve()
    if root != path and root not in path.parents:
        raise PermissionDenied("Audit archive path escapes AUDIT_ARCHIVE_ROOT.")
    return path


def verify_archive(archive: AuditArchiveRecord) -> list[str]:
    path = _archive_path(archive)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if not hmac.compare_digest(digest, archive.sha256):
        raise PermissionDenied("Audit archive checksum verification failed.")
    expected_signature = hmac.new(
        _signing_key(),
        _signature_payload(
            archive.archive_id,
            archive.model_label,
            archive.timestamp_field,
            archive.cutoff_at,
            archive.record_count,
            archive.sha256,
        ),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, archive.signature):
        raise PermissionDenied("Audit archive signature verification failed.")

    record_ids: list[str] = []
    with gzip.open(path, "rt", encoding="utf-8") as bundle:
        header = json.loads(bundle.readline()).get("manifest", {})
        if (
            header.get("archive_id") != str(archive.archive_id)
            or header.get("model_label") != archive.model_label
            or header.get("timestamp_field") != archive.timestamp_field
            or int(header.get("record_count", -1)) != archive.record_count
        ):
            raise PermissionDenied("Audit archive manifest verification failed.")
        for line in bundle:
            record_ids.append(str(json.loads(line)["pk"]))
    if len(record_ids) != archive.record_count or len(set(record_ids)) != len(
        record_ids
    ):
        raise PermissionDenied("Audit archive row-count verification failed.")
    return record_ids


def _approval_token_valid(provided: str) -> bool:
    expected = str(getattr(settings, "AUDIT_RETENTION_APPROVAL_TOKEN", ""))
    return bool(expected) and hmac.compare_digest(str(provided), expected)


def purge_verified_archive(
    archive: AuditArchiveRecord,
    model: type[Model],
    *,
    approval_token: str,
    using: str = "default",
) -> int:
    if archive.status != AuditArchiveRecord.Status.VERIFIED:
        raise PermissionDenied("Only verified, unpurged archives may be purged.")
    if archive.model_label != _model_label(model):
        raise PermissionDenied("Archive model does not match purge target.")
    if not _approval_token_valid(approval_token):
        raise PermissionDenied("Audit retention purge approval is missing or invalid.")

    record_ids = verify_archive(archive)
    holds = list(_active_holds(model, using=using))
    held_exists = bool(holds) and model.objects.using(using).filter(
        pk__in=record_ids
    ).filter(_legal_hold_filter(holds, archive.timestamp_field)).exists()
    if held_exists:
        raise PermissionDenied(
            "A legal hold now covers archived records; purge has been blocked."
        )

    database = connections[using]
    with transaction.atomic(using=using):
        manager = getattr(model, "objects", None)
        if isinstance(manager, AppendOnlyManager):
            table = database.ops.quote_name(model._meta.db_table)
            pk_column = database.ops.quote_name(model._meta.pk.column)
            placeholders = ", ".join(["%s"] * len(record_ids))
            with database.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM {table} WHERE {pk_column} IN ({placeholders})",
                    record_ids,
                )
                deleted = cursor.rowcount
        else:
            deleted, _ = model.objects.using(using).filter(
                pk__in=record_ids
            ).delete()
        if deleted != archive.record_count:
            raise PermissionDenied(
                "Purge count did not match the verified archive; transaction rolled back."
            )
        archive.status = AuditArchiveRecord.Status.PURGED
        archive.purged_at = timezone.now()
        archive.save(using=using, update_fields=["status", "purged_at"])
    return deleted


def archive_and_optionally_purge(
    model: type[Model],
    timestamp_field: str,
    cutoff_at,
    *,
    purge: bool = False,
    approval_token: str = "",
    using: str = "default",
) -> ArchiveResult:
    result = create_archive(
        model, timestamp_field, cutoff_at, using=using
    )
    if purge and result.archive:
        purge_verified_archive(
            result.archive,
            model,
            approval_token=approval_token,
            using=using,
        )
    return result
