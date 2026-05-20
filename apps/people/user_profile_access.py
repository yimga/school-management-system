"""Safe access to user-linked people profiles when schema may lag migrations."""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, OperationalError, ProgrammingError

_PROFILE_SCHEMA_ERRORS = (ProgrammingError, DatabaseError, OperationalError)


def safe_teacher_profile(user):
    """Return ``TeacherProfile`` for *user*, or ``None`` if absent or schema is behind."""
    if not user or not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.teacher_profile
    except ObjectDoesNotExist:
        return None
    except _PROFILE_SCHEMA_ERRORS:
        return None
