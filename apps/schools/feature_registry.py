"""
Feature registry: module codes that can be enabled per school (Phase 3).
School.features is JSONB {"library": true, "transport": false}; sidebar/API filter by has_feature(code).
"""
from typing import TypedDict


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
]


def get_available_modules():
    """Return list of module specs for module market UI."""
    return list(FEATURE_REGISTRY)


def get_module_by_code(code: str) -> ModuleSpec | None:
    for m in FEATURE_REGISTRY:
        if m.get("code") == code:
            return m
    return None
