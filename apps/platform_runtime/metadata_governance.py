"""Governed metadata lifecycle contracts for the configuration center.

The metadata catalog remains the source of truth. These helpers describe the
preview, impact, drift, and audit posture around proposed metadata changes
without mutating tenant or platform state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


PRIVACY_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


@dataclass(frozen=True)
class MetadataChange:
    entity: str
    field: str = ""
    action: str = "update"
    current_privacy: str = "internal"
    proposed_privacy: str = "internal"
    owner: str = ""
    reason: str = ""
    destructive: bool = False


def _rank(value: str) -> int:
    return PRIVACY_RANK.get(str(value or "").lower(), PRIVACY_RANK["internal"])


def _normalize_change(raw: MetadataChange | dict[str, Any]) -> MetadataChange:
    if isinstance(raw, MetadataChange):
        return raw
    return MetadataChange(
        entity=str(raw.get("entity") or ""),
        field=str(raw.get("field") or ""),
        action=str(raw.get("action") or "update"),
        current_privacy=str(raw.get("current_privacy") or "internal"),
        proposed_privacy=str(raw.get("proposed_privacy") or "internal"),
        owner=str(raw.get("owner") or ""),
        reason=str(raw.get("reason") or ""),
        destructive=bool(raw.get("destructive")),
    )


def build_metadata_change_set(
    changes: list[MetadataChange | dict[str, Any]],
    *,
    current_version: str = "1.0",
    proposed_version: str = "1.1",
    scope: str = "platform",
    tenant_id: str = "",
) -> dict[str, Any]:
    normalized = [_normalize_change(change) for change in changes]
    errors: list[str] = []
    privacy_changes: list[dict[str, str]] = []
    affected_entities = sorted({change.entity for change in normalized if change.entity})
    affected_fields = sorted(
        {
            f"{change.entity}.{change.field}"
            for change in normalized
            if change.entity and change.field
        }
    )

    for change in normalized:
        if not change.entity:
            errors.append("Metadata change is missing entity.")
        if not change.owner:
            errors.append(f"{change.entity or 'Unknown'} metadata change is missing owner.")
        if _rank(change.proposed_privacy) < _rank(change.current_privacy):
            errors.append(
                f"{change.entity}.{change.field or '*'} attempts to downgrade privacy "
                f"from {change.current_privacy} to {change.proposed_privacy}."
            )
        if change.current_privacy != change.proposed_privacy:
            privacy_changes.append(
                {
                    "entity": change.entity,
                    "field": change.field,
                    "from": change.current_privacy,
                    "to": change.proposed_privacy,
                }
            )

    destructive = any(change.destructive or change.action in {"delete", "drop"} for change in normalized)
    requires_approval = destructive or bool(privacy_changes) or scope == "platform"
    return {
        "ok": not errors,
        "scope": scope,
        "tenant_id": tenant_id if scope == "tenant" else "",
        "current_version": current_version,
        "proposed_version": proposed_version,
        "affected_entities": affected_entities,
        "affected_fields": affected_fields,
        "privacy_changes": privacy_changes,
        "requires_approval": requires_approval,
        "rollback_coverage": {
            "snapshot_required": True,
            "destructive_change": destructive,
            "non_destructive_supported": not destructive,
            "manual_review_required": destructive,
        },
        "changes": [change.__dict__ for change in normalized],
        "errors": errors,
    }


def preview_metadata_change_set(
    change_set: dict[str, Any],
    *,
    tenant_context: str = "",
) -> dict[str, Any]:
    scope = change_set.get("scope") or "platform"
    tenant_safe = scope == "tenant" and bool(tenant_context) or scope == "platform"
    return {
        "ok": bool(change_set.get("ok")) and tenant_safe,
        "non_mutating": True,
        "tenant_safe": tenant_safe,
        "leaks_other_tenants": False,
        "scope": scope,
        "tenant_context": tenant_context if scope == "tenant" else "",
        "affected_entities": change_set.get("affected_entities", []),
        "affected_fields": change_set.get("affected_fields", []),
        "privacy_audit_required": bool(change_set.get("privacy_changes")),
        "rollback_coverage": change_set.get("rollback_coverage", {}),
        "errors": list(change_set.get("errors", [])),
    }


def analyze_metadata_impact(change_set: dict[str, Any]) -> dict[str, Any]:
    entities = set(change_set.get("affected_entities", []))
    affected_modules = sorted(
        module
        for module, watched in {
            "people": {"Person", "Student", "Guardian"},
            "academics": {"Enrollment", "Course", "Class"},
            "finance": {"Invoice", "Payment"},
            "reports": {"Student", "Enrollment", "Invoice", "Payment"},
            "imports_exports": {"Person", "Student", "Guardian", "Invoice"},
            "dashboards": {"Student", "Invoice", "Payment"},
        }.items()
        if entities.intersection(watched)
    )
    return {
        "affected_modules": affected_modules,
        "affected_reports": ["student360", "finance_summary"] if entities else [],
        "affected_imports_exports": "imports_exports" in affected_modules,
        "affected_dashboards": "dashboards" in affected_modules,
        "privacy_classification_impact": change_set.get("privacy_changes", []),
        "regional_variant_impact": bool(entities.intersection({"Course", "Enrollment"})),
        "approval_required": bool(change_set.get("requires_approval")),
    }


def detect_metadata_drift(
    registry_rows: list[dict[str, Any]],
    *,
    generated_at: datetime | None = None,
    now: datetime | None = None,
    max_age_hours: int = 24,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    stale = False
    if generated_at is None:
        stale = True
    else:
        stale = (now - generated_at).total_seconds() > max_age_hours * 3600
    findings = []
    for row in registry_rows:
        missing = [
            key
            for key in ("owner", "scope", "proof", "test")
            if not str(row.get(key) or "").strip()
        ]
        if stale or missing:
            findings.append(
                {
                    "name": row.get("name", ""),
                    "missing": missing,
                    "stale_generated_artifact": stale,
                    "severity": "high" if "owner" in missing or "proof" in missing else "medium",
                    "primary_action": "Assign owner/proof/test and regenerate registry.",
                }
            )
    return {
        "ok": not findings,
        "stale_generated_artifact": stale,
        "finding_count": len(findings),
        "findings": findings,
    }


def build_metadata_audit_event(
    *,
    actor: str,
    action: str,
    entity: str,
    field: str = "",
    scope: str = "platform",
    tenant_id: str = "",
    reason: str = "",
    evidence_path: str = "",
    timestamp: datetime | None = None,
) -> dict[str, str]:
    occurred_at = timestamp or datetime.now(timezone.utc)
    return {
        "actor": actor,
        "action": action,
        "entity": entity,
        "field": field,
        "scope": scope,
        "tenant_id": tenant_id if scope == "tenant" else "",
        "reason": reason,
        "timestamp": occurred_at.isoformat(),
        "evidence_path": evidence_path,
    }
