"""Per-school tenant context for the analytics nightly batches.

``apps.analytics`` and ``apps.people`` are listed in TENANT_APPS only
(config/settings.py), so under ``USE_DJANGO_TENANTS`` their tables exist
EXCLUSIVELY inside tenant schemas. A management command run from cron -- or via
``call_command`` from a Celery task -- has no tenant middleware, so its
connection sits on ``public`` where those relations do not exist: every read
comes back empty and every write raises, while the command still prints its
success line and the beat records a healthy run.

``apps.schools.celery_tasks._run_with_tenant_context`` already covers BOTH
deployments (``tenant_context(client)`` under django-tenants, ``rls_school``
under RLS), so this is a thin re-entrant wrapper over it rather than a second
implementation of tenancy.
"""

from __future__ import annotations

import logging
import threading

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, OperationalError

logger = logging.getLogger("apps.analytics.tenant_batch")

# Tenant resolution failures. The runnable's own errors are NOT in this tuple —
# each command keeps its own error handling for the work it does.
_TENANT_CONTEXT_ERRORS = (
    ImportError,
    ValueError,
    ObjectDoesNotExist,
    DatabaseError,
    OperationalError,
)

_ACTIVE = threading.local()


def run_for_school(school, runnable, *, label: str, default=None):
    """Invoke ``runnable()`` inside ``school``'s tenant context.

    Re-entrant: ``send_risk_digest`` drives ``ai_narrate_risk_digest`` in-process
    for a school it has already entered, and letting the inner exit reset the
    session would leave the rest of the outer body unscoped.

    A tenant that cannot be resolved is logged and skipped (``default`` is
    returned) so one bad school does not end the batch.
    """
    school_id = str(getattr(school, "id", "") or "")
    if not school_id or getattr(_ACTIVE, "school_id", None) == school_id:
        return runnable()

    from apps.schools import celery_tasks as _tenant

    previous = getattr(_ACTIVE, "school_id", None)
    _ACTIVE.school_id = school_id
    try:
        return _tenant._run_with_tenant_context(
            school_id=school_id, runnable=runnable
        )
    except _TENANT_CONTEXT_ERRORS:
        logger.exception(
            "%s: could not enter tenant context for school=%s; skipping",
            label,
            school_id,
        )
        return default
    finally:
        _ACTIVE.school_id = previous
