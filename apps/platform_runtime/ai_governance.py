"""
Tenant + platform AI governance — operational intelligence defaults.

- Platform flag ``RUNMYCAMPUS_AI_ENABLED`` must be set for any LLM path.
- Per-tenant policy lives in ``School.settings["ai_policy"]`` (JSON), e.g.::

    {
      "tenant_ai_enabled": true,
      "allow_external_providers": false,
      "allow_external_student_pii": false
    }

- External network + paid APIs require both env ``RUNMYCAMPUS_AI_ALLOW_EXTERNAL``
  and tenant ``allow_external_providers`` when a school is present.
- Student PII must not leave the trust boundary unless tenant explicitly allows it.
"""

from __future__ import annotations

import os
from typing import Any


def read_tenant_ai_policy(school) -> dict[str, Any]:
    """Return normalized ai_policy dict from School.settings (may be empty)."""
    if school is None:
        return {}
    raw = getattr(school, "settings", None)
    if not isinstance(raw, dict):
        return {}
    pol = raw.get("ai_policy")
    return dict(pol) if isinstance(pol, dict) else {}


def _northstar_ai_enabled() -> bool:
    return os.environ.get("RUNMYCAMPUS_AI_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _external_network_allowed_env() -> bool:
    return os.environ.get("RUNMYCAMPUS_AI_ALLOW_EXTERNAL", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def resolve_effective_external_network(*, school) -> bool:
    """
    External inference is allowed only when env permits AND tenant opts in
    (when school is present).
    """
    if not _external_network_allowed_env():
        return False
    if school is None:
        return True
    pol = read_tenant_ai_policy(school)
    return bool(pol.get("allow_external_providers"))


def resolve_effective_enabled(*, school) -> bool:
    """Global gate AND tenant may disable explicitly via ai_policy.tenant_ai_enabled=False."""
    if not _northstar_ai_enabled():
        return False
    if school is None:
        return True
    pol = read_tenant_ai_policy(school)
    if pol.get("tenant_ai_enabled") is False:
        return False
    return True


def resolve_allow_external_pii(*, school) -> bool:
    """Explicit tenant permission to include identifiable student data off-box."""
    if school is None:
        return False
    pol = read_tenant_ai_policy(school)
    return bool(pol.get("allow_external_student_pii"))


def get_public_ai_governance_context(*, school) -> dict[str, Any]:
    """
    Template-safe summary (no secrets). For banners and operator UX.
    """
    pol = read_tenant_ai_policy(school)
    enabled = resolve_effective_enabled(school=school)
    ext_net = resolve_effective_external_network(school=school)
    return {
        "platform_ai_env_enabled": _northstar_ai_enabled(),
        "tenant_ai_enabled": pol.get("tenant_ai_enabled"),
        "effective_ai_enabled": enabled,
        "local_first": True,
        "external_network_effective": ext_net,
        "external_opt_in_required": True,
        "external_student_pii_allowed": resolve_allow_external_pii(school=school),
        "audit_prompts_metadata": True,
    }
