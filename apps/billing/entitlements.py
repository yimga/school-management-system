"""
Entitlements service (RunMyCampus blueprint A1).
APIs: can(tenant, "MODULE_X"), limits(tenant), usage(tenant, limit_type).
Use these instead of direct is_feature_enabled or quota DB access across apps.
§2.4: Typed exceptions only; no broad except (RUNMYCAMPUS broad_exception_audit).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Typed exceptions for entitlement/quota lookups (ImportError, DB, attribute access).
_ENTITLEMENT_CAN_EXC = (ImportError, AttributeError, TypeError, ValueError)
_ENTITLEMENT_DB_EXC = (ImportError, AttributeError, TypeError, ValueError)


def can(school, capability: str) -> bool:
    """
    Return True if the tenant (school) is entitled to the capability/module.
    Replaces direct is_feature_enabled checks; single entry point for feature gates.
    """
    if school is None:
        return False
    try:
        from apps.schools.models import is_feature_enabled
        return is_feature_enabled(school, capability)
    except _ENTITLEMENT_CAN_EXC as e:
        logger.debug("Entitlement can(%s, %s) failed: %s", getattr(school, "pk", None), capability, e)
        return False


def limits(school) -> Dict[str, Dict[str, Any]]:
    """
    Return per-tenant limits (seats, storage, SMS quota, api_calls, etc.).
    Keys: limit_type (e.g. "api_calls", "max_students"). Values: { "limit_value", "period_days" }.
    """
    if school is None or not getattr(school, "pk", None):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    try:
        from django.db import DatabaseError
        from apps.schools.models import TenantQuotaLimit
        for q in TenantQuotaLimit.objects.filter(school_id=school.pk, is_active=True).values(
            "limit_type", "limit_value", "period_days"
        ):
            out[str(q["limit_type"])] = {
                "limit_value": q["limit_value"],
                "period_days": q["period_days"],
            }
    except (DatabaseError, *_ENTITLEMENT_DB_EXC) as e:
        logger.debug("Entitlement limits(school_id=%s) failed: %s", getattr(school, "pk", None), e)
    # Plan-based limits (e.g. max_students, max_staff) from school.plan
    plan = getattr(school, "plan", None)
    if plan:
        for attr in ("max_students", "max_staff"):
            val = getattr(plan, attr, None)
            if val is not None and isinstance(val, (int, float)):
                out.setdefault(attr, {"limit_value": int(val), "period_days": None})
    return out


def usage(school, limit_type: str = "api_calls", period_days: Optional[int] = None) -> Dict[str, Any]:
    """
    Return current usage for the tenant for the given limit_type (e.g. api_calls, storage_mb).
    Returns { "used": int, "period_date" or "period_start": ... } when available.
    """
    if school is None or not getattr(school, "pk", None):
        return {"used": 0}
    try:
        from django.db import DatabaseError
        from django.utils import timezone
        from django.db.models import Sum
        from apps.schools.models import TenantApiUsage

        today = timezone.now().date()
        qs = TenantApiUsage.objects.filter(school_id=school.pk, limit_type=limit_type)
        if period_days:
            from datetime import timedelta
            start = today - timedelta(days=period_days)
            qs = qs.filter(period_date__gte=start)
        agg = qs.aggregate(total=Sum("request_count"))
        used = int(agg["total"] or 0)
        return {"used": used, "limit_type": limit_type}
    except (DatabaseError, *_ENTITLEMENT_DB_EXC) as e:
        logger.debug("Entitlement usage(school_id=%s, limit_type=%s) failed: %s", getattr(school, "pk", None), limit_type, e)
        return {"used": 0}
