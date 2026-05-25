"""
Colon-style permission manifest v1 (tenant Permission.code registry).

ReBAC tuples (Postgres) + signed offline read snapshots ship in batch 1507.
CRDT-merge admin IAM is explicitly rejected — offline grants use intent queue only.
"""

from __future__ import annotations

from typing import Iterable


def colon_tokens_from_permissions() -> list[str]:
    """Export sorted Permission.code values as manifest tokens."""
    from apps.accounts.models import Permission

    return sorted(
        Permission.objects.values_list("code", flat=True).distinct(),
    )


def manifest_snapshot() -> dict:
    tokens = colon_tokens_from_permissions()
    return {
        "version": "1.0",
        "format": "colon_token",
        "token_count": len(tokens),
        "tokens": tokens,
        "advanced_capabilities": {
            "postgres_rebac": {
                "status": "IMPLEMENTED",
                "tuple_store": "accounts.RelationshipTuple",
                "check_api": "apps.accounts.rebac.check",
                "writers": [
                    "SchoolMembership",
                    "StudentGuardian",
                    "TeacherAssignment",
                    "User.roles",
                ],
            },
            "offline_iam_snapshot": {
                "status": "IMPLEMENTED",
                "endpoint": "/api/offline/permission_snapshot/",
                "read_only": True,
                "offline_admin_grants": False,
            },
            "crdt_edge_iam_admin": {
                "status": "REJECTED",
                "reason": "No CRDT-merge role grants; use OfflineAccessIntent + server check",
            },
        },
    }


def validate_token(token: str) -> bool:
    return bool(token) and "." in token and " " not in token
