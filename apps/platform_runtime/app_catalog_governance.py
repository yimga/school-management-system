"""Marketplace lifecycle governance contracts."""

from __future__ import annotations

from typing import Any


REVIEW_STATES = ("submitted", "in_review", "approved", "rejected", "published", "suspended", "deprecated")
PARTNER_STATES = ("draft_partner", "verified_partner", "trusted_partner", "suspended_partner")


def build_scope_consent(app: dict[str, Any]) -> dict[str, Any]:
    scopes = list(app.get("scopes") or app.get("manifest", {}).get("scopes") or [])
    return {
        "app_key": app.get("app_key") or app.get("slug"),
        "requested_scopes": scopes,
        "data_access": [scope.split(":")[0] for scope in scopes],
        "tenant_impact": app.get("tenant_impact", "tenant_scoped"),
        "billing_impact": app.get("billing_model", "metadata_ready_only"),
        "webhook_impact": list(app.get("webhooks") or []),
        "uninstall_posture": "revoke_scopes_disable_webhooks_preserve_audit",
        "consent_required": bool(scopes),
    }


def evaluate_app_publish_readiness(app: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "review_approved": app.get("review_state") in {"approved", "published"},
        "security_review": app.get("security_review") == "approved",
        "privacy_review": app.get("privacy_review") == "approved",
        "support_contact": bool(app.get("support_contact")),
        "docs": bool(app.get("docs_url")),
        "scope_consent": bool(build_scope_consent(app)["requested_scopes"]),
        "billing_truth": app.get("settlement_live") is not True or bool(app.get("settlement_proof")),
    }
    return {
        "ok": all(checks.values()),
        "review_states": REVIEW_STATES,
        "partner_states": PARTNER_STATES,
        "checks": checks,
        "external_readiness": "live_verified" if app.get("settlement_proof") else "external_required",
        "errors": [name for name, passed in checks.items() if not passed],
    }


def sandbox_install_plan(app: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
    return {
        "app_key": app.get("app_key") or app.get("slug"),
        "tenant_id": tenant_id,
        "sandbox_install": True,
        "test_payloads": list(app.get("test_payloads") or ["ping", "sample_event"]),
        "webhook_test_required": bool(app.get("webhooks")),
        "usage_test_required": app.get("billing_model") == "usage",
        "audit_required": True,
    }


def uninstall_plan(app: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
    return {
        "app_key": app.get("app_key") or app.get("slug"),
        "tenant_id": tenant_id,
        "steps": [
            "revoke_scopes",
            "disable_webhooks",
            "stop_usage_meter",
            "preserve_audit",
            "record_tenant_data_retention_note",
        ],
        "rollback_supported": True,
    }
