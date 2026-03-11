"""
Tenant runtime precedence chain.

Canonical order:
platform default -> registry default -> blueprint default -> policy bundle ->
entitlement/plan gate -> tenant override -> sandbox/preview override
"""
from __future__ import annotations

PRECEDENCE_ORDER = [
    "platform_default",
    "registry_default",
    "blueprint_default",
    "policy_bundle",
    "entitlement_gate",
    "tenant_override",
    "sandbox_override",
]

PRECEDENCE_ALIASES = {
    "platform": "platform_default",
    "region": "registry_default",
    "registry": "registry_default",
    "blueprint": "blueprint_default",
    "policy": "policy_bundle",
    "plan": "entitlement_gate",
    "entitlement": "entitlement_gate",
    "tenant": "tenant_override",
    "sandbox": "sandbox_override",
    "preview": "sandbox_override",
}

PRECEDENCE_LABELS = {
    "platform_default": "Platform default",
    "registry_default": "Registry default",
    "blueprint_default": "Blueprint default",
    "policy_bundle": "Policy bundle",
    "entitlement_gate": "Entitlement/plan gate",
    "tenant_override": "Tenant override",
    "sandbox_override": "Sandbox/preview override",
}

PRECEDENCE_INDEX = {key: index for index, key in enumerate(PRECEDENCE_ORDER)}


def normalize_scope(scope: str | None) -> str:
    if not scope:
        return ""
    normalized = str(scope).strip().lower()
    return PRECEDENCE_ALIASES.get(normalized, normalized)


def precedence_rank(scope: str) -> int:
    """Return rank for scope (higher = wins when merging)."""
    return PRECEDENCE_INDEX.get(normalize_scope(scope), -1)


def describe_precedence_chain() -> list[dict[str, object]]:
    return [
        {
            "key": key,
            "label": PRECEDENCE_LABELS[key],
            "rank": PRECEDENCE_INDEX[key],
        }
        for key in PRECEDENCE_ORDER
    ]


def merge_by_precedence(*, values: list[tuple[str, object]]) -> object | None:
    """
    Given [(scope, value), ...], return the value with highest precedence.
    """
    if not values:
        return None
    best_scope = max(values, key=lambda item: precedence_rank(item[0]))
    return best_scope[1]
