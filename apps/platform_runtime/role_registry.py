"""Canonical role-name registry — single source of truth for role tokens.

The platform's hard-coded role strings live HERE and nowhere else. App code
that needs to compare against a role should import the named constant from
this module (or `User.Role.<NAME>.value` for the Django TextChoices form);
inline string literals like ``"ADMIN"`` / ``"TEACHER"`` etc. anywhere
outside this module are a "no hardcoding" contract violation enforced by
``scripts/scan_role_strings.py``.

Why this module exists:
    The canonical Django ``User.Role`` ``TextChoices`` class
    (apps/accounts/models.py) defines ~20 role tokens for ORM use, but
    permission-check sites + dashboard role gates + analytics filters
    constantly need the bare string. Without a named-constant SOT for the
    top-5 highest-touch tokens, every comparison site hardcodes the
    literal and the 7-layer configurability contract is silently bypassed.

The 5 tokens enumerated here are the load-bearing role names — the ones
that appear in 100+ comparison sites across the codebase. Lower-volume
role tokens (``HOD``, ``BURSAR``, ``LEADERSHIP`` etc.) remain governed by
``User.Role`` only.
"""

from __future__ import annotations

ROLE_ADMIN: str = "ADMIN"
ROLE_TEACHER: str = "TEACHER"
ROLE_PARENT: str = "PARENT"
ROLE_STUDENT: str = "STUDENT"
ROLE_PROPRIETOR: str = "PROPRIETOR"
ROLE_COACH: str = "COACH"

ALL_ROLES: frozenset[str] = frozenset(
    {
        ROLE_ADMIN,
        ROLE_TEACHER,
        ROLE_PARENT,
        ROLE_STUDENT,
        ROLE_PROPRIETOR,
        ROLE_COACH,
    }
)

__all__ = [
    "ROLE_ADMIN",
    "ROLE_TEACHER",
    "ROLE_PARENT",
    "ROLE_STUDENT",
    "ROLE_PROPRIETOR",
    "ROLE_COACH",
    "ALL_ROLES",
]
