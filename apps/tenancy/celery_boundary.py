"""
Celery task boundary pinning — keeps async provisioning scoped to one tenant.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from apps.tenancy.boundary_core_guard import pinned_tenant_boundary

F = TypeVar("F", bound=Callable[..., Any])


def with_tenant_task_boundary(school_id: Any, *, host: str = "celery") -> Any:
    """Context manager for explicit Celery / background task tenant pin."""
    return pinned_tenant_boundary(school_id=school_id, host=host)


def tenant_boundary_task(*, host: str = "celery", school_kw: str = "school_id") -> Callable[[F], F]:
    """
    Decorator for tasks whose first positional arg or ``school_kw`` names the tenant.

    Example::

        @shared_task
        @tenant_boundary_task()
        def my_task(school_id: str, ...):
            ...
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            sid = kwargs.get(school_kw)
            if sid is None and args:
                sid = args[0]
            if sid is None:
                return fn(*args, **kwargs)
            with pinned_tenant_boundary(school_id=sid, host=host):
                return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
