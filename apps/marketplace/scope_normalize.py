"""Wave 6 — normalize marketplace scope codes for AppScope + AppPermissionScope."""

from __future__ import annotations


def scope_domain_for_code(code: str) -> str:
    """Map a scope code to a stable domain label for AppPermissionScope."""
    c = (code or "").strip().lower()
    if not c:
        return ""
    if ":" in c:
        return c.split(":", 1)[0].strip()[:64]
    if "." in c:
        return c.split(".", 1)[0].strip()[:64]
    return c[:64]


def normalize_scope_code(code: str) -> str:
    return (code or "").strip()[:80]


def ensure_permission_scope_row(code: str):
    """Get or create canonical AppPermissionScope for a manifest scope code."""
    from apps.marketplace.models import AppPermissionScope

    norm = normalize_scope_code(code)
    if not norm:
        return None
    domain = scope_domain_for_code(norm)
    access = AppPermissionScope.Access.READ
    low = norm.lower()
    if ":write" in low or low.endswith(":write") or ".write" in low:
        access = AppPermissionScope.Access.WRITE
    elif ":admin" in low or low.endswith(":admin") or ".admin" in low:
        access = AppPermissionScope.Access.ADMIN
    return AppPermissionScope.objects.get_or_create(
        code=norm,
        defaults={
            "domain": domain,
            "access": access,
            "description": f"Catalog scope ({domain})",
        },
    )[0]
