"""Derive, per model AND per school, which optional admin fields go unused.

The auto-fill layer reduces what a person has to TYPE.  This reduces what they have
to READ, which is the larger number: across both admin sites 3,642 editable fields
are presented on add forms while only 1,608 are required.  A school that has never
once filled ``middle_name`` in 500 student records is asked about it on every single
add form, forever.

WHAT MAKES THIS DERIVED AND NOT GUESSED
    The answer comes from the tenant's own rows.  ``derive_unused_optional_fields``
    counts, for each optional field, how many existing records of that model in that
    school carry a value.  Zero out of a meaningful sample is evidence.  Nothing here
    infers from field names, types, or what other tenants do.

THE FOUR GUARDS, EACH LOAD-BEARING
    1. SAMPLE FLOOR — below ``MIN_ROWS_DEFAULT`` rows nothing is inferred at all.
       "Never used" across three records is not a finding, it is a new school.
    2. THE PERSON WINS — inference applies only to a surface the user has never
       curated.  The moment they hide or reveal anything here, their choice is the
       whole answer and this module stops contributing.  It is a starting position,
       never an override.
    3. OPTIONAL ONLY — required fields are not eligible, enforced by the caller
       passing only the optional set, and again by the contract builder which
       refuses to hide a required field.
    4. REVERSIBLE AND VISIBLE — inferred fields ride in the contract tagged with
       their reason and row count, so the surface can say "your school has not used
       this" rather than pretending the person chose it.  "Show all" still shows all.

Hidden is not the same as absent: the existing machinery keeps hidden values in the
bound form for validation and blocks a crafted POST from changing them.  This module
only decides the STARTING hidden set; it changes none of that.

LIMITS
    * A field used once in five years then abandoned reads as used.  Deliberate —
      the alternative is a recency window, which would start hiding fields a school
      uses annually.
    * Many-to-many fields are not sampled (they need a join per field, and the cost
      lands on an interactive page load).  They are always treated as used.
    * The count is cached per (model, school); a school that starts using a field
      keeps seeing it hidden until the entry expires.  ``CACHE_SECONDS_DEFAULT``
      trades that staleness against a per-render aggregate query.
"""

from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import FieldError
from django.db import DatabaseError
from django.db.models import Case, Count, IntegerField, Q, When


logger = logging.getLogger(__name__)

#: Platform-constant layer of the configurability cascade; each is overridable as a
#: Django setting (and therefore by env var where settings read one).
MIN_ROWS_DEFAULT = 25
CACHE_SECONDS_DEFAULT = 900
MAX_SAMPLED_FIELDS = 40
CACHE_KEY_PREFIX = "rmc_admin_field_usage_v1"

#: Field classes whose emptiness cannot be expressed as a cheap NULL/'' predicate,
#: or whose sampling cost lands on an interactive request.
UNSAMPLED_FIELD_TYPES = frozenset({"ManyToManyField"})

#: Text-ish fields store "unset" as the empty string as often as NULL, so both have
#: to count as empty or every blank-defaulted CharField reads as universally used.
TEXTUAL_FIELD_TYPES = frozenset(
    {
        "CharField",
        "TextField",
        "SlugField",
        "EmailField",
        "URLField",
        "FileField",
        "ImageField",
        "GenericIPAddressField",
    }
)


def inference_enabled() -> bool:
    return bool(getattr(settings, "RMC_ADMIN_FIELD_USAGE_INFERENCE_ENABLED", True))


def min_rows() -> int:
    try:
        return max(1, int(getattr(settings, "RMC_ADMIN_FIELD_USAGE_MIN_ROWS", MIN_ROWS_DEFAULT)))
    except (TypeError, ValueError):
        return MIN_ROWS_DEFAULT


def cache_seconds() -> int:
    try:
        return max(
            0, int(getattr(settings, "RMC_ADMIN_FIELD_USAGE_CACHE_SECONDS", CACHE_SECONDS_DEFAULT))
        )
    except (TypeError, ValueError):
        return CACHE_SECONDS_DEFAULT


def _cache_key(model, school_pk) -> str:
    return f"{CACHE_KEY_PREFIX}:{model._meta.label_lower}:{school_pk}"


def _sampleable(model, name: str) -> bool:
    from django.core.exceptions import FieldDoesNotExist

    try:
        field = model._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    if not getattr(field, "concrete", False):
        return False
    if type(field).__name__ in UNSAMPLED_FIELD_TYPES:
        return False
    return True


def _emptiness_q(model, name: str) -> Q:
    """A Q matching rows where this field carries no value."""
    field = model._meta.get_field(name)
    empty = Q(**{f"{name}__isnull": True})
    if type(field).__name__ in TEXTUAL_FIELD_TYPES:
        empty |= Q(**{name: ""})
    return empty


def derive_unused_optional_fields(
    model, school, optional_names: Iterable[str]
) -> tuple[frozenset[str], int]:
    """Return ``(never-used field names, rows sampled)`` for one school's records.

    Returns an empty set — never a partial guess — whenever the evidence is
    insufficient: no school, no ``school`` field on the model, inference disabled,
    too few rows, or any database error.
    """

    if not inference_enabled() or school is None:
        return frozenset(), 0
    if not any(f.name == "school" for f in model._meta.fields):
        return frozenset(), 0

    names = [n for n in dict.fromkeys(optional_names) if _sampleable(model, n)]
    if not names:
        return frozenset(), 0
    # A very wide model would otherwise build a 100-expression aggregate on an
    # interactive request; the cap keeps the query bounded and predictable.
    names = names[:MAX_SAMPLED_FIELDS]

    school_pk = getattr(school, "pk", None)
    if school_pk is None:
        return frozenset(), 0

    key = _cache_key(model, school_pk)
    cached = cache.get(key)
    if isinstance(cached, tuple) and len(cached) == 2:
        unused, sampled = cached
        return frozenset(unused), int(sampled)

    try:
        # tenant-isolation-allow: explicit-school-filter-is-the-whole-point-of-this-query
        queryset = model._default_manager.filter(school=school)
        aggregates = {"rmc_total": Count("pk")}
        for index, name in enumerate(names):
            aggregates[f"rmc_used_{index}"] = Count(
                Case(
                    When(~_emptiness_q(model, name), then=1),
                    output_field=IntegerField(),
                )
            )
        row = queryset.aggregate(**aggregates)
    except (DatabaseError, FieldError, TypeError, ValueError):
        logger.warning(
            "admin field-usage inference unavailable model=%s",
            model._meta.label_lower,
            exc_info=True,
        )
        return frozenset(), 0

    total = int(row.get("rmc_total") or 0)
    if total < min_rows():
        # Cache the negative too: a small school would otherwise re-run this
        # aggregate on every add-form render for no possible benefit.
        cache.set(key, (tuple(), total), cache_seconds())
        return frozenset(), total

    unused = tuple(
        name for index, name in enumerate(names) if not int(row.get(f"rmc_used_{index}") or 0)
    )
    cache.set(key, (unused, total), cache_seconds())
    logger.info(
        "admin_field_usage model=%s school=%s rows=%s unused=%s",
        model._meta.label_lower,
        school_pk,
        total,
        len(unused),
    )
    return frozenset(unused), total


def invalidate(model, school) -> None:
    """Drop one cached sample. Call after a bulk import changes what a school uses."""
    school_pk = getattr(school, "pk", None)
    if school_pk is not None:
        cache.delete(_cache_key(model, school_pk))
