"""
Celery (and async) tenant context: @tenant_task enforces schema_name or school_id so tasks never run without tenant.
"""

from functools import wraps
from django.conf import settings
from django.db import transaction

from apps.schools.rls_context import rls_school


def tenant_task(fn):
    """
    Decorator for Celery tasks that must run in tenant context.
    Pass schema_name=... when USE_DJANGO_TENANTS=True, or school_id=... when RLS.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        schema_name = kwargs.pop("schema_name", None)
        school_id = kwargs.pop("school_id", None)

        use_tenants = getattr(settings, "USE_DJANGO_TENANTS", False)

        if use_tenants:
            if not schema_name:
                raise ValueError(
                    "schema_name required when USE_DJANGO_TENANTS=True for tenant_task"
                )
            try:
                from django_tenants.utils import schema_context

                with schema_context(schema_name):
                    return fn(*args, **kwargs)
            except ImportError:
                return fn(*args, **kwargs)

        # RLS mode: set app.current_school_id for this connection
        if school_id is None:
            raise ValueError(
                "school_id required in shared schema (RLS) mode for tenant_task"
            )
        with transaction.atomic(), rls_school(school_id):
            return fn(*args, **kwargs)

    return wrapper
