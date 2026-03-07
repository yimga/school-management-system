"""
Unified feature-toggle resolver.

Priority order:
1) School-specific override (FeatureToggleState with school set)
2) Global override (FeatureToggleState with school null)
3) Definition default
4) Caller fallback
"""

from __future__ import annotations

from typing import Optional

from django.db import DatabaseError, OperationalError, ProgrammingError

from apps.siteconfig.models import FeatureToggleDefinition, FeatureToggleState


def _normalized_key(key: str) -> str:
    return (key or "").strip().lower().replace(" ", "_")


def ensure_toggle_definition(
    key: str,
    *,
    label: str | None = None,
    description: str = "",
    category: str = "",
    scope: str = FeatureToggleDefinition.Scope.SCHOOL,
    default_enabled: bool = False,
    metadata: dict | None = None,
) -> FeatureToggleDefinition:
    normalized = _normalized_key(key)
    defaults = {
        "label": label or normalized,
        "description": description,
        "category": category,
        "scope": scope,
        "default_enabled": bool(default_enabled),
        "metadata": metadata or {},
    }
    definition, _ = FeatureToggleDefinition.objects.get_or_create(key=normalized, defaults=defaults)
    return definition


def resolve_toggle(
    key: str,
    *,
    school=None,
    fallback: Optional[bool] = None,
) -> Optional[bool]:
    normalized = _normalized_key(key)
    if not normalized:
        return fallback
    try:
        definition = (
            FeatureToggleDefinition.objects.filter(key=normalized, is_active=True)
            .only("id", "default_enabled")
            .first()
        )
        if not definition:
            return fallback

        if school is not None:
            school_state = (
                FeatureToggleState.objects.filter(definition=definition, school=school)
                .values_list("is_enabled", flat=True)
                .first()
            )
            if school_state is not None:
                return bool(school_state)

        global_state = (
            FeatureToggleState.objects.filter(definition=definition, school__isnull=True)
            .values_list("is_enabled", flat=True)
            .first()
        )
        if global_state is not None:
            return bool(global_state)

        return bool(definition.default_enabled)
    except (OperationalError, ProgrammingError, DatabaseError):
        return fallback


def set_toggle_state(
    key: str,
    *,
    enabled: bool,
    school=None,
    user=None,
    label: str | None = None,
    description: str = "",
    category: str = "",
    scope: str = FeatureToggleDefinition.Scope.SCHOOL,
    default_enabled: bool = False,
    metadata: dict | None = None,
) -> FeatureToggleState:
    definition = ensure_toggle_definition(
        key,
        label=label,
        description=description,
        category=category,
        scope=scope,
        default_enabled=default_enabled,
        metadata=metadata,
    )
    state, _ = FeatureToggleState.objects.get_or_create(
        definition=definition,
        school=school,
        defaults={"is_enabled": bool(enabled), "updated_by": user},
    )
    if state.is_enabled != bool(enabled) or state.updated_by_id != getattr(user, "id", None):
        state.is_enabled = bool(enabled)
        state.updated_by = user
        state.save(update_fields=["is_enabled", "updated_by", "updated_at"])
    return state


def resolve_module_enabled(code: str, *, school=None, fallback: Optional[bool] = None) -> bool:
    module_code = (code or "").strip().lower()
    if not module_code:
        return bool(fallback)
    resolved = resolve_toggle(f"module.{module_code}", school=school, fallback=fallback)
    return bool(resolved)
