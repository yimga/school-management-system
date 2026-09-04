"""Shared ``--school`` token resolution for Migration Cloud operator commands."""

from __future__ import annotations

from django.core.management.base import CommandError

from apps.migration_cloud.quarantine_resolution import resolve_school_from_token
from apps.schools.models import School


def resolve_school_or_error(token: str) -> School:
    """Resolve a tenant by pk, uuid, slug, subdomain, or alias map."""
    token = str(token or "").strip()
    if not token:
        raise CommandError("--school is required.")
    school = resolve_school_from_token(token)
    if school is None:
        raise CommandError(f"School not found for {token!r}.")
    return school
