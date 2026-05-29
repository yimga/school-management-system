"""
Canonical org-level role strings for OrgMembership.

Use OrgMembership.Role (TextChoices) in application code; import these
constants when a stable string is required outside the model layer.
"""

from __future__ import annotations

ROLE_OWNER: str = "owner"
ROLE_GROUP_ADMIN: str = "group_admin"
ROLE_INSPECTOR: str = "inspector"
ROLE_SUPERINTENDENT: str = "superintendent"

ALL_ORG_ROLES: frozenset[str] = frozenset(
    {
        ROLE_OWNER,
        ROLE_GROUP_ADMIN,
        ROLE_INSPECTOR,
        ROLE_SUPERINTENDENT,
    }
)

__all__ = [
    "ROLE_OWNER",
    "ROLE_GROUP_ADMIN",
    "ROLE_INSPECTOR",
    "ROLE_SUPERINTENDENT",
    "ALL_ORG_ROLES",
]
