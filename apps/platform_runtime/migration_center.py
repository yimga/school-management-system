"""Tenant-safe migration center contracts.

These helpers provide deterministic preview, mapping, quarantine, quality, and
apply posture without writing imported school data.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


MIGRATION_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "students": {
        "required": ["admission_number", "first_name", "last_name"],
        "optional": ["email", "date_of_birth", "class_code", "guardian_email"],
        "duplicate_keys": ["admission_number", "email"],
    },
    "teachers": {
        "required": ["staff_number", "first_name", "last_name"],
        "optional": ["email", "department", "phone"],
        "duplicate_keys": ["staff_number", "email"],
    },
    "guardians": {
        "required": ["first_name", "last_name", "student_admission_number"],
        "optional": ["email", "phone", "relationship"],
        "duplicate_keys": ["email", "phone"],
    },
    "classes": {
        "required": ["class_code", "name"],
        "optional": ["level", "section", "homeroom_teacher"],
        "duplicate_keys": ["class_code"],
    },
    "invoices": {
        "required": ["invoice_number", "student_admission_number", "amount"],
        "optional": ["due_date", "fee_category", "currency"],
        "duplicate_keys": ["invoice_number"],
    },
    "receipts": {
        "required": ["receipt_number", "invoice_number", "amount"],
        "optional": ["paid_at", "method", "reference"],
        "duplicate_keys": ["receipt_number", "reference"],
    },
}


def sample_template(entity: str) -> dict[str, Any]:
    template = MIGRATION_TEMPLATES[entity]
    return {
        "entity": entity,
        "columns": template["required"] + template["optional"],
        "required": template["required"],
        "optional": template["optional"],
    }


def build_field_mapping(
    source_fields: list[str],
    *,
    entity: str,
    transforms: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    template = MIGRATION_TEMPLATES[entity]
    transforms = transforms or {}
    allowed = set(template["required"] + template["optional"])
    rows = []
    for source in source_fields:
        destination = source if source in allowed else ""
        rows.append(
            {
                "source_field": source,
                "destination_field": destination,
                "transformation": transforms.get(source, ""),
                "required": str(destination in template["required"]).lower(),
                "validation_status": "mapped" if destination else "unmapped",
            }
        )
    return rows


def _signature(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def preview_migration(
    *,
    entity: str,
    rows: list[dict[str, Any]],
    tenant_id: str,
    mapping: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    template = MIGRATION_TEMPLATES[entity]
    invalid_rows = []
    duplicate_candidates = []
    seen: dict[str, int] = {}
    required = template["required"]
    duplicate_keys = template["duplicate_keys"]

    for index, row in enumerate(rows, start=1):
        missing = [field for field in required if not str(row.get(field) or "").strip()]
        if missing:
            invalid_rows.append({"row": index, "reason": f"Missing required fields: {', '.join(missing)}"})
        for key in duplicate_keys:
            token = str(row.get(key) or "").strip().lower()
            if not token:
                continue
            compound = f"{key}:{token}"
            if compound in seen:
                duplicate_candidates.append(
                    {"row": index, "matches_row": seen[compound], "field": key, "value": token}
                )
            else:
                seen[compound] = index

    quality = calculate_data_quality(rows=rows, invalid_count=len(invalid_rows), duplicate_count=len(duplicate_candidates), required=required)
    return {
        "ok": not invalid_rows,
        "preview_id": f"{tenant_id}:{entity}:{_signature(rows)}",
        "entity": entity,
        "tenant_id": tenant_id,
        "entity_count": len(rows),
        "required_columns": required,
        "optional_columns": template["optional"],
        "field_mapping": mapping or build_field_mapping(list(rows[0].keys()) if rows else [], entity=entity),
        "missing_fields": sorted({field for row in rows for field in required if not str(row.get(field) or "").strip()}),
        "duplicate_candidates": duplicate_candidates,
        "invalid_rows": invalid_rows,
        "quarantine": build_quarantine(invalid_rows),
        "rollback_posture": {
            "can_revert_created_records": True,
            "manual_review_required": bool(duplicate_candidates),
            "destructive_delete_forbidden": True,
        },
        "data_quality_score": quality,
        "audit_required": True,
    }


def build_quarantine(invalid_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "row": str(row["row"]),
            "reason": str(row["reason"]),
            "fix_action": "correct_and_retry",
            "ignore_requires_reason": "true",
            "audit_required": "true",
        }
        for row in invalid_rows
    ]


def calculate_data_quality(
    *,
    rows: list[dict[str, Any]],
    invalid_count: int,
    duplicate_count: int,
    required: list[str],
) -> dict[str, Any]:
    total = max(len(rows), 1)
    complete_required = 0
    for row in rows:
        if all(str(row.get(field) or "").strip() for field in required):
            complete_required += 1
    completeness = complete_required / total
    penalty = min(0.8, (invalid_count + duplicate_count) / total)
    score = max(0, round((completeness - penalty) * 100))
    return {
        "score": score,
        "completeness": round(completeness, 2),
        "duplicates": duplicate_count,
        "invalid_values": invalid_count,
        "readiness": "ready" if score >= 90 else "needs_review",
    }


def apply_preview(preview: dict[str, Any], *, tenant_id: str, actor: str, idempotency_key: str = "") -> dict[str, Any]:
    if preview.get("tenant_id") != tenant_id:
        return {"ok": False, "errors": ["Tenant cannot apply a migration preview for another school."]}
    if not preview.get("preview_id"):
        return {"ok": False, "errors": ["Migration apply requires a preview."]}
    return {
        "ok": preview.get("ok", False),
        "migration_run_id": idempotency_key or preview["preview_id"],
        "tenant_id": tenant_id,
        "actor": actor,
        "status": "ready_to_apply" if preview.get("ok") else "quarantined",
        "audit": {
            "actor": actor,
            "tenant_id": tenant_id,
            "event": "migration_apply_requested",
            "preview_id": preview["preview_id"],
        },
    }
