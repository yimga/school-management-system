"""Bulk school-creation service.

CSV → many School rows. Operates AROUND the locked wizard
(super_views_create_school_wizard.py) — we create the row directly
and let post_save signals (incl. lifecycle.signals) fan out the
expected side effects.

CSV columns (header row required):
  name (required, max 255)
  slug (required, unique, lowercased)
  subdomain (optional; defaults to slug)
  country_code (optional, ISO 3166-1 alpha-2)
  sub_system (optional, one of EN/FR/INT; defaults to EN)
  contact_email (optional; if present, suggests an admin user — not auto-created here)
  primary_sector (optional)

Extra columns are preserved in row.extras for diagnostics but not
written to the School row.

Public API:
    parse_csv(file_obj) -> ParseResult
    apply_rows(rows, actor=None) -> ApplyResult

Both are pure functions over Python objects; no Django request needed.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from django.db import IntegrityError, transaction

from apps.schools.models import School

from .services import record_stage

logger = logging.getLogger(__name__)


_REQUIRED_COLUMNS = {"name", "slug"}
_OPTIONAL_COLUMNS = {
    "subdomain",
    "country_code",
    "sub_system",
    "contact_email",
    "primary_sector",
}
_VALID_SUB_SYSTEMS = {"EN", "FR", "INT"}
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,118}[a-z0-9]$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")


@dataclass
class ParsedRow:
    line_no: int
    name: str = ""
    slug: str = ""
    subdomain: str = ""
    country_code: str = ""
    sub_system: str = "EN"
    contact_email: str = ""
    primary_sector: str = ""
    extras: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass
class ParseResult:
    rows: list
    header_errors: list = field(default_factory=list)

    @property
    def valid_rows(self) -> list:
        return [r for r in self.rows if r.is_valid]

    @property
    def invalid_rows(self) -> list:
        return [r for r in self.rows if not r.is_valid]

    @property
    def total(self) -> int:
        return len(self.rows)


@dataclass
class CreatedRow:
    line_no: int
    slug: str
    school_id: Optional[str] = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.school_id) and not self.error


@dataclass
class ApplyResult:
    created: list
    failed: list

    @property
    def total_attempted(self) -> int:
        return len(self.created) + len(self.failed)

    @property
    def total_ok(self) -> int:
        return sum(1 for r in self.created if r.ok)


def parse_csv(file_obj) -> ParseResult:
    """Parse a CSV upload into ParsedRow dataclasses.

    Accepts file-like object (uploaded file, StringIO, etc.). Honors
    UTF-8 with optional BOM. Empty rows are skipped silently. Lines
    over 5000 are refused (sane cap; bulk creation is not for full
    migration imports — use Migration Cloud for that).
    """
    raw = file_obj.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig", errors="replace")
    else:
        text = raw.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text))
    rows: list = []
    header_errors: list = []
    if reader.fieldnames is None:
        return ParseResult(rows=[], header_errors=["empty CSV (no header)"])
    field_set = {(name or "").strip().lower() for name in reader.fieldnames}
    missing = _REQUIRED_COLUMNS - field_set
    if missing:
        header_errors.append(f"missing required columns: {', '.join(sorted(missing))}")
        return ParseResult(rows=[], header_errors=header_errors)

    seen_slugs: set = set()
    for line_no, raw_row in enumerate(reader, start=2):
        if not any((raw_row or {}).values()):
            continue
        if len(rows) >= 5000:
            header_errors.append("row cap exceeded (5000) — split your file")
            break
        row = ParsedRow(line_no=line_no)
        for key, value in (raw_row or {}).items():
            if not key:
                continue
            normalized_key = key.strip().lower()
            value = (value or "").strip()
            if normalized_key in _REQUIRED_COLUMNS or normalized_key in _OPTIONAL_COLUMNS:
                setattr(row, normalized_key, value)
            else:
                row.extras[normalized_key] = value
        _validate(row, seen_slugs)
        rows.append(row)
    return ParseResult(rows=rows, header_errors=header_errors)


def _validate(row: ParsedRow, seen_slugs: set) -> None:
    if not row.name:
        row.errors.append("name is required")
    elif len(row.name) > 255:
        row.errors.append("name exceeds 255 chars")
    if not row.slug:
        row.errors.append("slug is required")
    else:
        slug = row.slug.lower()
        if not _SLUG_RE.match(slug):
            row.errors.append("slug must be lowercase alnum+hyphens, 3-120 chars")
        elif slug in seen_slugs:
            row.errors.append("duplicate slug within this file")
        else:
            seen_slugs.add(slug)
            row.slug = slug
    if row.subdomain:
        sub = row.subdomain.lower()
        if not _SLUG_RE.match(sub):
            row.errors.append("subdomain must be lowercase alnum+hyphens, 3-120 chars")
        else:
            row.subdomain = sub
    if row.country_code:
        if not _COUNTRY_RE.match(row.country_code):
            row.errors.append("country_code must be 2 letters (ISO 3166-1 alpha-2)")
        else:
            row.country_code = row.country_code.upper()
    if row.sub_system:
        row.sub_system = row.sub_system.upper()
        if row.sub_system not in _VALID_SUB_SYSTEMS:
            row.errors.append(f"sub_system must be one of {sorted(_VALID_SUB_SYSTEMS)}")
    else:
        row.sub_system = "EN"
    if row.contact_email and not _EMAIL_RE.match(row.contact_email):
        row.errors.append("contact_email is not a valid email")


def apply_rows(rows: Iterable[ParsedRow], *, actor=None) -> ApplyResult:
    """Create one School per valid row. Best-effort: a single failure does
    not roll back the whole batch — each row is its own atomic block.

    Calls record_stage() explicitly so lifecycle gets a 'note' that names
    the bulk source; the schools.post_save listener would also fire, but
    we want the bulk attribution preserved in the timeline.
    """
    created: list = []
    failed: list = []
    for row in rows:
        if not row.is_valid:
            failed.append(
                CreatedRow(
                    line_no=row.line_no,
                    slug=row.slug,
                    error="; ".join(row.errors) or "validation failed",
                )
            )
            continue
        try:
            with transaction.atomic():
                # School.objects.create() is the simplest cross-version-safe
                # path; the wizard's async multi-phase pipeline is not
                # invoked here. Operators using bulk should use Migration
                # Cloud for full provisioning of large school populations.
                school = School.objects.create(
                    name=row.name,
                    slug=row.slug,
                    subdomain=row.subdomain or row.slug,
                    sub_system=row.sub_system,
                    country_code=row.country_code,
                    is_active=False,  # gated until operator approves
                )
                if row.primary_sector:
                    school.primary_sector = row.primary_sector[:64]
                    school.save(update_fields=["primary_sector"])
                record_stage(
                    school,
                    "REQUESTED",
                    actor=actor,
                    note=f"Bulk CSV row {row.line_no}",
                    payload={"source": "bulk_csv", "line_no": row.line_no},
                )
            created.append(CreatedRow(line_no=row.line_no, slug=row.slug, school_id=str(school.id)))
        except IntegrityError as exc:
            failed.append(
                CreatedRow(
                    line_no=row.line_no,
                    slug=row.slug,
                    error=f"integrity error (likely duplicate slug or subdomain across existing schools): {type(exc).__name__}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "lifecycle.bulk_create.row_failed line=%s slug=%s err=%s",
                row.line_no,
                row.slug,
                type(exc).__name__,
            )
            failed.append(
                CreatedRow(
                    line_no=row.line_no,
                    slug=row.slug,
                    error=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
            )
    return ApplyResult(created=created, failed=failed)
