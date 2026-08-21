"""Shared helpers for tenant-side landers.

Three pieces of shared plumbing every per-domain lander uses:

1. ``student_lookup_field(available)`` — pick the canonical external-id
   field name available on the tenant ``StudentProfile`` (different
   deployments use ``external_id``, ``sis_external_id``, ``source_id``,
   or ``admission_number``).

2. ``filter_to_model_fields(defaults, model)`` — drop keys the tenant
   model doesn't declare. Lets landers send the full canonical row
   without worrying about schema drift across tenants.

3. ``coerce_date`` / ``coerce_int`` / ``coerce_decimal`` / ``truthy`` —
   defensive coercions so a stray empty string or "yes" doesn't crash
   the lander; the row gets quarantined instead.
"""

from __future__ import annotations

import hashlib

from apps.migration_cloud.landers.reason_codes import (
    classify_message,
    normalize_reason_code,
)


def derive_external_id(
    *,
    first_name: str = "",
    middle_name: str = "",
    last_name: str = "",
    date_of_birth=None,
    place_of_birth: str = "",
    prefix: str = "auto",
) -> str:
    """Deterministic surrogate upsert key for a source row carrying no external id.

    ``external_id`` is the landers' upsert key -- it is what makes re-running a
    bundle UPDATE an existing person instead of duplicating them. Plenty of real
    rosters carry no source-system id column at all (a plain name/DOB/class
    spreadsheet is the norm for a school migrating off paper), and those rows were
    quarantined ``missing_required`` and NOTHING landed -- on an atomic bundle that
    also rolls back the perfectly valid files beside them.

    Minting a RANDOM id would land the row once and then duplicate it on every
    re-apply, breaking the single most-asked-for property of a migration. Hashing
    the row's stable identity keeps the upsert idempotent across re-runs and across
    two bundles carrying the same roster.

    Only identity-STABLE fields participate. Name, date of birth and place of birth
    do not change between exports; grade_level / section / status do, and folding
    those in would make a promoted student hash to a new id and duplicate at exactly
    the moment the school most needs continuity.

    Returns "" when there is no name to key on -- such a row is genuinely
    unidentifiable and must still be quarantined rather than silently invented.
    """
    parts = [
        str(first_name or "").strip(),
        str(middle_name or "").strip(),
        str(last_name or "").strip(),
    ]
    name = " ".join(" ".join(parts).split()).casefold()
    if not name:
        return ""
    seed = "|".join(
        (
            name,
            str(date_of_birth or "").strip(),
            str(place_of_birth or "").strip().casefold(),
        )
    )
    return f"{prefix}-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20]}"

import datetime as _dt
import hashlib
import re
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import IntegrityError, transaction


@contextmanager
def row_savepoint():
    """Isolate one row's DB write in a SAVEPOINT so a per-row failure under the
    forced-atomic finance apply rolls back only that write — not the whole bundle.

    Finance forces the orchestrator to wrap the ENTIRE apply in one
    ``transaction.atomic()`` (money must be all-or-nothing vs the control totals).
    Inside that block a raw ``IntegrityError`` — or a DB error SWALLOWED by a
    best-effort audit write (id-mapping / conflict / asset / DFV) — marks the whole
    connection ``needs_rollback``, so the lander's per-row ``try/except`` cannot
    continue: the next query raises ``TransactionManagementError`` and every GOOD
    row rolls back with the one bad one. Wrapping each write in a savepoint makes
    the per-row quarantine actually work. In autocommit (non-atomic) mode this is a
    harmless single-statement transaction, so it is safe to apply unconditionally.
    """
    with transaction.atomic():
        yield


_EXTERNAL_ID_CANDIDATES = ("external_id", "sis_external_id", "source_id", "admission_number")


def student_lookup_field(available: set[str]) -> str:
    for c in _EXTERNAL_ID_CANDIDATES:
        if c in available:
            return c
    return "admission_number"


def staff_lookup_field(available: set[str]) -> str:
    for c in ("external_id", "sis_external_id", "employee_id", "staff_number"):
        if c in available:
            return c
    return "external_id"


def model_field_names(model) -> set[str]:
    return {f.name for f in model._meta.get_fields()}


# Row keys a history file may use to name the student it refers to. Ordered by
# how specific the key is, so an explicitly student-scoped column beats a bare
# "name" column on a file that also names somebody else (a guardian, a teacher).
_STUDENT_NAME_KEYS = (
    "student_name",
    "student_full_name",
    "child_name",
    "ward_name",
    "learner_name",
    "pupil_name",
    "full_name",
    "name",
)
_STUDENT_DOB_KEYS = ("student_date_of_birth", "student_dob", "date_of_birth", "dob")
_STUDENT_INDEX_ATTR = "_rmc_student_identity_index"


def student_name_from_row(row) -> str:
    """The student's name as written on a history row, or ""."""
    for key in _STUDENT_NAME_KEYS:
        value = " ".join(str((row or {}).get(key) or "").split())
        if value:
            return value
    return ""


def name_tokens(*parts: Any) -> frozenset:
    """The set of name tokens, casefolded, punctuation-normalised.

    A SET rather than a sequence because the whole reason a school lands here is
    that nobody can be sure whether its files are written given-name-first or
    family-name-first -- and the roster may have been split one way while the
    attendance sheet is written the other. Comparing sets makes the match immune
    to that ordering, to comma forms ("Lovelace, Ada") and to double spacing,
    without guessing at either order.
    """
    out: list[str] = []
    for part in parts:
        cleaned = str(part or "").replace(",", " ").replace(".", " ").replace("-", " ")
        out.extend(t.casefold() for t in cleaned.split() if t)
    return frozenset(out)


def name_identity_key(*parts: Any) -> str:
    """Order-independent identity key for a person's name.

    Deliberately a SORTED token set rather than a formatted string: the whole
    reason a school lands here is that nobody can be sure whether its files are
    written given-name-first or family-name-first, and the roster may have been
    split one way while the attendance sheet is written the other. Comparing the
    set of name tokens makes the match immune to that ordering, to comma forms
    ("Lovelace, Ada") and to double spacing, without guessing at either order.
    """
    tokens: list[str] = []
    for part in parts:
        tokens.extend(str(part or "").replace(",", " ").split())
    return " ".join(sorted(t.casefold() for t in tokens if t))


def _student_identity_index(ctx, student_model) -> dict:
    """Name -> candidate pks for this school's students, built once per artifact.

    Cached on the LanderContext, which the orchestrator creates fresh per
    artifact, so a file with 40,000 attendance rows costs ONE query rather than
    one per row. Nothing in the history landers creates students, so the index
    cannot go stale within the artifact it serves.
    """
    cached = getattr(ctx, _STUDENT_INDEX_ATTR, None)
    if cached is not None:
        return cached

    fields = model_field_names(student_model)
    name_fields = [f for f in ("first_name", "middle_name", "last_name") if f in fields]
    by_name: dict = {}
    by_name_dob: dict = {}
    by_pair: dict = {}
    index = {
        "by_name": by_name,
        "by_name_dob": by_name_dob,
        "by_pair": by_pair,
        "tokens": {},
        "dob": {},
        "usable": bool(name_fields),
    }
    try:
        setattr(ctx, _STUDENT_INDEX_ATTR, index)
    except Exception:  # noqa: BLE001 - a frozen/slotted ctx just costs us the cache
        pass
    if not name_fields:
        return index

    has_dob = "date_of_birth" in fields
    columns = ["pk", *name_fields] + (["date_of_birth"] if has_dob else [])
    qs = student_model.objects.all()  # tenant-isolation-allow: scoped-below-via-ctx-school-when-model-has-school-field
    school = getattr(ctx, "school", None)
    if school is not None and "school" in fields:
        qs = qs.filter(school=school)
    for values in qs.values_list(*columns).iterator():
        pk, name_parts = values[0], values[1 : 1 + len(name_fields)]
        tokens = name_tokens(*name_parts)
        if not tokens:
            continue
        by_name.setdefault(" ".join(sorted(tokens)), set()).add(pk)
        index["tokens"][pk] = tokens
        index["dob"][pk] = str(values[-1] or "") if has_dob else ""
        for pair in _token_pairs(tokens):
            by_pair.setdefault(pair, set()).add(pk)
    return index


def _token_pairs(tokens: frozenset) -> list[tuple]:
    """Every 2-token combination, the index's coarse bucket key.

    Two tokens is the smallest a real name gets (given + family), so pairing
    finds every candidate whose stored name overlaps the row's by at least that
    much, without scanning the roster once per row.
    """
    ordered = sorted(tokens)
    return [
        (ordered[i], ordered[j])
        for i in range(len(ordered))
        for j in range(i + 1, len(ordered))
    ]


def _name_candidates(index: dict, tokens: frozenset) -> set:
    """Students whose stored name is compatible with the row's name.

    Compatible means one token set CONTAINS the other. Containment rather than
    equality is load-bearing in both directions: ``StudentProfile`` has no
    middle-name column, so a roster row "ANDONGMAD FAVOUR ANGU" is stored as two
    tokens and would never match its own file again; and a history file that
    writes only "ANDONGMAD ANGU" for a pupil recorded with a middle name should
    still find them. Uniqueness is enforced by the caller, so a loosened match
    that pulls in two pupils resolves to nobody rather than to a guess.
    """
    exact = index["by_name"].get(" ".join(sorted(tokens))) or set()
    if len(exact) == 1:
        return set(exact)
    pool: set = set(exact)
    for pair in _token_pairs(tokens):
        pool |= index["by_pair"].get(pair, set())
    stored = index["tokens"]
    return {
        pk
        for pk in pool
        if stored.get(pk, frozenset()) <= tokens or tokens <= stored.get(pk, frozenset())
    }


def resolve_student(
    *, ctx, student_model, lookup_field: str, external_id: str, row=None
):
    """School-scoped student resolution shared by the history landers.

    On schema-per-tenant deployments the surrounding schema_context already
    isolates the query; on single-schema deployments (school-FK scoping,
    sqlite dev/test lane) an unscoped external-id lookup can resolve a
    same-id student from ANOTHER school — exactly the hazard of an
    inter-school transfer, where source and target share the external id
    by design. Scope by the bundle's school whenever the model carries one.

    An explicit id always wins. When the row carries no id — or an id that
    matches nobody — fall back to the student's NAME, because the schools whose
    roster has no id column also have no id in their attendance, grades or fee
    files: they identify pupils by name in every file they own, and an id-only
    resolver rejects every row they will ever upload.

    Ambiguity is never guessed. A name shared by two pupils resolves to None and
    the caller quarantines the row with a reason the school can act on, rather
    than silently attaching one child's attendance record to their namesake.
    """
    qs = student_model.objects.all()  # tenant-isolation-allow: scoped-below-via-ctx-school-when-model-has-school-field
    school = getattr(ctx, "school", None)
    if school is not None and "school" in model_field_names(student_model):
        qs = qs.filter(school=school)

    external_id = str(external_id or "").strip()
    if external_id:
        found = qs.filter(**{lookup_field: external_id}).first()
        if found is not None:
            return found

    name = student_name_from_row(row)
    if not name:
        return None
    index = _student_identity_index(ctx, student_model)
    if not index["usable"]:
        return None
    tokens = name_tokens(name)
    if not tokens:
        return None

    candidates = _name_candidates(index, tokens)
    if len(candidates) > 1:
        # Two pupils answer to this name; a date of birth on the row separates
        # them. Without one the row is genuinely ambiguous and stays unresolved.
        dob = _row_dob(row)
        if dob:
            narrowed = {pk for pk in candidates if index["dob"].get(pk) == dob}
            if len(narrowed) == 1:
                candidates = narrowed
    if len(candidates) == 1:
        return qs.filter(pk=next(iter(candidates))).first()
    return None


def _row_dob(row) -> str:
    """The student's date of birth as written on a history row, ISO-normalised."""
    for dob_key in _STUDENT_DOB_KEYS:
        raw = (row or {}).get(dob_key)
        if raw:
            parsed = coerce_date(raw)
            return str(parsed or "").strip() or str(raw).strip()
    return ""


def ambiguous_student_name(*, ctx, student_model, row=None) -> bool:
    """True when the row's name matches SEVERAL of this school's students.

    Lets a lander tell "we have never heard of this pupil" apart from "two of
    your pupils share this name" — different problems needing different fixes,
    and a quarantine reason that says which is the difference between a school
    fixing its file in ten minutes and giving up on the migration.
    """
    name = student_name_from_row(row)
    if not name:
        return False
    index = _student_identity_index(ctx, student_model)
    if not index["usable"]:
        return False
    return len(_name_candidates(index, name_tokens(name))) > 1


def filter_to_model_fields(defaults: dict[str, Any], model) -> dict[str, Any]:
    available = model_field_names(model)
    return {k: v for k, v in defaults.items() if k in available and v not in (None, "")}


# Canonical enrollment_status token → StudentProfile.Status value. Kept here so
# the students AND enrollment landers map identically (both write onto the same
# StudentProfile.status column). Returns "" for tokens with no confident mapping —
# the caller then leaves status untouched and preserves the raw token in DFV, so a
# vendor-specific value is never silently coerced to a wrong lifecycle state.
_ENROLLMENT_STATUS_MAP = {
    "new": "NEW", "new_admission": "NEW", "admitted": "NEW", "fresh": "NEW",
    "active": "RETURNING", "enrolled": "RETURNING", "current": "RETURNING",
    "continuing": "RETURNING", "returning": "RETURNING", "promoted": "RETURNING",
    "probation": "PROBATION", "on_probation": "PROBATION", "suspended": "PROBATION",
    "graduated": "ALUMNI", "alumni": "ALUMNI", "completed": "ALUMNI", "passed_out": "ALUMNI",
    "withdrawn": "TRANSFERRED", "transferred": "TRANSFERRED", "left": "TRANSFERRED",
    "exited": "TRANSFERRED", "inactive": "TRANSFERRED", "dropped": "TRANSFERRED",
}


def map_enrollment_status(raw: Any) -> str:
    """Map a canonical enrollment_status token to a ``StudentProfile.Status`` value.

    Returns "" when there is no confident mapping so the caller leaves ``status``
    untouched (the field is ``blank=True``) and can preserve the raw token as a
    custom field instead of writing an invalid choice.
    """
    if not raw:
        return ""
    return _ENROLLMENT_STATUS_MAP.get(str(raw).strip().lower(), "")


# Canonical attendance status → the exact lowercase ``Attendance.Status`` choice.
# The canonical present/absent/late/excused already ARE the choices; this only
# folds aliases (and the out-of-choice holiday/suspended) into a valid value so
# every landed row is a real choice that report filters and get_status_display see.
_ATTENDANCE_STATUS_MAP = {
    "present": "present", "p": "present", "here": "present",
    "absent": "absent", "a": "absent", "unexcused": "absent", "suspended": "absent",
    "late": "late", "l": "late", "tardy": "late",
    "excused": "excused", "e": "excused", "holiday": "excused", "leave": "excused",
}


def map_attendance_status(raw: Any, *, valid: set[str], default: str) -> str:
    """Normalize a canonical attendance token to a valid ``Attendance.Status``.

    Pass-through when the token already matches a choice; else fold known aliases;
    else fall back to ``default`` (the model's own default) rather than an invalid
    single-letter code.
    """
    token = str(raw or "").strip().lower()
    if token in valid:
        return token
    return _ATTENDANCE_STATUS_MAP.get(token, default)


def truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "t", "present", "primary")


def coerce_date(v: Any) -> _dt.date | None:
    if v in (None, ""):
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    try:
        return _dt.date.fromisoformat(str(v).strip()[:10])
    except (TypeError, ValueError):
        return None


def coerce_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        try:
            return int(float(str(v).strip()))
        except (TypeError, ValueError):
            return None


def coerce_decimal(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    s = str(v).strip().replace(",", "").replace("$", "")
    try:
        return Decimal(s)
    except (TypeError, InvalidOperation):
        return None


# --- ID mapping / asset / conflict helpers (sms-v3.7) -----------------------

def record_id_mapping(
    *,
    ctx,
    legacy_id: str,
    canonical_obj: Any,
    domain: str,
) -> None:
    """Persist a ``MigrationIdMapping`` row so future lookups can answer
    "what's the new ID for old ID X?". Best-effort — never raises."""
    if not legacy_id or canonical_obj is None:
        return
    try:
        from apps.migration_cloud.models import MigrationBundle, MigrationIdMapping
    except Exception:  # noqa: BLE001
        return
    try:
        bundle = MigrationBundle.objects.filter(pk=ctx.bundle_id).only(  # tenant-isolation-allow: PK lookup by internal bundle id
            "pk", "school_id", "discovery_summary"
        ).first()
        if bundle is None:
            return
        namespace = ((bundle.discovery_summary or {}).get("source") or {}).get(
            "chosen"
        ) or "unknown_custom"
        canonical_model = f"{canonical_obj.__class__.__module__}.{canonical_obj.__class__.__name__}"
        # ``domain`` is lookup identity, NOT a default — as a default, a later
        # lander touching the same canonical row (students upsert followed by
        # an enrollment update) matched this row and rewrote its domain,
        # erasing the earlier domain's audit entry.
        # Savepoint so a failed audit write's swallow (below) doesn't poison the
        # forced-atomic finance apply's outer transaction.
        with row_savepoint():
            MigrationIdMapping.objects.update_or_create(
                legacy_namespace=namespace,
                legacy_id=str(legacy_id)[:128],
                canonical_model=canonical_model[:128],
                school_id=bundle.school_id,
                domain=domain[:32],
                defaults={
                    "bundle": bundle,
                    "canonical_pk": str(getattr(canonical_obj, "pk", ""))[:64],
                },
            )
    except Exception:  # noqa: BLE001 — never block lander on audit-table write
        import logging
        logging.getLogger(__name__).debug("record_id_mapping skipped", exc_info=True)


def resolve_canonical_pk_by_legacy(*, ctx, legacy_id: str, domain: str) -> str | None:
    """Reverse :func:`record_id_mapping`: return the canonical PK a source LEGACY id
    maps to within this bundle's school, or ``None``.

    A roster can carry cross-references as the SOURCE system's own ids — e.g. a
    teacher row's ``SUBJECTS="96_98_106"`` naming subject ids. When those entities
    landed and recorded a ``MigrationIdMapping`` under the same legacy id, this
    turns the id back into the canonical row's pk so the reference can be
    reconstructed. School-scoped by the bundle; best-effort (never raises)."""
    if not legacy_id:
        return None
    try:
        from apps.migration_cloud.models import MigrationBundle, MigrationIdMapping
    except Exception:  # noqa: BLE001
        return None
    try:
        bundle = MigrationBundle.objects.filter(pk=ctx.bundle_id).only(  # tenant-isolation-allow: PK lookup by internal bundle id
            "pk", "school_id", "discovery_summary"
        ).first()
        if bundle is None:
            return None
        namespace = ((bundle.discovery_summary or {}).get("source") or {}).get(
            "chosen"
        ) or "unknown_custom"
        row = (
            MigrationIdMapping.objects.filter(  # tenant-isolation-allow: scoped by bundle.school_id
                legacy_namespace=namespace,
                legacy_id=str(legacy_id)[:128],
                school_id=bundle.school_id,
                domain=domain[:32],
            )
            .order_by("-created_at")
            .first()
        )
        return row.canonical_pk if row is not None else None
    except Exception:  # noqa: BLE001
        return None


_ASSET_KEY_PATTERNS = {
    "photo": ("photo_url", "photo", "photo_path", "image_url"),
    "immunization": ("immunization_url", "immunization_scan"),
    "report_card": ("report_card_url", "report_card_pdf"),
    "transcript": ("transcript_url", "transcript_pdf"),
    "id_card": ("id_card_url", "id_card_image"),
}


def detect_and_register_assets(
    *,
    ctx,
    legacy_id: str,
    entity_kind: str,
    row: dict,
) -> None:
    """Scan a canonical row for asset URLs and register pending fetches.

    Standard keys per entity kind; safe no-op if none present.
    """
    if not legacy_id:
        return
    try:
        from apps.migration_cloud.asset_pipeline import register_asset
        from apps.migration_cloud.models import MigrationBundle
    except Exception:  # noqa: BLE001
        return
    bundle = MigrationBundle.objects.filter(pk=ctx.bundle_id).first()  # tenant-isolation-allow: PK lookup by internal bundle id
    if bundle is None:
        return
    for asset_kind, keys in _ASSET_KEY_PATTERNS.items():
        for key in keys:
            uri = (row.get(key) or "").strip() if isinstance(row.get(key), str) else ""
            if not uri:
                continue
            try:
                with row_savepoint():  # isolate the asset write from the atomic apply
                    register_asset(
                        bundle=bundle,
                        entity_kind=entity_kind,
                        legacy_id=str(legacy_id),
                        asset_kind=asset_kind,
                        source_uri=uri,
                    )
            except Exception:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).debug(
                    "detect_and_register_assets register failed", exc_info=True,
                )


def detect_conflict(
    *,
    ctx,
    domain: str,
    canonical_obj: Any,
    incoming: dict,
    legacy_id: str = "",
) -> bool:
    """Detect upsert conflict. Returns True if an existing-vs-incoming diff was logged.

    Compares ``incoming`` (filtered to keys present on the model) against
    ``canonical_obj``'s current values. When non-empty fields would change,
    logs a ``MigrationConflict`` row for operator review.
    """
    if canonical_obj is None or not incoming:
        return False
    try:
        from apps.migration_cloud.models import (
            ConflictResolution, MigrationBundle, MigrationConflict,
        )
    except Exception:  # noqa: BLE001
        return False
    model = canonical_obj.__class__
    field_names = {f.name for f in model._meta.get_fields()}
    existing: dict = {}
    incoming_clean: dict = {}
    changed: list[str] = []
    for k, v in incoming.items():
        if k not in field_names:
            continue
        cur = getattr(canonical_obj, k, None)
        # Treat empty string vs None as no-diff to suppress noise.
        cur_norm = "" if cur in (None,) else str(cur)
        new_norm = "" if v in (None, "") else str(v)
        if cur_norm == new_norm:
            continue
        # Only count as conflict when the existing value is non-empty
        # (otherwise it's a normal "fill-in-missing" update).
        if cur_norm == "":
            continue
        existing[k] = _jsonable(cur)
        incoming_clean[k] = _jsonable(v)
        changed.append(k)
    if not changed:
        return False
    try:
        bundle = MigrationBundle.objects.filter(pk=ctx.bundle_id).first()  # tenant-isolation-allow: PK lookup by internal bundle id
        if bundle is None:
            return False
        canonical_model_path = f"{model.__module__}.{model.__name__}"
        with row_savepoint():  # isolate the audit write from the atomic apply
            MigrationConflict.objects.create(
                bundle=bundle,
                domain=domain[:32],
                canonical_model=canonical_model_path[:128],
                canonical_pk=str(getattr(canonical_obj, "pk", ""))[:64],
                legacy_id=str(legacy_id)[:128],
                existing_values=existing,
                incoming_values=incoming_clean,
                changed_fields=changed,
                resolution=ConflictResolution.PENDING,
            )
        return True
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).debug("detect_conflict log failed", exc_info=True)
        return False


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)[:200]


# --- Quarantine source-row threading (audit C-4) ----------------------------

_QUARANTINE_ROW_MAX_KEYS = 60


def _row_snapshot(row: Any) -> dict[str, Any]:
    """Bounded, JSON-safe copy of a source row for a quarantine record.

    Values are truncated (via :func:`_jsonable`, 200 chars) and the key count is
    capped so a pathological wide row can't bloat the quarantine payload. The row
    stays inside the tenant's own quarantine table — the same trust boundary as
    the data being landed — so no additional redaction is applied here.
    """
    if not isinstance(row, dict):
        return {"_value": _jsonable(row)}
    out: dict[str, Any] = {}
    for i, (k, v) in enumerate(row.items()):
        if i >= _QUARANTINE_ROW_MAX_KEYS:
            out["_truncated"] = True
            break
        out[str(k)[:64]] = _jsonable(v)
    return out


# Source per-row status tokens that denote a DELETED / retired record (audit D-3).
# OneRoster ships ``status=tobedeleted``; other SIS use withdrawn/inactive/archived.
# Normalised (spaces / dashes / underscores stripped, lowercased) before matching.
_TOMBSTONE_STATUSES = frozenset({
    "tobedeleted", "deleted", "withdrawn", "inactive", "archived", "removed", "void",
})
# Canonical + common unmapped keys a per-row status can arrive under.
_DELETE_MARKER_KEYS = ("record_status", "_source_status", "_status", "_unmapped.status", "status")


def is_tombstone_status(value: Any) -> bool:
    """True when a status token denotes a deleted / retired source record."""
    token = str(value or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    return token in _TOMBSTONE_STATUSES


def row_marks_deletion(row: Any) -> bool:
    """True when a canonical row carries a source 'deleted' status marker (audit D-3).

    OneRoster (and other SIS) ship a per-row ``status``; a ``tobedeleted``
    STRUCTURAL row (course / class) must NOT be imported as active. This checks the
    canonical ``record_status`` and the common unmapped fallbacks, tolerating both
    the raw ``tobedeleted`` and the value-mapped ``withdrawn``. Used ONLY by the
    structural landers (academics / sections) — student / enrollment landers treat
    ``withdrawn`` as a legitimate lifecycle value, not a deletion, so they never
    call this.
    """
    if not isinstance(row, dict):
        return False
    return any(key in row and is_tombstone_status(row.get(key)) for key in _DELETE_MARKER_KEYS)


def record_row_error(
    result,
    row: Any,
    message: str,
    *,
    reason_code: str | None = None,
    field: str | None = None,
) -> None:
    """Hold one row, keeping the row itself and WHY it was held.

    This is the whole lander failure contract. It increments
    ``result.quarantined``, appends ``message`` to ``result.errors`` (the
    back-compat surface every consumer already reads), and appends the structured
    twin to ``result.error_rows`` in LOCKSTEP so the orchestrator can pair them by
    index.

    Three things travel with the row, and each closes a specific hole:

    ``row``
        The bounded source-row snapshot. **You cannot replay a row you did not
        keep**, so without this the automated remediation the zero-touch spec
        describes cannot exist at all — no matter how good the remediator is.

    ``reason_code``
        A ``landers.reason_codes`` value. Omit it and the message is classified by
        substring-matching English, which is how 68 of 108 failure sites ended up
        in ``lander_error`` — the bucket that means "a person must look at this".
        Declaring the code is how a row stops needing a person.

    ``field``
        The offending column, when the lander knows it. A school can act on
        "``date_of_birth`` was empty" in a way they cannot act on "missing
        student/date/status".

    Bookkeeping never breaks a lander: the structured append is guarded, and a
    failure there still leaves the count and the message intact.
    """
    result.quarantined += 1
    result.errors.append(message)
    try:
        declared = normalize_reason_code(reason_code)
        result.error_rows.append({
            "error": message,
            "row": _row_snapshot(row),
            "reason_code": declared or classify_message(message),
            "reason_source": "declared" if declared else "fallback",
            "field": str(field)[:64] if field else None,
        })
    except Exception:  # noqa: BLE001 — quarantine bookkeeping never breaks a lander
        pass


def record_row_note(result, message: str, row: Any = None) -> None:
    """Record a diagnostic that is NOT a held row.

    The row LANDED; something attached to it did not — a custom-attributes sweep,
    an extras write, an optional lookup. Ten such sites used to append to
    ``result.errors`` without incrementing ``quarantined``, so each one minted a
    "held for review" quarantine record that the board's count never included.
    The tenant saw a partial-write warning presented as a rejected row, and the
    banner and the table disagreed about how many rows were held.

    These are still durable and still surfaced — the orchestrator logs them and
    stores them on the run — they are simply not counted as rows anyone must
    review. Nothing is hidden; it is filed under what it actually is.
    """
    try:
        entry: dict[str, Any] = {"note": message}
        if row is not None:
            entry["row"] = _row_snapshot(row)
        result.notes.append(entry)
    except Exception:  # noqa: BLE001 — diagnostics never break a lander
        pass


def conflict_resolution_for(*, ctx, canonical_obj: Any) -> str:
    """Look up a resolved-conflict decision for this row, if any.

    Returns 'OVERWRITE' (default), 'PRESERVE' (skip update), or 'MERGE'
    (the lander caller can decide field-by-field). Operators set this via
    the conflict review UI before re-running apply.
    """
    if canonical_obj is None:
        return "OVERWRITE"
    try:
        from apps.migration_cloud.models import ConflictResolution, MigrationConflict
    except Exception:  # noqa: BLE001
        return "OVERWRITE"
    try:
        canonical_model_path = f"{canonical_obj.__class__.__module__}.{canonical_obj.__class__.__name__}"
        row = (
            MigrationConflict.objects.filter(
                bundle_id=ctx.bundle_id,
                canonical_model=canonical_model_path,
                canonical_pk=str(getattr(canonical_obj, "pk", "")),
            )
            .exclude(resolution=ConflictResolution.PENDING)
            .order_by("-resolved_at")
            .first()
        )
        if row is None:
            return "OVERWRITE"
        return row.resolution
    except Exception:  # noqa: BLE001
        return "OVERWRITE"


def upsert_with_conflict_detection(
    *,
    ctx,
    domain: str,
    model: Any,
    lookup: dict,
    defaults: dict,
    legacy_id: str = "",
) -> tuple[Any, bool, bool]:
    """Conflict-aware ``update_or_create`` shared by every domain lander.

    Looks up the existing row by ``lookup``; if one exists, logs any
    existing-vs-incoming diff as a ``MigrationConflict`` for operator review
    (:func:`detect_conflict`) and honours a prior ``PRESERVE`` resolution the
    operator set from the conflict-review UI. Otherwise it upserts normally.

    Returns ``(obj, created, preserved)``. ``preserved`` is True when the
    operator resolved this row as PRESERVE — the caller should count the row
    as *skipped* and NOT apply the incoming values. This is the same
    conflict-aware path ``student_lander`` pioneered, factored out so EVERY
    domain gets the same operator review surface, not just students.
    """
    existing = model.objects.filter(**lookup).first()  # tenant-isolation-allow: lander runs inside schema_context(bundle.schema_name)
    if existing is not None:
        detect_conflict(
            ctx=ctx,
            domain=domain,
            canonical_obj=existing,
            incoming=defaults,
            legacy_id=legacy_id,
        )
        if conflict_resolution_for(ctx=ctx, canonical_obj=existing) == "PRESERVE":
            return existing, False, True
    # Per-row savepoint: a constraint/FK failure here rolls back only this upsert so
    # the caller's per-row quarantine survives the forced-atomic finance apply.
    with row_savepoint():
        obj, created = model.objects.update_or_create(**lookup, defaults=defaults)
    return obj, created, False


# --- Structure provisioning helpers (shared with structure_lander) ----------
# The SPLIT scaffold lander (``structure_lander``) pioneered these; factored
# here so the ``sections``/``staff``/``academics`` landers provision required
# FK parents the SAME safe way (reuse-by-(school,name), mint a target-scoped
# GLOBALLY-unique code, never reuse the source's code — which on single-schema
# would collide with / resolve ANOTHER school's row).


def _slug_upper(value: str, width: int = 8) -> str:
    return (re.sub(r"[^A-Z0-9]+", "", (value or "").upper())[:width]) or "X"


def _scope_token(school) -> str:
    """A SHORT, stable per-school token for a minted code.

    ``School.pk`` is a 36-char UUID on this platform, so a bare ``{prefix}{pk}``
    already exceeds the 30-char ``code`` column — the ``[:30]`` truncation then
    drops the NAME entirely and every minted code collapses to one value, so the
    2nd..Nth provisioned Department/Specialty/Classroom all collide on the
    ``unique=True`` code and quarantine (0 land past the first). Hash a long id
    down to 6 hex chars; keep a short integer pk verbatim so existing
    integer-pk deployments' codes are unchanged.
    """
    sid = str(getattr(school, "pk", "") or "0")
    if len(sid) > 8:  # magic-number-allow: short-integer-pk-threshold (UUIDs are 36)
        return hashlib.sha1(sid.encode("utf-8")).hexdigest()[:6]
    return sid


def mint_scoped_code(*, prefix: str, name: str, school, model, code_field: str = "code") -> str:
    """A fresh, GLOBALLY-unique code for a provisioned structure row.

    ``Department``/``Specialty``/``Classroom.code`` are ``unique=True`` platform-
    wide, so the source's code MUST NOT be reused (it would collide or, worse,
    resolve the SOURCE school's row). Deterministic per (school, name) for stable
    re-runs, with a hash fallback if the short form ever collides. The school
    token is length-bounded (:func:`_scope_token`) so the NAME always survives
    the 30-char cap even when ``School.pk`` is a UUID.
    """
    sid = _scope_token(school)
    base = _slug_upper(name)
    candidate = f"{prefix}{sid}-{base}"[:30]  # magic-number-allow: code column max_length=30
    if not model.objects.filter(**{code_field: candidate}).exists():  # tenant-isolation-allow: code is a GLOBALLY-unique column; global existence check is intentional
        return candidate
    digest = hashlib.sha256(f"{sid}:{prefix}:{name}".encode("utf-8")).hexdigest()[:6]
    return f"{prefix}{sid}-{base[:4]}-{digest}"[:30]  # magic-number-allow: code column max_length=30


def get_or_create_named(*, model, school, name, create_kwargs=None, result=None):
    """Reuse an existing (school, name) row or create one. Never mutates an
    existing row (the target's own config wins). ``create_kwargs`` is a callable
    returning the extra create-only kwargs (e.g. a minted code / required FKs)."""
    qs = model.objects.all()  # tenant-isolation-allow: scoped-below-by-school-when-present / schema-context-isolates
    fields = model_field_names(model)
    if "school" in fields and school is not None:
        qs = qs.filter(school=school)
    obj = qs.filter(name=name).order_by("pk").first()
    if obj is not None:
        return obj, False
    kwargs: dict[str, Any] = {"name": name}
    if "school" in fields and school is not None:
        kwargs["school"] = school
    if create_kwargs is not None:
        kwargs.update(create_kwargs())
    # Per-row savepoint so a parent-provision failure doesn't poison the atomic apply.
    try:
        with row_savepoint():
            obj = model.objects.create(**kwargs)
    except IntegrityError:
        # Lost a create race with a concurrent wave-thread that provisioned the SAME
        # shared parent (same school+name) — parallel artifacts in one wave run on
        # separate DB connections, so both can miss the filter above and both try to
        # create. The savepoint rolled back only this create and left the outer
        # transaction intact, so re-fetch the winner by its identity (school, name —
        # this helper's contract) instead of spuriously quarantining the child row
        # that needed this parent (#8). A miss on re-fetch is a real integrity failure,
        # not a benign create race — surface it.
        obj = qs.filter(name=name).order_by("pk").first()
        if obj is None:
            raise
        return obj, False
    if result is not None:
        result.created_ids.append(obj.pk)
    return obj, True


def _free_username(User, base: str) -> str:
    base = (re.sub(r"[^a-zA-Z0-9._-]+", "", base or "") or "user")[:130]  # magic-number-allow: username-stem-cap-leaves-digest-room-under-150
    if not User.objects.filter(username=base).exists():
        return base
    digest = hashlib.sha256(base.lower().encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"[:150]  # magic-number-allow: django-username-field-max-length-150


def resolve_or_provision_user(
    *, User, username_hint: str, email: str, first_name: str, last_name: str,
    role: str, dry_run: bool,
):
    """Return ``(user, reason)`` — reason set only when user is None.

    Resolution order: existing platform user by username_hint → by email →
    provision a NEW account (role as given, UNUSABLE password — no credential is
    ever minted; the person activates via the normal invite/reset flow). Existing
    users are NEVER mutated (their role/names/credentials stay theirs). Mirrors
    ``guardian_lander._resolve_or_provision_user`` so staff land the same way
    guardians do.
    """
    if username_hint:
        user = User.objects.filter(username=username_hint).first()
        if user is not None:
            return user, ""
    if email:
        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            return user, ""
    if not (email or first_name or last_name or username_hint):
        return None, "no email or name to resolve or provision a user"
    if dry_run:
        return None, ""  # would provision — preview counts it as landable
    stem = username_hint or (email.split("@", 1)[0] if email else f"{first_name}.{last_name}")
    username = _free_username(User, stem)
    # Savepoint-wrap provisioning: under the forced-atomic finance apply a raw
    # create_user IntegrityError (e.g. a concurrent apply racing the same
    # email-derived username) would otherwise mark the WHOLE connection
    # needs_rollback, aborting the entire finance-bearing bundle instead of
    # quarantining this one row. The savepoint rolls back only this provisioning
    # and re-raises to the caller's per-row except.
    try:
        with row_savepoint():
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
            )
            if role and hasattr(user, "role"):
                user.role = role
            user.set_unusable_password()
            user.save()
    except IntegrityError:
        # Lost a create race with a concurrent wave-thread provisioning the SAME
        # person (parallel artifacts, separate connections, same email-derived
        # username). Re-resolve by EMAIL — the identity — so the child row binds to the
        # winner instead of being spuriously quarantined (#8). Deliberately NOT by the
        # bare username: two DIFFERENT people can collide on a username derivation, and
        # merging them would be a data-integrity bug worse than a quarantine — so with
        # no email match we re-raise and quarantine honestly.
        user = User.objects.filter(email__iexact=email).first() if email else None
        if user is None:
            raise
    return user, ""


def persist_dfv_extras(
    *, ctx, entity_type: str, entity_id: Any, extras: dict[str, Any], result=None,
) -> None:
    """Persist non-model canonical fields to ``apps.metadata.DynamicFieldValue``
    so the no-data-loss invariant holds for columns the first-class model lacks
    (e.g. staff ``hire_date`` / ``role`` on ``TeacherProfile``). Best-effort — a
    failure is recorded on ``result`` (visible), never silently swallowed."""
    clean = {k: v for k, v in extras.items() if v not in (None, "")}
    if not clean:
        return
    try:
        from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
    except Exception as exc:  # noqa: BLE001
        if result is not None:
            record_row_note(
                result,
                f"{entity_type} extras: metadata models unavailable: {type(exc).__name__}",
            )
        return
    for field_key, value in clean.items():
        try:
            with row_savepoint():  # isolate each DFV write from the atomic apply
                DynamicFieldDefinition.objects.get_or_create(
                    entity_type=entity_type,
                    field_key=field_key,
                    school=getattr(ctx, "school", None),
                    defaults={"label": field_key.replace("_", " ").title(), "data_type": "json"},
                )
                DynamicFieldValue.objects.update_or_create(
                    entity_type=entity_type,
                    entity_id=str(entity_id)[:64],
                    field_key=field_key,
                    defaults=filter_to_model_fields(
                        {"value_json": {"v": value}, "school": getattr(ctx, "school", None)},
                        DynamicFieldValue,
                    ),
                )
        except Exception as exc:  # noqa: BLE001 — extras are best-effort, recorded
            if result is not None:
                record_row_note(
                    result,
                    f"{entity_type} extras write failed for {field_key}: {type(exc).__name__}",
                )


def resolve_name_order(ctx) -> str:
    """The operator's chosen combined-name order, or "" to auto-detect.

    Returned as the ``order`` argument for
    :func:`apps.migration_cloud.transformers.name_split.split_full_name`. Empty
    keeps the existing locale/country heuristic, so an unset preference behaves
    exactly as before.
    """
    options = getattr(ctx, "transformer_options", None) or {}
    order = str(options.get("name_order") or "").strip().lower()
    return order if order in {"first_last", "last_first", "spanish_double"} else ""


def split_name_for(ctx, full_name: str) -> tuple[str, str, str]:
    """Split a combined name honouring the operator's choice, then the locale.

    Every person lander splits combined names the same way, and each had grown
    its own copy of this call; centralising it means a preference chosen once on
    the review page applies identically to students, staff and alumni.
    """
    from apps.migration_cloud.transformers.name_split import split_full_name

    school = getattr(ctx, "school", None)
    country = getattr(school, "country_code", "") if school is not None else ""
    return split_full_name(full_name, order=resolve_name_order(ctx) or None, country=country)


def unresolved_student_reason(
    *,
    domain: str,
    ctx,
    student_model,
    row=None,
    external_id: str = "",
    lookup_field: str = "",
) -> str:
    """A quarantine reason that names the fix, not the internal column.

    Four distinct situations hid behind one message. A school reading "no student
    with admission_number=''" cannot tell whether it uploaded the files in the
    wrong order, misspelled a name, has two pupils who share one, or simply has
    no column identifying anybody -- and each needs a different correction.
    """
    name = student_name_from_row(row)
    ext = str(external_id or "").strip()
    if name and ambiguous_student_name(ctx=ctx, student_model=student_model, row=row):
        return (
            f"{domain}: more than one of your pupils is named '{name}', so this row "
            f"is ambiguous. Add a date of birth column, or a student id column, to "
            f"say which one it belongs to."
        )
    if name and ext:
        return (
            f"{domain}: no pupil matches the id '{ext}' or the name '{name}'. Import "
            f"your student list before this file, or correct the row."
        )
    if name:
        return (
            f"{domain}: no pupil named '{name}' has been imported yet. Import your "
            f"student list before this file, or correct the spelling on this row."
        )
    if ext:
        return (
            f"{domain}: no pupil carries the id '{ext}'. Import your student list "
            f"before this file, or add a student name column so the row can be "
            f"matched by name instead."
        )
    return (
        f"{domain}: this row does not say which pupil it belongs to. Add a student "
        f"id column or a student name column."
    )
