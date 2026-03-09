"""
Attach request.tenant_ctx (TenantContext) after tenant/school is resolved.
Must run after TenantMiddleware (RLS) or TenantSchemaSchoolBridgeMiddleware (schema).
"""
import logging

from django.utils.deprecation import MiddlewareMixin

from apps.tenancy.context import TenantContext

logger = logging.getLogger(__name__)


def _request_host(request) -> str:
    h = request.META.get("HTTP_X_FORWARDED_HOST") or request.META.get("HTTP_HOST") or ""
    if isinstance(h, str) and "," in h:
        h = h.split(",")[0].strip()
    if ":" in h:
        h = h.split(":", 1)[0].strip()
    return (h or "").lower()


def _school_json_payload(school, primary_attr: str, legacy_attr: str) -> dict:
    """Read the live School JSON field first, then fall back to legacy alias names."""
    if school is None:
        return {}
    for attr_name in (primary_attr, legacy_attr):
        if not hasattr(school, attr_name):
            continue
        value = getattr(school, attr_name)
        if isinstance(value, dict):
            return value
    return {}


def build_tenant_context_from_request(request) -> TenantContext:
    """Build TenantContext from request.school (RLS) or request.tenant (schema)."""
    host = _request_host(request)
    school = getattr(request, "school", None)
    tenant = getattr(request, "tenant", None)

    if tenant is not None and hasattr(tenant, "schema_name"):
        # Schema-per-tenant: request.tenant is Client
        school = getattr(tenant, "school", None)
        school_id = school.id if school else None
        country = getattr(school, "country", None) if school else None
        timezone = None
        try:
            from apps.siteconfig.tenant_config import get_tenant_locale
            if school:
                locale = get_tenant_locale(school=school)
                timezone = (locale.get("timezone") or locale.get("default_timezone") or "").strip() or None
        except Exception:
            pass
        feature_flags = _school_json_payload(school, "features", "features_json")
        policy_overrides = _school_json_payload(school, "settings", "settings_json")
        return TenantContext(
            tenant_id=str(tenant.id) if hasattr(tenant, "id") else getattr(tenant, "schema_name", "") or "",
            schema_name=getattr(tenant, "schema_name", None),
            school_id=school_id,
            country=str(country) if country else None,
            timezone=timezone,
            feature_flags=feature_flags,
            policy_overrides=policy_overrides,
            host=host,
        )

    if school is not None:
        country = getattr(school, "country", None)
        timezone = None
        try:
            from apps.siteconfig.tenant_config import get_tenant_locale
            locale = get_tenant_locale(school=school)
            timezone = (locale.get("timezone") or locale.get("default_timezone") or "").strip() or None
        except Exception as e:
            logger.warning("get_tenant_locale failed (school context): %s", e)
        feature_flags = _school_json_payload(school, "features", "features_json")
        policy_overrides = _school_json_payload(school, "settings", "settings_json")
        return TenantContext(
            tenant_id=str(school.id),
            schema_name=None,
            school_id=school.id,
            country=str(country) if country else None,
            timezone=timezone,
            feature_flags=feature_flags,
            policy_overrides=policy_overrides,
            host=host,
        )

    return TenantContext.empty(host=host)


class TenantContextMiddleware(MiddlewareMixin):
    """
    Set request.tenant_ctx (TenantContext) after tenant/school resolution.
    Run after TenantMiddleware or TenantSchemaSchoolBridgeMiddleware.
    """

    def process_request(self, request):
        request.tenant_ctx = build_tenant_context_from_request(request)
        return None
