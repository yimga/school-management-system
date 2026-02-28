"""
Feature registry: module codes that can be enabled per school (Phase 3).
School.features is JSONB {"library": true, "transport": false}; sidebar/API filter by has_feature(code).
"""
from __future__ import annotations

from typing import TypedDict

from apps.siteconfig.models import FeatureToggleDefinition


class ModuleSpec(TypedDict, total=False):
    code: str
    name: str
    description: str
    price: str  # optional, e.g. "Free" or "1000 XAF/year"


# Registry of available modules (code -> ModuleSpec). Extend as needed.
FEATURE_REGISTRY: list[ModuleSpec] = [
    {"code": "library", "name": "Library", "description": "Library management and book lending.", "price": "Free"},
    {"code": "transport", "name": "Transport", "description": "School bus and transport fee management.", "price": "Free"},
    {"code": "canteen", "name": "Canteen", "description": "Canteen and meal plans.", "price": "Free"},
    {"code": "parent_chat", "name": "Parent Chat", "description": "Direct messaging with parents.", "price": "Free"},
    {"code": "cahier_de_texte", "name": "Cahier de Texte", "description": "Homework and class diary.", "price": "Free"},
    {"code": "offline_mode", "name": "Offline Mode", "description": "Offline sync for marks and attendance (requires Offline Mode enabled globally in Feature Control).", "price": "Free"},
    # Plan XVI: Blueprint extras
    {"code": "alumni", "name": "Alumni", "description": "Alumni network and post-graduation tracking.", "price": "Free"},
    {"code": "dormitory", "name": "Dormitory", "description": "Boarding and dorm management.", "price": "Free"},
]


def _definition_key(code: str) -> str:
    return f"module.{(code or '').strip().lower()}"


def ensure_module_registry_seeded() -> None:
    for module in FEATURE_REGISTRY:
        code = str(module.get("code") or "").strip().lower()
        if not code:
            continue
        key = _definition_key(code)
        defaults = {
            "label": str(module.get("name") or code.title()),
            "description": str(module.get("description") or ""),
            "category": "modules",
            "scope": FeatureToggleDefinition.Scope.SCHOOL,
            "default_enabled": False,
            "is_active": True,
            "metadata": {"price": str(module.get("price") or "Free")},
        }
        definition, created = FeatureToggleDefinition.objects.get_or_create(key=key, defaults=defaults)
        if created:
            continue
        changed = False
        if definition.category != "modules":
            definition.category = "modules"
            changed = True
        if not definition.label and defaults["label"]:
            definition.label = defaults["label"]
            changed = True
        if not definition.description and defaults["description"]:
            definition.description = defaults["description"]
            changed = True
        metadata = dict(getattr(definition, "metadata", None) or {})
        if "price" not in metadata:
            metadata["price"] = defaults["metadata"]["price"]
            definition.metadata = metadata
            changed = True
        if changed:
            definition.save(update_fields=["category", "label", "description", "metadata", "updated_at"])


def get_available_modules():
    """Return list of module specs for module market UI."""
    ensure_module_registry_seeded()
    rows = (
        FeatureToggleDefinition.objects.filter(
            category="modules",
            scope=FeatureToggleDefinition.Scope.SCHOOL,
            is_active=True,
        )
        .order_by("label", "key")
    )
    modules: list[ModuleSpec] = []
    for row in rows:
        key = str(row.key or "")
        code = key[7:] if key.startswith("module.") else key
        if not code:
            continue
        metadata = dict(getattr(row, "metadata", None) or {})
        modules.append(
            {
                "code": code,
                "name": str(row.label or code.title()),
                "description": str(row.description or ""),
                "price": str(metadata.get("price") or "Free"),
            }
        )
    if modules:
        return modules
    return list(FEATURE_REGISTRY)


def get_module_by_code(code: str) -> ModuleSpec | None:
    for m in FEATURE_REGISTRY:
        if m.get("code") == code:
            return m
    return None
