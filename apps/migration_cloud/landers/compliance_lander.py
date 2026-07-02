"""Compliance lander — persists canonical compliance-check rows into ``apps.compliance.ComplianceCheck``.

Canonical row shape::

    {
        "subject_external_id": "PS-1029",      # informational — subject the check pertains to
        "category":            "immunization"|"safeguarding"|"fee"|"academic"|...,
        "status":              "complete"|"pending"|"failed"|"overdue",
        "due_date":            "2026-04-30",
        "completed_date":      "2026-04-25",   # optional
        "notes":               "...",
    }

Upsert key: (region or default, check_type, check_date). Compliance
records are immutable history; re-runs of the same bundle never
duplicate.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class ComplianceLander(Lander):
    domain = "compliance"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.compliance.models import ComplianceCheck
        except ImportError as exc:
            raise LanderError(
                f"ComplianceLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        c_fields = model_field_names(ComplianceCheck)

        for row in canonical_rows:
            check_type = (row.get("category") or row.get("check_type") or "").strip()
            if not check_type:
                result.quarantined += 1
                result.errors.append(
                    f"compliance: missing category/check_type in {row!r}"
                )
                continue
            due = coerce_date(row.get("due_date"))
            completed = coerce_date(row.get("completed_date"))
            check_date = completed or due or _dt.date.today()
            status = (row.get("status") or "pending").strip().lower()
            notes = (row.get("notes") or row.get("findings") or "").strip()
            subject_ext = (row.get("subject_external_id") or "").strip()

            defaults: dict[str, Any] = {}
            if "check_type" in c_fields:
                defaults["check_type"] = check_type[:64]
            if "status" in c_fields:
                defaults["status"] = status[:32]
            if "findings" in c_fields and notes:
                defaults["findings"] = notes[:2000]
            if "remediation_notes" in c_fields and notes:
                defaults["remediation_notes"] = notes[:2000]
            if "remediation_required" in c_fields:
                defaults["remediation_required"] = status in ("failed", "overdue", "pending")
            if "remediation_deadline" in c_fields and due is not None:
                defaults["remediation_deadline"] = due
            if "issues_found" in c_fields:
                defaults["issues_found"] = 1 if status in ("failed", "overdue") else 0
            if "issues_resolved" in c_fields:
                defaults["issues_resolved"] = 1 if status == "complete" else 0
            defaults = filter_to_model_fields(defaults, ComplianceCheck)

            lookup_kwargs: dict[str, Any] = {}
            if "check_type" in c_fields:
                lookup_kwargs["check_type"] = check_type[:64]
            if "check_date" in c_fields:
                lookup_kwargs["check_date"] = check_date

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = ComplianceCheck.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                from ._helpers import upsert_with_conflict_detection
                _co_legacy = f"{check_type}:{check_date.isoformat()}:{subject_ext}"
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="compliance", model=ComplianceCheck,
                    lookup=lookup_kwargs, defaults=defaults, legacy_id=_co_legacy,
                )
                if preserved:
                    result.skipped += 1
                    record_id_mapping(ctx=ctx, legacy_id=_co_legacy, canonical_obj=obj, domain="compliance")
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
                record_id_mapping(
                    ctx=ctx,
                    legacy_id=_co_legacy,
                    canonical_obj=obj, domain="compliance",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"compliance upsert failed for {check_type} @ {check_date}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return result


register("compliance", ComplianceLander())
