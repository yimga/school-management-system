"""Shared link + navigation context for public developer surfaces (runmycampus.com)."""

from __future__ import annotations

from django.urls import NoReverseMatch, reverse


def _abs(request, path: str) -> str:
    return request.build_absolute_uri(path)


def _reverse_abs(request, name: str, *, urlconf: str | None = None) -> str:
    kwargs = {"urlconf": urlconf} if urlconf else {}
    try:
        return request.build_absolute_uri(reverse(name, **kwargs))
    except NoReverseMatch:
        return ""


def developer_nav_items(request) -> list[dict]:
    """Primary developer section nav (paths safe on config.public_urls)."""
    items = [
        ("developer_hub", "/developer/", "Hub"),
        ("developer_console", "/developer/console/", "Console"),
        ("developer_portal", "/developer-portal/", "Portal"),
        ("developer_public_api_docs", "/developers/api-docs/", "API summary"),
        ("marketing_developers", "/developers/", "Platform story"),
        ("developer_api", "/developers/api/", "REST API"),
        ("developer_webhooks", "/developers/webhooks/", "Webhooks"),
        ("developer_integrations", "/developers/integrations/", "Integrations"),
        ("developer_sdk_page", "/developers/sdk/", "SDK guide"),
        ("developer_app_building", "/developers/app-building/", "App building"),
        ("marketplace_dev:public_app_catalog_api", "/marketplace/api/v1/catalog/", "Catalog API"),
        ("marketplace_dev:publisher_signup", "/marketplace/publisher/signup/", "Publisher signup"),
    ]
    out: list[dict] = []
    for name, fallback, label in items:
        href = _reverse_abs(request, name, urlconf="config.public_urls") or _abs(request, fallback)
        out.append({"name": name, "href": href, "label": label})
    return out


def developer_link_context(request) -> dict:
    """Absolute URLs for hub, console, portal, discovery, and operator tools."""
    base = _abs(request, "/").rstrip("/")
    pub = "config.public_urls"

    def r(name: str, fallback: str = "") -> str:
        url = _reverse_abs(request, name, urlconf=pub)
        return url or (_abs(request, fallback) if fallback else "")

    return {
        "v2_manifest": f"{base}/api/v2/manifest.json",
        "v1_manifest": f"{base}/api/v1/manifest.json",
        "v2_ping": f"{base}/api/v2/ping/",
        "oauth_token": f"{base}/api/v1/oauth/token/",
        "oauth_authorize": f"{base}/api/v1/oauth/authorize/",
        "integration_context": f"{base}/api/v1/platform/integration-context/",
        "scoped_ping": f"{base}/api/v1/platform/scoped-ping/",
        "api_center": r("apicenter:dashboard", "/api-center/"),
        "api_center_docs": r("apicenter:api_portal_docs", "/api-center/docs/"),
        "developer_hub": r("developer_hub", "/developer/"),
        "developer_console": r("developer_console", "/developer/console/"),
        "developer_portal": r("developer_portal", "/developer-portal/"),
        "sdk": r("developer_sdk", "/developer-portal/sdk/"),
        "sandbox": r("developer_sandbox", "/developer-portal/sandbox/"),
        "public_api_docs": r("developer_public_api_docs", "/developers/api-docs/"),
        "publisher_signup": r("marketplace_dev:publisher_signup", "/marketplace/publisher/signup/"),
        "catalog_api": r("marketplace_dev:public_app_catalog_api", "/marketplace/api/v1/catalog/"),
        "interop_hub": f"{base}/api/interop/",
        "interop_oneroster": f"{base}/api/interop/oneroster/",
        "interop_lti13": f"{base}/api/interop/lti13/",
        "interop_edfi": f"{base}/api/interop/edfi/",
        "interop_ceds": f"{base}/api/interop/ceds/",
        "admin_developer_applications": f"{base}/admin/apicenter/developerapplication/",
        "admin_marketplace_apps": f"{base}/admin/marketplace/marketplaceapp/",
        "admin_tenant_subscriptions": f"{base}/admin/billing/tenantsubscription/",
        "sdk_repo": "https://github.com/runmycampus/sdk",
    }
