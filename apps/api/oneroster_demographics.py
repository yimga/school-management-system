"""v4.00.59 — OneRoster v1.2 Demographics endpoints (read-only).
v4.00.60 — Demographics POST/PUT write coverage.

Surfaces the OneRoster ``Demographic`` resource as a projection over
``apps.people.models.StudentProfile`` data. Sparse projection — only the
fields we actually hold (sex / birthDate) are populated; the rest of the
v1.2 spec fields are emitted as empty strings per the optional-field
contract.

Endpoints (mounted under ``/api/roster/v1p2/``):

* ``GET  demographics/`` — paginated list
* ``GET  demographics/<sourcedId>/`` — single record
* ``GET  students/<sourcedId>/demographics/`` — projection for one student
* ``POST demographics/put/`` — create/upsert a Demographic (Idempotency-Key)
* ``PUT  demographics/<sourcedId>/`` — update an existing Demographic by demo-<pk>

Writes are persisted on StudentProfile for the fields we model
(``gender``, ``date_of_birth``, ``place_of_birth``). The optional v1.2
race/ethnicity/citizenship fields are accepted-and-stored in an in-process
override ring (cap 500) so subsequent reads echo what the caller wrote
(matches the optional-field contract — caller-supplied data round-trips).

All endpoints are bearer-gated via the existing ``apps.api.oneroster._gate``
contract. NEVER raises — model unavailability returns 503; missing rows
return 404.
"""
from __future__ import annotations

import json as _json
import logging
import re
from typing import Any, Iterable

from django.core.cache import cache
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.api.oneroster import _envelope, _gate, _paginate

logger = logging.getLogger(__name__)


_GENDER_TO_SEX = {
    "MALE": "male",
    "FEMALE": "female",
    "NON_BINARY": "other",
    "OTHER": "other",
    "PREFER_NOT_TO_SAY": "",
}

# Inverse map for write-path: OneRoster `sex` → StudentProfile.Gender choice.
_SEX_TO_GENDER = {
    "male": "MALE",
    "female": "FEMALE",
    "other": "OTHER",
}

# v4.00.60 — In-process override ring for optional v1.2 fields that have no
# backing column on StudentProfile (race / ethnicity / citizenship / etc).
# Keyed by ``demo-<pk>``. Cap 500; eviction is oldest-first.
_DEMOGRAPHIC_OVERRIDES: dict[str, dict[str, str]] = {}
_DEMOGRAPHIC_OVERRIDES_CAP = 500
_DEMOGRAPHIC_OVERRIDE_FIELDS = (
    "americanIndianOrAlaskaNative",
    "asian",
    "blackOrAfricanAmerican",
    "nativeHawaiianOrOtherPacificIslander",
    "white",
    "demographicRaceTwoOrMoreRaces",
    "hispanicOrLatinoEthnicity",
    "countryOfBirthCode",
    "stateOfBirthAbbreviation",
    "publicSchoolResidenceStatus",
)


def _set_demographic_overrides(sid: str, payload: dict[str, Any]) -> None:
    """Store optional v1.2 fields the caller supplied. NEVER raises."""
    try:
        kept: dict[str, str] = {}
        for k in _DEMOGRAPHIC_OVERRIDE_FIELDS:
            if k in payload:
                kept[k] = str(payload.get(k) or "")[:64]
        if kept:
            _DEMOGRAPHIC_OVERRIDES[sid] = kept
            if len(_DEMOGRAPHIC_OVERRIDES) > _DEMOGRAPHIC_OVERRIDES_CAP:
                # oldest-first eviction
                first = next(iter(_DEMOGRAPHIC_OVERRIDES))
                _DEMOGRAPHIC_OVERRIDES.pop(first, None)
    except Exception as exc:  # noqa: BLE001
        logger.debug("demographic overrides set failed: %s", exc)


def _idempotency_key(request: HttpRequest) -> str:
    return (
        request.META.get("HTTP_IDEMPOTENCY_KEY", "").strip()
        or request.META.get("HTTP_X_IDEMPOTENCY_KEY", "").strip()
    )


_IDEMPOTENCY_TTL = 60 * 60 * 24


def _idem_cache_key(sourced_id: str, idem: str) -> str:
    return f"roster:demographics:idempo:{sourced_id}:{idem}"


def _hash_payload(method: str, path: str, body_bytes: bytes) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(method.encode("ascii"))
    h.update(b"|")
    h.update(path.encode("utf-8", errors="replace"))
    h.update(b"|")
    h.update(body_bytes)
    return h.hexdigest()


def _demographic_from_student(s) -> dict[str, Any]:
    """Project a StudentProfile row into a OneRoster Demographic dict.

    Sparse fields per the v1.2 contract: missing data emits an empty
    string rather than null so JSON consumers don't need null-checks.
    """
    birth_date = ""
    if getattr(s, "date_of_birth", None) is not None:
        try:
            birth_date = s.date_of_birth.isoformat()
        except Exception:  # noqa: BLE001
            birth_date = ""
    sex = _GENDER_TO_SEX.get((getattr(s, "gender", "") or "").upper(), "")
    date_last_modified = ""
    upd = getattr(s, "updated_at", None) or getattr(s, "modified_at", None)
    if upd is not None:
        try:
            date_last_modified = upd.isoformat()
        except Exception:  # noqa: BLE001
            date_last_modified = ""
    sid = f"demo-{s.pk}"
    # v4.00.61 — OneRoster v1.2 spec Appendix link field. Each Demographic
    # records the User sourcedIds it applies to. Our projection is 1:1
    # (one Demographic ← one StudentProfile ← one User), so the array
    # carries a single User.pk string. Empty when the StudentProfile
    # has no linked user (rare — orphaned profile rows).
    user_sourced_ids: list[str] = []
    user_id = getattr(s, "user_id", None)
    if user_id:
        user_sourced_ids.append(str(user_id))
    # v4.00.62 — non-spec auxiliary fields surfaced for ?orgSourcedId= +
    # ?role= filters. Underscore-prefixed so OneRoster spec consumers can
    # ignore them, but still present in the JSON so filtering is testable.
    org_sid = ""
    school_id = getattr(s, "school_id", None)
    if school_id:
        org_sid = str(school_id)
    # StudentProfile is always role=student per OneRoster v1.2 vocabulary.
    role = "student"
    rec = {
        "sourcedId": sid,
        "status": "active",
        "dateLastModified": date_last_modified,
        "birthDate": birth_date,
        "sex": sex,
        "americanIndianOrAlaskaNative": "",
        "asian": "",
        "blackOrAfricanAmerican": "",
        "nativeHawaiianOrOtherPacificIslander": "",
        "white": "",
        "demographicRaceTwoOrMoreRaces": "",
        "hispanicOrLatinoEthnicity": "",
        "countryOfBirthCode": "",
        "stateOfBirthAbbreviation": "",
        "cityOfBirth": (getattr(s, "place_of_birth", "") or ""),
        "publicSchoolResidenceStatus": "",
        # v4.00.61 spec link field — GUIDRef array per IMS OneRoster v1.2.
        "userSourcedIds": user_sourced_ids,
        # v4.00.62 auxiliary filter fields (non-spec, underscore-prefixed).
        "_orgSourcedId": org_sid,
        "_role": role,
    }
    # v4.00.60 — fold in any caller-supplied optional fields stored in the
    # override ring so caller-supplied race/ethnicity/citizenship round-trips.
    overrides = _DEMOGRAPHIC_OVERRIDES.get(sid)
    if overrides:
        for k, v in overrides.items():
            rec[k] = v
    return rec


# v4.00.65 — OneRoster v1.2 Roster Service spec § 4.13 ?sort=/?orderBy=.
#
# Spec text: "sort - Identifies the field to sort the returned objects by.
# orderBy - Identifies the sort order: 'asc' (default) or 'desc'."
#
# We allow sorting by any top-level field of the projected record. Unknown
# fields no-op (no order change). Bad orderBy values fall back to 'asc'.
# Empty string short-circuits to no-op (operator-facing surface — don't 400).
_SORT_ALLOW_DESC = frozenset(("desc", "DESC"))


def _apply_sort(items: list[dict[str, Any]], sort_field: str, order_by: str) -> list[dict[str, Any]]:
    """Sort items in-place per OneRoster v1.2 spec § 4.13 (sort + orderBy)."""
    field = (sort_field or "").strip()
    if not field:
        return items
    direction = (order_by or "").strip()
    reverse = direction in _SORT_ALLOW_DESC
    # Guard against TypeError when the field is missing/None on some rows —
    # coerce to empty string so sort is total. We do NOT 400 on unknown
    # field per the operator-facing-surface contract.
    return sorted(items, key=lambda r: (r.get(field) or ""), reverse=reverse)


# v4.00.64 — OneRoster v1.2 Roster Service spec § 4.13 ?fields= field-mask.
# Returns only the fields listed in the comma-separated query parameter,
# plus ``sourcedId`` which is always preserved (clients use it as the
# record key). Unknown fields are silently dropped. Empty/missing param
# means "no mask" — return the full record.
#
# Spec text: "fields - Identifies the fields of the resource that are to
# be returned in the response. This is a comma-separated list of fields."
#
# Operator-facing semantics:
#   ?fields=sex,birthDate          → returns {sourcedId, sex, birthDate}
#   ?fields=                       → no mask, full record
#   ?fields=bogus                  → returns {sourcedId} only
#   ?fields=sourcedId              → returns {sourcedId} (no-op explicit)
_FIELDS_MASK_PIN = ("sourcedId",)


def _parse_fields_mask(raw: str) -> tuple[str, ...] | None:
    """Return parsed mask tuple or None when no mask is active."""
    raw = (raw or "").strip()
    if not raw:
        return None
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def _apply_fields_mask(rec: dict[str, Any], mask: tuple[str, ...] | None) -> dict[str, Any]:
    """Return a record with only the requested fields (plus sourcedId)."""
    if mask is None:
        return rec
    keep = set(mask) | set(_FIELDS_MASK_PIN)
    return {k: v for k, v in rec.items() if k in keep}


def _iter_demographics() -> Iterable[dict[str, Any]]:
    try:
        from apps.people.models import StudentProfile
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster demographics: StudentProfile unavailable: %s", exc)
        return
    qs = StudentProfile.objects.all()  # tenant-isolation-allow: oneroster-demographics-platform-scope-bearer-auth
    for s in qs[:1000]:
        yield _demographic_from_student(s)


@require_http_methods(["GET"])
def demographics_collection(request: HttpRequest):
    """v4.00.59 — Paginated list of Demographic records.

    Filters (v4.00.61 + v4.00.62):
      * ``?userSourcedId=<pk>`` — match records whose ``userSourcedIds``
        array contains the supplied User sourcedId
      * ``?orgSourcedId=<pk>`` (v4.00.62) — scope to one school (matches
        the projection's ``_orgSourcedId`` aux field which carries the
        StudentProfile.school_id as a string)
      * ``?role=<value>`` (v4.00.62) — filter by OneRoster role vocab;
        StudentProfile rows always project as ``role="student"`` so the
        only meaningful values are ``"student"`` (passes through) or any
        other value (zero rows). Useful when an external sync pipeline
        wants to assert the projection only returns students.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    items = list(_iter_demographics())
    user_filter = (request.GET.get("userSourcedId") or "").strip()
    if user_filter:
        items = [r for r in items if user_filter in (r.get("userSourcedIds") or [])]
    org_filter = (request.GET.get("orgSourcedId") or "").strip()
    if org_filter:
        items = [r for r in items if r.get("_orgSourcedId") == org_filter]
    role_filter = (request.GET.get("role") or "").strip()
    if role_filter:
        items = [r for r in items if r.get("_role") == role_filter]
    # v4.00.63 — OneRoster v1.2 spec ?dateLastModifiedAbove=<ISO> filter
    # (Roster Service spec § 4.13 "Service interactions / Query"). Returns
    # only records whose ``dateLastModified`` is strictly greater than the
    # supplied bound. Bound is compared as ISO-8601 strings (lex-sortable
    # for ISO timestamps with consistent timezone). Malformed bound:
    # fall through to unfiltered (operator-facing surface, don't 400).
    above = (request.GET.get("dateLastModifiedAbove") or "").strip()
    if above:
        items = [r for r in items if (r.get("dateLastModified") or "") > above]
    # v4.00.66 — OneRoster v1.2 spec § 4.13 ?filter= boolean expression.
    # Grammar: predicate (logical_op predicate)*; predicate is
    # field comparison_op 'value'. AND-precedence > OR-precedence.
    # Parser is fail-safe — bad expr falls through to no-op (operator UI).
    filter_expr = (request.GET.get("filter") or "").strip()
    if filter_expr:
        from apps.api.oneroster_filter import apply_filter as _apply_filter
        items = _apply_filter(items, filter_expr)
    # v4.00.65 — OneRoster v1.2 spec § 4.13 ?sort= + ?orderBy=. Sort BEFORE
    # masking so the operator can sort by a field they then drop from the
    # projection (e.g. sort by dateLastModified, return only sourcedId).
    sort_field = (request.GET.get("sort") or "").strip()
    order_by = (request.GET.get("orderBy") or "").strip()
    if sort_field:
        items = _apply_sort(items, sort_field, order_by)
    # v4.00.64 — OneRoster v1.2 Roster Service spec § 4.13 ?fields= mask.
    mask = _parse_fields_mask(request.GET.get("fields") or "")
    if mask is not None:
        items = [_apply_fields_mask(r, mask) for r in items]
    page, meta = _paginate(request, items)
    return _envelope("demographics", page, meta)


@require_http_methods(["GET"])
def demographic_detail(request: HttpRequest, sourced_id: str):
    """v4.00.59 — Single Demographic record by sourcedId (``demo-<pk>``)."""
    gate = _gate(request)
    if gate is not None:
        return gate
    if not sourced_id.startswith("demo-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    pk = sourced_id[5:]
    if not pk:
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    try:
        from apps.people.models import StudentProfile
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=503)
    try:
        obj = StudentProfile.objects.filter(pk=pk).first()  # tenant-isolation-allow: oneroster-demographic-by-pk-bearer-auth
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    if obj is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    rec = _demographic_from_student(obj)
    mask = _parse_fields_mask(request.GET.get("fields") or "")
    if mask is not None:
        rec = _apply_fields_mask(rec, mask)
    return JsonResponse({"demographic": rec})


@require_http_methods(["GET"])
def student_demographics(request: HttpRequest, sourced_id: str):
    """v4.00.59 — Demographic for a single student, identified by user pk.

    ``sourced_id`` here is the student's user pk (matches the OneRoster
    students endpoint sourcedId, which projects User.pk).
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    try:
        from apps.people.models import StudentProfile
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=503)
    try:
        obj = StudentProfile.objects.filter(user_id=sourced_id).first()  # tenant-isolation-allow: oneroster-demographic-by-user-id-bearer-auth
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    if obj is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    rec = _demographic_from_student(obj)
    mask = _parse_fields_mask(request.GET.get("fields") or "")
    if mask is not None:
        rec = _apply_fields_mask(rec, mask)
    return JsonResponse({"demographic": rec})


# ---------------------------------------------------------------------------
# v4.00.60 — Demographics POST/PUT writes.
#
# POST /api/roster/v1p2/demographics/put/        — create/upsert
# PUT  /api/roster/v1p2/demographics/<sid>/      — update existing demo-<pk>
#
# Both require ``Idempotency-Key`` header. Body shape:
#   {"demographic": {
#       "sourcedId": "demo-12",   # required on PUT; optional on POST
#       "sex": "male" | "female" | "other",
#       "birthDate": "2008-04-15",
#       "cityOfBirth": "Lagos",
#       "studentSourcedId": "<student_pk>",   # required on POST when no sourcedId
#       # optional, accepted and round-tripped via override ring:
#       "americanIndianOrAlaskaNative": "yes"/"no"/"",
#       ...
#   }}
#
# Replay contract:
#   * same Idempotency-Key + same payload bytes → 200/201 cached body w/
#     ``Idempotency-Replay: true``
#   * same Idempotency-Key + different payload  → 409 idempotency mismatch
# ---------------------------------------------------------------------------

def _parse_demographic_payload(body_bytes: bytes):
    """Return (inner_dict, error_response_or_None)."""
    if not body_bytes:
        return None, JsonResponse({"error": "empty_body"}, status=400)
    try:
        payload = _json.loads(body_bytes)
    except (ValueError, TypeError):
        return None, JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse({"error": "bad_envelope"}, status=400)
    inner = payload.get("demographic")
    if not isinstance(inner, dict):
        return None, JsonResponse({"error": "missing_demographic_envelope"}, status=400)
    err = _validate_birth_date(inner)
    if err is not None:
        return None, err
    err = _validate_sex_enum(inner)
    if err is not None:
        return None, err
    err = _validate_country_of_birth_code(inner)
    if err is not None:
        return None, err
    err = _validate_state_of_birth_abbreviation(inner)
    if err is not None:
        return None, err
    err = _validate_city_of_birth(inner)
    if err is not None:
        return None, err
    err = _validate_country_of_citizenship(inner)
    if err is not None:
        return None, err
    err = _validate_race_ethnicity_bool_flags(inner)
    if err is not None:
        return None, err
    err = _validate_middle_name(inner)
    if err is not None:
        return None, err
    err = _validate_gender_identity(inner)
    if err is not None:
        return None, err
    return inner, None


# v4.00.66 — Demographics POST/PUT `countryOfBirthCode` ISO 3166-1 alpha-2.
# OneRoster v1.2 spec Demographics.countryOfBirthCode field carries a
# 2-letter ISO 3166-1 alpha-2 country code (e.g. "NG", "US", "GB").
# Empty string is an explicit clear (preserved). Anything else must match
# the COUNTRY_LOCALIZATION SOT — operators get a 400 with the received
# value + a short note pointing at the SOT.
#
# We resolve the allow-set lazily so the platform's full ISO 3166-1 list
# stays the SoT (we don't carry a duplicate hardcoded list in demographics).
_COUNTRY_OF_BIRTH_CODE_RE = re.compile(r"^[A-Za-z]{2}$")


def _resolve_iso_3166_alpha2_codes() -> frozenset:
    """Pull the ISO 3166-1 alpha-2 codes the platform knows about.

    Walks COUNTRY_LOCALIZATION keys that look like a 2-letter code (skips
    subdivision codes like ``US-CA``). NEVER raises — returns empty set
    on import failure so the validator falls through to regex-only.
    """
    try:
        from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    except Exception:  # noqa: BLE001
        return frozenset()
    return frozenset(
        k for k in COUNTRY_LOCALIZATION.keys()
        if isinstance(k, str) and len(k) == 2 and k.isalpha() and k.isupper()
    )


def _validate_country_of_birth_code(inner: dict[str, Any]):
    """Return None on accept; JsonResponse(400) on reject."""
    if "countryOfBirthCode" not in inner:
        return None
    raw = str(inner.get("countryOfBirthCode") or "").strip()
    if not raw:
        return None  # explicit clear
    if not _COUNTRY_OF_BIRTH_CODE_RE.match(raw):
        return JsonResponse(
            {"error": "bad_country_of_birth_code",
             "reason": "expected_iso_3166_1_alpha_2",
             "received": raw[:32]},
            status=400,
        )
    code = raw.upper()
    allow = _resolve_iso_3166_alpha2_codes()
    # When the SOT is empty (model unavailable), accept any well-shaped
    # alpha-2 code; the regex above guarantees the shape.
    if allow and code not in allow:
        return JsonResponse(
            {"error": "bad_country_of_birth_code",
             "reason": "not_in_iso_3166_1_alpha_2",
             "received": code,
             "note": "must match a 2-letter ISO 3166-1 code from COUNTRY_LOCALIZATION SOT"},
            status=400,
        )
    return None


# v4.00.67 — Demographics POST/PUT `stateOfBirthAbbreviation` ISO 3166-2
# subdivision validation, SCOPED to `countryOfBirthCode`.
#
# Spec semantics: `stateOfBirthAbbreviation` is the subdivision portion of
# the ISO 3166-2 code (the part after the dash). E.g. for someone born in
# California, USA: countryOfBirthCode="US" + stateOfBirthAbbreviation="CA".
# The COUNTRY_LOCALIZATION SOT carries entries keyed `<COUNTRY>-<SUB>`
# (e.g. `US-CA`, `JP-13`); we walk the SOT scoped to the requested
# country and accept only known subdivisions.
#
# Without a country: shape check only (1-3 alphanumeric chars). Caller
# pattern in the wild is to send country+state together, so the missing-
# country case is permissive — operators sometimes send subdivision
# without country during partial updates.
#
# Empty string allowed (explicit clear). Reasons:
#   * bad_shape: regex didn't match
#   * not_in_iso_3166_2: well-shaped but not a known subdivision of the
#                       supplied country
_STATE_OF_BIRTH_ABBR_RE = re.compile(r"^[A-Za-z0-9]{1,3}$")


def _resolve_iso_3166_2_subdivisions(country: str) -> frozenset:
    """Walk COUNTRY_LOCALIZATION keys looking for ``<country>-<subdivision>``
    entries. Returns the subdivision-suffix set (case preserved as-stored).
    """
    if not country:
        return frozenset()
    try:
        from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    except Exception:  # noqa: BLE001
        return frozenset()
    prefix = f"{country}-"
    out = set()
    for k in COUNTRY_LOCALIZATION.keys():
        if isinstance(k, str) and k.startswith(prefix):
            tail = k[len(prefix):]
            if tail:
                out.add(tail)
    return frozenset(out)


def _validate_state_of_birth_abbreviation(inner: dict[str, Any]):
    """Return None on accept; JsonResponse(400) on reject."""
    if "stateOfBirthAbbreviation" not in inner:
        return None
    raw = str(inner.get("stateOfBirthAbbreviation") or "").strip()
    if not raw:
        return None  # explicit clear
    if not _STATE_OF_BIRTH_ABBR_RE.match(raw):
        return JsonResponse(
            {"error": "bad_state_of_birth_abbreviation",
             "reason": "bad_shape",
             "received": raw[:32],
             "note": "expected 1-3 alphanumeric chars (ISO 3166-2 subdivision suffix)"},
            status=400,
        )

    # Scope to the supplied countryOfBirthCode when present in the same body.
    country = str(inner.get("countryOfBirthCode") or "").strip().upper()
    if not country:
        # No country to scope against — shape check passed, accept.
        return None

    allow = _resolve_iso_3166_2_subdivisions(country)
    if not allow:
        # SOT carries no subdivisions for this country (e.g. tiny island
        # nations). Shape-only is the best we can do — accept.
        return None

    # Compare case-insensitively because the SOT keys preserve casing
    # (e.g. US-CA vs JP-13 vs MX-CDMX). We do not auto-uppercase here.
    received_upper = raw.upper()
    allow_upper = {s.upper() for s in allow}
    if received_upper not in allow_upper:
        return JsonResponse(
            {"error": "bad_state_of_birth_abbreviation",
             "reason": "not_in_iso_3166_2",
             "received": raw,
             "country": country,
             "note": f"must match a known {country}-<subdivision> entry in COUNTRY_LOCALIZATION SOT"},
            status=400,
        )
    return None


# v4.00.77 — Demographics POST/PUT `genderIdentity` extended vocabulary.
#
# OneRoster v1.2 spec sex enum (v4.00.65) is the binary-ish {male,female,
# other} vocabulary. The genderIdentity field is the v1.2 spec's extended
# identity vocabulary — overlaps but is NOT the same. Per CDE 2026:
#   male, female, non_binary, transgender_male, transgender_female,
#   prefer_not_to_say, prefer_to_self_describe
# When ``prefer_to_self_describe`` is supplied, the caller may include
# ``genderIdentityDescription`` (free text, max 80 chars, no control
# chars). Other values must NOT include the description field — defended
# locally to avoid "self_describe + description" stealth combos.
GENDER_IDENTITY_VOCAB = frozenset((
    "male", "female", "non_binary",
    "transgender_male", "transgender_female",
    "prefer_not_to_say", "prefer_to_self_describe",
))
_GENDER_IDENTITY_DESC_MAX_LEN = 80
_GENDER_IDENTITY_DESC_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _validate_gender_identity(inner: dict[str, Any]):
    """Return None on accept; JsonResponse(400) on reject."""
    if "genderIdentity" not in inner:
        return None
    raw = str(inner.get("genderIdentity") or "").strip().lower()
    if not raw:
        return None  # explicit clear
    if raw not in GENDER_IDENTITY_VOCAB:
        return JsonResponse(
            {"error": "bad_gender_identity",
             "reason": "value_not_in_vocab",
             "received": str(inner.get("genderIdentity") or "")[:32],
             "allowed": sorted(GENDER_IDENTITY_VOCAB)},
            status=400,
        )
    desc = str(inner.get("genderIdentityDescription") or "")
    if desc:
        if raw != "prefer_to_self_describe":
            return JsonResponse(
                {"error": "bad_gender_identity",
                 "reason": "description_requires_self_describe",
                 "note": "genderIdentityDescription is only valid when genderIdentity=prefer_to_self_describe"},
                status=400,
            )
        if len(desc) > _GENDER_IDENTITY_DESC_MAX_LEN:
            return JsonResponse(
                {"error": "bad_gender_identity",
                 "reason": "description_too_long",
                 "received_length": len(desc),
                 "max_length": _GENDER_IDENTITY_DESC_MAX_LEN},
                status=400,
            )
        if _GENDER_IDENTITY_DESC_CONTROL_RE.search(desc):
            return JsonResponse(
                {"error": "bad_gender_identity",
                 "reason": "description_control_chars"},
                status=400,
            )
    return None


# v4.00.76 — Demographics POST/PUT `middleName` length + character-set validation.
#
# OneRoster v1.2 doesn't define a length cap on middleName, but the
# downstream User row carries CharField(max_length=80) — anything longer
# silently truncates, which is a data-loss bug.
#
# Same control-character defense as cityOfBirth (v4.00.68); 80-char cap
# matches the User.middle_name column. Empty allowed (explicit clear).
_MIDDLE_NAME_MAX_LEN = 80
_MIDDLE_NAME_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _validate_middle_name(inner: dict[str, Any]):
    """Return None on accept; JsonResponse(400) on reject."""
    if "middleName" not in inner:
        return None
    raw = str(inner.get("middleName") or "")
    if not raw:
        return None  # explicit clear
    if len(raw) > _MIDDLE_NAME_MAX_LEN:
        return JsonResponse(
            {"error": "bad_middle_name",
             "reason": "too_long",
             "received_length": len(raw),
             "max_length": _MIDDLE_NAME_MAX_LEN},
            status=400,
        )
    if _MIDDLE_NAME_CONTROL_CHAR_RE.search(raw):
        return JsonResponse(
            {"error": "bad_middle_name",
             "reason": "control_chars",
             "note": "control characters (U+0000-U+001F, U+007F-U+009F) are rejected"},
            status=400,
        )
    return None


# v4.00.70 — Demographics POST/PUT race / ethnicity boolean-flag validation.
#
# OneRoster v1.2 Demographics carries 7 boolean race / ethnicity flags
# (the CDE / federal data-collection set):
#   americanIndianOrAlaskaNative, asian, blackOrAfricanAmerican,
#   hispanicOrLatinoEthnicity, nativeHawaiianOrOtherPacificIslander,
#   white, demographicRaceTwoOrMoreRaces
# Wave v4.00.70 introduces the validator framework + lights up the first
# flag (americanIndianOrAlaskaNative). Subsequent waves wire the other six
# behind the same validator — adding each field to RACE_ETHNICITY_BOOL_FIELDS
# is the entire integration point.
#
# Accept shapes:
#   * literal bools True / False
#   * strings "true" / "false" / "yes" / "no" / "1" / "0" / "y" / "n"
#     (case-insensitive — accommodates form-encoded callers)
#   * empty string ("") is explicit clear
# Reject:
#   * anything else -> 400 bad_race_ethnicity_flag w/ field + received echo
RACE_ETHNICITY_BOOL_FIELDS = frozenset((
    "americanIndianOrAlaskaNative",         # v4.00.70
    "asian",                                # v4.00.71
    "blackOrAfricanAmerican",               # v4.00.71
    "hispanicOrLatinoEthnicity",            # v4.00.72
    "nativeHawaiianOrOtherPacificIslander", # v4.00.73
    "white",                                # v4.00.74
    "demographicRaceTwoOrMoreRaces",        # v4.00.75 (complete set)
))
_TRUE_STRINGS = frozenset(("true", "yes", "1", "y", "t"))
_FALSE_STRINGS = frozenset(("false", "no", "0", "n", "f"))


def _coerce_boolish(value: Any) -> tuple[bool, Any]:
    """Return ``(ok, coerced_bool)``. ``ok=False`` means the value was
    neither a bool nor a recognized truthy/falsey string."""
    if isinstance(value, bool):
        return True, value
    if value is None:
        return True, False
    s = str(value).strip().lower()
    if s == "":
        return True, False  # explicit clear
    if s in _TRUE_STRINGS:
        return True, True
    if s in _FALSE_STRINGS:
        return True, False
    return False, None


def _validate_race_ethnicity_bool_flags(inner: dict[str, Any]):
    """Return None on accept; JsonResponse(400) on reject."""
    for field in RACE_ETHNICITY_BOOL_FIELDS:
        if field not in inner:
            continue
        ok, _coerced = _coerce_boolish(inner.get(field))
        if not ok:
            return JsonResponse(
                {"error": "bad_race_ethnicity_flag",
                 "reason": "not_boolish",
                 "field": field,
                 "received": str(inner.get(field) or "")[:32],
                 "note": "expected bool or one of true/false/yes/no/1/0"},
                status=400,
            )
    return None


# v4.00.69 — Demographics POST/PUT `countryOfCitizenship` multi-value.
#
# Per OneRoster v1.2, ``countryOfCitizenship`` carries one OR more ISO 3166-1
# alpha-2 codes (dual citizens are common). We accept the field as either:
#   * a comma-separated string (``"US,NG,GB"``) — common from caller code
#     that doesn't want to build a list
#   * a JSON list (``["US", "NG", "GB"]``) — strict v1.2 shape
# Each code is validated independently against the same SOT
# ``_resolve_iso_3166_alpha2_codes()`` walk used by ``countryOfBirthCode``.
# A single bad code rejects the whole field with the bad value echoed.
#
# Failure classes:
#   * bad_shape: a code is not 2 letters (regex check)
#   * not_in_iso_3166_1_alpha_2: well-shaped but not a known country code
#   * too_many_values: > 5 codes (typo guard — no real person holds more)
# Empty string / empty list allowed (explicit clear). All comparisons are
# case-insensitive (codes uppercased before SOT lookup).
_COUNTRY_OF_CITIZENSHIP_MAX_VALUES = 5


def _normalize_citizenship_list(raw: Any) -> list[str]:
    """Coerce the input shape (string CSV or JSON list) to a list of upper-cased
    codes. Returns [] when the input is empty / None.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        out = []
        for item in raw:
            s = str(item or "").strip().upper()
            if s:
                out.append(s)
        return out
    s = str(raw or "").strip()
    if not s:
        return []
    return [piece.strip().upper() for piece in s.split(",") if piece.strip()]


def _validate_country_of_citizenship(inner: dict[str, Any]):
    """Return None on accept; JsonResponse(400) on reject."""
    if "countryOfCitizenship" not in inner:
        return None
    codes = _normalize_citizenship_list(inner.get("countryOfCitizenship"))
    if not codes:
        return None  # explicit clear allowed
    if len(codes) > _COUNTRY_OF_CITIZENSHIP_MAX_VALUES:
        return JsonResponse(
            {"error": "bad_country_of_citizenship",
             "reason": "too_many_values",
             "received_count": len(codes),
             "max_values": _COUNTRY_OF_CITIZENSHIP_MAX_VALUES},
            status=400,
        )
    allow = _resolve_iso_3166_alpha2_codes()
    for code in codes:
        if not _COUNTRY_OF_BIRTH_CODE_RE.match(code):
            return JsonResponse(
                {"error": "bad_country_of_citizenship",
                 "reason": "bad_shape",
                 "received": code[:32],
                 "note": "each code must be a 2-letter ISO 3166-1 alpha-2 value"},
                status=400,
            )
        if allow and code not in allow:
            return JsonResponse(
                {"error": "bad_country_of_citizenship",
                 "reason": "not_in_iso_3166_1_alpha_2",
                 "received": code,
                 "note": "must match a 2-letter ISO 3166-1 code from COUNTRY_LOCALIZATION SOT"},
                status=400,
            )
    return None


# v4.00.68 — Demographics POST/PUT `cityOfBirth` length + character-set
# validation.
#
# OneRoster v1.2 Demographic.cityOfBirth is free-text (the spec carries no
# length cap and no character-class restriction). Real-world callers ship
# everything from "Lagos" to multi-line addresses to control-character
# garbage from copy-paste-from-Excel mistakes — both of which corrupt the
# downstream StudentProfile.place_of_birth field (CharField(max_length=120)).
#
# Failure classes:
#   * too_long: > 120 chars (matches the DB column width — write-path already
#     truncates to 120 silently; we make the rejection explicit so the
#     operator notices the data loss)
#   * control_chars: contains C0/C1 control chars (tab/newline/etc.) — these
#     break the diagnostic UI and the CSV export
#
# Empty string is allowed (explicit clear). Sex-character classes (unicode
# letters / spaces / dashes / dots / commas / apostrophes / parens / digits)
# are accepted because city names worldwide include all of these (e.g.
# "St. John's", "Stratford-upon-Avon", "São Paulo", "Washington, D.C.").
_CITY_OF_BIRTH_MAX_LEN = 120
_CITY_OF_BIRTH_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _validate_city_of_birth(inner: dict[str, Any]):
    """Return None on accept; JsonResponse(400) on reject."""
    if "cityOfBirth" not in inner:
        return None
    raw = str(inner.get("cityOfBirth") or "")
    if not raw:
        return None  # explicit clear allowed
    if len(raw) > _CITY_OF_BIRTH_MAX_LEN:
        return JsonResponse(
            {"error": "bad_city_of_birth",
             "reason": "too_long",
             "received_length": len(raw),
             "max_length": _CITY_OF_BIRTH_MAX_LEN},
            status=400,
        )
    if _CITY_OF_BIRTH_CONTROL_CHAR_RE.search(raw):
        return JsonResponse(
            {"error": "bad_city_of_birth",
             "reason": "control_chars",
             "note": "control characters (U+0000-U+001F, U+007F-U+009F) are rejected"},
            status=400,
        )
    return None


# v4.00.65 — Demographics POST/PUT `sex` enum validation per OneRoster v1.2
# spec § 4.13 vocabulary. The Demographics schema's `sex` field is a closed
# enum: ``male`` / ``female`` / ``other`` (case-insensitive). Empty string
# is an explicit clear (preserved). Anything else is 400.
_DEMOGRAPHIC_SEX_VOCAB = frozenset(("male", "female", "other"))


def _validate_sex_enum(inner: dict[str, Any]):
    """Return None on accept; JsonResponse(400) on reject."""
    if "sex" not in inner:
        return None
    raw = str(inner.get("sex") or "").strip().lower()
    if not raw:
        return None  # explicit clear allowed
    if raw not in _DEMOGRAPHIC_SEX_VOCAB:
        return JsonResponse(
            {"error": "bad_sex_enum",
             "reason": "value_not_in_vocab",
             "received": str(inner.get("sex") or "")[:32],
             "allowed": sorted(_DEMOGRAPHIC_SEX_VOCAB)},
            status=400,
        )
    return None


# v4.00.64 — Demographics POST/PUT body validation.
#
# OneRoster v1.2 Demographic.birthDate is ISO-8601 date (YYYY-MM-DD).
# Two failure classes we reject with 400:
#   * malformed string (non-ISO / non-numeric components)
#   * out-of-range value: future date OR pre-floor (1900-01-01)
# Empty string is allowed (explicit clear).
# Strict floor 1900 is sufficient — no living student in our cohort is
# older than that, and we never want to accept the year 0001 typo.
_BIRTH_DATE_FLOOR_YEAR = 1900


def _validate_birth_date(inner: dict[str, Any]):
    """Return None on accept; JsonResponse(400) on reject."""
    if "birthDate" not in inner:
        return None
    raw = str(inner.get("birthDate") or "").strip()
    if not raw:
        return None  # explicit clear — allowed
    try:
        from datetime import date as _date
        parts = raw.split("-")
        if len(parts) != 3:
            return JsonResponse(
                {"error": "bad_birth_date", "reason": "expected_YYYY_MM_DD"},
                status=400,
            )
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        bd = _date(y, m, d)
    except (ValueError, TypeError):
        return JsonResponse(
            {"error": "bad_birth_date", "reason": "unparseable"},
            status=400,
        )
    from datetime import date as _date2
    today = _date2.today()
    if bd > today:
        return JsonResponse(
            {"error": "bad_birth_date", "reason": "future_date_rejected",
             "birthDate": raw},
            status=400,
        )
    if bd.year < _BIRTH_DATE_FLOOR_YEAR:
        return JsonResponse(
            {"error": "bad_birth_date", "reason": "before_floor",
             "floor_year": _BIRTH_DATE_FLOOR_YEAR},
            status=400,
        )
    return None


def _apply_demographic_to_student(s, inner: dict[str, Any]) -> None:
    """Write the mappable demographic fields onto a StudentProfile instance.

    v4.00.63 — when ``_orgSourcedId`` is supplied AND resolves to a real
    School row, the student is re-bound to that school. Useful for
    cross-tenant transfers driven from an upstream SIS. Bad orgSourcedId
    (non-numeric / school not found) is silently dropped so a buggy
    integration doesn't corrupt the student row.
    """
    changed = False
    if "sex" in inner:
        sex_val = str(inner.get("sex") or "").strip().lower()
        gender = _SEX_TO_GENDER.get(sex_val, "")
        if gender and getattr(s, "gender", "") != gender:
            s.gender = gender
            changed = True
        elif sex_val == "" and getattr(s, "gender", ""):
            s.gender = ""
            changed = True
    if "birthDate" in inner:
        bd = str(inner.get("birthDate") or "").strip()
        if bd:
            try:
                from datetime import date as _date
                y, m, d = bd.split("-")
                s.date_of_birth = _date(int(y), int(m), int(d))
                changed = True
            except (ValueError, TypeError):
                pass
        else:
            if getattr(s, "date_of_birth", None) is not None:
                s.date_of_birth = None
                changed = True
    if "cityOfBirth" in inner:
        city = str(inner.get("cityOfBirth") or "")[:120]
        if getattr(s, "place_of_birth", "") != city:
            s.place_of_birth = city
            changed = True
    # v4.00.63 — _orgSourcedId override: move the student to a different
    # school. Requires the school FK to resolve; non-existent school_id
    # is silently dropped (operator-facing API, fail-soft).
    if "_orgSourcedId" in inner:
        new_org = str(inner.get("_orgSourcedId") or "").strip()
        if new_org:
            try:
                from apps.schools.models import School
                target = School.objects.filter(pk=new_org).first()  # tenant-isolation-allow: oneroster-demographic-org-override-write-bearer-auth
                if target is not None and getattr(s, "school_id", None) != target.pk:
                    s.school = target
                    changed = True
            except (ValueError, TypeError, Exception) as exc:  # noqa: BLE001
                logger.debug("demographic org override failed: %s", exc)
        else:
            # Empty string explicitly clears the school binding.
            if getattr(s, "school_id", None) is not None:
                s.school = None
                changed = True
    if changed:
        s.save()


@csrf_exempt
@require_http_methods(["POST"])
def post_demographic(request: HttpRequest):
    """v4.00.60 — POST /api/roster/v1p2/demographics/put/

    Creates or upserts a Demographic record. ``sourcedId`` resolves the
    target StudentProfile (``demo-<pk>``); otherwise ``studentSourcedId``
    points to a User (User.pk) which must have an existing StudentProfile.
    """
    gate = _gate(request)
    if gate is not None:
        return gate

    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key("post", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    inner, err = _parse_demographic_payload(body_bytes)
    if err is not None:
        return err

    try:
        from apps.people.models import StudentProfile
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=503)

    obj = None
    sid_in = str(inner.get("sourcedId") or "").strip()
    if sid_in.startswith("demo-"):
        pk_str = sid_in[5:]
        try:
            obj = StudentProfile.objects.filter(pk=pk_str).first()  # tenant-isolation-allow: oneroster-demographic-post-by-pk
        except (ValueError, TypeError):
            return JsonResponse({"error": "bad_sourced_id"}, status=400)
    if obj is None:
        stu_sid = str(inner.get("studentSourcedId") or "").strip()
        if not stu_sid:
            return JsonResponse({"error": "missing_student_sourced_id"}, status=400)
        try:
            obj = StudentProfile.objects.filter(user_id=stu_sid).first()  # tenant-isolation-allow: oneroster-demographic-post-by-user-id
        except (ValueError, TypeError):
            return JsonResponse({"error": "bad_student_sourced_id"}, status=400)
    if obj is None:
        return JsonResponse({"error": "student_not_found"}, status=404)

    _apply_demographic_to_student(obj, inner)
    sid_out = f"demo-{obj.pk}"
    _set_demographic_overrides(sid_out, inner)
    body = {"demographic": _demographic_from_student(obj)}
    cache.set(ck, {"payload_hash": payload_hash, "status": 200, "response_body": body}, _IDEMPOTENCY_TTL)
    return JsonResponse(body, status=200)


@csrf_exempt
@require_http_methods(["PUT"])
def put_demographic(request: HttpRequest, sourced_id: str):
    """v4.00.60 — PUT /api/roster/v1p2/demographics/<sourced_id>/

    Updates an existing Demographic. ``sourced_id`` is ``demo-<pk>``.
    """
    gate = _gate(request)
    if gate is not None:
        return gate

    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    if not sourced_id.startswith("demo-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    pk_str = sourced_id[5:]
    if not pk_str:
        return JsonResponse({"error": "bad_sourced_id"}, status=400)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key(sourced_id, idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    inner, err = _parse_demographic_payload(body_bytes)
    if err is not None:
        return err

    try:
        from apps.people.models import StudentProfile
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=503)
    try:
        obj = StudentProfile.objects.filter(pk=pk_str).first()  # tenant-isolation-allow: oneroster-demographic-put-by-pk
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    if obj is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)

    _apply_demographic_to_student(obj, inner)
    _set_demographic_overrides(sourced_id, inner)
    body = {"demographic": _demographic_from_student(obj)}
    cache.set(ck, {"payload_hash": payload_hash, "status": 200, "response_body": body}, _IDEMPOTENCY_TTL)
    return JsonResponse(body, status=200)
