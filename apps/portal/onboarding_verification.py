"""
§2.4 Raw SQL wrap: onboarding verification delegates to siteconfig.repositories.migrations_repository.
Used by management command verify_onboarding_setup; no raw SQL in portal (repo holds single SELECT).
"""
from __future__ import annotations

from typing import Optional

from apps.siteconfig.repositories.migrations_repository import is_migration_applied


def check_siteconfig_migration_applied(
    app: str = "siteconfig",
    migration_name: str = "0043_sitesettings_admission_number_config",
) -> Optional[bool]:
    """
    Return True if the given migration is applied, False if not, None on DB error.
    Delegates to siteconfig.repositories.migrations_repository.is_migration_applied.
    """
    return is_migration_applied(app=app, migration_name=migration_name)
