"""
Thread-safe tenant boundary core guard.

Pins the validated tenant school_id for the active request/task and verifies
raw SQL parameters (via Django execute_wrapper) and explicit ORM filter kwargs
before they reach the database.

Platform/control-plane contexts without a pinned school_id skip enforcement.
Cross-tenant management commands must use ``boundary_bypass()`` or ``rls_bypass()``.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from apps.tenancy.exceptions import SecurityIsolationException

logger = logging.getLogger(__name__)

_SCHOOL_KWARG_KEYS = frozenset(
    {
        "school_id",
        "school",
        "school__id",
        "school__pk",
    }
)

_SQL_SCHOOL_LITERAL = re.compile(
    r"""(?:\bschool_id\b|\bschools_school\.id\b)\s*(?:=|<>|!=|IN)\s*['"]?([0-9a-fA-F-]{8,36})""",
    re.IGNORECASE,
)

_bypass_depth: ContextVar[int] = ContextVar("tenancy_boundary_bypass_depth", default=0)
_pin_state: ContextVar["_PinState | None"] = ContextVar("tenancy_boundary_pin", default=None)


@dataclass(frozen=True)
class _PinState:
    school_id: str
    host: str
    token: str


def _normalize_school_id(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        raise SecurityIsolationException(
            "Invalid tenant school_id: boolean is not allowed.",
            detail="school_id=bool",
        )
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        sid = value.strip()
        if not sid or sid.lower() in {"none", "null"}:
            return ""
        if len(sid) > 128:
            raise SecurityIsolationException(
                "Invalid tenant school_id: exceeds maximum length.",
                detail=f"len={len(sid)}",
            )
        return sid
    raise SecurityIsolationException(
        "Invalid tenant school_id type for boundary pin.",
        detail=type(value).__name__,
    )


def is_boundary_bypassed() -> bool:
    return _bypass_depth.get() > 0


@contextmanager
def boundary_bypass(*, reason: str = ""):
    """Temporarily disable boundary enforcement (management commands, migrations)."""
    token = _bypass_depth.set(_bypass_depth.get() + 1)
    try:
        if reason:
            logger.debug("tenancy.boundary_bypass enter reason=%s", reason)
        yield
    finally:
        _bypass_depth.reset(token)


def get_pinned_school_id() -> str | None:
    state = _pin_state.get()
    if state is None or not state.school_id:
        return None
    return state.school_id


def pin_tenant_boundary(*, school_id: Any, host: str = "") -> str:
    """
    Pin the active tenant school_id on the current context.
    Returns an opaque token for ``unpin_tenant_boundary``.
    """
    sid = _normalize_school_id(school_id)
    token = uuid.uuid4().hex
    _pin_state.set(_PinState(school_id=sid, host=(host or "").lower(), token=token))
    return token


def unpin_tenant_boundary(token: str) -> None:
    state = _pin_state.get()
    if state is None:
        return
    if state.token != token:
        logger.warning(  # pii-logging-smell-allow: logs only non-reversible 8-char token prefixes for mismatch debug, never the full pin token
            "tenancy.boundary_unpin token_mismatch expected=%s got=%s",
            state.token[:8],
            (token or "")[:8],
        )
        return
    _pin_state.set(None)


def _school_ids_in_mapping(mapping: Mapping[str, Any]) -> set[str]:
    found: set[str] = set()
    for key, value in mapping.items():
        key_norm = str(key).lower()
        if key_norm in _SCHOOL_KWARG_KEYS or key_norm.endswith("_school_id"):
            sid = _normalize_school_id(value)
            if sid:
                found.add(sid)
        if isinstance(value, Mapping):
            found.update(_school_ids_in_mapping(value))
    return found


def _school_ids_in_params(params: Any) -> set[str]:
    found: set[str] = set()
    if params is None:
        return found
    if isinstance(params, Mapping):
        return _school_ids_in_mapping(params)
    if isinstance(params, (list, tuple)):
        for item in params:
            found.update(_school_ids_in_params(item))
        return found
    return found


def _school_ids_in_sql(sql: str) -> set[str]:
    if not sql:
        return set()
    return {m.group(1) for m in _SQL_SCHOOL_LITERAL.finditer(sql)}


def verify_tenant_boundary_scope(
    *,
    pinned_school_id: str,
    sql: str = "",
    params: Any = None,
    orm_kwargs: Mapping[str, Any] | None = None,
) -> None:
    """
    Raise SecurityIsolationException when an explicit school_id diverges from pin.
    """
    if not pinned_school_id or is_boundary_bypassed():
        return

    pinned = _normalize_school_id(pinned_school_id)
    candidates: set[str] = set()
    candidates.update(_school_ids_in_sql(sql))
    candidates.update(_school_ids_in_params(params))
    if orm_kwargs:
        candidates.update(_school_ids_in_mapping(orm_kwargs))

    foreign = {sid for sid in candidates if sid and sid != pinned}
    if foreign:
        raise SecurityIsolationException(
            "Cross-tenant database boundary violation detected.",
            detail=f"pinned={pinned[:8]}… foreign={sorted(foreign)[0][:8]}…",
            code="cross_tenant_leak",
        )


def verify_orm_filter_kwargs(model_label: str, kwargs: Mapping[str, Any]) -> None:
    """Validate ORM .filter(**kwargs) against the active pin."""
    pinned = get_pinned_school_id()
    if not pinned:
        return
    try:
        verify_tenant_boundary_scope(
            pinned_school_id=pinned,
            orm_kwargs=kwargs,
        )
    except SecurityIsolationException as exc:
        raise SecurityIsolationException(
            f"ORM tenant boundary violation on {model_label}.",
            detail=exc.detail,
            code=exc.code,
        ) from exc


class TenantBoundaryExecuteWrapper:
    """Django connection.execute_wrapper callable — intercepts raw SQL."""

    def __call__(self, execute, sql, params, many, context):
        pinned = get_pinned_school_id()
        if pinned and not is_boundary_bypassed():
            verify_tenant_boundary_scope(
                pinned_school_id=pinned,
                sql=str(sql or ""),
                params=params,
            )
        return execute(sql, params, many, context)


def make_execute_wrapper() -> TenantBoundaryExecuteWrapper:
    return TenantBoundaryExecuteWrapper()


@contextmanager
def pinned_tenant_boundary(*, school_id: Any, host: str = ""):
    """Explicit pin for Celery tasks and tests."""
    token = pin_tenant_boundary(school_id=school_id, host=host)
    try:
        yield token
    finally:
        unpin_tenant_boundary(token)


def integrate_rls_bypass_context() -> None:
    """
    Extend apps.schools.rls_context bypass managers to also bypass boundary guard.
    Idempotent — safe to call from AppConfig.ready().
    """
    try:
        from apps.schools import rls_context as rls_mod
    except ImportError:
        return

    if getattr(integrate_rls_bypass_context, "_integrated", False):
        return

    original_bypass = rls_mod.rls_bypass

    @contextmanager
    def _rls_bypass_with_boundary():
        with boundary_bypass(reason="rls_bypass"):
            with original_bypass():
                yield

    rls_mod.rls_bypass = _rls_bypass_with_boundary
    integrate_rls_bypass_context._integrated = True  # type: ignore[attr-defined]
