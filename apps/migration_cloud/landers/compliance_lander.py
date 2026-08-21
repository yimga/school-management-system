"""Compliance lander — preserves canonical compliance-check rows as custom records.

Canonical row shape::

    {
        "subject_external_id": "PS-1029",      # subject the check pertains to
        "category":            "immunization"|"safeguarding"|"fee"|"academic"|...,
        "status":              "complete"|"pending"|"failed"|"overdue",
        "due_date":            "2026-04-30",
        "completed_date":      "2026-04-25",   # optional
        "notes":               "...",
    }

Design note: the platform's first-class ``apps.compliance.ComplianceCheck`` is a
REGION-scoped regulatory model (required ``region``→RegionConfig +
``requirement``→RegionalComplianceRequirement FKs, no ``school`` column) — a
provisioning contract that per-subject migration rows can't satisfy without
fabricating bogus regulatory config. Rather than force-fit (which
IntegrityError-quarantined every row) or invent regulatory rows, we PRESERVE each
compliance row losslessly as a ``DynamicFieldValue`` custom record keyed to a
stable (subject, category, date) identity, so the data migrates and is visible.
Re-runs update the same record; distinct records stay distinct.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    persist_dfv_extras,
    record_row_error,
)
from .base import Lander, LanderContext, LanderResult, register
from .reason_codes import LANDER_ERROR, MISSING_REQUIRED


class ComplianceLander(Lander):
    domain = "compliance"
    # Persists the ENTIRE row (every non-empty key) to DynamicFieldValue, so it
    # already captures all custom_fields.*/_unmapped.* residuals itself.
    sweeps_custom_columns = True

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        result = LanderResult()
        for row in canonical_rows:
            category = (row.get("category") or row.get("check_type") or "").strip()
            if not category:
                record_row_error(
                    result,
                    row,
                    f"compliance: missing category/check_type in {row!r}",
                    reason_code=MISSING_REQUIRED,
                )
                continue
            subject_ext = (row.get("subject_external_id") or "").strip()
            due = coerce_date(row.get("due_date"))
            completed = coerce_date(row.get("completed_date"))
            key_date = (completed or due or _dt.date.today()).isoformat()
            # Stable per-record identity → re-runs update the same custom record
            # instead of duplicating; distinct (subject, category, date) stay distinct.
            record_key = f"{subject_ext or 'unknown'}:{category}:{key_date}"[:64]
            record = {k: str(v) for k, v in row.items() if v not in (None, "")}

            if ctx.dry_run:
                result.created += 1
                continue
            try:
                persist_dfv_extras(
                    ctx=ctx,
                    entity_type="compliance",
                    entity_id=record_key,
                    extras={"record": record},
                    result=result,
                )
                result.created += 1
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"compliance preserve failed for {category} @ {key_date}: "
                    f"{type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result


register("compliance", ComplianceLander())
