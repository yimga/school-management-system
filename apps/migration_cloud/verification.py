"""Post-apply VERIFICATION — prove uploaded rows actually landed in the tenant.

Two passes live here, and they prove different things:

* **Pass 1** (:func:`verify_landed_counts`) — re-queries the tenant and counts.
  It catches a rollback, a wrong-school write, a filtered save. It is a COUNT,
  so it cannot see a truncated field, a mis-mapped column, or a coerced value.
* **Pass 2** (:func:`verify_bundle_checksums`) — a cryptographic (SHA-256)
  record-by-record comparison of the SOURCE artifact against the LANDED database
  row, read independently of each other. This is the integrity proof; the count
  above is the liveness check. See the PASS 2 banner further down.

``reconciliation.py`` historically computed "parity" by comparing the profiler's
source row-count against the **landers' own self-reported** created/updated counts
(pulled from the ``MigrationRun`` audit trail) — it never re-queried the tenant.
So a lander that reported ``created=100`` but whose writes were rolled back,
scoped to the wrong school, or filtered out on save would still show 100% parity.

This module re-queries each domain's REAL tenant model, **under the tenant schema
and scoped to the bundle's school**, so reconciliation can report the honest
chain ``source → landed(self-reported) → visible(actually in the school)`` and
flag drift when creates did not persist.

It mirrors :func:`apps.migration_cloud.guardrails.compute_observed_totals` (same
``schema_context`` + field-aware school scoping) but generalised to every domain
we can confidently map to a concrete model. A domain without a confident model
mapping simply returns no count (honest "not verified") rather than guessing.
"""

from __future__ import annotations

import hashlib
import importlib
import logging
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, Iterable, Sequence
from django.core.exceptions import FieldDoesNotExist, FieldError, ValidationError
from django.db import DatabaseError

from .landers.base import LanderError

#: Failures a source re-read or a per-domain verification can realistically hit:
#: unreadable or corrupt artifact bytes, a value the source cannot coerce, a
#: lookup that is not there, a database refusal. Named explicitly rather than
#: catching ``Exception`` so a NameError or AttributeError from a typo still
#: crashes loudly instead of being filed as "the source was unreadable" -- this
#: repo has already lost a whole guardian artifact to a NameError nothing caught.
#: Bound at MODULE scope: an ``except`` tuple is evaluated only when something is
#: raised, so a lazily-imported class would NameError at the moment it is needed.
_SOURCE_READ_ERRORS = (
    OSError,
    ValueError,
    TypeError,
    LookupError,
    ArithmeticError,
    DatabaseError,
    # The domain exception for exactly this: the artifact's bytes were never
    # captured at ingest, so there is nothing to re-read. Naming it is the
    # point -- it is a REPORTED state, not an unexpected failure.
    LanderError,
)

logger = logging.getLogger(__name__)


# canonical domain -> (module path, model class name). The count is always scoped
# to the bundle's school: field-aware — a direct ``school`` FK, else
# ``student__school``, else unscoped under ``schema_context`` (which already
# isolates the tenant in schema-per-tenant mode). Add a domain here only once its
# landing model is confirmed; an unmapped domain reports no visible count rather
# than counting the wrong table.
_DOMAIN_MODELS: dict[str, tuple[str, str]] = {
    "students": ("apps.people.models", "StudentProfile"),
    "staff": ("apps.people.models", "TeacherProfile"),
    "guardians": ("apps.people.models", "StudentGuardian"),
    "finance": ("apps.finance.models", "Invoice"),
    # P1-Verify — extend beyond the original four so post-apply "visible in school"
    # covers the main landable domains tenants actually check.
    "attendance": ("apps.academics.models", "Attendance"),
    "grades": ("apps.evals.models", "Evaluation"),
    "behavior": ("apps.academics.models", "Incident"),
    "sections": ("apps.academics.models", "Classroom"),
    "health": ("apps.schoolops.models", "HealthRecord"),
    "events": ("apps.school_events.models", "SchoolEvent"),
    "library": ("apps.schoolops.models", "LibraryItem"),
    "transport": ("apps.schoolops.models", "Route"),
    "hostel": ("apps.schoolops.models", "HostelRoom"),
    "cafeteria": ("apps.schoolops.models", "CanteenMeal"),
    "transcripts": ("apps.people.models", "TranscriptVaultItem"),
    "athletics_teams": ("apps.athletics.models", "Team"),
    "transport_assignments": ("apps.schoolops.models", "TransportAssignment"),
    "hostel_assignments": ("apps.schoolops.models", "HostelAssignment"),
    "cafeteria_assignments": ("apps.schoolops.models", "MealPlanBalance"),
    # P1-Verify-2 (2026-07-25) — these landers write REAL, school-scoped
    # first-class rows but had no visible-count proof, so a wrong-school /
    # rolled-back / filtered-save regression on them was invisible to
    # reconciliation. Each model below carries a DIRECT ``school`` FK, so the
    # count matches the domain's self-reported creates (drift-correct):
    #   * academics  → Subject: a SIS "courses" upload; the tenant's Subjects.
    #   * structure  → SubjectAssignment: the SPLIT scaffold's created unit
    #     (one per row), which co-lands the school's Specialties/Classrooms —
    #     so a landed structure bundle is proven, incl. specialties.
    #   * communications → Message; athletics_memberships → TeamMembership;
    #     athletics_fixtures → Fixture.
    "academics": ("apps.academics.models", "Subject"),
    "structure": ("apps.academics.models", "SubjectAssignment"),
    "communications": ("apps.communication.models", "Message"),
    "athletics_memberships": ("apps.athletics.models", "TeamMembership"),
    "athletics_fixtures": ("apps.athletics.models", "Fixture"),
    # Deliberately NOT mapped: ``alumni`` lands into StudentProfile (shared with
    # ``students``) so a domain-keyed count would double-count the roster; and
    # ``payroll`` / ``compliance`` / ``schedule`` persist only DynamicFieldValue
    # blobs (no importable first-class model — ScheduleEntry needs the solved
    # timetable graph; see schedule_lander) — all stay the honest "not verified"
    # case.
}


def domains_with_verification() -> set[str]:
    """The set of canonical domains this module can re-query. (For tests/UI.)"""
    return set(_DOMAIN_MODELS)


def _school_scoped_count(model: Any, school: Any) -> int:
    """Count rows of ``model`` visible for ``school`` (field-aware scoping).

    Models whose link to the school is not literally ``school`` / ``student``
    (``HostelRoom.hostel -> Hostel.school``, a transcripts row's ``issuing_school``,
    a ``student_profile`` FK) previously fell through to ``.all()``. In the shared-
    schema (RLS) path ``.all()`` counts EVERY school's rows, so a wrong-school write
    could never drop the visible count below the source count — drift could not fire
    and the bundle would seal + purge its encrypted source on a false "all visible".
    Recognise the indirect school paths so the visible-count check actually scopes.
    """
    field_names = {f.name for f in model._meta.get_fields()}
    if "school" in field_names:
        qs = model.objects.filter(school=school)  # tenant-isolation-allow: scoped by the model's own school FK
    elif "issuing_school" in field_names:
        qs = model.objects.filter(issuing_school=school)  # tenant-isolation-allow: scoped by the model's issuing_school FK
    elif "student" in field_names:
        qs = model.objects.filter(student__school=school)  # tenant-isolation-allow: scoped via student__school=school
    elif "student_profile" in field_names:
        qs = model.objects.filter(student_profile__school=school)  # tenant-isolation-allow: scoped via student_profile__school=school
    elif "hostel" in field_names:
        qs = model.objects.filter(hostel__school=school)  # tenant-isolation-allow: scoped via hostel__school=school (HostelRoom -> Hostel.school)
    else:
        qs = model.objects.all()  # tenant-isolation-allow: no school field; schema_context isolates the tenant
    return qs.count()


def verify_landed_counts(
    bundle: Any, *, domains: list[str] | None = None
) -> dict[str, int]:
    """Re-query the tenant and return ``{domain: rows_visible_in_school}``.

    Only domains we can confidently map to a model are returned (unmapped or
    errored domains are omitted, never guessed). Runs under the bundle's tenant
    schema so counts reflect exactly what the school actually sees. Never raises —
    a bad mapping logs a warning and is skipped so it can't break reconcile.
    """
    school = getattr(bundle, "school", None)
    if school is None:
        return {}
    schema_name = getattr(bundle, "schema_name", "") or ""

    def _run_under_schema(fn: Callable[[], Any]) -> Any:
        if not schema_name:
            return fn()
        try:
            from django_tenants.utils import schema_context
        except ImportError:
            return fn()
        from django.db import connection
        if not hasattr(connection, "set_schema"):
            # Non-tenant DB backend (single-schema sqlite test/dev lane, or an
            # RLS single-schema deploy): there is no schema to switch and
            # entering schema_context raises AttributeError ('DatabaseWrapper'
            # has no 'tenant'). Everything already lives in one schema, so run
            # as-is. Mirrors the guard in orchestrator._land_under_schema.
            return fn()
        with schema_context(schema_name):
            return fn()

    wanted = set(domains) if domains else None
    out: dict[str, int] = {}
    for domain, (module_path, model_attr) in _DOMAIN_MODELS.items():
        if wanted is not None and domain not in wanted:
            continue
        try:
            module = importlib.import_module(module_path)
            model = getattr(module, model_attr)
        except (ImportError, AttributeError):  # model unavailable in this deploy
            continue
        try:
            out[domain] = _run_under_schema(
                lambda m=model: _school_scoped_count(m, school)
            )
        except (DatabaseError, FieldError, ValueError, TypeError):  # a bad mapping must never break reconcile
            logger.warning(
                "migration_cloud.verify: visible-count failed for domain=%s",
                domain,
                exc_info=True,
            )
    return out



# ---------------------------------------------------------------------------
# PASS 2 — cryptographic SOURCE-vs-LANDED record checksums
# ---------------------------------------------------------------------------
# Everything above this line is PASS 1 territory: it counts. ``verify_landed_counts``
# re-queries the tenant and answers "are there as many rows as the landers said they
# created?". That is a real check -- it catches a rollback, a wrong-school write, a
# filtered save -- and reconciliation already blocks the APPLIED -> RECONCILED seal on
# it. But a row COUNT is not an integrity proof. It is blind to:
#
#   * a truncated field   (``max_length`` clipped a 90-char surname to 80)
#   * a mis-mapped column (the phone number landed in ``section``)
#   * a coerced value     (a decimal rounded; an uncoercible value stored as NULL)
#   * a substituted row   (100 rows landed, but 50 of them are duplicates of one row)
#
# In every one of those the count matches exactly and the migration reports parity.
#
# This pass closes that. For each domain with a declared spec below it:
#
#   1. re-reads the SOURCE bytes from the encrypted artifact blob and re-parses them
#      through the same mapping/transform chain the apply used
#      (``orchestrator._iter_canonical_rows``);
#   2. INDEPENDENTLY re-reads the LANDED row straight out of the tenant database
#      under ``schema_context`` (``.values()`` -- raw column values, no model
#      instance, no property, nothing carried over from the apply);
#   3. computes a stable, field-ordered SHA-256 over each side and compares them.
#
# The two digests are computed from two different reads of two different stores. No
# value is shared between them -- which is the whole point. A digest that both sides
# derive from the same in-memory row proves only that Python can hash a dict twice.
#
# WHAT THIS PASS DOES AND DOES NOT CLAIM
# --------------------------------------
# * It proves: every value the SOURCE asserted for a compared field is now in the
#   database, verbatim, on the row carrying that record's identity.
# * It does NOT prove the database holds nothing else. Landers upsert and skip empty
#   values, so a field the source left blank keeps whatever was there before. Only
#   fields NON-EMPTY in the source are compared -- comparing blanks would produce
#   false divergences on every re-import.
# * It does NOT re-derive the transform. The source side is the CANONICAL row (post
#   mapping + transformers), i.e. the record the pipeline committed to landing. A
#   mis-TRANSFORM upstream (the date parser choosing the wrong order) is identical on
#   both sides and is invisible here; that is the profiler's and the operator's
#   review, not the checksum's. What this catches is everything that happened
#   BETWEEN "the pipeline decided to write X" and "the database now holds Y".
# * Domains without a spec are NOT silently passed. They are reported by name in
#   ``unverifiable_domains`` so the report can never be read as "all clear".
#
# WHY A FIELD IS EXCLUDED RATHER THAN COMPARED
# --------------------------------------------
# Each spec carries an ``excluded`` map naming every field it does NOT compare and
# why. A field the lander DERIVES (an enum remap, a locale-aware name split, a
# conditional fold into another column, a value read off a resolved parent) is left
# out on purpose. Re-implementing the derivation here would only compare our copy of
# the lander to the lander -- it would prove nothing, and any drift between the two
# copies would cry divergence on a perfectly healthy import. Coverage bought that way
# is worse than no coverage, because it looks like proof.

CHECKSUM_ALGORITHM = "sha256"

# Field separator inside the digest pre-image. Unit/record separators are used
# instead of a printable delimiter so a value CONTAINING the delimiter cannot forge
# a different record's pre-image (the classic "a|bc" vs "ab|c" collision).
_DIGEST_UNIT_SEP = "\x1f"
_DIGEST_RECORD_SEP = "\x1e"
# Distinct from the empty string so "field is absent" and "field is ''" are not the
# same pre-image.
_DIGEST_NULL = "\x00NULL\x00"
# Joins the parts of a composite identity (student + date, student + artifact + hash).
_IDENTITY_SEP = "\x1d"


def normalise_for_digest(value: Any) -> str:
    """Canonical text for one value, for hashing on BOTH sides.

    Representation is normalised; VALUE is not. Whitespace around a string is
    stripped (every lander strips before writing, so a trailing space is never a real
    divergence) but case, interior spacing, and length are preserved -- a truncation
    or a case change MUST survive into the digest.
    """
    import datetime as _dt
    from decimal import Decimal

    if value is None:
        return _DIGEST_NULL
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, _dt.datetime):
        # A DateTimeField column hands back an AWARE datetime, while a source
        # value parsed from ``2026-02-01`` is NAIVE. That difference is
        # representation, not value, and left alone it would report a divergence
        # on every healthy datetime import. Anchor naive values in the same
        # default timezone Django would have used when storing them, then compare
        # both sides as UTC instants -- a genuinely different moment still differs.
        try:
            from django.conf import settings as _settings
            from django.utils import timezone as _timezone

            if getattr(_settings, "USE_TZ", False):
                if _timezone.is_naive(value):
                    value = _timezone.make_aware(
                        value, _timezone.get_default_timezone()
                    )
                value = value.astimezone(_dt.timezone.utc)
        except (ValueError, OverflowError, TypeError):  # outside Django: compare as-is
            pass
        return value.isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, _dt.time):
        return value.isoformat()
    if isinstance(value, Decimal):
        # Normalise scale so Decimal("1.50") and Decimal("1.5") agree; a genuine
        # value change still moves the digest.
        try:
            return format(value.normalize(), "f")
        except (ValueError, OverflowError, TypeError):  # NaN/Inf: fall through to str()
            return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(Decimal(str(value)).normalize(), "f")
    return str(value).strip()


def record_digest(record: dict[str, Any], fields: "Sequence[str]") -> str:
    """Stable, field-ORDERED SHA-256 over ``fields`` of ``record``.

    ``fields`` is an explicit ordered sequence, never ``record.keys()`` -- dict order
    is an accident of construction, and the two sides here are built by different
    code, so hashing key order would make the digest depend on how the dict was
    assembled rather than on what it contains. The field NAME is folded into the
    pre-image too, so two values swapped between columns (the mis-mapped-column case)
    changes the digest instead of cancelling out.
    """
    units = [
        name + _DIGEST_UNIT_SEP + normalise_for_digest(record.get(name))
        for name in fields
    ]
    return hashlib.sha256(
        _DIGEST_RECORD_SEP.join(units).encode("utf-8")
    ).hexdigest()


def _identity_key(parts: Any) -> str:
    """Normalise an identity (scalar or ordered parts) into one comparable string.

    Both sides go through this, so a source identity assembled from canonical fields
    and a landed identity assembled from database columns cannot disagree merely
    because one held a ``date`` and the other its ISO text.
    """
    if parts is None:
        return ""
    if isinstance(parts, (list, tuple)):
        return _IDENTITY_SEP.join(normalise_for_digest(p) for p in parts)
    return normalise_for_digest(parts)


# --- Per-domain checksum specs ---------------------------------------------
# A domain is checksummable only once we can answer BOTH questions honestly:
#   (a) how to name the SAME record on both sides, without re-running any resolution
#       the lander did (fuzzy student matching, a graph resolver, a get-or-create of
#       a parent) -- because re-running it would be re-implementing the lander; and
#   (b) which fields the lander copies VERBATIM into a real model column.
#
# Two identity strategies are supported:
#
#   NATURAL  -- ``identity_columns`` names real database columns (following FKs where
#               needed, e.g. ``student__admission_number``). Both sides build the key
#               from data, so a source row with no landed match is genuinely MISSING.
#               Preferred: it can prove absence.
#   ID_MAP   -- ``id_map_domain`` joins through ``MigrationIdMapping``, the pointer
#               the lander itself recorded, keyed by a legacy id built from RAW
#               SOURCE fields. Used only where the destination row is addressable
#               solely through resolved foreign keys. The values on both sides are
#               still read independently, so a value divergence is still caught --
#               but the id-map write is best-effort, so its ABSENCE is not proof the
#               row is missing. Such rows go to ``unresolved_identity``, never to
#               ``missing_in_destination``, and never to ``matched``.


@dataclass(frozen=True)
class ChecksumSpec:
    """How to locate and compare one domain's records on both sides."""

    domain: str
    module_path: str
    model_attr: str
    #: canonical row -> identity scalar or ordered parts ("" / None = not identifiable)
    source_identity: "Callable[[dict[str, Any]], Any]"
    #: MODEL COLUMN -> canonical field name, or a callable(row) returning the value.
    #: Keyed by column so a canonical name differing from the column it lands in
    #: (``issue_date`` -> ``issued_date``) is expressed rather than assumed.
    fields: dict[str, Any]
    #: fields deliberately NOT compared, and why (surfaced in the report)
    excluded: dict[str, str]
    #: NATURAL strategy: model -> ordered list of columns forming the identity
    identity_columns: "Callable[[Any], list[str]] | None" = None
    #: ID_MAP strategy: the ``MigrationIdMapping.domain`` value the lander recorded
    id_map_domain: str = ""



# ---- helpers shared by the specs -------------------------------------------

def _student_identity_column(prefix: str = "") -> str:
    """The column a StudentProfile's source id lands in, on THIS deployment.

    Deployments differ (``external_id`` / ``sis_external_id`` / ``source_id`` /
    ``admission_number``), so this asks the lander's own resolver rather than
    hard-coding a guess. ``prefix`` follows a FK, e.g. ``student__``.
    """
    from apps.people.models import StudentProfile

    from .landers._helpers import student_lookup_field

    return prefix + student_lookup_field(
        {f.name for f in StudentProfile._meta.get_fields()}
    )


def _clean(value: Any) -> str:
    from .landers._helpers import _clean_source_string

    return _clean_source_string(value)


def _coerce_date(value: Any):
    from .landers._helpers import coerce_date

    return coerce_date(value)


def _s(value: Any) -> str:
    return str(value or "").strip()


# ---- students --------------------------------------------------------------

def _students_source_identity(row: dict[str, Any]) -> str:
    from .landers._helpers import derive_external_id

    external_id = _clean(row.get("external_id"))
    first = _clean(row.get("first_name"))
    last = _clean(row.get("last_name"))
    middle = _clean(row.get("middle_name"))
    # A row carrying only a combined ``full_name`` is landed by the lander via a
    # locale-aware split we deliberately do not replicate. Return no identity so the
    # row is bucketed ``unidentified`` -- visible, and never counted as matched.
    if not first or not last:
        return ""
    if not external_id:
        external_id = derive_external_id(
            first_name=first,
            middle_name=middle,
            last_name=last,
            date_of_birth=row.get("date_of_birth"),
            place_of_birth=row.get("place_of_birth"),
        )
    return external_id


# ---- academics -------------------------------------------------------------

def _academics_name(row: dict[str, Any]) -> str:
    name = _s(row.get("subject_name") or row.get("name") or row.get("title"))
    code = _s(row.get("subject_code") or row.get("code"))
    # The lander clips to the Subject.name column width before writing; mirror it so
    # its own clipping is never misread as a database truncation.
    return (name or code)[:120]  # magic-number-allow: mirrors academics_lander's clip


# ---- finance ---------------------------------------------------------------

def _finance_reference(row: dict[str, Any]) -> str:
    return _s(row.get("reference") or row.get("invoice_reference"))


def _finance_identity_columns(model: Any) -> list[str]:
    fields = {f.name for f in model._meta.get_fields()}
    # The lander picks the same column in the same order.
    return ["reference"] if "reference" in fields else ["payment_code"]


# ---- attendance ------------------------------------------------------------

def _attendance_source_identity(row: dict[str, Any]) -> Any:
    external_id = _s(row.get("student_external_id"))
    date_val = _coerce_date(row.get("date"))
    if not external_id or date_val is None:
        return ""
    return [external_id, date_val]


def _attendance_remarks(row: dict[str, Any]) -> str:
    # Canonical attendance carries the remark under ``notes``; the column is
    # ``remarks``. The lander reads notes first and clips to 255 -- mirror both, so
    # its own clip is never misread as a database truncation.
    return _s(row.get("notes") or row.get("remarks"))[:255]  # magic-number-allow: mirrors attendance_lander's clip


# ---- transcripts -----------------------------------------------------------

def _transcripts_artifact_type(row: dict[str, Any]) -> str:
    return _s(row.get("artifact_type") or "transcript")[:64]  # magic-number-allow: mirrors transcripts_lander's clip


def _transcripts_verification_hash(row: dict[str, Any]) -> str:
    """Recompute the lander's addressable-identity hash from RAW SOURCE fields.

    This is not a re-implemented transform: it is the record's ADDRESS, built by the
    lander out of four unmodified source values so an upsert stays idempotent without
    proliferating columns. Rebuilding the address is how we find the row; the row's
    VALUES are still read independently from the database and hashed separately.
    """
    payload_key = "::".join([
        _s(row.get("academic_year")),
        _s(row.get("term")),
        _s(row.get("subject_code") or row.get("subject")),
        str(row.get("final_grade") or ""),
    ])
    return hashlib.sha256(payload_key.encode("utf-8")).hexdigest()[:64]


def _transcripts_source_identity(row: dict[str, Any]) -> Any:
    external_id = _s(row.get("student_external_id"))
    if not external_id:
        return ""
    return [
        external_id,
        _transcripts_artifact_type(row),
        _transcripts_verification_hash(row),
    ]


def _transcripts_artifact_ref(row: dict[str, Any]) -> str:
    return str(row.get("artifact_ref") or "")[:512]  # magic-number-allow: mirrors transcripts_lander's clip


# ---- grades ----------------------------------------------------------------

_GRADE_COMPONENTS = (
    "seq1_score", "seq2_score", "exam_score", "mock_score",
    "practical_score", "internship_score", "test1", "test2",
)


def _grades_source_identity(row: dict[str, Any]) -> str:
    """The legacy id the grades lander records in MigrationIdMapping.

    Built from three RAW source strings, exactly as ``grades_lander`` builds it. The
    destination row is reachable ONLY through resolved foreign keys (student,
    academic year, term, subject assignment) chosen by a graph resolver with loose
    label matching and an active-year fallback -- re-running that resolution here
    would be re-implementing the lander, so we follow the pointer it left instead.
    """
    external_id = _s(row.get("student_external_id"))
    term_label = _s(row.get("term"))
    subject_label = _s(row.get("subject_code") or row.get("subject"))
    if not external_id or not term_label or not subject_label:
        return ""
    return f"{external_id}:{term_label}:{subject_label}"


def _grades_letter(row: dict[str, Any]) -> str:
    return _s(row.get("grade_letter") or row.get("letter_grade"))[:8]  # magic-number-allow: mirrors grades_lander's clip


# ---- guardians -------------------------------------------------------------

def _guardians_source_identity(row: dict[str, Any]) -> Any:
    """(student, email, phone) -- three values the lander copies verbatim.

    The lander's own key is ``(student, guardian_user)``, and ``guardian_user`` is
    resolved by username, then email, then a phone+name similarity match. Re-running
    that would be re-implementing it, so we address the row by the two guardian
    columns the lander writes UNCHANGED from the source instead, and leave
    ``whatsapp_number`` / ``address`` as the independently-compared payload.
    """
    external_id = _s(row.get("student_external_id"))
    email = _s(row.get("email"))
    phone = _s(row.get("phone"))
    if not external_id or not (email or phone):
        return ""
    return [external_id, email, phone]


# ---- events ----------------------------------------------------------------

def _events_start(row: dict[str, Any]):
    return _coerce_date(
        row.get("starts_at") or row.get("start_date") or row.get("date")
    )


def _events_slug(row: dict[str, Any]) -> str:
    """Rebuild the lander's computed slug -- the row's ADDRESS, not a payload value."""
    from django.utils.text import slugify

    starts = _events_start(row)
    title = _s(row.get("title") or row.get("name"))
    if starts is None or not title:
        return ""
    return (slugify(f"{title}-{starts.isoformat()}") or "event")[:100]  # magic-number-allow: mirrors events_lander's clip


def _events_title(row: dict[str, Any]) -> str:
    return _s(row.get("title") or row.get("name"))[:255]  # magic-number-allow: mirrors events_lander's clip


# ---- library ---------------------------------------------------------------

def _library_source_identity(row: dict[str, Any]) -> str:
    """ISBN only.

    The lander switches identity shape: with an ISBN it upserts on
    ``(school, isbn)``, without one on ``(school, title[, author])`` -- where title
    and author ARE the key, so comparing them would be circular, and a row with no
    author can match several books and quarantine on MultipleObjectsReturned. We
    verify only the ISBN-keyed rows, where title and author are genuinely
    independent payload; ISBN-less rows are reported ``unidentified``.
    """
    return _s(row.get("isbn"))[:32]  # magic-number-allow: mirrors library_lander's clip


# ---- staff -----------------------------------------------------------------

def _staff_source_identity(row: dict[str, Any]) -> str:
    from .landers._helpers import derive_external_id

    external_id = _s(
        row.get("staff_external_id") or row.get("external_id") or row.get("employee_id")
    )
    if external_id:
        return external_id
    first = _s(row.get("first_name"))
    last = _s(row.get("last_name"))
    if not (first or last):
        return ""
    return derive_external_id(
        first_name=first,
        last_name=last,
        date_of_birth=row.get("date_of_birth"),
        place_of_birth=row.get("place_of_birth"),
        prefix="auto-staff",
    )


# ---- sections / transport / cafeteria --------------------------------------

def _sections_name(row: dict[str, Any]) -> str:
    code = _s(row.get("section_code") or row.get("code"))
    return _s(row.get("name") or code)


def _transport_name(row: dict[str, Any]) -> str:
    return _s(row.get("route_name") or row.get("name"))[:128]  # magic-number-allow: mirrors transport_lander's clip


def _cafeteria_name(row: dict[str, Any]) -> str:
    return _s(row.get("meal_name") or row.get("name"))[:128]  # magic-number-allow: mirrors cafeteria_lander's clip


def _cafeteria_price(row: dict[str, Any]) -> Any:
    return row.get("price") or row.get("balance")


_CHECKSUM_SPECS: dict[str, ChecksumSpec] = {
    "students": ChecksumSpec(
        domain="students",
        module_path="apps.people.models",
        model_attr="StudentProfile",
        source_identity=_students_source_identity,
        identity_columns=lambda _m: [_student_identity_column()],
        fields={
            "first_name": "first_name",
            "last_name": "last_name",
            "date_of_birth": "date_of_birth",
            "gender": "gender",
            "place_of_birth": "place_of_birth",
            "joined_date": "joined_date",
            "joined_term": "joined_term",
            "section": "section",
            "exam_candidate_number": "exam_candidate_number",
            "exam_center_code": "exam_center_code",
            "exam_system": "exam_system",
        },
        excluded={
            "enrollment_status": "the lander remaps it through map_enrollment_status "
            "onto StudentProfile.status; comparing the raw token would cry divergence "
            "on a healthy import",
            "admission_number": "carries the IDENTITY on deployments whose "
            "StudentProfile has no external_id column, so it is the key here",
            "parent_phone": "the lander conditionally folds a student ``phone`` into "
            "it when the model has no phone column",
            "first_name/last_name (combined-name rows)": "a row carrying only "
            "``full_name`` is split locale-aware by the lander; such rows are reported "
            "``unidentified`` rather than compared against our own split",
            "middle_name/email/phone/grade_level/address": "land as DynamicFieldValue "
            "extras, not model columns, when the tenant model lacks them",
        },
    ),
    "finance": ChecksumSpec(
        domain="finance",
        module_path="apps.finance.models",
        model_attr="Invoice",
        source_identity=_finance_reference,
        identity_columns=_finance_identity_columns,
        fields={
            "total_amount": "amount",
            "due_date": "due_date",
            "issued_date": "issue_date",
            "notes": "description",
        },
        excluded={
            "student": "a resolved FK -- resolve_student falls back to fuzzy name "
            "matching, which we will not re-run",
            "profile": "the tenant's ComplianceProfile is provisioned by the lander, "
            "not carried in the source row",
            "balance_amount/status/invoice_type": "not written from the source row; "
            "they are model defaults or downstream ledger state",
        },
    ),
    "attendance": ChecksumSpec(
        domain="attendance",
        module_path="apps.academics.models",
        model_attr="Attendance",
        source_identity=_attendance_source_identity,
        identity_columns=lambda _m: [_student_identity_column("student__"), "date"],
        fields={"remarks": _attendance_remarks},
        excluded={
            "status": "the lander remaps the raw token through map_attendance_status "
            "against the model's own choices, with a default for anything unmatched",
            "classroom": "resolved per row by _resolve_row_classroom; it participates "
            "in the lander's upsert key, so two classrooms for one (student, date) "
            "are reported ``ambiguous_destination`` rather than silently matched",
            "school": "bound to the bundle's school, not read from the row",
        },
    ),
    "grades": ChecksumSpec(
        domain="grades",
        module_path="apps.evals.models",
        model_attr="Evaluation",
        source_identity=_grades_source_identity,
        id_map_domain="grades",
        fields={c: c for c in _GRADE_COMPONENTS},
        excluded={
            "letter_grade": "a pre_save signal (apps/evals/signals.py) recomputes it "
            "from the component scores through the tenant's grading converter, so the "
            "landed letter is DERIVED and never the source's -- a planted mismatch "
            "proved this, and comparing it would fail every healthy grades import",
            "score (aggregate)": "when a flat source carries one score and no "
            "components the lander lands it in exam_score AND stamps a provenance "
            "remark; that branch is conditional, so exam_score is compared only when "
            "the source names it directly",
            "remarks": "authored by the lander ('imported aggregate score'), not "
            "copied from the source",
            "student/academic_year/term/subject_assignment/teacher": "all resolved "
            "FKs -- the graph resolver matches labels loosely and falls back to the "
            "active year, so the row is addressed through the lander's own id-map",
            "final_score/normalized_value": "computed downstream from the components",
        },
    ),
    "transcripts": ChecksumSpec(
        domain="transcripts",
        module_path="apps.people.models",
        model_attr="TranscriptVaultItem",
        source_identity=_transcripts_source_identity,
        identity_columns=lambda _m: [
            _student_identity_column("student_profile__"),
            "artifact_type",
            "verification_hash",
        ],
        fields={"artifact_ref": _transcripts_artifact_ref, "issued_at": "issued_at"},
        excluded={
            "artifact_type/verification_hash": "both form the row's IDENTITY -- the "
            "hash is the lander's addressing scheme over four raw source values",
            "passport": "resolved through the platform's get-or-create passport "
            "service; not a source value",
            "issuing_school": "provenance FK resolved from the row's source school id "
            "with a fallback to the bundle's school",
        },
    ),
    "guardians": ChecksumSpec(
        domain="guardians",
        module_path="apps.people.models",
        model_attr="StudentGuardian",
        source_identity=_guardians_source_identity,
        identity_columns=lambda _m: [
            _student_identity_column("student__"),
            "email",
            "phone",
        ],
        fields={"whatsapp_number": "whatsapp_number", "address": "address"},
        excluded={
            "guardian_user": "resolved by username, then email, then a phone+name "
            "similarity match above a configurable score -- we will not re-run it, so "
            "the row is addressed by the verbatim email/phone columns instead",
            "relationship": "upper-cased and validated against the model's choices; "
            "anything unrecognised is dropped and the model default GUARDIAN applies",
            "preferred_contact": "same shape -- out-of-vocabulary values fall back to "
            "the model default EMAIL",
            "receives_email/receives_sms/receives_whatsapp/can_view_results/"
            "can_view_finance": "each is written only when the source column is "
            "present and non-empty; otherwise the model default stands",
            "is_primary": "not a StudentGuardian column at all -- the lander's own "
            "field filter drops it, so the source value lands nowhere",
            "first_name/last_name": "guardian names live on the auth User and are "
            "written only when that account is newly provisioned",
        },
    ),
    "events": ChecksumSpec(
        domain="events",
        module_path="apps.school_events.models",
        model_attr="SchoolEvent",
        source_identity=_events_slug,
        identity_columns=lambda _m: ["slug"],
        fields={"title": _events_title, "description": "description"},
        excluded={
            "start_at/end_at": "the lander forces start to 00:00 and end to 23:59 of "
            "the coerced DATE, and defaults a missing end to the start date, so the "
            "source time-of-day is deliberately discarded",
            "status": "never written -- every migrated event lands as the model "
            "default 'draft' regardless of the source",
            "location/category": "SchoolEvent has no such columns; both are folded "
            "into the metadata JSON blob (category defaulting to 'other')",
            "slug": "the row's computed IDENTITY (slugify(title + start date)), not a "
            "payload field",
        },
    ),
    "library": ChecksumSpec(
        domain="library",
        module_path="apps.schoolops.models",
        model_attr="LibraryItem",
        source_identity=_library_source_identity,
        identity_columns=lambda _m: ["isbn"],
        fields={"title": "title", "author": "author"},
        excluded={
            "isbn": "the row's IDENTITY on the shape we verify",
            "title/author (ISBN-less rows)": "without an ISBN the lander upserts on "
            "(school, title[, author]) -- title and author become the KEY, so "
            "comparing them would be circular; such rows are reported ``unidentified``",
            "copies_total": "``coerce_int(...) or 1`` folds a source 0, a blank and an "
            "unparseable value all to 1, so a landed 1 does not evidence the source",
            "item_type": "falls back from category to item_type to the literal 'book'",
            "is_active": "a multi-value source status is folded into a boolean, "
            "discarding the loan state",
        },
    ),
    "cafeteria": ChecksumSpec(
        domain="cafeteria",
        module_path="apps.schoolops.models",
        model_attr="CanteenMeal",
        source_identity=_cafeteria_name,
        identity_columns=lambda _m: ["name"],
        fields={"name": _cafeteria_name, "price": _cafeteria_price},
        excluded={
            "is_active": "hardcoded True by the lander, never read from the source",
            "school": "bound to the bundle's school, not read from the row",
        },
    ),
    # --- PRESENCE-only specs -------------------------------------------------
    # These four have a stable identity but no payload column the lander copies
    # verbatim ALONGSIDE it, so the digest covers the identity alone. That still
    # proves something a row count cannot -- that THIS source record reached the
    # tenant under its own key, and that 100 source rows did not land as 50
    # duplicates of one -- but it is NOT value verification, and the report labels
    # it ``presence`` so it can never be read as one.
    "academics": ChecksumSpec(
        domain="academics",
        module_path="apps.academics.models",
        model_attr="Subject",
        source_identity=_academics_name,
        identity_columns=lambda _m: ["name"],
        fields={"name": _academics_name},
        excluded={
            "credits": "create-only in get_or_create_named (an existing Subject is "
            "never mutated), so a re-import legitimately leaves it unchanged",
            "code/category": "not written from the source row by academics_lander",
        },
    ),
    "staff": ChecksumSpec(
        domain="staff",
        module_path="apps.people.models",
        model_attr="TeacherProfile",
        source_identity=_staff_source_identity,
        identity_columns=lambda _m: ["staff_id"],
        fields={"staff_id": _staff_source_identity},
        excluded={
            "position_title": "read through an ontology-synonym lookup that may take "
            "the value from a different column, then truncated to 120",
            "phone": "same synonym lookup, truncated to 50",
            "department": "the source department NAME is resolved or provisioned with "
            "a MINTED code; the source's own code is never reused",
            "user/first_name/last_name/email": "the auth account is resolved across "
            "three rungs (staff_id dedup, username, email) or newly provisioned, and "
            "an existing user is never mutated",
            "role": "mapped through staff_role_map onto a User.Role enum, and written "
            "only when the account still has an unusable password",
        },
    ),
    "sections": ChecksumSpec(
        domain="sections",
        module_path="apps.academics.models",
        model_attr="Classroom",
        source_identity=_sections_name,
        identity_columns=lambda _m: ["name"],
        fields={"name": _sections_name},
        excluded={
            "code": "a fresh target-scoped code is minted (CLS<school-token>-<SLUG>); "
            "the source's section_code is deliberately never reused because the column "
            "is uniqueness-constrained per school",
            "academic_year": "resolved to the school's active year, then any newest "
            "year, then a provisioned year literally named 'Imported' with placeholder "
            "dates",
            "department": "resolved or provisioned, defaulting to the literal 'General'",
            "EVERY column (re-import)": "sections_lander has no update path at all -- "
            "an existing (school, name) classroom is left entirely untouched, so no "
            "payload column can be attributed to this bundle",
        },
    ),
    "transport": ChecksumSpec(
        domain="transport",
        module_path="apps.schoolops.models",
        model_attr="Route",
        source_identity=_transport_name,
        identity_columns=lambda _m: ["name"],
        fields={"name": _transport_name},
        excluded={
            "is_active": "hardcoded True by the lander, never read from the source",
            "stops": "route stops are landed by transport_assignments, not here; the "
            "route row itself carries only its name",
        },
    ),
}


#: Domains Pass 1 can count but Pass 2 deliberately does NOT checksum, and why.
#: Named here rather than left as an absence: a domain missing from both lists would
#: look verified to anyone reading only the specs.
_CHECKSUM_UNVERIFIABLE: dict[str, str] = {
    "behavior": "the lander's identity includes incident_type, which is an enum remap "
    "folding every unmapped token to OTHER, plus a 500-char clip of description; the "
    "only column a re-import can actually change is severity, itself a remap that "
    "folds unknown values to MEDIUM. Nothing is left to compare that we did not derive.",
    "health": "HealthRecord has no verbatim column at all -- record_type is a "
    "lower-cased 32-char clip and notes is a composite the lander builds from four "
    "source fields; both are in the upsert key, so verifying it would mean rebuilding "
    "the lander's string formatting and comparing it to itself.",
    "communications": "the identity (recipient, subject) is stable but NOT 1:1 with a "
    "source message -- every message to one recipient sharing a subject collapses onto "
    "one row, and subject-less messages all collapse together, so a matched row cannot "
    "be attributed to a specific source record.",
    "structure": "SubjectAssignment is addressed by five resolved FKs (year, term, "
    "classroom, specialty, subject), each a get-or-create on a name with its own "
    "fallbacks; and its one payload column, coefficient, is create-only, so a "
    "re-import legitimately leaves it stale.",
    "hostel": "HostelRoom is keyed by its parent Hostel, which the lander provisions "
    "per row, so the identity depends on a lander-side get-or-create rather than on "
    "source data.",
    "athletics_teams": "the upsert key includes a resolved Season FK, and level / "
    "gender / status are enum remaps, so neither the identity nor any payload column "
    "is a verbatim source value.",
    "athletics_memberships": "identity is a pair of resolved FKs (team, student) with "
    "no verbatim payload column.",
    "athletics_fixtures": "identity depends on resolved Team / Season / venue FKs and "
    "the payload is scheduling state the lander computes.",
    "hostel_assignments": "identity is a pair of resolved FKs (student, room) with no "
    "verbatim payload column.",
    "transport_assignments": "identity is a pair of resolved FKs (student, route) with "
    "no verbatim payload column.",
    "cafeteria_assignments": "identity is a pair of resolved FKs (student, meal_plan) "
    "and the payload is lander-computed -- last_topup_at is set to timezone.now() on "
    "the top-up branch, so it can never equal a source value.",
}


def domains_with_checksum_verification() -> set[str]:
    """Domains Pass 2 can compare record-by-record. (For tests/UI/report.)"""
    return set(_CHECKSUM_SPECS)


def checksum_spec_exclusions() -> dict[str, dict[str, str]]:
    """Per domain, the fields Pass 2 deliberately does not compare, and why."""
    return {domain: dict(spec.excluded) for domain, spec in _CHECKSUM_SPECS.items()}


def checksum_unverifiable_domains() -> dict[str, str]:
    """Domains Pass 1 counts but Pass 2 will not checksum, each with its reason."""
    return dict(_CHECKSUM_UNVERIFIABLE)


def spec_verification_depth(spec: ChecksumSpec) -> str:
    """``value`` when the spec compares a column that is NOT part of its identity.

    A spec whose only compared column IS its identity is circular: the row was found
    BY that value, so the digest can never disagree. That is still a real PRESENCE
    check -- it proves this source record reached the tenant under its own key, which
    a row count cannot -- but calling it value verification would be a lie, so the two
    are named apart everywhere they are reported.
    """
    if spec.id_map_domain:
        return "value" if spec.fields else "presence"
    try:
        module = importlib.import_module(spec.module_path)
        model = getattr(module, spec.model_attr)
        identity = set(spec.identity_columns(model)) if spec.identity_columns else set()
    except (ImportError, AttributeError):  # model unavailable: judge on names alone
        identity = set()
    return "value" if (set(spec.fields) - identity) else "presence"


def checksum_coverage() -> dict[str, Any]:
    """The verified / unverified split across every domain Pass 1 knows about.

    Exposed so the split is a queryable fact rather than a claim in a report: a domain
    that gains a count check but no checksum spec shows up here immediately, and the
    value/presence distinction is carried rather than flattened.
    """
    countable = set(_DOMAIN_MODELS)
    depths = {d: spec_verification_depth(s) for d, s in _CHECKSUM_SPECS.items()}
    value = sorted(d for d, k in depths.items() if k == "value")
    presence = sorted(d for d, k in depths.items() if k == "presence")
    unverified = sorted(countable - set(_CHECKSUM_SPECS))
    return {
        "count_verified_domains": sorted(countable),
        "value_verified_domains": value,
        "presence_verified_domains": presence,
        "checksum_unverified_domains": unverified,
        "unverifiable_reasons": dict(_CHECKSUM_UNVERIFIABLE),
        "count_verified": len(countable),
        "value_verified": len(value),
        "presence_verified": len(presence),
        "checksum_unverified": len(unverified),
    }


@dataclass
class RecordDivergence:
    """One record that failed Pass 2 -- named, with values, not merely tallied."""

    domain: str
    identity: str
    kind: str  # "digest_mismatch" | "missing_in_destination"
    source_digest: str = ""
    landed_digest: str = ""
    #: field -> [source value, landed value] for the fields that actually differ
    field_diffs: dict[str, list[str]] = dc_field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "identity": self.identity,
            "kind": self.kind,
            "source_digest": self.source_digest,
            "landed_digest": self.landed_digest,
            "field_diffs": self.field_diffs,
        }


@dataclass
class DomainChecksumResult:
    """Pass 2 outcome for one domain. Every source record lands in ONE named bucket."""

    domain: str
    strategy: str = "natural"  # "natural" | "id_map"
    #: "value" when a column outside the identity was compared; "presence"
    #: when the digest covers the identity alone (the row reached the tenant
    #: under its own key, but no independent value was proved).
    depth: str = "value"
    source_records: int = 0
    matched: int = 0
    divergent: int = 0
    missing_in_destination: int = 0
    unidentified: int = 0
    #: id-map strategy only: the lander recorded no pointer for this source row. The
    #: id-map write is best-effort, so this is NOT proof the row is absent -- but it
    #: is equally NOT a match, so it can never be read as success.
    unresolved_identity: int = 0
    #: two or more landed rows share this record's identity; we refuse to pick one
    ambiguous_destination: int = 0
    skipped_over_cap: int = 0
    #: canonical fields this DEPLOYMENT could compare (spec fields that exist as
    #: real columns here). Per RECORD only the subset the source actually asserted
    #: is hashed, so this is the candidate set, not a per-row count.
    comparable_fields: list[str] = dc_field(default_factory=list)
    divergences: list[RecordDivergence] = dc_field(default_factory=list)
    #: set when the source bytes could not be re-read (purged / never captured)
    source_error: str = ""

    @property
    def bucketed(self) -> int:
        return (
            self.matched
            + self.divergent
            + self.missing_in_destination
            + self.unidentified
            + self.unresolved_identity
            + self.ambiguous_destination
            + self.skipped_over_cap
        )

    @property
    def tally_closes(self) -> bool:
        """Every source record is accounted for under a NAMED bucket.

        Printing SOME buckets is worse than printing none -- a refusal and a healthy
        row would wear the same shape. The verdict asserts this and fails loudly if
        it ever stops holding, rather than quietly reporting a subset.
        """
        return self.bucketed == self.source_records

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "strategy": self.strategy,
            "depth": self.depth,
            "source_records": self.source_records,
            "matched": self.matched,
            "divergent": self.divergent,
            "missing_in_destination": self.missing_in_destination,
            "unidentified": self.unidentified,
            "unresolved_identity": self.unresolved_identity,
            "ambiguous_destination": self.ambiguous_destination,
            "skipped_over_cap": self.skipped_over_cap,
            "bucketed_total": self.bucketed,
            "tally_closes": self.tally_closes,
            "comparable_fields": list(self.comparable_fields),
            "source_error": self.source_error,
            "divergences": [d.as_dict() for d in self.divergences],
        }


@dataclass
class BundleChecksumReport:
    """Pass 2 verdict for a whole bundle."""

    bundle_id: int
    generated_at: str
    algorithm: str = CHECKSUM_ALGORITHM
    per_domain: list[DomainChecksumResult] = dc_field(default_factory=list)
    #: domains present in the bundle that Pass 2 cannot compare, named
    unverifiable_domains: list[str] = dc_field(default_factory=list)
    notes: list[str] = dc_field(default_factory=list)

    @property
    def total_source_records(self) -> int:
        return sum(d.source_records for d in self.per_domain)

    @property
    def total_matched(self) -> int:
        return sum(d.matched for d in self.per_domain)

    @property
    def total_value_matched(self) -> int:
        """Records whose VALUES were proved, not merely their presence."""
        return sum(d.matched for d in self.per_domain if d.depth == "value")

    @property
    def total_presence_matched(self) -> int:
        return sum(d.matched for d in self.per_domain if d.depth == "presence")

    @property
    def total_divergent(self) -> int:
        return sum(d.divergent for d in self.per_domain)

    @property
    def total_missing(self) -> int:
        return sum(d.missing_in_destination for d in self.per_domain)

    @property
    def complete(self) -> bool:
        """True when Pass 2 examined everything it set out to examine.

        ``ok and complete`` is the only combination that means "proven". ``ok`` alone
        can be true over a very small slice of the bundle.
        """
        return not self.unverifiable_domains and all(
            d.tally_closes
            and not d.source_error
            and not d.skipped_over_cap
            and not d.unresolved_identity
            and not d.ambiguous_destination
            for d in self.per_domain
        )

    @property
    def ok(self) -> bool:
        """The integrity verdict. False means the migration must NOT be sealed.

        Note the last clause. A domain that read source records and matched NOTHING
        is a FAILURE even with zero divergences -- that is exactly the shape of an
        artifact whose every row was dismissed: an APPLIED bundle, an empty queue,
        and no landed data. ``quarantined >= row_count`` proves nothing landed, and
        neither does a divergence count of zero taken over zero comparisons.
        """
        if self.total_divergent or self.total_missing:
            return False
        for d in self.per_domain:
            if not d.tally_closes:
                return False
            if d.source_records > 0 and d.matched == 0:
                return False
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "generated_at": self.generated_at,
            "algorithm": self.algorithm,
            "ok": self.ok,
            "complete": self.complete,
            "total_source_records": self.total_source_records,
            "total_matched": self.total_matched,
            "total_value_matched": self.total_value_matched,
            "total_presence_matched": self.total_presence_matched,
            "total_divergent": self.total_divergent,
            "total_missing_in_destination": self.total_missing,
            "per_domain": [d.as_dict() for d in self.per_domain],
            "unverifiable_domains": list(self.unverifiable_domains),
            "notes": list(self.notes),
        }


def _school_scope_kwargs(model: Any, school: Any) -> dict[str, Any]:
    """Field-aware school filter, mirroring :func:`_school_scoped_count`.

    Under RLS (one shared schema) an unscoped read sees EVERY school's rows, so
    another tenant's row could satisfy a lookup and a wrong-school write would verify
    clean. Scope explicitly wherever the model gives us a path.
    """
    field_names = {f.name for f in model._meta.get_fields()}
    if "school" in field_names:
        return {"school": school}
    if "issuing_school" in field_names:
        return {"issuing_school": school}
    if "student" in field_names:
        return {"student__school": school}
    if "student_profile" in field_names:
        return {"student_profile__school": school}
    if "hostel" in field_names:
        return {"hostel__school": school}
    return {}


def _coerce_like_column(model: Any, model_field_name: str, value: Any) -> Any:
    """Put a SOURCE value into the shape the destination COLUMN stores it in.

    Without this the comparison would be about representation, not value: the source
    canonical row carries ``"2010-05-03"`` while the column hands back
    ``date(2010, 5, 3)``, and every healthy date row would read as a divergence.
    Running the source value through the destination field's own ``to_python`` makes
    the two comparable while keeping the comparison honest -- a genuinely WRONG date,
    or a rounded decimal, still lands on a different digest, because ``to_python``
    converts, it does not repair.

    When ``to_python`` refuses a value the LANDER would have accepted (its
    ``coerce_date`` / ``coerce_decimal`` / ``coerce_int`` are more forgiving than
    Django's field parsing), fall back to the lander's OWN helper rather than to the
    raw string. Using the identical helper is not re-implementing it, and it stops a
    messy-but-valid source value from being reported as a divergence it is not.

    Deliberately NOT applied to text columns: ``CharField.to_python`` only coerces to
    ``str``, and applying it would gain nothing while risking hiding a truncation.
    Text is compared exactly as stored.
    """
    try:
        field = model._meta.get_field(model_field_name)
    except FieldDoesNotExist:  # field absent on this deploy
        return value
    internal = field.get_internal_type()
    if internal in ("CharField", "TextField", "SlugField", "EmailField"):
        return value
    try:
        return field.to_python(value)
    except (ValidationError, ValueError, TypeError, ArithmeticError):  # fall through to the lander's own coercion
        pass
    try:
        from .landers._helpers import coerce_date, coerce_decimal, coerce_int

        if internal in ("DateField", "DateTimeField"):
            return coerce_date(value)
        if internal == "DecimalField":
            return coerce_decimal(value)
        if internal in ("IntegerField", "PositiveIntegerField", "SmallIntegerField", "BigIntegerField"):
            return coerce_int(value)
    except (ValueError, TypeError, ArithmeticError):  # an uncoercible source value IS a divergence
        pass
    return value


def _source_value(getter: Any, row: dict[str, Any]) -> Any:
    """Read one field's SOURCE value: a canonical field name, or a callable(row).

    The callable form exists for the handful of columns whose source is a fallback
    chain the lander itself applies (``notes`` before ``remarks``) or a clip to the
    column width the lander itself performs -- mirroring those keeps the lander's own
    behaviour from being misread as a database defect. It is never used to re-derive
    a value the lander computed.
    """
    if callable(getter):
        return getter(row)
    return row.get(getter)


def _load_landed_natural(
    *, model: Any, school: Any, identity_columns: list[str], value_columns: list[str]
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Index the tenant's rows by their NATURAL identity. Returns (index, ambiguous).

    One query, following FKs where the identity needs them. A key appearing twice is
    recorded as ambiguous rather than last-write-wins: silently picking one row would
    let a duplicate-landing defect verify clean.
    """
    wanted = list(dict.fromkeys(identity_columns + value_columns))
    qs = model.objects.filter(  # tenant-isolation-allow: _school_scope_kwargs applies the model's own school path; schema_context isolates the tenant
        **_school_scope_kwargs(model, school)
    )
    index: dict[str, dict[str, Any]] = {}
    ambiguous: set[str] = set()
    for row in qs.values(*wanted):
        key = _identity_key([row.get(c) for c in identity_columns])
        if key in index:
            ambiguous.add(key)
            continue
        index[key] = row
    return index, ambiguous


def _load_landed_id_map(
    *, model: Any, school: Any, bundle: Any, id_map_domain: str, value_columns: list[str]
) -> dict[str, dict[str, Any]]:
    """Index the tenant's rows by the legacy id the LANDER recorded for them.

    Used only where the destination row is addressable solely through resolved
    foreign keys. The pointer comes from the apply; the VALUES still come from a
    fresh read of the database, so a value divergence is caught exactly as it is
    under the natural strategy.
    """
    from .models import MigrationIdMapping

    canonical_model = f"{model.__module__}.{model.__name__}"
    pk_by_legacy: dict[str, str] = {}
    mappings = MigrationIdMapping.objects.filter(  # tenant-isolation-allow: scoped by school_id AND the bundle's own pk
        school_id=getattr(school, "pk", None),
        domain=id_map_domain,
        canonical_model=canonical_model,
    ).values("legacy_id", "canonical_pk")
    for entry in mappings:
        pk = str(entry.get("canonical_pk") or "").strip()
        if pk:
            pk_by_legacy[str(entry.get("legacy_id") or "")] = pk

    if not pk_by_legacy:
        return {}

    rows_by_pk: dict[str, dict[str, Any]] = {}
    qs = model.objects.filter(  # tenant-isolation-allow: pk set derives from MigrationIdMapping rows already scoped to this school
        pk__in=list(pk_by_legacy.values())
    )
    for row in qs.values("pk", *value_columns):
        rows_by_pk[str(row.get("pk"))] = row

    index: dict[str, dict[str, Any]] = {}
    for legacy_id, pk in pk_by_legacy.items():
        landed = rows_by_pk.get(pk)
        # A recorded pointer whose row is GONE is a real absence, so keep the entry
        # and let the caller bucket it as missing rather than as never-mapped.
        index[legacy_id] = landed if landed is not None else {}
    return index


def _checksum_one_domain(
    *,
    spec: ChecksumSpec,
    school: Any,
    bundle: Any,
    source_rows: "Iterable[dict[str, Any]]",
    run_under_schema: "Callable[[Callable[[], Any]], Any]",
    max_records: int | None,
    max_divergences_recorded: int,
) -> DomainChecksumResult:
    use_id_map = bool(spec.id_map_domain)
    result = DomainChecksumResult(
        domain=spec.domain,
        strategy="id_map" if use_id_map else "natural",
        depth=spec_verification_depth(spec),
    )

    module = importlib.import_module(spec.module_path)
    model = getattr(module, spec.model_attr)
    model_fields = {f.name for f in model._meta.get_fields()}

    # Which fields we can actually compare on THIS deployment: declared in the spec
    # AND present as a real column on the tenant's model.
    pairs = sorted(
        (column, getter)
        for column, getter in spec.fields.items()
        if column in model_fields
    )  # field-ORDERED digest: fixed order, independent of dict construction order
    result.comparable_fields = [c for c, _ in pairs]
    value_columns = [c for c, _ in pairs]

    identity_columns: list[str] = []
    ambiguous_keys: set[str] = set()

    def _load() -> Any:
        if use_id_map:
            return _load_landed_id_map(
                model=model,
                school=school,
                bundle=bundle,
                id_map_domain=spec.id_map_domain,
                value_columns=value_columns,
            ), set()
        cols = list(spec.identity_columns(model)) if spec.identity_columns else []
        return (
            *_load_landed_natural(
                model=model,
                school=school,
                identity_columns=cols,
                value_columns=value_columns,
            ),
        ), cols

    loaded = run_under_schema(_load)
    if use_id_map:
        landed_by_identity, ambiguous_keys = loaded
    else:
        (landed_by_identity, ambiguous_keys), identity_columns = loaded

    for source_row in source_rows:
        result.source_records += 1
        if max_records is not None and result.source_records > max_records:
            result.skipped_over_cap += 1
            continue

        raw_identity = spec.source_identity(source_row)
        identity_key = _identity_key(raw_identity)
        if not raw_identity or not identity_key.strip(_IDENTITY_SEP).strip():
            result.unidentified += 1
            continue

        display_identity = (
            _IDENTITY_SEP.join(str(p) for p in raw_identity)
            if isinstance(raw_identity, (list, tuple))
            else str(raw_identity)
        ).replace(_IDENTITY_SEP, " | ")

        if identity_key in ambiguous_keys:
            result.ambiguous_destination += 1
            continue

        landed_row = landed_by_identity.get(identity_key)
        if landed_row is None:
            if use_id_map:
                # The lander left no pointer. Its id-map write is best-effort, so we
                # cannot call this absence -- but it is not a match either.
                result.unresolved_identity += 1
            else:
                result.missing_in_destination += 1
                if len(result.divergences) < max_divergences_recorded:
                    result.divergences.append(
                        RecordDivergence(
                            domain=spec.domain,
                            identity=display_identity,
                            kind="missing_in_destination",
                        )
                    )
            continue
        if not landed_row:
            # id-map pointed at a row that is no longer there: a real absence.
            result.missing_in_destination += 1
            if len(result.divergences) < max_divergences_recorded:
                result.divergences.append(
                    RecordDivergence(
                        domain=spec.domain,
                        identity=display_identity,
                        kind="missing_in_destination",
                    )
                )
            continue

        # Compare ONLY the fields the source actually asserted. Landers upsert and
        # skip empty values, so a blank source field legitimately leaves the stored
        # value alone; hashing it would manufacture divergences on every re-import.
        source_side: dict[str, Any] = {}
        landed_side: dict[str, Any] = {}
        compared: list[str] = []
        for column, getter in pairs:
            raw_source = _source_value(getter, source_row)
            if raw_source is None or str(raw_source).strip() == "":
                continue
            compared.append(column)
            source_side[column] = _coerce_like_column(model, column, raw_source)
            landed_side[column] = landed_row.get(column)

        if not compared:
            # The source asserted nothing comparable for this record. Locating it is
            # still a real result (the row exists under its identity), but calling it
            # "matched" would inflate the proof, so it is bucketed honestly.
            result.unresolved_identity += 1
            continue

        source_hash = record_digest(source_side, compared)
        landed_hash = record_digest(landed_side, compared)
        if source_hash == landed_hash:
            result.matched += 1
            continue

        result.divergent += 1
        if len(result.divergences) < max_divergences_recorded:
            diffs: dict[str, list[str]] = {}
            for column in compared:
                s_val = normalise_for_digest(source_side.get(column))
                l_val = normalise_for_digest(landed_side.get(column))
                if s_val != l_val:
                    diffs[column] = [s_val, l_val]
            result.divergences.append(
                RecordDivergence(
                    domain=spec.domain,
                    identity=display_identity,
                    kind="digest_mismatch",
                    source_digest=source_hash,
                    landed_digest=landed_hash,
                    field_diffs=diffs,
                )
            )
    return result


def _source_rows_by_domain(bundle: Any) -> dict[str, Any]:
    """Re-parse the bundle's SOURCE artifacts into canonical rows, per domain.

    Reuses the orchestrator's own reader so the source side is the same bytes,
    mapping and transform chain the apply consumed -- read AGAIN, from the encrypted
    blob, not carried over in memory. A domain whose bytes are gone (retention purge,
    never captured) is reported through the ``__error__`` channel so it shows up as
    unverified rather than as a silently empty (and therefore clean-looking) domain.
    """
    from .orchestrator import _build_jobs, _iter_canonical_rows

    rows_by_domain: dict[str, Any] = {}
    errors_by_domain: dict[str, str] = {}
    for job in _build_jobs(bundle):
        domain = getattr(job, "domain", "") or ""
        if domain not in _CHECKSUM_SPECS:
            continue
        try:
            rows_by_domain.setdefault(domain, []).extend(_iter_canonical_rows(job))
        except _SOURCE_READ_ERRORS as exc:  # unreadable source is a REPORTED state
            errors_by_domain[domain] = f"{type(exc).__name__}: {exc}"
    if errors_by_domain:
        rows_by_domain["__error__"] = errors_by_domain
    return rows_by_domain


def verify_bundle_checksums(
    bundle: Any,
    *,
    domains: list[str] | None = None,
    max_records_per_domain: int | None = None,
    max_divergences_recorded: int = 200,  # magic-number-allow: divergence enumeration cap
) -> BundleChecksumReport:
    """PASS 2 — compare SOURCE and LANDED records by SHA-256, and name every divergence.

    Returns a :class:`BundleChecksumReport`. ``report.ok`` is the verdict: ``False``
    means at least one record does not match, or is not in the destination at all, or
    a domain read source records and matched none of them. Callers MUST treat a false
    ``ok`` as a migration failure -- ``reconciliation.reconcile_bundle`` blocks the
    APPLIED -> RECONCILED seal on it (which also keeps the encrypted source blobs, so
    the evidence survives for the repair), and the ``verify_migration_checksums``
    management command exits non-zero.

    Never raises: an infrastructure failure becomes a note plus a false ``complete``,
    so a verifier that could not run is never mistaken for one that ran clean.
    """
    from django.utils import timezone

    report = BundleChecksumReport(
        bundle_id=int(getattr(bundle, "pk", 0) or 0),
        generated_at=timezone.now().isoformat(),
    )
    school = getattr(bundle, "school", None)
    if school is None:
        report.notes.append(
            "Bundle has no target school — Pass 2 cannot scope a destination read; "
            "nothing was verified."
        )
        report.unverifiable_domains.append("*")
        return report

    schema_name = getattr(bundle, "schema_name", "") or ""

    # MigrationBundle lives in SHARED_APPS (the PUBLIC schema); StudentProfile,
    # Invoice, Evaluation and the rest live in TENANT_APPS (a per-tenant schema). So
    # the destination read MUST be entered into the tenant schema explicitly. A blank
    # ``schema_name`` on a real schema-per-tenant connection means it would instead
    # run wherever the connection already is — public, which holds STALE copies of
    # those tenant tables. Comparing the source against the wrong table yields either
    # invented divergences or a false clean, and the false clean is the one that
    # purges the source blobs. Refuse.
    if not schema_name:
        try:
            from django.db import connection as _conn

            _schema_per_tenant = hasattr(_conn, "set_schema")
        except ImportError:  # django.db unavailable: treat as single-schema
            _schema_per_tenant = False
        if _schema_per_tenant:
            report.notes.append(
                "Bundle has no schema_name on a schema-per-tenant connection — the "
                "landed-row read would fall through to the PUBLIC schema, which holds "
                "stale copies of the tenant tables. Nothing was verified."
            )
            report.unverifiable_domains.append("*")
            return report

    def _run_under_schema(fn: "Callable[[], Any]") -> Any:
        if not schema_name:
            return fn()
        try:
            from django_tenants.utils import schema_context
        except ImportError:
            return fn()
        from django.db import connection

        if not hasattr(connection, "set_schema"):
            # Single-schema backend (the sqlite dev/test lane, or an RLS deploy):
            # there is no schema to enter and schema_context would raise. Mirrors the
            # guard in verify_landed_counts / orchestrator._land_under_schema.
            return fn()
        with schema_context(schema_name):
            return fn()

    try:
        rows_by_domain = _source_rows_by_domain(bundle)
    except _SOURCE_READ_ERRORS as exc:
        logger.warning(
            "migration_cloud.checksum: source re-read failed for bundle=%s",
            getattr(bundle, "pk", None),
            exc_info=True,
        )
        report.notes.append(
            f"Pass 2 could not re-read the bundle's source artifacts "
            f"({type(exc).__name__}); nothing was verified."
        )
        report.unverifiable_domains.append("*")
        return report

    source_errors: dict[str, str] = rows_by_domain.pop("__error__", {})

    # Name every domain the bundle carries that Pass 2 CANNOT compare. Silence here
    # would let a report covering four domains read as a whole-bundle clearance.
    try:
        per_artifact_domain = (
            getattr(bundle, "discovery_summary", None) or {}
        ).get("per_artifact_domain") or {}
        present = {(entry or {}).get("domain", "") for entry in per_artifact_domain.values()}
        report.unverifiable_domains = sorted(
            d for d in present if d and d not in _CHECKSUM_SPECS
        )
    except (AttributeError, TypeError, LookupError):  # best effort; never breaks the verdict
        pass

    wanted = set(domains) if domains else None
    for domain, spec in sorted(_CHECKSUM_SPECS.items()):
        if wanted is not None and domain not in wanted:
            continue
        if domain in source_errors:
            report.per_domain.append(
                DomainChecksumResult(domain=domain, source_error=source_errors[domain])
            )
            report.notes.append(
                f"{domain}: the source artifact could not be re-read "
                f"({source_errors[domain]}) — Pass 2 did not run for this domain."
            )
            continue
        rows = rows_by_domain.get(domain)
        if not rows:
            continue
        try:
            report.per_domain.append(
                _checksum_one_domain(
                    spec=spec,
                    school=school,
                    bundle=bundle,
                    source_rows=rows,
                    run_under_schema=_run_under_schema,
                    max_records=max_records_per_domain,
                    max_divergences_recorded=max_divergences_recorded,
                )
            )
        except _SOURCE_READ_ERRORS as exc:
            logger.warning(
                "migration_cloud.checksum: domain=%s failed", domain, exc_info=True
            )
            report.per_domain.append(
                DomainChecksumResult(
                    domain=domain, source_error=f"{type(exc).__name__}: {exc}"
                )
            )
            report.notes.append(
                f"{domain}: Pass 2 errored ({type(exc).__name__}) — treat as unverified."
            )
    return report
