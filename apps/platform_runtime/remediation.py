"""
Centralized tenant-safe remediation payloads for signup, provisioning, and setup flows.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class RemediationPayload:
    code: str
    message: str
    human_action: str = ""
    auto_fix_available: bool = False
    auto_fix_kind: str = ""
    owner_may_apply: bool = False
    suggested_values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_tenant_api_dict(
        self,
        *,
        operator_debug_reference: str = "",
        remediation_action_token: str = "",
    ) -> dict[str, Any]:
        """Phase 13 tenant-safe remediation response shape."""
        token = remediation_action_token or (
            self.auto_fix_kind if self.auto_fix_available and self.auto_fix_kind else ""
        )
        return {
            "error_type": self.code,
            "human_readable_explanation": self.human_action or self.message,
            "remediation_available": self.auto_fix_available or bool(token),
            "remediation_action_token": token,
            "tenant_safe_message": self.message,
            "operator_debug_reference": operator_debug_reference[:128],
            # Back-compat fields consumed by provisioning progress UI
            "code": self.code,
            "human_action": self.human_action,
            "auto_fix_available": self.auto_fix_available,
            "auto_fix_kind": self.auto_fix_kind,
            "owner_may_apply": self.owner_may_apply,
            "suggested_values": dict(self.suggested_values),
        }


_OWNER_AUTO_FIX_KINDS = frozenset(
    {
        "requeue_provision",
        "resend_welcome",
        "retry_dns_sync",
    }
)


def normalize_remediation(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize legacy ``suggested_remediation`` blobs to the canonical API shape."""
    empty = RemediationPayload(code="", message="").to_dict()
    if not raw or not isinstance(raw, dict):
        return empty
    kind = str(raw.get("auto_fix_kind", "") or "").strip()
    auto = bool(raw.get("auto_fix_available"))
    return RemediationPayload(
        code=str(raw.get("code", "") or ""),
        message=str(raw.get("message", "") or raw.get("human_action", "") or "")[:500],
        human_action=str(raw.get("human_action", "") or "")[:500],
        auto_fix_available=auto,
        auto_fix_kind=kind,
        owner_may_apply=auto and kind in _OWNER_AUTO_FIX_KINDS,
        suggested_values=dict(raw.get("suggested_values") or {}),
    ).to_dict()


def signup_slug_taken_remediation(slug: str) -> RemediationPayload:
    base = (slug or "").strip().lower()
    suggestions = []
    if base:
        suggestions = [f"{base}-2", f"{base}-school", f"my-{base}"]
    return RemediationPayload(
        code="signup.slug_taken",
        message="This school URL is already taken. Choose another.",
        human_action="Pick a different subdomain — try adding your city or campus name.",
        auto_fix_available=False,
        suggested_values={"alternatives": suggestions[:3]},
    )


def provisioning_failed_remediation(
    *,
    error: str = "",
    auto_fix_kind: str = "requeue_provision",
) -> RemediationPayload:
    summary = (error or "Provisioning did not complete.").strip()[:500]
    return RemediationPayload(
        code="tenant.provisioning_failed",
        message=summary,
        human_action="Retry setup from your provisioning dashboard or contact support if this repeats.",
        auto_fix_available=True,
        auto_fix_kind=auto_fix_kind,
        owner_may_apply=auto_fix_kind in _OWNER_AUTO_FIX_KINDS,
    )


def from_workflow_run(run: Any | None) -> dict[str, Any]:
    """Map a workflow run's ``suggested_remediation`` field to the canonical dict."""
    if run is None:
        return RemediationPayload(code="", message="").to_dict()
    raw = getattr(run, "suggested_remediation", None) or {}
    if not isinstance(raw, dict):
        return RemediationPayload(code="", message="").to_dict()
    kind = str(raw.get("auto_fix_kind", "") or "").strip()
    auto = bool(raw.get("auto_fix_available"))
    return RemediationPayload(
        code=str(raw.get("code", "tenant.provisioning_failed") or "tenant.provisioning_failed"),
        message=str(raw.get("message", "") or raw.get("human_action", "") or "")[:500],
        human_action=str(raw.get("human_action", "") or "")[:500],
        auto_fix_available=auto,
        auto_fix_kind=kind,
        owner_may_apply=auto and kind in _OWNER_AUTO_FIX_KINDS,
        suggested_values=dict(raw.get("suggested_values") or {}),
    ).to_dict()
