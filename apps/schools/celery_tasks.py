"""
Tenant-aware Celery task base: run task body in tenant_context (schema mode) or rls_school (RLS mode).
Use for tasks that must run with a specific tenant scope. Pass schema_name/client_id or school_id.
"""
import logging

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, OperationalError

logger = logging.getLogger(__name__)


def get_active_school_ids():
    """Return list of active school IDs for iterating tenant-scoped tasks. Uses public/schools table."""
    try:
        from apps.schools.models import School
        return list(School.objects.filter(is_active=True).values_list("id", flat=True))
    except (ImportError, DatabaseError, OperationalError, AttributeError, TypeError) as e:
        logger.warning("get_active_school_ids: %s", e)
        return []


def _resolve_client(schema_name=None, client_id=None, school_id=None):
    """Resolve django_tenants Client from schema_name, client_id, or school_id. Returns None if not USE_DJANGO_TENANTS."""
    if not getattr(settings, "USE_DJANGO_TENANTS", False):
        return None
    try:
        from django_tenants.models import Client

        if schema_name:
            return Client.objects.get(schema_name=schema_name)
        if client_id is not None:
            return Client.objects.get(pk=client_id)
        if school_id is not None:
            from apps.schools.models import School
            from apps.schools.domain_sync import ensure_tenant_client_for_school

            school = School.objects.filter(pk=school_id).first()
            if school:
                return ensure_tenant_client_for_school(school)
    except (ImportError, ObjectDoesNotExist, DatabaseError, OperationalError, AttributeError, TypeError) as e:
        logger.warning("Could not resolve tenant client: %s", e)
    return None


def _run_with_tenant_context(schema_name=None, client_id=None, school_id=None, runnable=None, *args, **kwargs):
    """
    Run callable with tenant context: tenant_context(client) when USE_DJANGO_TENANTS else rls_school(school_id).
    runnable(*args, **kwargs) is invoked inside the context.
    """
    use_tenants = getattr(settings, "USE_DJANGO_TENANTS", False)
    if use_tenants:
        client = _resolve_client(schema_name=schema_name, client_id=client_id, school_id=school_id)
        if client is None:
            raise ValueError(
                "Tenant client could not be resolved (schema_name=%s, client_id=%s, school_id=%s)"
                % (schema_name, client_id, school_id)
            )
        from django_tenants.utils import tenant_context
        with tenant_context(client):
            return runnable(*args, **kwargs)
    # RLS mode: need school_id
    sid = school_id
    if sid is None and (schema_name or client_id is not None):
        from apps.schools.models import School
        if client_id is not None:
            try:
                from django_tenants.models import Client
                c = Client.objects.get(pk=client_id)
                school = School.objects.filter(id=c.id).first() or School.objects.filter(slug=c.schema_name).first()
                if school:
                    sid = str(school.id)
            except (ImportError, ObjectDoesNotExist, DatabaseError, OperationalError, AttributeError, TypeError):
                pass
        if sid is None and schema_name:
            school = School.objects.filter(slug=schema_name).first() or School.objects.filter(subdomain=schema_name).first()
            if school:
                sid = str(school.id)
    if sid is None:
        raise ValueError("school_id (or schema_name/client_id to resolve school) required for RLS mode")
    from apps.schools.rls_context import rls_school
    with rls_school(sid):
        return runnable(*args, **kwargs)


try:
    from celery import Task
except ImportError:
    Task = object


class TenantAwareTask(Task):
    """
    Celery task base that runs the task body inside tenant context.
    When USE_DJANGO_TENANTS=True: uses tenant_context(client) from schema_name/client_id/school_id.
    When USE_DJANGO_TENANTS=False: uses rls_school(school_id).
    Pass schema_name=, client_id=, or school_id= in apply_async kwargs; or pass school_id as first arg.
    Example:
        @shared_task(bind=True, base=TenantAwareTask)
        def my_task(self, school_id, other_arg):
            # Runs inside tenant context; School.objects.filter(...) sees only that school in RLS mode.
            return do_something(other_arg)
    """

    def __call__(self, *args, **kwargs):
        schema_name = kwargs.get("schema_name")
        client_id = kwargs.get("client_id")
        school_id = kwargs.get("school_id")
        if not any((schema_name, client_id is not None, school_id is not None)) and args:
            school_id = str(args[0])
        def _run():
            return super().__call__(*args, **kwargs)
        return _run_with_tenant_context(
            schema_name=schema_name,
            client_id=client_id,
            school_id=school_id,
            runnable=_run,
        )
