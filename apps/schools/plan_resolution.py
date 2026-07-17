"""Which plan governs a school, and binding the default at provisioning.

Tenants never pick a plan -- no comparable platform lets them. Salesforce
provisions an org from an already-signed subscription; Shopify creates a shop
on a real ``trial`` row; Slack creates a workspace on a real ``Free`` row;
Stripe gives a customer with no subscription NO entitlements rather than
unlimited ones. The plan is stamped at tenant creation, from a default, and
changed later through billing. What varies between them is only who decided it
first, never whether the tenant has one.

``School.plan`` is nullable and nothing guaranteed it was set, so resolution had
no total answer: a school could run forever on ``plan_id = None``. That is only
survivable because the plan is currently a GRANTOR rather than a gate --
``is_feature_enabled`` unions four sources and every branch can only say yes --
so a missing plan costs the school nothing, the free tier never binds, and the
upgrade trigger can never fire.

This module makes resolution total. It deliberately does NOT make the plan a
gate: that would withdraw access from live tenants and is a separate decision.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def resolve_plan(school):
    """The plan governing ``school``: its own, else the platform default.

    Read-only -- never creates a row, because defining a plan and its pricing is
    a product decision, not something to fabricate at read time.

    Returns ``None`` only when there is nothing to resolve: no school, or the
    platform has no ``is_default`` plan at all. The latter is a platform
    misconfiguration, not a tenant state, and is returned rather than raised
    because this is read on request paths and must never 500 a tenant.
    """
    if school is None:
        return None
    plan = getattr(school, "plan", None)
    if plan is not None:
        return plan
    try:
        from apps.siteconfig.models_platform_catalog import Plan

        return Plan.get_default_plan()
    except (ImportError, AttributeError, TypeError, ValueError):
        logger.warning(
            "plan resolution could not read the platform default for school=%s",
            getattr(school, "id", None),
            exc_info=True,
        )
        return None


def ensure_school_plan(school) -> bool:
    """Bind the platform default plan when the school has none.

    Returns True when a plan was bound. Never overrides an existing plan: an
    established tenant's posture is not ours to rewrite.

    SAFE ONLY BECAUSE THE DEFAULT PLAN IS NO LONGER A FUSE. ``free-starter``
    previously carried max_students=50 / max_staff=5 while ``UsageLimitMiddleware``
    403'd every request once a school reached the cap -- binding the default to
    a real school would have bricked it at student #51, and the MISSING plan was
    what protected live tenants. The cap now refuses only the enrolment that
    exceeds it, and the default plan is uncapped on size. If someone puts a size
    cap back on the default plan, this function starts handing every new school
    a fuse -- ``test_the_bound_default_does_not_cap_the_school`` fails loudly if
    that happens.
    """
    if school is None:
        return False
    if getattr(school, "plan_id", None) is not None:
        return False
    default_plan = resolve_plan(school)
    if default_plan is None:
        logger.warning(
            "no default plan is configured — school=%s provisioned plan-less",
            getattr(school, "id", None),
        )
        return False
    school.plan = default_plan
    school.save(update_fields=["plan", "updated_at"])
    return True
