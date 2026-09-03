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
import re
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import IntegrityError, transaction

_SOURCE_NULL_LITERALS = frozenset({"", "none", "nan", "n/a", "na", "null", "-", "0"})


def _clean_source_string(value: Any) -> str:
    """Normalize spreadsheet null sentinels (``nan``, ``none``, …) to empty."""
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    s = str(value).strip()
    if s.lower() in _SOURCE_NULL_LITERALS:
        return ""
    return s


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


# Columns a model REGENERATES inside its own ``save()`` instead of taking them
# from the caller. On ``StudentProfile`` that is ``search_index`` (rebuilt from
# name + codes + dynamic fields on EVERY save), the minted ``admission_number``
# / ``student_code``, ``referral_code``, and the ``auto_now`` ``updated_at``.
# Django writes ONLY the columns named in ``update_fields``, so a narrowed save
# computes these and then throws them away: a roster name correction left the
# pupil unfindable under their corrected name, and a specialty link minted an
# admission number that never reached the row. Any narrowed write carries them.
_DERIVED_ON_SAVE_FIELDS = (
    "search_index",
    "admission_number",
    "student_code",
    "referral_code",
    "updated_at",
)


def save_scoped(obj, fields) -> None:
    """``obj.save()`` narrowed to the columns this source row actually supplied.

    A bare ``save()`` rewrites EVERY column from the in-memory snapshot the
    lander read earlier in the row, so anything committed to that row in the
    meantime is silently reverted -- including the columns the source file never
    mentioned. That window is not theoretical: apply runs the artifacts of one
    wave in PARALLEL threads on separate connections
    (``orchestrator._run_waves``), and wave 1 holds ``students`` AND ``alumni``,
    which upsert the same ``StudentProfile`` rows.

    Narrowing is not a lock. Two writers that both supply the SAME field still
    race on it, and nothing here can order them -- the canonical row carries no
    version, epoch or source timestamp to compare (see the students ontology
    entry). What narrowing removes is the blast radius: the ~30 untouched
    columns a full save was re-asserting from a stale snapshot.

    ``_DERIVED_ON_SAVE_FIELDS`` ride along so narrowing never silently drops a
    value the model generated for itself. Falls back to a full save on an
    unsaved instance or a model whose ``_meta`` cannot be read, so this is safe
    on every tenant model shape a lander meets.
    """
    try:
        concrete: set[str] = set()
        for f in obj._meta.local_concrete_fields:
            concrete.add(f.name)
            concrete.add(f.attname)
        concrete -= {obj._meta.pk.name, obj._meta.pk.attname}
    except (AttributeError, TypeError):
        # The block above only walks ``_meta``: an object with no ``_meta``, a
        # ``_meta`` with no ``local_concrete_fields``, or a model whose ``pk`` is
        # None all surface as AttributeError, and a non-iterable
        # ``local_concrete_fields`` as TypeError. That IS "unknown model shape";
        # anything else raised here is a bug in this function and must not be paid
        # for with a silent full save that rewrites ~30 stale columns.
        obj.save()
        return
    if getattr(obj, "pk", None) is None:
        obj.save()
        return
    scoped = {f for f in fields if f in concrete}
    scoped.update(f for f in _DERIVED_ON_SAVE_FIELDS if f in concrete)
    if not scoped:
        obj.save()
        return
    obj.save(update_fields=sorted(scoped))


_EXTERNAL_ID_CANDIDATES = ("external_id", "sis_external_id", "source_id", "admission_number")


def student_lookup_field(available: set[str]) -> str:
    for c in _EXTERNAL_ID_CANDIDATES:
        if c in available:
            return c
    return "admission_number"


# Every column a pupil's source id may actually have LANDED in. ``student_code``
# is here and NOT in ``_EXTERNAL_ID_CANDIDATES`` on purpose: the students lander
# prefers ``student_code`` as its upsert key (student_lander._lookup_field), so a
# roster whose source id differs from its admission number -- the normal case,
# not the edge case -- lands the id in ``student_code`` while ``admission_number``
# holds the school's own number. Every history lander then asked for the id under
# ``admission_number``, missed, and quarantined the row as "no pupil carries the
# id" for a pupil that had just landed in the same bundle.
#
# The repair is a WIDENING, never a reordering. ``student_lookup_field`` still
# answers with exactly the column it answered with before -- 13 landers and
# ``verification.py`` read that answer -- and that column is still tried FIRST.
# ``student_code`` is appended LAST so it can only ever be reached where the
# caller would otherwise have fallen through to name matching or quarantined.
#
# Order is load-bearing because NOTHING constrains these columns against each
# other. StudentProfile.Meta carries three INDEPENDENT partial unique indexes
# (school+client_offline_id, school+student_code, school+admission_no), so one
# pupil's student_code may legally equal a DIFFERENT pupil's admission number.
# Trying the caller's own column first means such a clash resolves to the same
# pupil it resolves to today: this widening cannot introduce a wrong match, and
# it does not pretend to cure the pre-existing one.
_STUDENT_IDENTITY_LOOKUP_FIELDS = _EXTERNAL_ID_CANDIDATES + ("student_code",)


def student_identity_fields(available, *, primary: str = "") -> tuple[str, ...]:
    """Identity columns to try when resolving a pupil by source id, in order.

    ``primary`` -- the caller's own ``student_lookup_field`` answer -- is tried
    first and unchanged, so every row that resolves today resolves to the same
    pupil. The rest are additive fallbacks. Only columns the model actually
    carries are returned, so this stays schema-tolerant.
    """
    ordered: list[str] = []
    if primary and primary in available:
        ordered.append(primary)
    for c in _STUDENT_IDENTITY_LOOKUP_FIELDS:
        if c in available and c not in ordered:
            ordered.append(c)
    return tuple(ordered)


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
        # The caller's own column first (unchanged), then the other columns a
        # source id can have landed in -- above all ``student_code``, which is
        # what the students lander upserts on. See _STUDENT_IDENTITY_LOOKUP_FIELDS.
        for field in student_identity_fields(
            model_field_names(student_model), primary=lookup_field
        ):
            found = qs.filter(**{field: external_id}).first()
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


_ACADEMICS_IDENTITY_KEYS = (
    "subject_name",
    "subject_code",
    "name",
    "title",
    "code",
    "course_name",
    "course_code",
)


_PDF_STAT_METADATA_KEYS = frozenset(
    {"page", "line", "column", "sheet", "table", "row", "cell", "block", "stats"}
)


def row_is_unstructured_text_fragment(row: dict | None, *, artifact: str = "") -> bool:
    """True when a row is only a PDF/stat-sheet text line with no domain identity.

    PDF tabularisation emits ``raw_line`` rows when a page has no grade-table or
    key/value structure (headers, footers, column titles). Those lines are not
    importable course records and should be skipped — not held for review.

    Also catches ``school_stats*.pdf`` metadata-only rows (page/line keys, no
    subject/student identity) that never carried a ``raw_line`` field.
    """
    if not isinstance(row, dict):
        return False
    flat: dict[str, Any] = dict(row)
    custom_fields = row.get("custom_fields")
    if isinstance(custom_fields, dict):
        for key, value in custom_fields.items():
            flat.setdefault(f"custom_fields.{key}", value)
            flat.setdefault(key, value)
    raw_line = (
        flat.get("custom_fields.raw_line")
        or flat.get("raw_line")
        or (custom_fields.get("raw_line") if isinstance(custom_fields, dict) else None)
    )
    artifact_name = str(artifact or "").lower()
    if not str(raw_line or "").strip():
        if artifact_name.endswith(".pdf") or "school_stats" in artifact_name:
            for key in _ACADEMICS_IDENTITY_KEYS:
                if str(flat.get(key) or "").strip():
                    return False
            for key in _STUDENT_IDENTITY_KEYS:
                if str(flat.get(key) or "").strip():
                    return False
            meaningful = {
                key: value
                for key, value in flat.items()
                if key != "custom_fields"
                and value not in (None, "", [], {})
                and str(value).strip()
            }
            if not meaningful:
                return True
            return all(
                key in _PDF_STAT_METADATA_KEYS
                or key.startswith("custom_fields.")
                for key in meaningful
            )
        return False
    for key in _ACADEMICS_IDENTITY_KEYS:
        if str(flat.get(key) or "").strip():
            return False
    meaningful = {
        key: value
        for key, value in flat.items()
        if key != "custom_fields"
        and value not in (None, "", [], {})
        and str(value).strip()
    }
    if not meaningful:
        return False
    allowed_keys = {"raw_line", "custom_fields.raw_line"}
    return all(
        key in allowed_keys or key.startswith("custom_fields.")
        for key in meaningful
    )


_STUDENT_IDENTITY_KEYS = (
    "external_id",
    "student_external_id",
    "admission_number",
    "student_code",
    "first_name",
    "last_name",
    "full_name",
)

_DOMAIN_IDENTITY_KEYS: dict[str, tuple[str, ...]] = {
    "academics": _ACADEMICS_IDENTITY_KEYS,
    "students": _STUDENT_IDENTITY_KEYS,
    "enrollment": _STUDENT_IDENTITY_KEYS,
    "grades": _STUDENT_IDENTITY_KEYS + ("subject_code", "subject_name", "score", "letter_grade"),
    "attendance": _STUDENT_IDENTITY_KEYS,
    "behavior": _STUDENT_IDENTITY_KEYS,
    "staff": ("staff_id", "employee_number", "email", "first_name", "last_name", "full_name"),
}


def _flatten_source_row(row: dict | None) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    flat: dict[str, Any] = dict(row)
    custom_fields = row.get("custom_fields")
    if isinstance(custom_fields, dict):
        for key, value in custom_fields.items():
            flat.setdefault(f"custom_fields.{key}", value)
            flat.setdefault(key, value)
    return flat


def domain_identity_is_known(domain: str) -> bool:
    """True when we have identity keys for this domain and can judge its rows.

    Only a handful of the lander domains are mapped in ``_DOMAIN_IDENTITY_KEYS``.
    For the rest, "has identity" is unanswerable, and an unanswerable question
    must never be read as "no".
    """
    return bool(_DOMAIN_IDENTITY_KEYS.get(str(domain or "").strip().lower()))


def row_has_domain_identity(domain: str, source_row: dict | None) -> bool:
    """True when at least one domain-specific identity field is populated."""
    keys = _DOMAIN_IDENTITY_KEYS.get(str(domain or "").strip().lower(), ())
    if not keys:
        return False
    flat = _flatten_source_row(source_row)
    for key in keys:
        val = flat.get(key)
        if val is None:
            continue
        if str(val).strip().lower() in {"", "nan", "none", "null"}:
            continue
        return True
    return False


def row_is_pdf_noise_hold(domain: str, source_row: dict | None, artifact: str = "") -> bool:
    """PDF/stat rows with no domain identity — not reviewable records.

    Closes the gap where PDF tabularisation emits lines that land in
    ``missing_required`` because subject/student ids are empty, but the row was
    never an importable record (headers, stats blocks, footers).
    """
    if row_is_unstructured_text_fragment(source_row, artifact=artifact):
        return True
    # A domain with no identity keys cannot be judged. ``row_has_domain_identity``
    # returns False both for "identity fields are empty" and for "I have never
    # heard of this domain", and only 7 of the 28 lander domains are mapped.
    # Reading the second as the first made every held finance, payroll, guardian,
    # transcript and library row that came off a PDF look like page furniture --
    # an invoice row carrying amount, currency and due date was auto-dismissed.
    # Genuine noise in those domains is still caught above, by the fragment test,
    # which reads the row instead of the domain. UNKNOWN means keep.
    if not domain_identity_is_known(domain):
        return False
    artifact_name = str(artifact or "").lower()
    if not artifact_name.endswith(".pdf"):
        # This gate used to sit BELOW a `"school_stats" in artifact_name`
        # shortcut, so a .csv or .xlsx whose NAME contained school_stats was
        # dismissed by a rule whose whole contract is PDF tabularisation noise.
        # Filenames are operator-supplied, and derived stats reports already
        # have a stronger owner: is_derived_report() reads the HEADERS. If a
        # school_stats.csv reached quarantine as academics rows, that check
        # already declined to call it derived -- overruling it on a substring
        # is a weaker test beating a better one, and it silently discards the
        # real CSV mapping gaps that are supposed to reach a human.
        return False
    return not row_has_domain_identity(domain, source_row)


def _enrich_split_combined_name(
    enriched: dict[str, Any],
    flat: dict[str, Any],
    evidence: list[str],
    *,
    school=None,
    transformer_options: dict | None = None,
) -> None:
    """Split a combined name column into first/last when either is missing."""
    first = str(flat.get("first_name") or "").strip()
    last = str(flat.get("last_name") or "").strip()
    full = str(
        flat.get("full_name") or flat.get("name") or flat.get("student_name") or ""
    ).strip()
    if full and (not first or not last):
        if school is not None:
            from types import SimpleNamespace

            ctx = SimpleNamespace(
                school=school,
                transformer_options=transformer_options or {},
            )
            fn, _mn, ln = split_name_for(ctx, full)
        else:
            parts = full.split()
            if len(parts) >= 2:
                fn, ln = " ".join(parts[:-1]), parts[-1]
            elif parts:
                fn, ln = parts[0], parts[0]
            else:
                fn, ln = "", ""
        if fn and not first:
            enriched["first_name"] = fn
            evidence.append("first_name←full_name")
        if ln and not last:
            enriched["last_name"] = ln
            evidence.append("last_name←full_name")


def _enrich_student_identity_keys(
    enriched: dict[str, Any],
    flat: dict[str, Any],
    evidence: list[str],
    *,
    school=None,
    transformer_options: dict | None = None,
) -> None:
    """Backfill pupil identity fields from sibling columns on the same row."""
    ext = str(
        flat.get("external_id")
        or flat.get("student_external_id")
        or flat.get("admission_number")
        or flat.get("student_code")
        or flat.get("exam_candidate_number")
        or ""
    ).strip()
    if ext:
        if not str(flat.get("external_id") or "").strip():
            enriched["external_id"] = ext
            evidence.append("external_id←identity_alias")
        if not str(flat.get("student_external_id") or "").strip():
            enriched["student_external_id"] = ext
            evidence.append("student_external_id←identity_alias")

    admission = str(flat.get("admission_number") or "").strip()
    student_code = str(flat.get("student_code") or "").strip()
    exam_no = str(flat.get("exam_candidate_number") or "").strip()

    if not str(flat.get("external_id") or flat.get("student_external_id") or "").strip():
        if admission:
            enriched["external_id"] = admission
            enriched["student_external_id"] = admission
            evidence.append("external_id←admission_number")
        elif student_code:
            enriched["external_id"] = student_code
            enriched["student_external_id"] = student_code
            evidence.append("external_id←student_code")
        elif exam_no:
            enriched["external_id"] = exam_no
            enriched["student_external_id"] = exam_no
            evidence.append("external_id←exam_candidate_number")

    first = str(enriched.get("first_name") or flat.get("first_name") or "").strip()
    last = str(enriched.get("last_name") or flat.get("last_name") or "").strip()
    if not str(flat.get("external_id") or flat.get("student_external_id") or "").strip():
        derived = derive_external_id(
            first_name=first,
            middle_name=str(flat.get("middle_name") or "").strip(),
            last_name=last,
            date_of_birth=flat.get("date_of_birth"),
            place_of_birth=str(flat.get("place_of_birth") or "").strip(),
        )
        if derived:
            enriched["external_id"] = derived
            enriched["student_external_id"] = derived
            evidence.append("external_id←identity_hash")

    _enrich_split_combined_name(
        enriched,
        flat,
        evidence,
        school=school,
        transformer_options=transformer_options,
    )

    first = str(enriched.get("first_name") or flat.get("first_name") or "").strip()
    last = str(enriched.get("last_name") or flat.get("last_name") or "").strip()
    full = str(enriched.get("full_name") or flat.get("full_name") or "").strip()
    if not full and first and last:
        enriched["full_name"] = f"{first} {last}".strip()
        evidence.append("full_name←first_name+last_name")


def enrich_missing_required_row(
    domain: str,
    row: dict | None,
    *,
    school=None,
    transformer_options: dict | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Apply defensible defaults when evidence exists in the same row.

    Returns ``(enriched_row, evidence)`` — empty evidence means do not auto-enrich.
    """
    if not isinstance(row, dict):
        return {}, []
    enriched = dict(row)
    evidence: list[str] = []
    flat = _flatten_source_row(row)
    domain_key = str(domain or "").strip().lower()

    if domain_key == "academics":
        name = str(
            flat.get("subject_name")
            or flat.get("course_name")
            or flat.get("name")
            or flat.get("title")
            or ""
        ).strip()
        code = str(
            flat.get("subject_code")
            or flat.get("code")
            or flat.get("course_code")
            or ""
        ).strip()
        if not name and code:
            enriched["subject_name"] = code
            evidence.append("subject_name←subject_code")
        elif name and not code:
            enriched["subject_code"] = name[:120]  # magic-number-allow: Subject.name max_length
            evidence.append("subject_code←subject_name")
        if not str(flat.get("title") or "").strip() and name:
            enriched["title"] = name
            evidence.append("title←subject_name")

    elif domain_key in {"students", "enrollment", "attendance", "behavior", "alumni"}:
        _enrich_student_identity_keys(
            enriched,
            flat,
            evidence,
            school=school,
            transformer_options=transformer_options,
        )

    elif domain_key == "grades":
        _enrich_student_identity_keys(
            enriched,
            flat,
            evidence,
            school=school,
            transformer_options=transformer_options,
        )
        subject = str(
            flat.get("subject_code")
            or flat.get("subject")
            or flat.get("subject_name")
            or flat.get("title")
            or flat.get("course_name")
            or ""
        ).strip()
        if subject and not str(flat.get("subject_code") or "").strip():
            enriched["subject_code"] = subject
            evidence.append("subject_code←subject_label")
        term = str(flat.get("term") or flat.get("trimestre") or flat.get("semester") or "").strip()
        if term and not str(flat.get("term") or "").strip():
            enriched["term"] = term
            evidence.append("term←period_alias")

    elif domain_key == "guardians":
        child_ref = str(
            flat.get("student_external_id")
            or flat.get("child_external_id")
            or flat.get("pupil_id")
            or flat.get("student_id")
            or flat.get("admission_number")
            or ""
        ).strip()
        if child_ref and not str(flat.get("student_external_id") or "").strip():
            enriched["student_external_id"] = child_ref
            evidence.append("student_external_id←child_ref")
        _enrich_split_combined_name(
            enriched,
            flat,
            evidence,
            school=school,
            transformer_options=transformer_options,
        )

    elif domain_key == "staff":
        ext = str(
            flat.get("staff_external_id")
            or flat.get("external_id")
            or flat.get("employee_id")
            or flat.get("staff_number")
            or flat.get("employee_number")
            or ""
        ).strip()
        if not ext:
            emp = str(flat.get("employee_number") or flat.get("employee_id") or "").strip()
            if emp:
                enriched["staff_external_id"] = emp
                evidence.append("staff_external_id←employee_number")
        _enrich_split_combined_name(
            enriched,
            flat,
            evidence,
            school=school,
            transformer_options=transformer_options,
        )
        first = str(enriched.get("first_name") or flat.get("first_name") or "").strip()
        last = str(enriched.get("last_name") or flat.get("last_name") or "").strip()
        if not str(enriched.get("staff_external_id") or flat.get("staff_external_id") or "").strip():
            derived = derive_external_id(
                first_name=first,
                last_name=last,
                date_of_birth=flat.get("date_of_birth"),
                place_of_birth=str(flat.get("place_of_birth") or "").strip(),
                prefix="auto-staff",
            )
            if derived:
                enriched["staff_external_id"] = derived
                evidence.append("staff_external_id←identity_hash")
        email = str(flat.get("email") or "").strip()
        if email and not str(enriched.get("staff_external_id") or "").strip():
            enriched["staff_external_id"] = f"email-{hashlib.sha256(email.casefold().encode()).hexdigest()[:16]}"
            evidence.append("staff_external_id←email_hash")

    elif domain_key in {"structure", "sections"}:
        label = str(
            flat.get("name")
            or flat.get("classroom_name")
            or flat.get("section_name")
            or flat.get("class_name")
            or flat.get("room_name")
            or ""
        ).strip()
        if label and not str(flat.get("name") or "").strip():
            enriched["name"] = label
            evidence.append("name←section_alias")

    elif domain_key == "specialties":
        name = str(flat.get("name") or flat.get("title") or "").strip()
        code = str(flat.get("code") or "").strip()
        if not name and code:
            enriched["name"] = code
            evidence.append("name←code")
        elif name and not code:
            enriched["code"] = name[:30]  # magic-number-allow: Specialty.code max_length
            evidence.append("code←name")

    elif domain_key == "finance":
        ref = str(
            flat.get("reference")
            or flat.get("invoice_reference")
            or flat.get("invoice_number")
            or flat.get("invoice_no")
            or ""
        ).strip()
        if ref and not str(flat.get("reference") or "").strip():
            enriched["reference"] = ref
            evidence.append("reference←invoice_alias")
        amount_raw = (
            flat.get("amount")
            if flat.get("amount") not in (None, "")
            else flat.get("total")
            if flat.get("total") not in (None, "")
            else flat.get("total_amount")
            if flat.get("total_amount") not in (None, "")
            else flat.get("invoice_amount")
        )
        if amount_raw not in (None, "") and flat.get("amount") in (None, ""):
            enriched["amount"] = amount_raw
            evidence.append("amount←total_alias")
        student_ref = str(
            flat.get("student_external_id")
            or flat.get("admission_number")
            or flat.get("student_code")
            or flat.get("pupil_id")
            or ""
        ).strip()
        if student_ref and not str(flat.get("student_external_id") or "").strip():
            enriched["student_external_id"] = student_ref
            evidence.append("student_external_id←id_alias")
        issue_raw = (
            flat.get("issue_date")
            if flat.get("issue_date") not in (None, "")
            else flat.get("issued_date")
            if flat.get("issued_date") not in (None, "")
            else flat.get("invoice_date")
        )
        if issue_raw not in (None, "") and flat.get("issue_date") in (None, ""):
            enriched["issue_date"] = issue_raw
            evidence.append("issue_date←issued_alias")
        paid_raw = (
            flat.get("paid_amount")
            if flat.get("paid_amount") not in (None, "")
            else flat.get("amount_paid")
        )
        if paid_raw not in (None, "") and flat.get("paid_amount") in (None, ""):
            enriched["paid_amount"] = paid_raw
            evidence.append("paid_amount←amount_paid_alias")

    if not evidence:
        return row, []
    return enriched, evidence


def normalize_canonical_row(
    domain: str,
    row: dict[str, Any],
    ctx,
) -> dict[str, Any]:
    """Apply the same defensible defaults during initial landing as autopilot replay."""
    enriched, _evidence = enrich_missing_required_row(
        domain,
        row,
        school=getattr(ctx, "school", None),
        transformer_options=getattr(ctx, "transformer_options", None) or {},
    )
    return enriched if _evidence else row


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

def record_bundle_scoped_key(
    *,
    ctx,
    legacy_id: str,
    domain: str,
    canonical_pk: str,
) -> None:
    """Persist a bundle-scoped identity without a first-class model (e.g. payroll DFV).

    Best-effort — never raises.
    """
    if not legacy_id or not canonical_pk:
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
        with row_savepoint():
            MigrationIdMapping.objects.update_or_create(
                legacy_namespace=namespace,
                legacy_id=str(legacy_id)[:128],
                canonical_model="migration_cloud.bundle_scoped",
                school_id=bundle.school_id,
                domain=domain[:32],
                defaults={
                    "bundle": bundle,
                    "canonical_pk": str(canonical_pk)[:64],
                },
            )
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).debug("record_bundle_scoped_key skipped", exc_info=True)


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
    try:
        from django.db.models import Model

        if isinstance(value, Model):
            pk = value.pk
            if pk is None or isinstance(pk, (str, int, float, bool)):
                return pk
            return str(pk)
    except Exception:  # noqa: BLE001
        pass
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:  # noqa: BLE001
            pass
    return str(value)[:200]


def json_field_safe(value: Any) -> Any:
    """Make a structure safe for Django ``JSONField`` persistence."""
    import json

    try:
        return json.loads(json.dumps(value, default=_jsonable))
    except (TypeError, ValueError):
        return str(value)[:500]


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


def maybe_stall_pulse(*, every: int = 1, counter: int = 0) -> None:
    """Pulse the apply stall watchdog during long lander loops."""
    from apps.migration_cloud.apply_stall import maybe_stall_pulse as _pulse

    _pulse(every=every, counter=counter)


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


def explicit_conflict_resolution_for(*, ctx, canonical_obj: Any) -> str:
    """The operator's RECORDED decision for this object in this bundle, or "".

    ``conflict_resolution_for`` collapses "no decision" into its OVERWRITE
    default, which is right for the ordinary field idiom (import refreshes,
    PRESERVE is the opt-out). A caller whose default is PROTECT -- the subject
    category, where "off the default" is the only proxy for a deliberate edit --
    needs the absence of a decision distinguished from the decision, or the
    default would reinstate exactly the silent overturn the protection exists
    to stop.
    """
    if canonical_obj is None:
        return ""
    try:
        from apps.migration_cloud.models import ConflictResolution, MigrationConflict
    except ImportError:
        return ""
    from django.db import DataError, OperationalError, ProgrammingError

    try:
        canonical_model_path = (
            f"{canonical_obj.__class__.__module__}.{canonical_obj.__class__.__name__}"
        )
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
        return "" if row is None else str(row.resolution)
    except (DataError, OperationalError, ProgrammingError):
        # A best-effort READ: an unreadable conflict table means "no recorded
        # decision", which fails to the protective default upstream.
        return ""


def conflict_resolution_for(*, ctx, canonical_obj: Any) -> str:
    """Look up a resolved-conflict decision for this row, if any.

    Returns 'OVERWRITE' (default), 'PRESERVE' (skip update), or 'MERGE'
    (the lander caller can decide field-by-field). Operators set this via
    the conflict review UI before re-running apply.

    DELIBERATE ASYMMETRY with ``explicit_conflict_resolution_for`` above -- do
    not harmonise them. HERE absent-means-OVERWRITE, because this serves the
    ordinary field idiom where the import refreshing data is the point and
    PRESERVE is the operator's opt-out. THERE absent-means-"", because that
    caller's default is PROTECT (a value someone set by hand) and collapsing
    "nobody decided" into "overwrite" is precisely the silent overturn the
    protective branch exists to stop. Making these two return the same thing
    for an absent row would reintroduce that data-loss path while looking like
    a cleanup.
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
# FK parents the SAME safe way (reuse-by-(school,name), mint a code scoped to the
# TARGET school, never reuse the source's — which carries the source system's
# namespace into the target's catalog and, anywhere a ``code`` lookup is not
# school-scoped, resolves ANOTHER school's row).


def _slug_upper(value: str, width: int = 8) -> str:
    return (re.sub(r"[^A-Z0-9]+", "", (value or "").upper())[:width]) or "X"


def _scope_token(school) -> str:
    """A SHORT, stable per-school token for a minted code.

    ``School.pk`` is a 36-char UUID on this platform, so a bare ``{prefix}{pk}``
    already exceeds the 30-char ``code`` column — the ``[:30]`` truncation then
    drops the NAME entirely and every minted code collapses to one value, so the
    2nd..Nth provisioned Department/Specialty/Classroom -- all in the SAME school
    -- collide on the per-``(school, code)`` unique code and quarantine (0 land
    past the first). Hash a long id down to 6 hex chars; keep a short integer pk
    verbatim so existing integer-pk deployments' codes are unchanged.
    """
    sid = str(getattr(school, "pk", "") or "0")
    if len(sid) > 8:  # magic-number-allow: short-integer-pk-threshold (UUIDs are 36)
        # Shortens a long pk into a stable 6-hex code. The docstring above
        # promises existing deployments' codes are unchanged, so the digest
        # is a contract: usedforsecurity=False satisfies B324 without
        # touching a single output byte.
        return hashlib.sha1(
            sid.encode("utf-8"), usedforsecurity=False
        ).hexdigest()[:6]
    return sid


def mint_scoped_code(*, prefix: str, name: str, school, model, code_field: str = "code") -> str:
    """A fresh code for a provisioned structure row, scoped to the target school.

    ``Department.code`` (``uniq_department_school_code``, academics migration
    0076) and ``Specialty.code``/``Classroom.code``
    (``uniq_specialty_school_code``/``uniq_classroom_school_code``, migration
    0085) are unique per ``(school, code)`` — NOT platform-wide. The source's
    code is still not reused: it carries the source system's namespace into the
    target's catalog, and anywhere a ``code`` lookup is not school-scoped it
    resolves the SOURCE school's row. Deterministic per (school, name) for stable
    re-runs, with a hash fallback if the short form ever collides. The school
    token is length-bounded (:func:`_scope_token`) so the NAME always survives
    the 30-char cap even when ``School.pk`` is a UUID.

    The freshness probe below is deliberately left unscoped, and that is safe
    rather than an oversight. ``candidate`` always embeds THIS school's own
    :func:`_scope_token`, so a row belonging to another school can only match it
    by a 6-hex SHA-1 collision on the school pk — a hit therefore all but always
    means this school already holds the candidate, which is exactly the question
    being asked. And the probe has no veto: both branches return a string, so an
    unscoped (strictly wider) probe can only ever append a hash suffix, never
    block a create. Scoping it would be equally correct and is the safer default
    for new code; it is left alone here because changing it would change minted
    codes on re-run for no behavioural gain.
    """
    sid = _scope_token(school)
    base = _slug_upper(name)
    candidate = f"{prefix}{sid}-{base}"[:30]  # magic-number-allow: code column max_length=30
    if not model.objects.filter(**{code_field: candidate}).exists():  # tenant-isolation-allow: freshness-probe-for-a-candidate-that-already-embeds-this-schools-scope-token; a cross-school hit needs a sha1 collision on the school pk, and a hit can only append a suffix, never block a create
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


def user_is_linkable_to_school(user, school) -> bool:
    """May an import bind this EXISTING ``user`` to ``school``?

    ``accounts.User`` / ``schools.SchoolMembership`` are SHARED_APPS in the
    public schema, so an email lookup inside a lander sees EVERY tenant's users.
    Taking the first hit let a bundle uploaded by school A bind school B's
    headteacher to an A record — and, for guardians, hand that account a
    ``SchoolMembership`` in A (``ensure_school_membership`` is deliberately
    additive and cannot be the gate). Linkable means: already a member here, or
    a member of NO school yet (a freshly provisioned / unclaimed account). A
    user who belongs only to OTHER schools is not linkable by a weak key —
    genuine inter-school transfers carry the platform identity and land through
    the username rung instead.
    """
    if user is None or school is None or not getattr(user, "pk", None):
        return True
    try:
        from apps.schools.models import SchoolMembership
    except Exception:  # noqa: BLE001 — membership model absent → no scoping signal
        return True
    memberships = SchoolMembership.objects.filter(user=user)  # tenant-isolation-allow: the cross-school reach IS what this gate measures
    if memberships.filter(school=school).exists():
        return True
    return not memberships.exists()


#: Held-row wording for a weak-key match that belongs to a DIFFERENT tenant.
#: Phrased for the school admin reading the quarantine table, and it names the
#: way out (re-upload carrying the platform username).
FOREIGN_SCHOOL_MATCH_REASON = (
    "email {email!r} already belongs to a user in another school — not linked. "
    "Supply that person's platform username to move them deliberately."
)


def resolve_or_provision_user(
    *, User, username_hint: str, email: str, first_name: str, last_name: str,
    role: str, dry_run: bool, school: Any = None,
):
    """Return ``(user, reason)`` — reason set only when user is None.

    Resolution order: existing platform user by username_hint → by email →
    provision a NEW account (role as given, UNUSABLE password — no credential is
    ever minted; the person activates via the normal invite/reset flow). Existing
    users are NEVER mutated (their role/names/credentials stay theirs). Mirrors
    ``guardian_lander._resolve_or_provision_user`` so staff land the same way
    guardians do.

    The email rung is school-scoped (:func:`user_is_linkable_to_school`): a match
    that belongs only to ANOTHER tenant holds the row instead of linking.
    """
    if username_hint:
        user = User.objects.filter(username=username_hint).first()
        if user is not None:
            return user, ""
    if email:
        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            if not user_is_linkable_to_school(user, school):
                return None, FOREIGN_SCHOOL_MATCH_REASON.format(email=email)
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
        #
        # School-scoped like the email rung above, and for the same reason: this
        # lookup is reached exactly when that rung saw nothing, so the winner is
        # a row that committed in the window between the rung and this insert —
        # and a concurrent import running for a DIFFERENT tenant is precisely
        # the writer that wins that race. Recovering it unscoped would re-open
        # the cross-tenant bind through the back door.
        user = User.objects.filter(email__iexact=email).first() if email else None
        if user is not None and not user_is_linkable_to_school(user, school):
            return None, FOREIGN_SCHOOL_MATCH_REASON.format(email=email)
        if user is None:
            raise
    return user, ""


def dfv_import_source_ref(ctx) -> str:
    """A locator for THIS import as a DynamicFieldValue provenance stamp.

    Bundle and artifact ids are deployment-local, which is fine: the stamp answers
    "which import wrote this, HERE" for the re-import guard and for an operator
    reading the row -- it is never used to resolve identity across deployments.
    """
    bundle = getattr(ctx, "bundle_id", "") or ""
    artifact = getattr(ctx, "artifact_id", "") or ""
    return f"bundle:{bundle}/artifact:{artifact}"[:120]


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
    from apps.metadata.services import upsert_dynamic_field_value

    for field_key, value in clean.items():
        try:
            _preserved = False
            with row_savepoint():  # isolate each DFV write from the atomic apply
                DynamicFieldDefinition.objects.get_or_create(
                    entity_type=entity_type,
                    field_key=field_key,
                    school=getattr(ctx, "school", None),
                    defaults={"label": field_key.replace("_", " ").title(), "data_type": "json"},
                )
                # `school` stays in the LOOKUP (inside the guarded writer), never
                # in defaults -- metadata is a SHARED app, one table for every
                # tenant, and entity_id is the target's pk as a string, which
                # collides across tenants as a matter of course.
                #
                # GUARDED write. Measured 2026-09-02: the bare update_or_create
                # here overwrote unconditionally, so re-uploading a file silently
                # clobbered values a person had corrected by hand (the tenant EAV
                # forms, the admin break-glass screen and set_dynamic_field_value
                # all stamp "human"). A deliberate edit is that school's decision
                # and an import does not outrank it -- kept, and said out loud.
                _obj, _created, _preserved = upsert_dynamic_field_value(
                    school=getattr(ctx, "school", None),
                    entity_type=entity_type,
                    entity_id=str(entity_id)[:64],
                    field_key=field_key,
                    value_json={"v": value},
                    source="import",
                    source_ref=dfv_import_source_ref(ctx),
                )
            if _preserved and result is not None:
                record_row_note(
                    result,
                    f"{entity_type}[{str(entity_id)[:64]}].{field_key}: kept the "
                    "value a person set; the import does not outrank it",
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
