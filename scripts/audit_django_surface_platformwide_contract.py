from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    errors: list[str] = []

    tenant_urls = _read("config/tenant_urls.py")
    platform_urls = _read("config/urls.py")
    admin_py = _read("config/admin.py")
    backend_base = _read("templates/backend_base_tenant.html")
    admin_base = _read("templates/admin/base.html")
    admin_base_site = _read("templates/admin/base_site.html")
    tenant_backend_css_path = ROOT / "static/css/rmc-django-surface-canvas-parity.css"
    tenant_backend_css = (
        tenant_backend_css_path.read_text(encoding="utf-8", errors="replace")
        if tenant_backend_css_path.exists()
        else ""
    )

    required_route_tokens = (
        'path("admin/", tenant_admin_site.urls)',
        'path("configuration/", school_configuration_center',
        'path("configuration/<path:remaining>", school_configuration_center)',
        'path("school/settings/", school_configuration_center',
        'path("school/configuration/", school_configuration_center',
    )
    for token in required_route_tokens:
        if token not in tenant_urls:
            errors.append(f"config/tenant_urls.py missing tenant route token: {token}")

    if "admin_host_dispatch" not in platform_urls:
        errors.append("config/urls.py must dispatch /admin/ by host, not hard-bind one AdminSite")
    if 'path("admin/", admin_host_dispatch' not in platform_urls:
        errors.append("config/urls.py missing host-aware /admin/ dispatch")
    if "tenant_admin_site = TenantAdminSite" not in admin_py:
        errors.append("config/admin.py missing tenant_admin_site")
    if "platform_admin_site = PlatformAdminSite" not in admin_py:
        errors.append("config/admin.py missing platform_admin_site")
    if 'index_template_name = "admin/index_tenant.html"' not in admin_py:
        errors.append("TenantAdminSite must use the tenant-specific Django admin index")
    if "def has_permission" not in admin_py or "self._is_platform_host(request)" not in admin_py:
        errors.append("TenantAdminSite must deny platform-host access")

    tenant_backend_tokens = (
        "rmc-django-surface-canvas",
        'data-rmc-django-surface-canvas="tenant-backend"',
        'data-rmc-django-surface-scope="tenant"',
        'data-rmc-admin-canvas-contract="intelligent-full-width"',
        'data-rmc-admin-content="canvas-first"',
        "rmc-django-surface-canvas-parity.css",
        "?v=20260712-tenant-backend-parity",
    )
    for token in tenant_backend_tokens:
        if token not in backend_base:
            errors.append(f"templates/backend_base_tenant.html missing {token}")

    tenant_backend_css_tokens = (
        'data-rmc-django-surface-canvas="tenant-backend"',
        "tenant backend/configuration parity",
        "max-inline-size: none !important",
        "grid-template-columns: minmax(0, 1fr) !important",
        "iframe[data-rmc-preview-frame]",
        "reportcard-builder-layout",
        "theme-experience-grid",
        "site-settings-layout",
    )
    if not tenant_backend_css_path.exists():
        errors.append("static/css/rmc-django-surface-canvas-parity.css is missing")
    for token in tenant_backend_css_tokens:
        if token not in tenant_backend_css:
            errors.append(f"rmc-django-surface-canvas-parity.css missing {token}")

    admin_tokens = (
        'data-rmc-admin-canvas-host="{% if is_manager_host %}operator{% else %}tenant{% endif %}"',
        'data-rmc-admin-content="canvas-first"',
        "rmc-admin-django-canvas-contract.css",
        "?v=20260719-full-fill",
    )
    for token in admin_tokens:
        if token not in admin_base and token not in admin_base_site:
            errors.append(f"shared admin templates missing {token}")

    index_tenant = _read("templates/admin/index_tenant.html")
    for token in (
        'data-rmc-admin-surface="smart-index"',
        'data-rmc-django-workspace="admin-index"',
        "rmc-admin-catalog-index",
    ):
        if token not in index_tenant:
            errors.append(f"templates/admin/index_tenant.html missing {token}")
    if "Raw model CRUD only" in index_tenant:
        errors.append("tenant admin index must not be Raw model CRUD-only empty shell")

    if errors:
        print("DJANGO_SURFACE_PLATFORMWIDE_CONTRACT_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("DJANGO_SURFACE_PLATFORMWIDE_CONTRACT_PASS")
    print("  operator_admin: shared host-aware /admin/ dispatch")
    print("  tenant_admin: tenant_admin_site on tenant /admin/")
    print("  tenant_backend: backend_base_tenant canvas parity for backend/configuration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
