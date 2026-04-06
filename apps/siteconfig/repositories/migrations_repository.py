"""
Django migrations state: query whether a migration is applied.
§2.4 migration state lookup now uses Django's MigrationRecorder; portal.onboarding_verification delegates here.
Staff/onboarding verification only.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.db.utils import DatabaseError, OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

_MIGRATION_CHECK_ERRORS = (OperationalError, ProgrammingError, DatabaseError)


def is_migration_applied(app: str, migration_name: str) -> Optional[bool]:
    """
    Return True if the given migration is applied, False if not, None on DB error.
    Single place for migration-state lookup; used by portal.onboarding_verification.
    """
    try:
        recorder = MigrationRecorder(connection)
        if not recorder.has_table():
            return False
        return (app, migration_name) in recorder.applied_migrations()
    except _MIGRATION_CHECK_ERRORS as e:
        logger.warning(
            "migrations_repository: migration check failed app=%s migration=%s error=%s",
            app,
            migration_name,
            e,
            exc_info=True,
        )
        return None
