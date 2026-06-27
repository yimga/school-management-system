"""Wave A: the single keyed accessor over the ONE effective-config resolver.

PROBLEM (target #2): reading one config value today means knowing WHICH domain
helper to call (``get_effective_feature_control_settings`` for flags,
``get_effective_marketplace_integration_settings`` for secrets, attribute access
on ``get_effective_site_settings`` for the rest). That per-domain fan-out is the
read-side fragmentation.

CONVERGENCE: ``get_effective_config(school, key)`` is the canonical single-key
read. It does NOT re-query the ORM or re-implement precedence — it delegates to
``get_effective_site_settings`` (the one merged + request/TTL-cached resolver,
apps/platform_runtime/helpers.py:370), which already layers
``RuntimeDefaults`` base -> ``School.settings`` -> wizard
``School.settings['runtime_defaults']`` in the correct order. Callers stop
needing to know the store; precedence + caching are reused, never duplicated.

Scope note: this resolves FIRST-CLASS config fields (the 116 typed
``RuntimeDefaults`` columns, tenant-overridable — gated by
``scripts/verify_runtime_defaults_model_parity.py``). Nested feature-flag lookups
inside ``backend_feature_flags`` and the multi-source feature arbiter remain
``feature_enabled()`` (Wave D / target #11); this returns the field value (e.g.
the whole ``backend_feature_flags`` dict) and does not descend into it.
"""

from __future__ import annotations

from typing import Any

_MISSING = object()


def get_effective_config(
    school: Any = None,
    key: str = "",
    *,
    request: Any = None,
    default: Any = None,
) -> Any:
    """Return the effective value of a single config ``key`` for ``school``.

    Precedence (inherited from get_effective_site_settings, not re-implemented):
    School.settings[key] > School.settings['runtime_defaults'][key] >
    RuntimeDefaults.<key>. Returns ``default`` when the key is unknown or the
    resolver is unavailable (the resolver itself is fail-soft and may return None
    very early in boot / on a broken singleton).
    """
    if not key:
        return default

    from apps.platform_runtime.helpers import get_effective_site_settings

    site = get_effective_site_settings(request=request, school=school)
    if site is None:
        return default
    value = getattr(site, key, _MISSING)
    if value is _MISSING:
        return default
    return value


def get_config_owner(key: str) -> str:
    """Return the ownership domain for ``key`` (single classification source).

    Thin alias over the existing ``classify_site_settings_field`` so callers that
    need routing (snapshots, policy compilation, bulk export) have one entry point
    that lives next to the read resolver.
    """
    from apps.siteconfig.domain_ownership import classify_site_settings_field

    return classify_site_settings_field(key)
