"""Buyer trust and procurement evidence packet contracts."""

from __future__ import annotations

from typing import Any


def build_procurement_packet(*, tenant_id: str = "", external_status: dict[str, Any] | None = None) -> dict[str, Any]:
    external_status = external_status or {}
    psp_live = bool(external_status.get("psp_live_verified") and external_status.get("psp_evidence_path"))
    certifications = external_status.get("certifications") or []
    return {
        "tenant_id": tenant_id,
        "security_summary": "Role-based access, tenant isolation, audited sensitive actions, and controlled impersonation.",
        "data_handling_summary": "Tenant-scoped education records with export and access audit posture.",
        "tenant_isolation_summary": "Tenant routes and configuration surfaces are separated from platform configuration.",
        "offline_posture": "Offline readiness is surfaced with conflict and sync governance.",
        "audit_posture": "Sensitive actions require actor, timestamp, tenant/scope, reason, event, and evidence path.",
        "external_dependency_status": {
            "psp": "live_verified" if psp_live else "external_required",
            "settlement": "external_required",
            "certifications": certifications,
        },
        "compliance_status": "evidence_ready_repo_scope",
        "implementation_process": "preview, mapping, validation, approval, apply, monitor, rollback posture.",
        "support_process": "support level, escalation, owner, and SLA are package-governed.",
        "honesty": {
            "claims_soc2": "SOC 2 certified" in certifications,
            "claims_iso27001": "ISO 27001 certified" in certifications,
            "claims_pci": "PCI certified" in certifications,
            "psp_live_ready_claim_allowed": psp_live,
        },
    }
