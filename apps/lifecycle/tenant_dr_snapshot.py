"""Compile, sign, and persist daily tenant immutable snapshots.

A snapshot is a gzip-compressed, HMAC-SHA256-signed JSON document. The signing
key is derived from ``SECRET_KEY`` mixed with the school id, so a blob is bound
to both the platform secret and the owning tenant. ``restore_from_snapshot``
verifies the signature *before* parsing or materializing anything (fail closed
on tamper).

Payload contract (``schema_version`` "2.0"):

- ``counts`` — aggregate row counts (kept for backward compatibility and for a
  cheap restore-integrity check).
- ``tables`` — REAL restorable row data for the self-contained tenant config
  core, captured via ``django.core.serializers`` (``python`` format), which
  preserves field types (dates / decimals / JSON / FK-by-pk) faithfully.

Restorable scope (self-contained: no auth-User / PII dependency, no PROTECT FK
to an out-of-scope parent — see ``docs/DR_SELF_HOST_RESTORE_RUNBOOK.md``):

    schools.School (the target config row, upserted by slug)
    academics.AcademicYear   (natural key: school + name)
    academics.Department     (natural key: code)
    academics.Term           (natural key: academic_year + name)
    academics.Classroom      (natural key: code)
    people.StudentProfile    (natural key: student_code; ``user`` FK nulled)

Captured for counts but NOT auto-restored (documented in the runbook):
TeacherProfile (non-null User FK), Invoice / Payment (PROTECT FK to
ComplianceProfile / Counterparty). Those remain a roadmap item.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

SNAPSHOT_SCHEMA_VERSION = "2.0"


@dataclass(frozen=True)
class _RestoreSpec:
    """Declarative restore plan for one snapshotted table.

    ``app_label`` / ``model_name`` resolve a registered model. ``natural_key``
    is the tuple of field names whose values uniquely identify a row within the
    restored tenant (used for idempotent upsert). ``remap_fk`` maps a FK field
    name → the ``(app_label, model_name)`` of an in-scope parent so intra-
    snapshot references are rewritten to freshly restored pks. ``null_fields``
    are FK columns deliberately cleared on restore (out-of-scope dependency,
    e.g. ``StudentProfile.user``).
    """

    app_label: str
    model_name: str
    natural_key: tuple[str, ...]
    remap_fk: dict[str, tuple[str, str]]
    null_fields: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.app_label}.{self.model_name}"


# Dependency-ordered restore plan. Parents precede children so FK remap targets
# already exist when a child is restored.
RESTORE_PLAN: tuple[_RestoreSpec, ...] = (
    _RestoreSpec(
        app_label="academics",
        model_name="AcademicYear",
        natural_key=("name",),
        remap_fk={},
    ),
    _RestoreSpec(
        app_label="academics",
        model_name="Department",
        natural_key=("code",),
        remap_fk={},
    ),
    _RestoreSpec(
        app_label="academics",
        model_name="Term",
        # ``unique_together = (academic_year, name)`` — both needed for idempotency.
        natural_key=("academic_year", "name"),
        remap_fk={"academic_year": ("academics", "AcademicYear")},
    ),
    _RestoreSpec(
        app_label="academics",
        model_name="Classroom",
        natural_key=("code",),
        remap_fk={
            "academic_year": ("academics", "AcademicYear"),
            "department": ("academics", "Department"),
        },
    ),
    _RestoreSpec(
        app_label="people",
        model_name="StudentProfile",
        natural_key=("student_code",),
        remap_fk={},
        null_fields=("user",),
    ),
)


def _signing_key(school_id: str) -> bytes:
    material = (
        str(getattr(settings, "SECRET_KEY", "") or "")
        + ":tenant-snapshot:"
        + str(school_id)
    ).encode("utf-8")
    return hashlib.sha256(material).digest()


def sign_payload(payload_bytes: bytes, *, school_id: str) -> str:
    return hmac.new(_signing_key(school_id), payload_bytes, hashlib.sha256).hexdigest()


def verify_signature(payload_bytes: bytes, signature_hex: str, *, school_id: str) -> bool:
    expected = sign_payload(payload_bytes, school_id=school_id)
    return hmac.compare_digest(expected, str(signature_hex or ""))


def _snapshot_roots() -> tuple[Path, Path]:
    repo = Path(getattr(settings, "BASE_DIR", ".")).resolve()
    primary = repo / "var" / "tenant_snapshots" / "primary"
    secondary = repo / "var" / "tenant_snapshots" / "secondary"
    primary.mkdir(parents=True, exist_ok=True)
    secondary.mkdir(parents=True, exist_ok=True)
    return primary, secondary


def _serialize_rows(queryset) -> list[dict[str, Any]]:
    """Serialize a queryset to plain JSON-safe dicts via Django's ``json`` serializer.

    The ``json`` serializer emits ``{"model", "pk", "fields"}`` with every field
    value coerced to a JSON-natural type (ISO date/datetime strings,
    decimal-as-string, FK-as-pk). We parse the JSON string back into dicts so
    the result drops straight into the snapshot payload (which is itself
    ``json.dumps``-ed) and round-trips cleanly into ``serializers.deserialize``
    on restore. The ``python`` serializer would instead emit native
    ``datetime.date`` / ``Decimal`` objects that ``json.dumps`` cannot encode.
    """
    from django.core import serializers

    return json.loads(serializers.serialize("json", queryset))


def compile_snapshot_payload(school) -> dict[str, Any]:
    """Tenant state for DR: aggregate counts + REAL restorable config rows.

    ``counts`` is retained for backward compatibility and as a restore sanity
    check; ``tables`` carries the actual rows that ``restore_from_snapshot``
    materializes.
    """
    from apps.schools.models import SchoolMembership
    from apps.people.models import StudentProfile, TeacherProfile
    from apps.finance.models import Invoice, Payment
    from apps.academics.models import AcademicYear, Classroom, Department, Term

    sid = str(school.pk)

    school_config = {
        "slug": getattr(school, "slug", ""),
        "name": getattr(school, "name", ""),
        "subdomain": getattr(school, "subdomain", ""),
    }
    # Capture the School config row itself (restored as an upsert by slug).
    school_config["row"] = _serialize_rows(
        type(school).objects.filter(pk=school.pk)
    )

    tables: dict[str, list[dict[str, Any]]] = {
        "academics.AcademicYear": _serialize_rows(
            AcademicYear.objects.filter(school=school)
        ),
        "academics.Department": _serialize_rows(
            Department.objects.filter(school=school)
        ),
        "academics.Term": _serialize_rows(Term.objects.filter(school=school)),
        "academics.Classroom": _serialize_rows(
            Classroom.objects.filter(school=school)
        ),
        "people.StudentProfile": _serialize_rows(
            StudentProfile.objects.filter(school=school)
        ),
    }

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "school_id": sid,
        "slug": getattr(school, "slug", ""),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "school_config": school_config,
        "counts": {
            "memberships": SchoolMembership.objects.filter(school=school).count(),
            "students": StudentProfile.objects.filter(school=school).count(),
            "teachers": TeacherProfile.objects.filter(school=school).count(),
            "invoices": Invoice.objects.filter(school=school).count(),
            "payments": Payment.objects.filter(school=school).count(),
        },
        "tables": tables,
    }


def _maybe_upload_object_storage(*, local_path: Path, object_key: str) -> str | None:
    """Optional S3-compatible secondary when ``TENANT_SNAPSHOT_S3_BUCKET`` is set."""
    bucket = (getattr(settings, "TENANT_SNAPSHOT_S3_BUCKET", None) or "").strip()
    if not bucket:
        return None
    try:
        import boto3  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("tenant_snapshot_s3_skipped boto3_unavailable bucket=%s", bucket)
        return None
    client = boto3.client(
        "s3",
        endpoint_url=getattr(settings, "TENANT_SNAPSHOT_S3_ENDPOINT", None) or None,
    )
    client.upload_file(str(local_path), bucket, object_key)
    uri = f"s3://{bucket}/{object_key}"
    logger.info("tenant_snapshot_s3_uploaded uri=%s bytes=%s", uri, local_path.stat().st_size)
    return uri


def capture_daily_snapshot(school, *, snapshot_date: date | None = None) -> dict[str, Any]:
    """Write gzip JSON to primary + secondary stores; persist metadata row."""
    from apps.lifecycle.models_dr_snapshot import TenantImmutableSnapshot

    day = snapshot_date or datetime.now(timezone.utc).date()
    payload = compile_snapshot_payload(school)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(raw)
    digest = hashlib.sha256(compressed).hexdigest()
    sig = sign_payload(compressed, school_id=str(school.pk))

    primary_root, secondary_root = _snapshot_roots()
    fname = f"{getattr(school, 'slug', school.pk)}_{day.isoformat()}.json.gz"
    primary_path = primary_root / fname
    secondary_path = secondary_root / fname
    primary_path.write_bytes(compressed)
    shutil.copy2(primary_path, secondary_path)
    s3_uri = _maybe_upload_object_storage(
        local_path=secondary_path,
        object_key=f"tenant_snapshots/{getattr(school, 'slug', school.pk)}/{day.isoformat()}.json.gz",
    )

    row, _created = TenantImmutableSnapshot.objects.update_or_create(
        school=school,
        snapshot_date=day,
        defaults={
            "primary_uri": primary_path.as_posix(),
            "secondary_uri": s3_uri or secondary_path.as_posix(),
            "payload_sha256": digest,
            "signature_hex": sig,
            "byte_size": len(compressed),
        },
    )
    return {
        "snapshot_id": str(row.pk),
        "school_id": str(school.pk),
        "snapshot_date": day.isoformat(),
        "byte_size": len(compressed),
        "payload_sha256": digest,
        "signature_hex": sig,
        "primary_uri": row.primary_uri,
        "secondary_uri": row.secondary_uri,
    }


def load_snapshot_payload(path: Path, *, school_id: str, expected_sig: str) -> dict[str, Any]:
    """Verify signature + decompress + parse a snapshot. Fail closed on tamper.

    This is the read-only half of restore: it raises before any DB write if the
    signature does not match (tamper / wrong key / corruption) or the blob is
    bound to a different school.
    """
    data = path.read_bytes()
    if not verify_signature(data, expected_sig, school_id=school_id):
        raise ValueError("snapshot_signature_mismatch")
    payload = json.loads(gzip.decompress(data).decode("utf-8"))
    if str(payload.get("school_id")) != str(school_id):
        raise ValueError("snapshot_school_mismatch")
    return payload


def _resolve_target_school(payload: dict[str, Any], target_school):
    """Resolve / create the School the rows are materialized under.

    If ``target_school`` is supplied it is used as-is (self-host: restore into a
    freshly provisioned tenant). Otherwise the School config row from the
    snapshot is upserted by ``slug`` so a same-platform restore re-creates the
    tenant shell faithfully.
    """
    from apps.schools.models import School

    if target_school is not None:
        return target_school

    cfg = payload.get("school_config") or {}
    slug = (cfg.get("slug") or payload.get("slug") or "").strip()
    if not slug:
        raise ValueError("snapshot_missing_school_slug")

    rows = cfg.get("row") or []
    defaults = {
        "name": cfg.get("name") or slug,
        "subdomain": cfg.get("subdomain") or slug,
    }
    if rows:
        # Prefer the faithfully serialized School fields when present.
        fields = rows[0].get("fields", {})
        defaults["name"] = fields.get("name", defaults["name"]) or defaults["name"]
        defaults["subdomain"] = (
            fields.get("subdomain", defaults["subdomain"]) or defaults["subdomain"]
        )
    school, _created = School.objects.update_or_create(slug=slug, defaults=defaults)
    return school


def _natural_lookup(spec: _RestoreSpec, fields: dict[str, Any], school) -> dict[str, Any]:
    lookup: dict[str, Any] = {}
    for key in spec.natural_key:
        lookup[key] = fields.get(key)
    # Always scope idempotency to the target school when the model is school-scoped.
    lookup["school"] = school
    return lookup


def restore_from_snapshot(
    path: Path,
    *,
    school_id: str,
    expected_sig: str,
    target_school=None,
    materialize: bool = True,
) -> dict[str, Any]:
    """Verify, then MATERIALIZE snapshot rows into a target school.

    Signature is verified first (fail closed on tamper — raises before any DB
    write). With ``materialize=True`` (default) the in-scope tables are upserted
    by natural key inside a single transaction; intra-snapshot FK references are
    rewritten to the freshly restored parent pks. The operation is idempotent:
    re-running it updates the same rows rather than duplicating them.

    Returns the parsed payload augmented with a ``restored`` report (per-table
    created / updated counts and the target school pk). ``materialize=False``
    preserves the legacy read-only behavior (verify + parse only).
    """
    payload = load_snapshot_payload(path, school_id=school_id, expected_sig=expected_sig)
    if not materialize:
        return payload

    from django.apps import apps as django_apps
    from django.core import serializers
    from django.db import transaction

    tables = payload.get("tables") or {}
    report: dict[str, Any] = {"tables": {}, "target_school_id": None}

    with transaction.atomic():
        school = _resolve_target_school(payload, target_school)
        report["target_school_id"] = str(school.pk)
        # old-pk -> new-pk, keyed by model label, for intra-snapshot FK remap.
        pk_map: dict[str, dict[Any, Any]] = {spec.label: {} for spec in RESTORE_PLAN}

        for spec in RESTORE_PLAN:
            model = django_apps.get_model(spec.app_label, spec.model_name)
            rows = tables.get(spec.label) or []
            created = 0
            updated = 0
            for raw in rows:
                old_pk = raw.get("pk")
                fields = dict(raw.get("fields") or {})

                # Rewrite in-scope FK references to freshly restored parent pks.
                for fk_field, parent in spec.remap_fk.items():
                    parent_label = f"{parent[0]}.{parent[1]}"
                    old_ref = fields.get(fk_field)
                    if old_ref is not None:
                        fields[fk_field] = pk_map.get(parent_label, {}).get(old_ref)

                # Clear out-of-scope FK columns (e.g. StudentProfile.user).
                for nf in spec.null_fields:
                    fields[nf] = None

                # Force tenant ownership onto the target school.
                from django.core.exceptions import FieldDoesNotExist

                try:
                    school_field = model._meta.get_field("school")
                except FieldDoesNotExist:  # pragma: no cover - model without school FK
                    school_field = None
                if school_field is not None and getattr(school_field, "concrete", False):
                    fields["school"] = school.pk

                lookup = _natural_lookup(spec, fields, school)
                existing = model.objects.filter(**lookup).first()

                # Deserialize a single object from the (remapped) field dict.
                # Use the JSON deserializer (matching the JSON serializer used at
                # capture time) so ISO date / decimal-string values parse back to
                # native types faithfully.
                record = {"model": spec.label.lower(), "pk": None, "fields": fields}
                obj_wrapper = next(
                    serializers.deserialize("json", json.dumps([record]))
                )
                instance = obj_wrapper.object
                if existing is not None:
                    instance.pk = existing.pk
                    instance.id = existing.pk
                    updated += 1
                else:
                    instance.pk = None
                    instance.id = None
                    created += 1
                instance.save()
                pk_map[spec.label][old_pk] = instance.pk

            report["tables"][spec.label] = {"created": created, "updated": updated}

    payload["restored"] = report
    return payload
