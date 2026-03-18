"""
B4 (Design System Blueprint): One grammar, three surface themes.
Single source of truth for surface identity: marketing, superadmin, tenant.
"""

from __future__ import annotations

# Surface identifiers (one design system, three expressions)
SURFACE_MARKETING = "marketing"
SURFACE_SUPERADMIN = "superadmin"
SURFACE_TENANT = "tenant"

SURFACE_CHOICES = [
    (SURFACE_MARKETING, "Marketing (runmycampus.com)"),
    (SURFACE_SUPERADMIN, "Superadmin (manager.runmycampus.com/super/)"),
    (SURFACE_TENANT, "Tenant (school subdomains / custom domains)"),
]


def get_surface_for_request(request) -> str:
    """
    Return the design surface for the current request: marketing, superadmin, or tenant.
    Used by templates and context processors to apply the correct theme/layout.
    """
    if request is None:
        return SURFACE_TENANT
    path = getattr(request, "path", "") or ""
    if path.startswith("/super/") or getattr(request, "is_super_request", False):
        return SURFACE_SUPERADMIN
    school = getattr(request, "school", None)
    if school is not None:
        return SURFACE_TENANT
    # Marketing: no tenant, not super (e.g. /, /pricing/, /product/)
    if path.startswith("/api/") or path.startswith("/backend/"):
        return SURFACE_TENANT
    return SURFACE_MARKETING
