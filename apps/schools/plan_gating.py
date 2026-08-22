"""Turn the subscription plan into a real ceiling for *premium* features.

Today ``is_feature_enabled`` is a pure union of grantors (plan, add-ons,
``School.features`` JSON, module manifest, policy fallback): the plan can only
ADD access, never bind, so the free tier never limits anything and there is no
"denied because it's not in your plan" outcome to hang an upgrade prompt on.

This module adds a *ceiling* for genuinely plan-gated codes, gated behind the
``RMC_PLAN_GATING_ENFORCED`` environment flag:

* **Flag OFF (default)** — ``plan_gating_enforced()`` returns ``False`` and
  ``is_feature_enabled`` behaves EXACTLY as before (pure union). The mechanism
  is completely inert; nothing is gated, nothing can lock out. This is the
  shipped state: staged for operator approval, not live.

* **Flag ON** — for a code in the plan-gated set (a code that some *paid* plan
  includes but the *default/free* plan does NOT), access is granted ONLY by an
  explicit grant: the resolved plan's ``included_features``, ``School.addons``,
  ``School.features`` JSON, or a materialized billing ``Entitlement``. The
  module-manifest / policy union can no longer silently open a premium feature,
  so the free tier finally binds and an upgrade CTA has a real signal.
  *Universal* codes (everything NOT in the plan-gated set — core modules every
  tier gets) still resolve through the existing union, so core access never
  binds. ``COMPLIMENTARY`` / ``MANUAL_OVERRIDE`` keep full access.

The plan-gated set is DERIVED from real, operator-maintained plan data — a code
is plan-gated iff it appears in some active plan's ``included_features`` but not
in the default/free plan's. If no paid plan differs from the free plan, the set
is empty and the flag is a no-op even when ON. Nothing here is hardcoded.

**Grandfathering (mandatory before flipping the flag ON):** run
``manage.py snapshot_plan_gated_grants --apply`` first. It records every
school's currently-effective plan-gated features as explicit ``School.features``
grants, so no existing school loses a feature it already uses when the ceiling
turns on. See that command + [[finding_parent_fee_take_rate_unwired_2026_07_17]]
for the surrounding revenue context.
"""
from __future__ import annotations

import logging
import os

from django.core.cache import cache
from django.db import DatabaseError, OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

_ENV_FLAG = "RMC_PLAN_GATING_ENFORCED"
_TRUTHY = {"1", "true", "yes", "on"}
_CACHE_KEY = "rmc_plan_gated_codes_v1"
_CACHE_TTL_SECONDS = 300  # magic-number-allow: plan-gated-set cache TTL seconds

_DB_ERRORS = (DatabaseError, OperationalError, ProgrammingError, AttributeError, TypeError)


def owner_free_trial_days(default: int = 30) -> int:
    """Configured free-trial length in days (reverse-trial default 30).

    Env-driven so it can be tuned per-deploy without a code change. 30 days is
    the approved default (2x the 14-day SaaS norm — justified by school
    procurement + roster-import time-to-value). Invalid/absent -> default.
    """
    raw = os.getenv("OWNER_FREE_TRIAL_DAYS", "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return default


def in_active_trial(school) -> bool:
    """True while a school is inside an unexpired free-trial window.

    This is the reverse-trial engine: while it returns True the school gets full
    feature access (see is_feature_enabled), and the moment ``trial_end_date``
    passes it returns False, so the plan ceiling binds and the school
    auto-downgrades to its plan's features — WITHOUT depending on the billing
    beat flipping FREE_TRIAL -> REGULAR. Data is never touched; only access
    changes, and re-upgrading restores everything.
    """
    if getattr(school, "billing_type", None) != "FREE_TRIAL":
        return False
    end = getattr(school, "trial_end_date", None)
    if end is None:
        # A FREE_TRIAL with no end date is treated as active (generous), matching
        # the "give trials as much as possible" intent.
        return True
    from django.utils import timezone

    return end >= timezone.now().date()


def plan_gating_enforced() -> bool:
    """True only when the operator has explicitly opted in via the env flag.

    Deliberately env-read (not a ``settings`` attribute) so the ceiling can be
    toggled per-deploy without a code change and without touching the settings
    module. Default (unset) is OFF.
    """
    return os.getenv(_ENV_FLAG, "").strip().lower() in _TRUTHY


def _normalize(code) -> str:
    return str(code or "").strip().lower()


def _compute_plan_gated_codes() -> frozenset[str]:
    """Codes in some active plan's included_features but NOT in the default/free plan."""
    try:
        from apps.siteconfig.models_platform_catalog import Plan
    except ImportError:
        return frozenset()
    try:
        default = Plan.get_default_plan()
        if default is None:
            # No ACTIVE default plan. Substituting an empty default_features set
            # here (what this did before) classifies EVERY feature of EVERY active
            # plan as plan-gated, so with the flag ON the ceiling denies every
            # capability a school reaches through the union -- a catalog
            # misconfiguration turning into a platform-wide lockout. Fail OPEN
            # instead: gate nothing, and say so loudly. The ceiling is a revenue
            # control; it must never be the cause of an outage.
            #
            # Two real routes into this state:
            #   1. Plans seeded AFTER siteconfig migration 0200 ran -- its seeder
            #      is ``if candidate is not None`` and marks no default on an
            #      empty table, and nothing sets one later except an operator;
            #   2. an operator deactivating the plan that carries is_default --
            #      ``plan_unique_default`` enforces at most ONE default, not that
            #      an ACTIVE one exists, while get_default_plan() filters on both.
            # Migration siteconfig.0211 closes route 2 with a check constraint;
            # this branch still guards route 1 and any pre-existing bad row.
            logger.warning(
                "plan_gating: no active default plan (is_default=True, is_active=True); "
                "the plan ceiling is INERT until one is set."
            )
            return frozenset()
        default_features = {
            _normalize(f) for f in (default.included_features or []) if f
        }
        gated: set[str] = set()
        for plan in Plan.objects.filter(is_active=True).only("included_features"):
            for feature in plan.included_features or []:
                normalized = _normalize(feature)
                if normalized and normalized not in default_features:
                    gated.add(normalized)
        return frozenset(gated)
    except _DB_ERRORS as exc:  # pragma: no cover - defensive on migrate/empty DB
        logger.debug("plan_gating._compute_plan_gated_codes skipped: %s", exc)
        return frozenset()


def plan_gated_feature_codes() -> frozenset[str]:
    """The plan-gated set, cached briefly (plan catalog changes rarely)."""
    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return cached
    codes = _compute_plan_gated_codes()
    try:
        cache.set(_CACHE_KEY, codes, _CACHE_TTL_SECONDS)
    except (DatabaseError, OperationalError, ValueError):  # pragma: no cover
        pass
    return codes


def is_plan_gated_code(normalized_code: str) -> bool:
    return normalized_code in plan_gated_feature_codes()


def clear_plan_gated_cache() -> None:
    """Invalidate the cached set (call after editing plans / in tests)."""
    try:
        cache.delete(_CACHE_KEY)
    except (DatabaseError, OperationalError):  # pragma: no cover
        pass


def plan_ceiling_grants(school, normalized_code: str) -> bool:
    """True iff an EXPLICIT grant covers this plan-gated code.

    Explicit = the resolved plan's included_features (plan-less resolves to the
    default plan, never "unrestricted"), an add-on, a ``School.features`` JSON
    grant (the grandfather snapshot writes here), or a materialized billing
    ``Entitlement``. The module-manifest / policy union is intentionally NOT
    consulted here — that is the whole point of the ceiling.
    """
    # Resolved plan (plan-less -> default) included_features.
    try:
        from apps.schools.plan_resolution import resolve_plan

        plan = resolve_plan(school)
    except ImportError:  # pragma: no cover
        plan = getattr(school, "plan", None)
    if plan is not None and getattr(plan, "included_features", None):
        if normalized_code in {_normalize(f) for f in plan.included_features if f}:
            return True

    # Add-ons.
    addons = getattr(school, "addons", None) or []
    if isinstance(addons, list) and normalized_code in {_normalize(a) for a in addons if a}:
        return True

    # Per-school features JSON (the grandfather snapshot + operator overrides).
    raw_features = getattr(school, "features", None) or {}
    if isinstance(raw_features, dict):
        for key, value in raw_features.items():
            if value and _normalize(key) == normalized_code:
                return True

    # Materialized billing Entitlement (reuse the reader in schools.models).
    try:
        from apps.schools.models import _materialized_feature_entitlement_state

        if _materialized_feature_entitlement_state(school, normalized_code) is True:
            return True
    except ImportError:  # pragma: no cover
        pass
    return False
