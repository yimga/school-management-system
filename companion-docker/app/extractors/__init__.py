"""Vendor extractors — PURE DATA TRANSFORMS (v3.38.0 architectural boundary).

Programmatic vendor login + DOM scraping + headless session replay
live in ``companion-extension/`` (the browser extension where the
operator's own authenticated tab is the security boundary). The
Docker sibling does NOT and MUST NOT contain code that
programmatically logs into any third-party SIS.

What these modules ARE: pre-processors that take an already-parsed
CSV (``list[dict[str,str]]``) — the operator manually exported it
from their SIS via the SIS's own export UI — and normalize
vendor-specific quirks (date formats, header casing, status codes,
nested keys, JSON-in-cell, separators) BEFORE the canonical-header
mapper runs.

What these modules ARE NOT: there is NO ``httpx.Client``, NO cookie
capture, NO session replay, NO HTTP call to any third-party SIS
endpoint. If you find yourself adding one, stop: that work belongs
in ``companion-extension/`` instead.
"""
from __future__ import annotations

from typing import Iterable, Optional


class ExtractorError(Exception):
    """Base for typed extractor errors."""


class InvalidCellValue(ExtractorError):
    """Raised when a cell value cannot be normalized (e.g. unparseable JSON
    where parsing is mandatory). Pre-processors PREFER passthrough over
    raising for unknown shapes; this is reserved for hard validation."""


class UnknownVendor(ExtractorError):
    """Raised when callers explicitly request a vendor that is not registered."""


def normalize_header(h: str) -> str:
    """Lowercase + replace whitespace/hyphens/dots/slashes with underscore.

    Collapses consecutive underscores and strips leading/trailing
    underscore. Strips surrounding single/double quotes. Used by every
    vendor extractor for case-insensitive header matching.
    """
    if h is None:
        return ""
    trimmed = h.strip().strip('"').strip("'")
    out: list[str] = []
    prev_us = False
    for ch in trimmed:
        c = ch.lower()
        if c in (" ", "\t", "-", ".", "/", "\\"):
            mapped = "_"
        else:
            mapped = c
        if mapped == "_":
            if prev_us:
                continue
            prev_us = True
        else:
            prev_us = False
        out.append(mapped)
    return "".join(out).strip("_")


# Mirror of vendor_signatures() in Rust extractors/mod.rs.
_VENDOR_SIGNATURES: list[tuple[str, frozenset[str]]] = [
    (
        "alma",
        frozenset(
            {
                "alma_id",
                "school_users_id",
                "user_type",
                "graphql_node",
                "extra_attributes",
                "custom_fields_json",
            }
        ),
    ),
    (
        "blackbaud",
        frozenset(
            {
                "student_firstname",
                "student_lastname",
                "student_id",
                "relationshiptype",
                "user_id",
                "host_id",
                "constituent_id",
                "user_modifieddate",
            }
        ),
    ),
    (
        "facts",
        frozenset(
            {
                "familyid",
                "personid",
                "tuition_balance",
                "facts_id",
                "school_year_id",
                "studentid",
                "renweb_id",
            }
        ),
    ),
    (
        "powerschool",
        frozenset(
            {
                "student_number",
                "dcid",
                "enroll_status",
                "lastfirst",
                "schoolid",
                "grade_level",
                "home_room",
                "entrydate",
                "exitdate",
            }
        ),
    ),
    (
        "skyward",
        frozenset(
            {
                "skyward_id",
                "other_id",
                "name_id",
                "entity_id",
                "school_year",
                "homeroom_teacher",
                "gradyr",
            }
        ),
    ),
    (
        "veracross",
        frozenset(
            {
                "person_id",
                "sex",
                "household_id",
                "studentemail",
                "facultyemail",
                "grad_year",
                "current_grade",
                "person_pk",
            }
        ),
    ),
]


def detect_vendor(headers: Iterable[str]) -> Optional[str]:
    """Return the vendor name whose signature-header set most overlaps the
    input headers. Requires at least 1 overlap. Tie-broken
    alphabetically (matches Rust sibling).

    Returns ``None`` when no vendor matches at least one header.
    """
    normalized = [normalize_header(h) for h in headers]
    best: tuple[str, int] | None = None
    # Iterate in alphabetic order (list is already sorted by vendor
    # name above).
    for vendor, sig in _VENDOR_SIGNATURES:
        hits = sum(1 for h in normalized if h in sig)
        if hits == 0:
            continue
        if best is None or hits > best[1]:
            best = (vendor, hits)
    return best[0] if best else None


def preprocess_for_vendor(
    vendor: Optional[str],
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Dispatch rows to the appropriate vendor pre-processor.

    Unknown vendor → identity (rows returned verbatim).
    """
    if vendor is None:
        return rows
    # Lazy imports so a broken/missing vendor module never breaks the
    # other five.
    if vendor == "powerschool":
        from . import powerschool

        return powerschool.preprocess_rows(rows)
    if vendor == "blackbaud":
        from . import blackbaud

        return blackbaud.preprocess_rows(rows)
    if vendor == "veracross":
        from . import veracross

        return veracross.preprocess_rows(rows)
    if vendor == "alma":
        from . import alma

        return alma.preprocess_rows(rows)
    if vendor == "facts":
        from . import facts

        return facts.preprocess_rows(rows)
    if vendor == "skyward":
        from . import skyward

        return skyward.preprocess_rows(rows)
    raise UnknownVendor(f"vendor not registered: {vendor!r}")


__all__ = [
    "ExtractorError",
    "InvalidCellValue",
    "UnknownVendor",
    "normalize_header",
    "detect_vendor",
    "preprocess_for_vendor",
]
