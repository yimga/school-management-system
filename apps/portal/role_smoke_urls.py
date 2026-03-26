"""
Canonical URL × role matrix for tenant portal smoke crawls.

Each entry: reverse this url_name on ``config.tenant_urls`` as a user with one of
``roles`` (``User.Role`` values). Optional flags tighten who may access the view.

Extend this list as new role-native surfaces ship; keep names resolvable without
path kwargs where possible.
"""

from __future__ import annotations

from typing import Any

from apps.accounts.models import User

# List of dicts: url_name, roles (iterable of User.Role), optional requires_staff, requires_superuser
PORTAL_ROLE_SMOKE_SEEDS: list[dict[str, Any]] = [
    {
        "url_name": "portal:parent_dashboard",
        "roles": (User.Role.PARENT,),
    },
    {
        "url_name": "portal:teacher_dashboard_alias",
        "roles": (User.Role.TEACHER,),
    },
    {
        "url_name": "portal:student_onboarding",
        "roles": (User.Role.STUDENT,),
    },
    {
        "url_name": "portal:employer_dashboard",
        "roles": (User.Role.EMPLOYER,),
    },
    {
        "url_name": "portal:support_request",
        "roles": (
            User.Role.PARENT,
            User.Role.TEACHER,
            User.Role.STUDENT,
        ),
    },
    {
        "url_name": "kb:kb_home",
        "roles": (
            User.Role.PARENT,
            User.Role.TEACHER,
            User.Role.STUDENT,
        ),
    },
    {
        "url_name": "finance:dashboard",
        "roles": (
            User.Role.BURSAR,
            User.Role.ACCOUNTANT,
            User.Role.ADMIN,
        ),
        "requires_staff": True,
    },
    {
        "url_name": "requests:dashboard",
        "roles": (
            User.Role.LEADERSHIP,
            User.Role.PRINCIPAL,
            User.Role.VICE_PRINCIPAL,
            User.Role.ADMIN,
        ),
        "requires_staff": True,
    },
    {
        "url_name": "accounts:backend_dashboard",
        "roles": (User.Role.ADMIN, User.Role.PRINCIPAL),
        "requires_staff": True,
    },
    {
        "url_name": "siteconfig:console_domains_hub",
        "roles": (User.Role.ADMIN,),
        "requires_staff": True,
        "requires_superuser": True,
    },
]
