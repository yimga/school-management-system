"""
Django migrations state: query whether a migration is applied.
§2.4 raw_sql_replacement_targets: single raw SQL for django_migrations lives here; portal.onboarding_verification delegates.
Staff/onboarding verification only.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.db import connection
from django.db.utils import DatabaseError, OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

_MIGRATION_CHECK_ERRORS = (OperationalError, ProgrammingError, DatabaseError)


def is_migration_applied(app: str, migration_name: str) -> Optional[bool]:
    """
    Return True if the given migration is applied, False if not, None on DB error.
    Single place for SELECT on django_migrations; used by portal.onboarding_verification.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name FROM django_migrations WHERE app = %s AND name = %s",
                [app, migration_name],
            )
            return cursor.fetchone() is not None
    except _MIGRATION_CHECK_ERRORS as e:
        logger.warning(
            "migrations_repository: migration check failed app=%s migration=%s error=%s",
            app,
            migration_name,
            e,
            exc_info=True,
        )
        return None
