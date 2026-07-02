"""
Feature registry: module codes that can be enabled per school (Phase 3).
School.features is JSONB {"library": true, "transport": false}; sidebar/API filter by has_feature(code).
"""

from __future__ import annotations

from typing import TypedDict

from apps.policies_rules.models import FeatureToggleDefinition


class ModuleSpec(TypedDict, total=False):
    code: str
    name: str
    description: str
    price: str  # optional, e.g. "Free" or "1000 XAF/year"


# Registry of available modules (code -> ModuleSpec). Extend as needed.
# N17: human-readable impact before module activation (module market).
MODULE_IMPACT_BULLETS: dict[str, list[str]] = {
    "library": [
        "Navigation and library workflows become visible for this school.",
        "Staff can manage catalog and lending when library UI is used.",
    ],
    "transport": [
        "Transport routes and fee tools appear for authorized roles.",
    ],
    "canteen": [
        "Canteen and meal-plan surfaces unlock for this tenant.",
    ],
    "parent_chat": [
        "Parent messaging features depend on this flag; review privacy policy.",
    ],
    "cahier_de_texte": [
        "Homework / class diary modules align with this toggle.",
    ],
    "offline_mode": [
        "Mobile offline sync is allowed only if global Offline Mode is also enabled.",
        "Devices must register before syncing queued changes.",
    ],
    "canary_tenant": [
        "Marks tenant for staged rollouts; may receive newer feature flags first.",
    ],
    "alumni": [
        "Alumni tracking and post-graduation workflows become available.",
    ],
    "dormitory": [
        "Boarding and dorm management surfaces unlock.",
    ],
    "inventory": [
        "Stock and location lines for school assets and supplies.",
    ],
    "clinic": [
        "Health record visibility for leadership; handle PHI per policy.",
    ],
    "timetabling": [
        "Published/draft schedule list; generation via scheduler API.",
    ],
    "substitutes": [
        "Staff can log absent teachers and optional cover assignments.",
        "Visible only in Operations hub when module is enabled.",
    ],
    "visitor_log": [
        "Reception can record visitor check-in and check-out for this school.",
        "Review data retention with your privacy policy.",
    ],
    "facilities_ops": [
        "Staff can log maintenance / facilities requests and update status.",
        "Not a full CMMS; use for internal triage until deeper integration.",
    ],
    "pos_stub": [
        "Quick sale lines are recorded for this school (till / event counter).",
        "Not integrated with full inventory or fiscal printers yet.",
    ],
}


def get_module_impact_bullets(code: str) -> list[str]:
    c = (code or "").strip().lower()
    if c in MODULE_IMPACT_BULLETS:
        return list(MODULE_IMPACT_BULLETS[c])
    return [
        "Sidebar and menus reflect this module when active.",
        "Policy cache is refreshed after toggle.",
    ]


FEATURE_REGISTRY: list[ModuleSpec] = [
    {
        "code": "library",
        "name": "Library",
        "description": "Library management and book lending.",
        "price": "Free",
    },
    {
        "code": "transport",
        "name": "Transport",
        "description": "School bus and transport fee management.",
        "price": "Free",
    },
    {
        "code": "canteen",
        "name": "Canteen",
        "description": "Canteen and meal plans.",
        "price": "Free",
    },
    {
        "code": "parent_chat",
        "name": "Parent Chat",
        "description": "Direct messaging with parents.",
        "price": "Free",
    },
    {
        "code": "cahier_de_texte",
        "name": "Cahier de Texte",
        "description": "Homework and class diary.",
        "price": "Free",
    },
    {
        "code": "offline_mode",
        "name": "Offline Mode",
        "description": "Offline sync for marks and attendance (requires Offline Mode enabled globally in Feature Control).",
        "price": "Free",
    },
    {
        "code": "canary_tenant",
        "name": "Canary Tenant",
        "description": "Mark this tenant as canary for staged rollouts (29.4).",
        "price": "Free",
    },
    # Plan XVI: Blueprint extras
    {
        "code": "alumni",
        "name": "Alumni",
        "description": "Alumni network and post-graduation tracking.",
        "price": "Free",
    },
    {
        "code": "dormitory",
        "name": "Dormitory",
        "description": "Boarding and dorm management.",
        "price": "Free",
    },
    {
        "code": "inventory",
        "name": "Inventory",
        "description": "Asset and supply stock by location.",
        "price": "Free",
    },
    {
        "code": "clinic",
        "name": "Clinic / health log",
        "description": "School health record log (leadership visibility).",
        "price": "Free",
    },
    {
        "code": "timetabling",
        "name": "Timetabling",
        "description": "Master schedule list and scheduler integration.",
        "price": "Free",
    },
    {
        "code": "substitutes",
        "name": "Substitutes / cover",
        "description": "Record teacher absence and substitute cover lines.",
        "price": "Free",
    },
    {
        "code": "visitor_log",
        "name": "Visitor log",
        "description": "Front-desk visitor check-in and check-out.",
        "price": "Free",
    },
    {
        "code": "facilities_ops",
        "name": "Facilities / maintenance",
        "description": "Log and track maintenance requests by location.",
        "price": "Free",
    },
    {
        "code": "pos_stub",
        "name": "POS / till (stub)",
        "description": "Record quick point-of-sale lines (events, counters).",
        "price": "Free",
    },
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
            # T21: modules ship default-ON so every tenant (past / present /
            # future) has the full module surface unless an operator explicitly
            # turns one off. An explicit per-school opt-out lives in
            # FeatureToggleState and still wins in resolve_toggle().
            "default_enabled": True,
            "is_active": True,
            "metadata": {"price": str(module.get("price") or "Free")},
        }
        definition, created = FeatureToggleDefinition.objects.get_or_create(
            key=key, defaults=defaults
        )
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
        # T21: bring already-seeded definitions up to the new default-ON baseline.
        # This flips the *definition default* only; a school that explicitly
        # disabled the module has a FeatureToggleState row that still overrides.
        if not definition.default_enabled:
            definition.default_enabled = True
            changed = True
        if changed:
            definition.save(
                update_fields=[
                    "category",
                    "label",
                    "description",
                    "metadata",
                    "default_enabled",
                    "updated_at",
                ]
            )


def get_available_modules():
    """Return list of module specs for module market UI."""
    ensure_module_registry_seeded()
    rows = FeatureToggleDefinition.objects.filter(
        category="modules",
        scope=FeatureToggleDefinition.Scope.SCHOOL,
        is_active=True,
    ).order_by("label", "key")
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
                "impact_bullets": get_module_impact_bullets(code),
            }
        )
    if modules:
        return modules
    return [
        {
            **dict(m),
            "impact_bullets": get_module_impact_bullets(str(m.get("code") or "")),
        }
        for m in FEATURE_REGISTRY
    ]


def get_module_by_code(code: str) -> ModuleSpec | None:
    for m in FEATURE_REGISTRY:
        if m.get("code") == code:
            return m
    return None
