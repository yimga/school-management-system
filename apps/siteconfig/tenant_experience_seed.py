"""Provision-time tenant experience policy seed (Phase B)."""

from __future__ import annotations

from typing import Any

from apps.siteconfig.tenant_experience_policy import (
    persist_tenant_experience_policy,
    tenant_experience_policy_defaults,
)
from apps.siteconfig.tenant_experience_presets import apply_experience_preset, PRESET_MINIMAL_V3

_PROVISION_SEEDED_KEY = "_provision_seeded"


def build_provision_tenant_experience_policy() -> dict[str, Any]:
    """Default policy for newly provisioned tenants."""
    policy = apply_experience_preset(PRESET_MINIMAL_V3)
    policy[_PROVISION_SEEDED_KEY] = True
    return policy


def ensure_tenant_experience_policy(site: Any, *, force: bool = False) -> dict[str, Any]:
    """Idempotent seed into cockpit_payload.tenant_experience_policy."""
    payload = getattr(site, "cockpit_payload", None) or {}
    if not isinstance(payload, dict):
        payload = {}
    existing = payload.get("tenant_experience_policy")
    if (
        not force
        and isinstance(existing, dict)
        and existing.get(_PROVISION_SEEDED_KEY)
    ):
        return existing
    if not force and isinstance(existing, dict) and existing:
        return existing
    policy = build_provision_tenant_experience_policy()
    persist_tenant_experience_policy(site, policy)
    return policy


__all__ = [
    "build_provision_tenant_experience_policy",
    "ensure_tenant_experience_policy",
]
