"""
Structured logging: request_id, tenant_id, user_id on every log line (RunMyCampus blueprint A4).
Middleware sets context; this filter adds the values to LogRecord.
"""
from contextvars import ContextVar
import logging

# Context vars set by RequestIdLoggingMiddleware
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
_tenant_id_ctx: ContextVar[str] = ContextVar("tenant_id", default="")
_user_id_ctx: ContextVar[str] = ContextVar("user_id", default="")


def set_request_logging_context(request_id: str = "", tenant_id: str = "", user_id: str = "") -> None:
    """Set context for the current request (called by middleware)."""
    _request_id_ctx.set(request_id or "")
    _tenant_id_ctx.set(tenant_id or "")
    _user_id_ctx.set(user_id or "")


def clear_request_logging_context() -> None:
    """Clear context (called at end of request)."""
    _request_id_ctx.set("")
    _tenant_id_ctx.set("")
    _user_id_ctx.set("")


class RequestContextFilter(logging.Filter):
    """Add request_id, tenant_id, user_id to every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", None) or _request_id_ctx.get() or "-"
        record.tenant_id = getattr(record, "tenant_id", None) or _tenant_id_ctx.get() or "-"
        record.user_id = getattr(record, "user_id", None) or _user_id_ctx.get() or "-"
        return True
