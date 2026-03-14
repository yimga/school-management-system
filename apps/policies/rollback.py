"""
Policy version rollback (RunMyCampus blueprint B3).
TenantBlueprint.active_bundle points to the active PolicyBundle; rollback = point to a previous bundle.
"""
from __future__ import annotations

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, IntegrityError

logger = logging.getLogger(__name__)


def set_active_policy_bundle(school, bundle) -> bool:
    """
    Set the active PolicyBundle for a school (staged rollout / rollback).
    bundle: PolicyBundle instance or id. Must belong to this school.
    Returns True if updated.
    """
    try:
        from apps.policies.models import TenantBlueprint, PolicyBundle
        if bundle is None:
            tb = TenantBlueprint.objects.filter(school=school).first()
            if tb:
                tb.active_bundle = None
                tb.save(update_fields=["active_bundle"])
                return True
            return False
        if not isinstance(bundle, PolicyBundle):
            bundle = PolicyBundle.objects.get(pk=bundle, school=school)
        if getattr(bundle, "school_id", None) and bundle.school_id != getattr(school, "pk", None):
            return False
        tb, _ = TenantBlueprint.objects.get_or_create(school=school, defaults={"active_bundle": bundle})
        if tb.active_bundle_id != bundle.pk:
            tb.active_bundle = bundle
            tb.save(update_fields=["active_bundle"])
        return True
    except (ObjectDoesNotExist, DatabaseError, IntegrityError, ValueError, TypeError) as e:
        logger.debug("set_active_policy_bundle failed: %s", e)
        return False


def list_policy_bundles_for_school(school):
    """Return queryset of PolicyBundle for this school (for rollback UI)."""
    from apps.policies.models import PolicyBundle
    return PolicyBundle.objects.filter(school=school).order_by("-version", "-created_at")
