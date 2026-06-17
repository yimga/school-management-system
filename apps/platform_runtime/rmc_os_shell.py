"""
RunMyCampus OS shell classification (tenant portal + control plane).

Descriptive only — not authorization. Used for ``data-rmc-os-*`` markers and UX grouping.
"""

from __future__ import annotations

from apps.accounts.models import User

_SCHOOL_ADMIN_ROLES: frozenset[str] = frozenset(
    {
        User.Role.SUPERADMIN,
        User.Role.ADMIN,
        User.Role.LEADERSHIP,
        User.Role.PRINCIPAL,
        User.Role.VICE_PRINCIPAL,
        User.Role.DEAN,
        User.Role.BURSAR,
        User.Role.IT_ADMIN,
        User.Role.HOD,
        User.Role.DEPT_LEAD,
        User.Role.FINANCE_STAFF,
        User.Role.ACCOUNTANT,
        User.Role.PROPRIETOR,
        User.Role.BOARDING_MANAGER,
        User.Role.DISCIPLINE_MASTER,
        User.Role.SECRETARY,
        User.Role.EXECUTIVE_ASSISTANT,
        User.Role.VIRTUAL_ASSISTANT,
        User.Role.COMMS_STAFF,
        User.Role.CENSOR,
    }
)


def _page_slug_from_path(path: str) -> str:
    raw = (path or "/").strip()
    if not raw or raw == "/":
        return "home"
    p = raw.strip("/").replace("/", "-")
    return p[:120] if p else "home"


def _role_label(code: str) -> str:
    if not code:
        return ""
    try:
        return User.Role(code).label
    except ValueError:
        return code.replace("_", " ").strip().title()


def resolve_rmc_os_shell(request) -> dict[str, str]:
    """Return stable keys for templates and audits."""
    user = getattr(request, "user", None)
    path = getattr(request, "path", "/") or "/"
    page_slug = _page_slug_from_path(path)

    if not user or not getattr(user, "is_authenticated", False):
        return {
            "role_cluster": "anonymous",
            "role_display": "",
            "page_slug": page_slug,
            "surface_kind": "public",
        }

    host_kind = getattr(request, "public_host_kind", None) or "tenant"

    if host_kind == "manager":
        role = (getattr(user, "role", None) or "").upper()
        if getattr(user, "is_superuser", False) or role == User.Role.SUPERADMIN:
            cluster = "founder_operator"
        else:
            cluster = "operator"
        return {
            "role_cluster": cluster,
            "role_display": _role_label(getattr(user, "role", "") or ""),
            "page_slug": page_slug,
            "surface_kind": "control-plane",
        }

    session = getattr(request, "session", None)
    try:
        from apps.accounts.portal_roles import get_nav_portal_role

        effective = get_nav_portal_role(request) or (
            (getattr(user, "role", None) or "").strip().upper()
        )
    except Exception:
        eff = ""
        if session is not None:
            from apps.accounts.portal_roles import ACTIVE_PORTAL_ROLE_KEY

            eff = (session.get(ACTIVE_PORTAL_ROLE_KEY) or "").strip().upper()
        effective = eff or (getattr(user, "role", None) or "").strip().upper()

    base_role = (getattr(user, "role", None) or "").strip().upper()

    if effective == User.Role.TEACHER:
        cluster = "teacher"
    elif effective == User.Role.PARENT:
        cluster = "parent"
    elif effective == User.Role.STUDENT:
        cluster = "student"
    elif effective in _SCHOOL_ADMIN_ROLES or base_role in _SCHOOL_ADMIN_ROLES:
        cluster = "school_admin"
    else:
        cluster = "school_staff"

    return {
        "role_cluster": cluster,
        "role_display": _role_label(effective or base_role),
        "page_slug": page_slug,
        "surface_kind": "tenant-portal",
    }
