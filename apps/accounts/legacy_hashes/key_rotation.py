"""MultiFernet key rotation tooling for v3.33.0.

Operator-facing helpers for walking every Fernet-wrapped column on the
platform and re-encrypting under the newest active key. Pairs with the
``DJANGO_CRYPTOGRAPHY_KEYS`` rotation contract documented in
``docs/SECURITY_KEYS.md``.

Security invariants (NEVER violate):

* **Zero key material in logs / audit trail.** The append-only
  ``KEY_ROTATION_LOG`` JSONL writes per-row decrypt success/fail
  booleans + table counts only — never the ciphertext, never the
  plaintext, never the key bytes themselves.
* **Per-row atomic.** Each re-encrypt write is wrapped in its own
  ``transaction.atomic()`` savepoint so a failure on row 47 does not
  poison the visibility of rows 1-46.
* **Tenant-isolation marker.** Rotation walks ALL tenants by design
  (every row in every model). The querysets carry
  ``# tenant-isolation-allow: ops-key-rotation-all-tenants`` markers
  so the scan_tenant_queryset_safety.py gate stays clean.
* **Constant-time compare.** When we need to compare two ciphertexts
  (verify the re-encryption did not no-op), we use ``hmac.compare_digest``.

Public surface:

* :func:`rotate_all_encrypted_columns(dry_run=True)` — walks every
  registered field and re-encrypts under the newest key.
* :func:`verify_no_orphan_ciphertexts()` — scans for ciphertext that
  cannot decrypt under any current key (lost-key indicator); returns
  per-model row-PK lists.
* :data:`KEY_ROTATION_LOG` — path template for the append-only audit
  trail. The actual filename is materialized per-run with the UTC ISO
  timestamp.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from django.apps import apps as django_apps
from django.db import connection, transaction

from .encryption import (
    EncryptedBinaryField,
    EncryptedCharField,
    EncryptedJSONField,
    _get_fernet,
    _get_primary_fernet,
    active_key_count,
    backend_in_use,
)

logger = logging.getLogger(__name__)

# Path TEMPLATE — callers materialize via ``_resolve_log_path()`` so the
# timestamp resolves at run time, not at module import time.
KEY_ROTATION_LOG = "logs/key_rotation_{utc_iso}.jsonl"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class RotationResult:
    """Per-table outcome from :func:`rotate_all_encrypted_columns`."""

    app_label: str
    model_name: str
    field_names: list[str] = field(default_factory=list)
    rows_scanned: int = 0
    rows_rewrapped: int = 0
    rows_skipped: int = 0
    rows_failed: int = 0

    @property
    def label(self) -> str:
        return f"{self.app_label}.{self.model_name}"

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "model": self.label,
            "fields": list(self.field_names),
            "rows_scanned": self.rows_scanned,
            "rows_rewrapped": self.rows_rewrapped,
            "rows_skipped": self.rows_skipped,
            "rows_failed": self.rows_failed,
        }


@dataclass
class OrphanCheckResult:
    """Per-model outcome from :func:`verify_no_orphan_ciphertexts`."""

    app_label: str
    model_name: str
    field_names: list[str] = field(default_factory=list)
    rows_scanned: int = 0
    orphan_pks: list[Any] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.app_label}.{self.model_name}"

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "model": self.label,
            "fields": list(self.field_names),
            "rows_scanned": self.rows_scanned,
            "orphan_count": len(self.orphan_pks),
            "orphan_pks": list(self.orphan_pks),
        }


# ---------------------------------------------------------------------------
# Field discovery
# ---------------------------------------------------------------------------


_ENCRYPTED_FIELD_TYPES = (
    EncryptedCharField,
    EncryptedJSONField,
    EncryptedBinaryField,
)


def _iter_encrypted_fields(model_filter: Optional[str] = None):
    """Yield (model, [field, ...]) pairs for every model that has at
    least one EncryptedCharField/JSONField/BinaryField declared.

    ``model_filter`` is the dotted ``app_label.ModelName`` string used
    by the management command's ``--model`` flag.
    """
    target_app = None
    target_model = None
    if model_filter:
        if "." not in model_filter:
            raise ValueError(
                f"model_filter must be 'app_label.ModelName', got {model_filter!r}"
            )
        target_app, target_model = model_filter.split(".", 1)

    for model in django_apps.get_models():
        meta = model._meta
        if target_app and meta.app_label != target_app:
            continue
        if target_model and meta.model_name.lower() != target_model.lower():
            continue
        encrypted = [
            f for f in meta.get_fields()
            if getattr(f, "concrete", False)
            and isinstance(f, _ENCRYPTED_FIELD_TYPES)
        ]
        if encrypted:
            yield model, encrypted


# ---------------------------------------------------------------------------
# Audit log writer
# ---------------------------------------------------------------------------


def _resolve_log_path(template: str = KEY_ROTATION_LOG) -> Path:
    """Materialize the audit log path for this run.

    Resolved relative to the Django ``BASE_DIR`` if it can be loaded,
    otherwise relative to the current working directory.
    """
    try:
        from django.conf import settings
        base = Path(getattr(settings, "BASE_DIR", os.getcwd()))
    except Exception:  # pragma: no cover
        base = Path(os.getcwd())
    utc_iso = datetime.now(tz=dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return base / template.format(utc_iso=utc_iso)


def _audit_line(path: Path, payload: dict[str, Any]) -> None:
    """Append one JSONL record. NEVER contains key material / plaintext /
    ciphertext.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        fh.write("\n")


# ---------------------------------------------------------------------------
# Core: rotate every encrypted column
# ---------------------------------------------------------------------------


def rotate_all_encrypted_columns(
    dry_run: bool = True,
    model_filter: Optional[str] = None,
    log_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Walk every model with Fernet-wrapped columns and re-encrypt
    each row under the newest active key.

    ``dry_run=True`` (default): scans every row, exercises the decrypt
    path under the MultiFernet, but never writes — used to confirm
    every row would round-trip cleanly before committing to writes.

    ``dry_run=False``: actually re-saves under the primary key. Each
    row goes through its own ``transaction.atomic()`` savepoint so a
    bad row can't corrupt the bulk pass.

    Returns a dict with per-table counts and a summary. Also appends
    one JSONL line per row + one summary line to the audit log. Audit
    log NEVER contains key material / plaintext / ciphertext.
    """
    log_file = log_path or _resolve_log_path()
    results: list[RotationResult] = []

    _audit_line(
        log_file,
        {
            "event": "rotation_start",
            "dry_run": dry_run,
            "model_filter": model_filter,
            "backend": backend_in_use(),
            "active_key_count": active_key_count(),
            "utc": datetime.now(tz=dt_timezone.utc).isoformat(),
        },
    )

    multi = _get_fernet()
    primary = _get_primary_fernet()

    for model, encrypted_fields in _iter_encrypted_fields(model_filter):
        res = RotationResult(
            app_label=model._meta.app_label,
            model_name=model._meta.model_name,
            field_names=[f.name for f in encrypted_fields],
        )
        # tenant-isolation-allow: ops-key-rotation-all-tenants
        qs = model._default_manager.all()
        # Force a stable order so re-runs hit rows in the same sequence.
        try:
            qs = qs.order_by("pk")
        except Exception:  # pragma: no cover - some virtual managers
            pass
        for row in qs.iterator():
            res.rows_scanned += 1
            try:
                # Decrypt + re-encrypt under primary.
                changed_any = False
                row_ok = True
                for fobj in encrypted_fields:
                    raw = _read_raw_column(model, row, fobj)
                    if raw in (None, "", b""):
                        continue
                    pt = _decrypt_raw(multi, raw, fobj)
                    if pt is None:
                        row_ok = False
                        break
                    new_ct = _encrypt_under(primary, pt, fobj)
                    if not _ciphertexts_equal(raw, new_ct):
                        changed_any = True
                        _write_raw_column(row, fobj, new_ct)
                if not row_ok:
                    res.rows_failed += 1
                    _audit_line(
                        log_file,
                        {
                            "event": "row_decrypt_failed",
                            "model": res.label,
                            "pk": row.pk,
                            "decrypted_ok": False,
                        },
                    )
                    continue
                if dry_run or not changed_any:
                    res.rows_skipped += 1
                    _audit_line(
                        log_file,
                        {
                            "event": "row_skipped",
                            "model": res.label,
                            "pk": row.pk,
                            "decrypted_ok": True,
                            "dry_run": dry_run,
                            "already_under_primary": (not changed_any),
                        },
                    )
                    continue
                # Write raw ciphertext via a parameterized raw-SQL UPDATE
                # that bypasses the field descriptor (queryset.update()
                # also calls get_prep_value, which would re-encrypt and
                # double-wrap). The values are written exactly as the
                # primary Fernet emitted them.
                with transaction.atomic():
                    table = model._meta.db_table
                    pk_col = model._meta.pk.column
                    set_cols = [fobj2.column for fobj2 in encrypted_fields]
                    set_vals = [getattr(row, fobj2.attname) for fobj2 in encrypted_fields]
                    quote = connection.ops.quote_name
                    set_clause = ", ".join(f"{quote(c)} = %s" for c in set_cols)
                    sql = (
                        f"UPDATE {quote(table)} SET {set_clause} "
                        f"WHERE {quote(pk_col)} = %s"
                    )
                    # tenant-isolation-allow: ops-key-rotation-all-tenants
                    with connection.cursor() as cur:
                        cur.execute(sql, [*set_vals, row.pk])
                res.rows_rewrapped += 1
                _audit_line(
                    log_file,
                    {
                        "event": "row_rewrapped",
                        "model": res.label,
                        "pk": row.pk,
                        "decrypted_ok": True,
                    },
                )
            except Exception:  # noqa: BLE001 - log + count, never re-raise
                res.rows_failed += 1
                logger.exception(
                    "key_rotation_row_failed",
                    extra={"model": res.label, "pk": getattr(row, "pk", None)},
                )
                _audit_line(
                    log_file,
                    {
                        "event": "row_failed_exception",
                        "model": res.label,
                        "pk": getattr(row, "pk", None),
                        "decrypted_ok": False,
                    },
                )
        results.append(res)

    summary = {
        "event": "rotation_summary",
        "dry_run": dry_run,
        "model_filter": model_filter,
        "tables": [r.to_summary_dict() for r in results],
        "totals": {
            "rows_scanned": sum(r.rows_scanned for r in results),
            "rows_rewrapped": sum(r.rows_rewrapped for r in results),
            "rows_skipped": sum(r.rows_skipped for r in results),
            "rows_failed": sum(r.rows_failed for r in results),
        },
        "log_path": str(log_file),
    }
    _audit_line(log_file, summary)
    logger.info(
        "key_rotation_complete",
        extra={k: v for k, v in summary.items() if k != "tables"},
    )
    return summary


# ---------------------------------------------------------------------------
# Orphan check
# ---------------------------------------------------------------------------


def verify_no_orphan_ciphertexts(
    model_filter: Optional[str] = None,
) -> dict[str, Any]:
    """Scan every encrypted column; report rows that cannot decrypt
    under any currently-active key.

    Orphans are an emergency signal — they indicate that a key was
    dropped from ``DJANGO_CRYPTOGRAPHY_KEYS`` before its data finished
    rotating, OR that an off-key wrote a column outside the platform.
    Either way, the operator must triage before the next rotation.
    """
    results: list[OrphanCheckResult] = []
    multi = _get_fernet()

    for model, encrypted_fields in _iter_encrypted_fields(model_filter):
        res = OrphanCheckResult(
            app_label=model._meta.app_label,
            model_name=model._meta.model_name,
            field_names=[f.name for f in encrypted_fields],
        )
        # tenant-isolation-allow: ops-key-rotation-all-tenants
        qs = model._default_manager.all()
        try:
            qs = qs.order_by("pk")
        except Exception:  # pragma: no cover
            pass
        for row in qs.iterator():
            res.rows_scanned += 1
            for fobj in encrypted_fields:
                raw = _read_raw_column(model, row, fobj)
                if raw in (None, "", b""):
                    continue
                pt = _decrypt_raw(multi, raw, fobj)
                if pt is None:
                    res.orphan_pks.append(row.pk)
                    break
        results.append(res)

    totals = {
        "models_scanned": len(results),
        "rows_scanned": sum(r.rows_scanned for r in results),
        "orphan_count": sum(len(r.orphan_pks) for r in results),
    }
    payload = {
        "event": "orphan_scan_summary",
        "model_filter": model_filter,
        "tables": [r.to_summary_dict() for r in results],
        "totals": totals,
    }
    logger.info(
        "key_rotation_orphan_scan_complete",
        extra={"totals": totals, "model_filter": model_filter},
    )
    return payload


# ---------------------------------------------------------------------------
# Internals: read raw bytes, decrypt safely, write back
# ---------------------------------------------------------------------------


def _read_raw_column(model, row, fobj) -> Any:
    """Read the on-disk *ciphertext* column for ``fobj`` on ``row``.

    The Encrypted* fields' ``from_db_value`` decrypts transparently;
    to inspect the *ciphertext* we re-query the column via the
    underlying values list, which bypasses the descriptor.
    """
    raw_qs = model._default_manager.filter(pk=row.pk).values_list(fobj.attname, flat=True)
    # tenant-isolation-allow: ops-key-rotation-all-tenants
    raw = raw_qs.first()
    return raw


def _decrypt_raw(multi, raw: Any, fobj) -> Optional[Any]:
    """Decrypt the raw column under the MultiFernet.

    Returns the plaintext value typed for the field, or ``None`` if the
    ciphertext cannot decrypt under any active key. NEVER logs the
    ciphertext or the failure cause's bytes.
    """
    from cryptography.fernet import InvalidToken
    try:
        if isinstance(fobj, EncryptedBinaryField):
            if isinstance(raw, memoryview):
                raw = raw.tobytes()
            if isinstance(raw, str):
                raw_bytes = raw.encode("utf-8")
            else:
                raw_bytes = bytes(raw)
            return multi.decrypt(raw_bytes)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        plaintext_bytes = multi.decrypt(raw.encode("utf-8"))
        if isinstance(fobj, EncryptedJSONField):
            return json.loads(plaintext_bytes.decode("utf-8"))
        return plaintext_bytes.decode("utf-8")
    except (InvalidToken, ValueError, TypeError, AttributeError):
        return None


def _encrypt_under(primary, plaintext: Any, fobj) -> Any:
    """Encrypt ``plaintext`` under a single-key (primary) Fernet.

    Returns the on-disk shape for ``fobj`` (str for Char/JSON, bytes
    for Binary).
    """
    if isinstance(fobj, EncryptedBinaryField):
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")
        return primary.encrypt(bytes(plaintext))
    if isinstance(fobj, EncryptedJSONField):
        serialized = json.dumps(plaintext, separators=(",", ":"), sort_keys=True)
        return primary.encrypt(serialized.encode("utf-8")).decode("utf-8")
    if isinstance(plaintext, bytes):
        plaintext = plaintext.decode("utf-8")
    return primary.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def _ciphertexts_equal(a: Any, b: Any) -> bool:
    """Constant-time compare two ciphertexts. Returns False if either
    side cannot be coerced to bytes — that conservative answer forces
    a re-write rather than skipping.
    """
    try:
        if isinstance(a, memoryview):
            a = a.tobytes()
        if isinstance(b, memoryview):
            b = b.tobytes()
        if isinstance(a, str):
            a = a.encode("utf-8")
        if isinstance(b, str):
            b = b.encode("utf-8")
        if not isinstance(a, (bytes, bytearray)) or not isinstance(b, (bytes, bytearray)):
            return False
        return hmac.compare_digest(bytes(a), bytes(b))
    except (TypeError, ValueError, AttributeError):
        return False


def _write_raw_column(row, fobj, new_ct: Any) -> None:
    """Assign the new ciphertext to the *instance attribute* under
    ``fobj.attname`` so ``save(update_fields=[...])`` writes it without
    re-encrypting (the descriptor's ``get_prep_value`` would otherwise
    double-wrap).
    """
    # Bypass the descriptor: directly write to __dict__ under attname so
    # subsequent save() emits the literal ciphertext.
    setattr(row, fobj.attname, new_ct)


__all__ = [
    "KEY_ROTATION_LOG",
    "OrphanCheckResult",
    "RotationResult",
    "rotate_all_encrypted_columns",
    "verify_no_orphan_ciphertexts",
]
