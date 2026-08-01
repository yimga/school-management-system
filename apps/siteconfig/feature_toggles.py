"""
Unified feature-toggle resolver (Phase 10 — 10.2: capability registry with expiry).

Priority order:
1) School-specific override (FeatureToggleState with school set, not expired)
2) Global override (FeatureToggleState with school null, not expired)
3) Definition default
4) Caller fallback
"""

from __future__ import annotations

from typing import Optional

from django.db import DatabaseError, OperationalError, ProgrammingError
from django.db.models import Q
from django.utils import timezone

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
        "default_enabled": _default_enabled_for(normalized, default_enabled),
        "metadata": metadata or {},
    }
    definition, _ = FeatureToggleDefinition.objects.get_or_create(
        key=normalized, defaults=defaults
    )
    return definition


def _default_enabled_for(normalized_key: str, requested: bool) -> bool:
    """Definition default for a key, honouring the module registry's declaration.

    A definition's ``default_enabled`` is what every school without an explicit
    state row gets. Callers recording ONE school's decision pass
    ``default_enabled=False`` (they are describing that school, not the platform),
    so on a database where the module definitions had not been seeded yet, a
    single tenant opting out of ``library`` created the definition with
    ``default_enabled=False`` and thereby switched ``library`` off for **every
    other tenant**. The per-school state must never set the platform default.
    """
    if not normalized_key.startswith("module."):
        return bool(requested)
    try:
        from apps.schools.feature_registry import (
            MODULE_DEFAULT_ENABLED,
            registry_module_codes,
        )

        if normalized_key[len("module.") :] in registry_module_codes():
            return MODULE_DEFAULT_ENABLED
    except (ImportError, AttributeError, TypeError):
        pass
    return bool(requested)


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

        now = timezone.now()
        q_expiry = Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        if school is not None:
            school_state = (
                FeatureToggleState.objects.filter(definition=definition, school=school)
                .filter(q_expiry)
                .values_list("is_enabled", flat=True)
                .first()
            )
            if school_state is not None:
                return bool(school_state)

        global_state = (
            FeatureToggleState.objects.filter(
                definition=definition, school__isnull=True
            )
            .filter(q_expiry)
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
    if state.is_enabled != bool(enabled) or state.updated_by_id != getattr(
        user, "id", None
    ):
        state.is_enabled = bool(enabled)
        state.updated_by = user
        state.save(update_fields=["is_enabled", "updated_by", "updated_at"])
    return state


def resolve_module_enabled(
    code: str, *, school=None, fallback: Optional[bool] = None
) -> bool:
    module_code = (code or "").strip().lower()
    if not module_code:
        return bool(fallback)
    # ``resolve_toggle`` returns ``fallback`` when no FeatureToggleDefinition row
    # exists for the key. Those rows are seeded lazily by ``get_available_modules``,
    # i.e. as a side effect of *rendering the module market*. So on any database
    # where that page had not been opened yet — a freshly provisioned tenant, a
    # self-host/edge install, a restored backup — every declared module resolved
    # to the policy value (False) and all ten ``@require_feature`` surfaces
    # answered 403, until someone happened to list the catalog and silently
    # switched them all on. Availability must not depend on that.
    #
    # Applying the registry's own declared default here makes the unseeded and
    # seeded databases agree from the first request. An explicit per-school
    # FeatureToggleState opt-out still wins, because a definition then exists and
    # this fallback is never consulted.
    effective_fallback = fallback
    try:
        from apps.schools.feature_registry import (
            MODULE_DEFAULT_ENABLED,
            registry_module_codes,
        )

        if module_code in registry_module_codes():
            effective_fallback = bool(fallback) or MODULE_DEFAULT_ENABLED
    except (ImportError, AttributeError, TypeError):
        effective_fallback = fallback
    resolved = resolve_toggle(
        f"module.{module_code}", school=school, fallback=effective_fallback
    )
    return bool(resolved)
