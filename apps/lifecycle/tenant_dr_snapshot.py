"""Compile, encrypt, sign, and persist daily tenant immutable snapshots.

A snapshot is a gzip-compressed, Fernet-ENCRYPTED, HMAC-SHA256-signed JSON
document. Both the encryption key and the signing key are derived from
``SECRET_KEY`` mixed with the school id (under distinct domain-separation
labels, so the confidentiality key is never the same bytes as the integrity
key), binding a blob to both the platform secret and the owning tenant.
``restore_from_snapshot`` verifies the signature *before* decrypting, parsing,
or materializing anything (fail closed on tamper).

Why encryption and not just the signature: an HMAC proves integrity and
authenticity but gives ZERO confidentiality. The payload carries the tenant's
whole config core — student and teacher PII, the finance ledger, and
``accounts.User`` rows whose password HASHES are captured verbatim (see the
restorable scope below). Left as plain gzip, anyone able to read
``var/tenant_snapshots/`` or the optional ``TENANT_SNAPSHOT_S3_BUCKET`` could
``gzip.decompress`` the lot. The blob is now ciphertext at rest in every store.

Order is encrypt-then-MAC: the signature covers the CIPHERTEXT (the bytes
actually stored), so a tampered blob is rejected before any decryption is
attempted. Snapshots written before encryption landed are raw gzip and remain
restorable — ``_decrypt_blob`` passes a gzip-magic blob through unchanged. That
is not a downgrade vector: the HMAC is verified first, and an attacker cannot
forge it without ``SECRET_KEY``.

Payload contract (``schema_version`` "2.3"):

- ``counts`` — aggregate row counts (kept for backward compatibility and for a
  cheap restore-integrity check).
- ``tables`` — REAL restorable row data, captured via
  ``django.core.serializers`` (``json`` format), which preserves field types
  (dates / decimals / JSON / FK-by-pk) faithfully.

Restorable scope (see ``docs/DR_SELF_HOST_RESTORE_RUNBOOK.md``). The plan is
strictly FK-dependency ordered — parents precede children so an intra-snapshot
FK can be rewritten to the freshly restored parent pk:

    schools.School           (the target config row, upserted by slug)
    accounts.User            (staff identity required by TeacherProfile.user;
                              NOT school-scoped — keyed by username; password
                              HASH restored verbatim so DR keeps credentials)
    finance.ComplianceProfile(required PROTECT parent of Invoice.profile;
                              NOT school-scoped — keyed by name + country_code)
    academics.AcademicYear   (natural key: school + name)
    academics.Department     (natural key: school + code)
    academics.Term           (natural key: school + academic_year + name)
    academics.Classroom      (natural key: school + code)
    people.StudentProfile    (natural key: school + student_code; ``user`` nulled)
    people.TeacherProfile    (natural key: school + user; ``user`` remapped to a
                              restored accounts.User; payroll/photo FKs nulled)
    finance.Invoice          (natural key: school + payment_code; ``profile`` /
                              ``student`` / ``academic_year`` remapped; out-of-
                              scope optional FKs nulled; full_clean bypassed)
    finance.InvoiceLine      (natural key: invoice + description + amount;
                              ``invoice`` remapped; fee_item nulled. Restored
                              before Payment so the invoice's total is real when
                              the payment recalc fires)
    finance.Payment          (natural key: school + reference_number, with an
                              amount/paid_at fallback when blank; ``invoice`` /
                              ``student`` remapped; full_clean bypassed)

Schema 2.2 additionally restores tenant ACCESS and the start of the academic
record:

    academics.Subject        (natural key: school + name; the subject catalog)
    schools.SchoolMembership (natural key: user + school; ``user`` remapped to a
                              restored accounts.User — restores WHO can reach the
                              tenant + their role/ownership, so a recovered tenant
                              has admins and is reachable)
    academics.Attendance     (natural key: student + classroom + date; both FKs
                              remapped; the per-day attendance history)

Schema 2.3 additionally restores coursework (both models carry a non-null
``school`` FK, so capture is a plain school= filter and every FK parent is
already captured above):

    academics.LMSAssignment  (natural key: classroom + title + due_at; classroom
                              / subject / term / teacher remapped; attachment file
                              nulled — only the path string would survive)
    academics.LMSSubmission  (natural key: assignment + student; both remapped —
                              the grade + submission body; graded_by User and the
                              attachment file nulled as out-of-scope)

Still OUT of the restorable surface (deferred, larger FK closures / lower DR
priority): grades (evals.Evaluation → SubjectAssignment, whose natural key drags
Specialty + an M2M teacher set), messages (communication, wide user fan-out) and
the timetable (academics ScheduleEntry / TimeSlot). These are the next expansion.

The fail-closed HMAC signature guarantee is unchanged: ``restore_from_snapshot``
verifies the signature (and the bound school id) BEFORE opening any transaction
or writing any row, for the FULL expanded payload above.

Each schema bump is a pure superset — it only ADDS table keys. Older 2.0 / 2.1
snapshots restore unchanged (the new specs find no rows for their keys and are
no-ops), so reading legacy blobs stays backward-compatible.
"""

from __future__ import annotations

import base64
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
from django.core.serializers.json import DjangoJSONEncoder

logger = logging.getLogger(__name__)

SNAPSHOT_SCHEMA_VERSION = "2.3"


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

    ``school_scoped`` (default ``True``) controls two things: whether the row's
    ``school`` FK is forced onto the target tenant, and whether the idempotency
    lookup is scoped by ``school=``. Shared, NON-tenant parents that a tenant's
    rows merely reference (``accounts.User`` behind a teacher, the platform-level
    ``finance.ComplianceProfile`` behind an invoice) set this ``False`` so they
    upsert by their own global natural key without a (nonexistent) school filter.

    ``fallback_natural_key`` is consulted only when EVERY value of the primary
    ``natural_key`` is empty/None (e.g. a ``Payment`` with a blank
    ``reference_number``) so such rows still upsert idempotently rather than
    duplicating on re-run.

    ``raw_save`` bypasses an overridden ``Model.save`` (calling
    ``models.Model.save`` directly) for ledger tables whose ``save()`` runs
    ``full_clean`` / interactive-create validation (invoice-balance checks,
    payment_code autogen) that must not re-fire when faithfully restoring an
    already-validated historical row.
    """

    app_label: str
    model_name: str
    natural_key: tuple[str, ...]
    remap_fk: dict[str, tuple[str, str]]
    null_fields: tuple[str, ...] = ()
    school_scoped: bool = True
    fallback_natural_key: tuple[str, ...] = ()
    raw_save: bool = False

    @property
    def label(self) -> str:
        return f"{self.app_label}.{self.model_name}"


# Dependency-ordered restore plan. Parents precede children so FK remap targets
# already exist when a child is restored.
#
# FK-ordering rationale (each entry's remap targets appear ABOVE it):
#   User, ComplianceProfile  -> no in-scope parents (shared, global).
#   AcademicYear/Department   -> only School (resolved at the top of restore).
#   Term -> AcademicYear; Classroom -> AcademicYear + Department.
#   StudentProfile -> only School (user nulled).
#   TeacherProfile -> User (above) + Department (above); reports_to self-FK
#                     handled in-table via pk_map of the same label.
#   LMSAssignment -> Classroom + Subject + Term + TeacherProfile (all above).
#   LMSSubmission -> LMSAssignment (above) + StudentProfile (above).
#   Invoice -> ComplianceProfile (above) + StudentProfile + AcademicYear (above).
#   InvoiceLine -> Invoice (above); precedes Payment so the invoice total is real
#                  when the payment's post_save recalc evaluates the lines.
#   Payment -> Invoice (above) + StudentProfile (above).
RESTORE_PLAN: tuple[_RestoreSpec, ...] = (
    # --- Shared, non-tenant parents required by the children below -----------
    _RestoreSpec(
        app_label="accounts",
        model_name="User",
        # AbstractUser.username is globally unique — the stable identity key.
        natural_key=("username",),
        remap_fk={},
        school_scoped=False,
    ),
    _RestoreSpec(
        app_label="finance",
        model_name="ComplianceProfile",
        # Not school-scoped; (name, country_code) identifies the regional profile.
        natural_key=("name", "country_code"),
        remap_fk={},
        school_scoped=False,
    ),
    # --- Academic config core ------------------------------------------------
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
        app_label="academics",
        model_name="Subject",
        # UniqueConstraint(school, name) — school is forced, so name identifies.
        natural_key=("name",),
        remap_fk={},
    ),
    # --- People --------------------------------------------------------------
    _RestoreSpec(
        app_label="people",
        model_name="StudentProfile",
        natural_key=("student_code",),
        remap_fk={},
        null_fields=("user",),
    ),
    _RestoreSpec(
        app_label="people",
        model_name="TeacherProfile",
        # TeacherProfile has no school-scoped unique scalar; the OneToOne ``user``
        # (remapped to a restored accounts.User) is the stable identity key.
        natural_key=("user",),
        remap_fk={
            "user": ("accounts", "User"),
            "department": ("academics", "Department"),
            "reports_to": ("people", "TeacherProfile"),
        },
        # ``user`` is non-nullable (so it is remapped, never nulled). pay_scale
        # (payroll) + the profile photo are out of the config-core scope.
        null_fields=("pay_scale", "profile_photo"),
    ),
    # --- Access + academic record (schema 2.2) -------------------------------
    _RestoreSpec(
        app_label="schools",
        model_name="SchoolMembership",
        # unique_together (user, school) — school is forced, ``user`` (remapped to
        # a restored accounts.User) identifies the membership within the tenant.
        # Restores WHO can access the tenant and their role/ownership — without it
        # a restored tenant has no admins and is unreachable.
        natural_key=("user",),
        remap_fk={"user": ("accounts", "User")},
    ),
    _RestoreSpec(
        app_label="academics",
        model_name="Attendance",
        # UniqueConstraint(student, classroom, date) — both FKs are in scope and
        # remapped to the freshly restored parents. client_offline_id (an offline
        # -sync artifact) is restored verbatim; its (school, client_offline_id)
        # partial-unique is per-tenant and never collides on a fresh target.
        natural_key=("student", "classroom", "date"),
        remap_fk={
            "student": ("people", "StudentProfile"),
            "classroom": ("academics", "Classroom"),
        },
    ),
    # --- Coursework / LMS (schema 2.3) ---------------------------------------
    _RestoreSpec(
        app_label="academics",
        model_name="LMSAssignment",
        # The model has no unique constraint, so a piece of work is identified
        # within its (remapped) classroom by title + due date — the same
        # "parent + descriptive fields" pattern as finance.InvoiceLine. ``due_at``
        # may be null; _natural_lookup filters it as IS NULL, which is stable.
        natural_key=("classroom", "title", "due_at"),
        remap_fk={
            "classroom": ("academics", "Classroom"),
            "subject": ("academics", "Subject"),
            # ``term`` is nullable; remap only fires when a term_id is present.
            "term": ("academics", "Term"),
            "teacher": ("people", "TeacherProfile"),
        },
        # The uploaded attachment file is not part of the DR row scope (only the
        # path string would survive, dangling without the object store).
        null_fields=("attachment",),
    ),
    _RestoreSpec(
        app_label="academics",
        model_name="LMSSubmission",
        # unique_together (assignment, student) — both FKs are in scope and
        # remapped to the freshly restored parents. Mirrors academics.Attendance.
        natural_key=("assignment", "student"),
        remap_fk={
            "assignment": ("academics", "LMSAssignment"),
            "student": ("people", "StudentProfile"),
        },
        # ``graded_by`` is an out-of-scope User (may be any role) and the
        # submission attachment lives outside the DR row scope.
        null_fields=("graded_by", "attachment"),
    ),
    # --- Finance ledger ------------------------------------------------------
    _RestoreSpec(
        app_label="finance",
        model_name="Invoice",
        natural_key=("payment_code",),  # unique per Invoice
        remap_fk={
            "profile": ("finance", "ComplianceProfile"),
            "student": ("people", "StudentProfile"),
            "academic_year": ("academics", "AcademicYear"),
        },
        # Out-of-scope optional FKs / files cleared; the ledger row itself is real.
        null_fields=(
            "counterparty",
            "currency",
            "created_by",
            "updated_by",
            "attachment",
            "payment_proof",
        ),
        raw_save=True,
    ),
    _RestoreSpec(
        app_label="finance",
        model_name="InvoiceLine",
        # No school-scoped unique scalar; a line is identified within its (already
        # remapped) parent invoice by description + amount. Restored AFTER Invoice
        # (FK parent) and BEFORE Payment so the invoice carries its real total when
        # the payment's post_save recalc fires — without the lines, recalc would
        # zero the restored invoice's total.
        natural_key=("invoice", "description", "amount"),
        remap_fk={"invoice": ("finance", "Invoice")},
        # FeeItem is a tenant fee-catalog row outside the config-core scope.
        null_fields=("fee_item",),
        school_scoped=False,
    ),
    _RestoreSpec(
        app_label="finance",
        model_name="Payment",
        natural_key=("reference_number",),  # unique when present
        fallback_natural_key=("invoice", "amount", "paid_at"),
        remap_fk={
            "invoice": ("finance", "Invoice"),
            "student": ("people", "StudentProfile"),
        },
        null_fields=(
            "payment_method",
            "currency",
            "region",
            "created_by",
            "processed_by",
            "receipt_file",
        ),
        raw_save=True,
    ),
)


def _signing_key(school_id: str) -> bytes:
    material = (
        str(getattr(settings, "SECRET_KEY", "") or "")
        + ":tenant-snapshot:"
        + str(school_id)
    ).encode("utf-8")
    return hashlib.sha256(material).digest()


def _encryption_key(school_id: str) -> bytes:
    """Fernet key bound to the platform secret AND the owning tenant.

    Derived exactly like ``_signing_key`` but under a DISTINCT domain-separation
    label, so the confidentiality key is never the same bytes as the integrity
    key (reusing one key for both HMAC and encryption is a classic footgun).
    Fernet wants 32 url-safe-base64 bytes, which is what a base64'd sha256
    digest is.
    """
    material = (
        str(getattr(settings, "SECRET_KEY", "") or "")
        + ":tenant-snapshot-encryption:"
        + str(school_id)
    ).encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(material).digest())


# gzip's two magic bytes. A stored blob starting with these is a pre-encryption
# (legacy) snapshot rather than a Fernet token.
_GZIP_MAGIC = b"\x1f\x8b"


def encrypt_blob(compressed: bytes, *, school_id: str) -> bytes:
    """Fernet-encrypt a compressed snapshot payload (AES-CBC + HMAC under the hood)."""
    from cryptography.fernet import Fernet

    return Fernet(_encryption_key(school_id)).encrypt(compressed)


def decrypt_blob(data: bytes, *, school_id: str) -> bytes:
    """Decrypt a stored snapshot blob back to its gzip bytes.

    A legacy (pre-encryption) snapshot is raw gzip and is passed through
    unchanged so existing backups stay restorable — a DR system that cannot read
    its own history is worse than one that was late to encrypt. This is NOT a
    downgrade vector: callers verify the HMAC over these exact stored bytes
    BEFORE calling here, and an attacker cannot forge that signature without
    ``SECRET_KEY``.
    """
    if data[:2] == _GZIP_MAGIC:
        return data
    from cryptography.fernet import Fernet, InvalidToken

    try:
        return Fernet(_encryption_key(school_id)).decrypt(data)
    except InvalidToken as exc:
        # Wrong tenant key / wrong SECRET_KEY / corruption — fail closed.
        raise ValueError("snapshot_decrypt_failed") from exc


def sign_payload(payload_bytes: bytes, *, school_id: str) -> str:
    return hmac.new(_signing_key(school_id), payload_bytes, hashlib.sha256).hexdigest()


def verify_signature(payload_bytes: bytes, signature_hex: str, *, school_id: str) -> bool:
    expected = sign_payload(payload_bytes, school_id=school_id)
    return hmac.compare_digest(expected, str(signature_hex or ""))


def _snapshot_roots() -> tuple[Path, Path]:
    """Resolve the primary + secondary snapshot directories.

    Defaults to two subdirectories of ``BASE_DIR/var/tenant_snapshots`` (same as
    before). An operator can override EITHER via ``TENANT_SNAPSHOT_PRIMARY_DIR`` /
    ``TENANT_SNAPSHOT_SECONDARY_DIR`` (settings, env-driven) to place the second
    copy on a SEPARATELY MOUNTED disk/volume — making the two stores genuinely
    independent failure domains instead of two folders on one ephemeral disk.
    """
    repo = Path(getattr(settings, "BASE_DIR", ".")).resolve()
    default_primary = repo / "var" / "tenant_snapshots" / "primary"
    default_secondary = repo / "var" / "tenant_snapshots" / "secondary"

    primary_override = (getattr(settings, "TENANT_SNAPSHOT_PRIMARY_DIR", None) or "").strip()
    secondary_override = (
        getattr(settings, "TENANT_SNAPSHOT_SECONDARY_DIR", None) or ""
    ).strip()

    primary = Path(primary_override).expanduser() if primary_override else default_primary
    secondary = (
        Path(secondary_override).expanduser() if secondary_override else default_secondary
    )
    primary.mkdir(parents=True, exist_ok=True)
    secondary.mkdir(parents=True, exist_ok=True)
    return primary, secondary


def _paths_share_device(primary: Path, secondary: Path) -> bool:
    """True when both paths live on the same filesystem device (one failure domain)."""
    try:
        return primary.resolve().stat().st_dev == secondary.resolve().stat().st_dev
    except OSError:
        # If either path cannot be stated, treat as shared (fail-honest).
        return True


def snapshot_durability_status(
    primary: Path | None = None,
    secondary: Path | None = None,
) -> dict[str, Any]:
    """Classify snapshot durability for ops honesty (Metric #28).

    Classes:
      * ``object_storage`` — ``TENANT_SNAPSHOT_S3_BUCKET`` is set (off-box third leg)
      * ``split_volume`` — local primary/secondary on different ``st_dev``
      * ``ephemeral_dual_dir`` — two dirs on the same device (default layout)
    """
    if primary is None or secondary is None:
        primary, secondary = _snapshot_roots()
    bucket = (getattr(settings, "TENANT_SNAPSHOT_S3_BUCKET", None) or "").strip()
    if bucket:
        cls = "object_storage"
    elif not _paths_share_device(primary, secondary):
        cls = "split_volume"
    else:
        cls = "ephemeral_dual_dir"
    return {
        "class": cls,
        "independent": cls != "ephemeral_dual_dir",
        "primary": str(primary),
        "secondary": str(secondary),
        "s3_bucket": bucket or None,
        "same_device": _paths_share_device(primary, secondary),
    }


def _assert_or_warn_snapshot_durability(primary: Path, secondary: Path) -> dict[str, Any]:
    """Warn (or raise when required) when dual dirs share one ephemeral disk."""
    status = snapshot_durability_status(primary, secondary)
    if status["independent"]:
        return status
    msg = (
        "tenant_snapshot_durability_ephemeral primary=%s secondary=%s — "
        "both stores share one device; set TENANT_SNAPSHOT_SECONDARY_DIR on a "
        "separate volume or TENANT_SNAPSHOT_S3_BUCKET for an independent store"
    )
    logger.warning(msg, status["primary"], status["secondary"])
    if bool(getattr(settings, "TENANT_SNAPSHOT_REQUIRE_INDEPENDENT_STORES", False)):
        raise RuntimeError(
            "TENANT_SNAPSHOT_REQUIRE_INDEPENDENT_STORES=1 but snapshot stores are "
            f"ephemeral_dual_dir (primary={status['primary']}, "
            f"secondary={status['secondary']})"
        )
    return status


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
    from apps.accounts.models import User
    from apps.schools.models import SchoolMembership
    from apps.people.models import StudentProfile, TeacherProfile
    from apps.finance.models import ComplianceProfile, Invoice, InvoiceLine, Payment
    from apps.academics.models import (
        AcademicYear,
        Attendance,
        Classroom,
        Department,
        Subject,
        Term,
    )
    from apps.academics.models_lms import LMSAssignment, LMSSubmission

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

    # --- Tenant-scoped row sets ---------------------------------------------
    teachers_qs = TeacherProfile.objects.filter(school=school)
    invoices_qs = Invoice.objects.filter(school=school)
    payments_qs = Payment.objects.filter(school=school)

    # Shared, non-tenant PARENTS pulled in only because a tenant row references
    # them (closure of the FK graph above), restored by their global natural key:
    #   * the staff Users behind this school's teachers (TeacherProfile.user is
    #     a required OneToOne — non-nullable, so it cannot be cleared on restore);
    #   * the ComplianceProfiles behind this school's invoices (Invoice.profile
    #     is a PROTECT FK — the row cannot exist without its profile parent).
    teacher_user_ids = [
        uid for uid in teachers_qs.values_list("user_id", flat=True) if uid is not None
    ]
    # SchoolMembership users must also be captured — a membership row restored
    # against a user that was never snapshotted could not remap its ``user`` FK,
    # so the tenant's admins/owners would be lost on restore. Close the FK graph
    # over BOTH teacher identities and membership identities.
    membership_qs = SchoolMembership.objects.filter(school=school)
    membership_user_ids = [
        uid for uid in membership_qs.values_list("user_id", flat=True) if uid is not None
    ]
    invoice_profile_ids = [
        pid
        for pid in invoices_qs.values_list("profile_id", flat=True)
        if pid is not None
    ]
    # tenant-isolation-allow: closure-of-tenant-fk-graph-restricted-to-referenced-pks
    referenced_users_qs = User.objects.filter(
        pk__in=set(teacher_user_ids) | set(membership_user_ids)
    )
    # tenant-isolation-allow: closure-of-tenant-fk-graph-restricted-to-referenced-pks
    referenced_profiles_qs = ComplianceProfile.objects.filter(
        pk__in=set(invoice_profile_ids)
    )

    tables: dict[str, list[dict[str, Any]]] = {
        # Parents first (restore order is driven by RESTORE_PLAN, not dict order,
        # but keep capture readable in dependency order).
        "accounts.User": _serialize_rows(referenced_users_qs),
        "finance.ComplianceProfile": _serialize_rows(referenced_profiles_qs),
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
        "academics.Subject": _serialize_rows(Subject.objects.filter(school=school)),
        "people.StudentProfile": _serialize_rows(
            StudentProfile.objects.filter(school=school)
        ),
        "people.TeacherProfile": _serialize_rows(teachers_qs),
        # Access rows — WHO can reach the tenant and their role/ownership.
        "schools.SchoolMembership": _serialize_rows(membership_qs),
        # Student attendance history (student + classroom both in-scope parents).
        "academics.Attendance": _serialize_rows(
            Attendance.objects.filter(school=school)
        ),
        # Coursework — LMS assignments + student submissions (schema 2.3). Both
        # carry a NON-NULL school FK, so a plain school= filter is complete and
        # tenant-isolation-clean; every FK parent (classroom/subject/term/teacher,
        # and the assignment itself for submissions) is already captured above.
        "academics.LMSAssignment": _serialize_rows(
            LMSAssignment.objects.filter(school=school)
        ),
        "academics.LMSSubmission": _serialize_rows(
            LMSSubmission.objects.filter(school=school)
        ),
        "finance.Invoice": _serialize_rows(invoices_qs),
        # Invoice line items — an invoice restored without its lines loses its
        # real total (recalc would zero it). Scoped to this school's invoices.
        # tenant-isolation-allow: closure-of-tenant-fk-graph-via-invoice-school
        "finance.InvoiceLine": _serialize_rows(
            InvoiceLine.objects.filter(invoice__school=school)
        ),
        "finance.Payment": _serialize_rows(payments_qs),
    }

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "school_id": sid,
        "slug": getattr(school, "slug", ""),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "school_config": school_config,
        "counts": {
            "memberships": membership_qs.count(),
            "students": StudentProfile.objects.filter(school=school).count(),
            "teachers": TeacherProfile.objects.filter(school=school).count(),
            "subjects": Subject.objects.filter(school=school).count(),
            "attendance": Attendance.objects.filter(school=school).count(),
            "lms_assignments": LMSAssignment.objects.filter(school=school).count(),
            "lms_submissions": LMSSubmission.objects.filter(school=school).count(),
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
    """Write encrypted+signed JSON to primary + secondary stores; persist metadata row."""
    from apps.lifecycle.models_dr_snapshot import TenantImmutableSnapshot

    day = snapshot_date or datetime.now(timezone.utc).date()
    payload = compile_snapshot_payload(school)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(raw)
    # Encrypt-then-MAC: the tenant PII / password hashes / ledger never touch a
    # disk or an S3 bucket as plaintext, and the signature covers the CIPHERTEXT
    # (the bytes actually stored) so tamper is caught before any decryption.
    stored = encrypt_blob(compressed, school_id=str(school.pk))
    digest = hashlib.sha256(stored).hexdigest()
    sig = sign_payload(stored, school_id=str(school.pk))

    primary_root, secondary_root = _snapshot_roots()
    _assert_or_warn_snapshot_durability(primary_root, secondary_root)
    fname = f"{getattr(school, 'slug', school.pk)}_{day.isoformat()}.json.gz"
    primary_path = primary_root / fname
    secondary_path = secondary_root / fname
    primary_path.write_bytes(stored)
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
            "byte_size": len(stored),
        },
    )
    return {
        "snapshot_id": str(row.pk),
        "school_id": str(school.pk),
        "snapshot_date": day.isoformat(),
        "byte_size": len(stored),
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

    Order matters: verify the HMAC over the stored bytes FIRST, then decrypt.
    Never decrypt attacker-controlled bytes you have not authenticated.
    """
    data = path.read_bytes()
    if not verify_signature(data, expected_sig, school_id=school_id):
        raise ValueError("snapshot_signature_mismatch")
    compressed = decrypt_blob(data, school_id=school_id)
    payload = json.loads(gzip.decompress(compressed).decode("utf-8"))
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


def _key_all_empty(fields: dict[str, Any], keys: tuple[str, ...]) -> bool:
    """True when every value for ``keys`` is None or an empty string."""
    return all((fields.get(k) in (None, "")) for k in keys)


def _natural_lookup(spec: _RestoreSpec, fields: dict[str, Any], school) -> dict[str, Any]:
    """Idempotent-upsert lookup for one row.

    Uses the primary ``natural_key``; if every primary-key value is blank/None
    (e.g. a Payment with no ``reference_number``) it falls back to
    ``fallback_natural_key`` so re-running restore still upserts rather than
    duplicating. School-scoped models also pin ``school=`` so idempotency never
    bleeds across tenants.
    """
    keys = spec.natural_key
    if spec.fallback_natural_key and _key_all_empty(fields, spec.natural_key):
        keys = spec.fallback_natural_key
    lookup: dict[str, Any] = {key: fields.get(key) for key in keys}
    # Scope idempotency to the target school only when the model is school-scoped.
    if spec.school_scoped:
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

                # Force tenant ownership onto the target school — only for
                # school-scoped models. Shared parents (accounts.User,
                # finance.ComplianceProfile) keep their own (non-tenant) values.
                from django.core.exceptions import FieldDoesNotExist

                if spec.school_scoped:
                    try:
                        school_field = model._meta.get_field("school")
                    except FieldDoesNotExist:  # pragma: no cover - no school FK
                        school_field = None
                    if school_field is not None and getattr(
                        school_field, "concrete", False
                    ):
                        fields["school"] = school.pk

                lookup = _natural_lookup(spec, fields, school)
                existing = model.objects.filter(**lookup).first()

                # Deserialize a single object from the (remapped) field dict.
                # Use the JSON deserializer (matching the JSON serializer used at
                # capture time) so ISO date / decimal-string values parse back to
                # native types faithfully.
                record = {"model": spec.label.lower(), "pk": None, "fields": fields}
                # DjangoJSONEncoder so UUID FK values (e.g. fields["school"] = a UUID
                # School pk), Decimals and dates serialize — plain json.dumps raises
                # "Object of type UUID is not JSON serializable" and broke restore for
                # any tenant with UUID-bearing rows.
                obj_wrapper = next(
                    serializers.deserialize(
                        "json", json.dumps([record], cls=DjangoJSONEncoder)
                    )
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
                # Ledger tables (Invoice / Payment) carry an overridden ``save``
                # that runs interactive-create validation (full_clean, balance
                # checks, payment_code autogen). A faithfully restored historical
                # row was already valid at capture time, so bypass it and write
                # the row as-is via the base ``Model.save``.
                if spec.raw_save:
                    from django.db import models as _dj_models

                    _dj_models.Model.save(instance)
                else:
                    instance.save()
                pk_map[spec.label][old_pk] = instance.pk

            report["tables"][spec.label] = {"created": created, "updated": updated}

    payload["restored"] = report
    return payload
