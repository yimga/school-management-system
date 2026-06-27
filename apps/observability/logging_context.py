"""
Structured logging: request_id, tenant_id, user_id, school_id, http_method, request_path,
remote_addr, http_referer, http_user_agent, http_host, content_type, accept_language,
accept_encoding, x_forwarded_for, x_forwarded_proto, x_forwarded_host, content_length,
http_origin, query_string, server_protocol, request_scheme, server_name on every log line (A4).
Middleware sets context; this filter adds the values to LogRecord.
"""

from contextvars import ContextVar
import logging

# Context vars set by RequestIdLoggingMiddleware
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
_tenant_id_ctx: ContextVar[str] = ContextVar("tenant_id", default="")
_user_id_ctx: ContextVar[str] = ContextVar("user_id", default="")
_school_id_ctx: ContextVar[str] = ContextVar("school_id", default="")
# Operator-impersonation markers (Wave C #4 Phase 2). When a platform operator is
# acting inside a tenant via the impersonation session, request.user IS the operator
# (it is not swapped to the tenant user), so the audit actor is already correct — these
# flag the "during impersonation of school X" fact so mutations can be told apart from
# the operator's normal actions. Default False/"" outside impersonation.
_during_impersonation_ctx: ContextVar[bool] = ContextVar(
    "during_impersonation", default=False
)
_impersonated_school_id_ctx: ContextVar[str] = ContextVar(
    "impersonated_school_id", default=""
)
_http_method_ctx: ContextVar[str] = ContextVar("http_method", default="")
_request_path_ctx: ContextVar[str] = ContextVar("request_path", default="")
_remote_addr_ctx: ContextVar[str] = ContextVar("remote_addr", default="")
_http_referer_ctx: ContextVar[str] = ContextVar("http_referer", default="")
_http_user_agent_ctx: ContextVar[str] = ContextVar("http_user_agent", default="")
_http_host_ctx: ContextVar[str] = ContextVar("http_host", default="")
_content_type_ctx: ContextVar[str] = ContextVar("content_type", default="")
_accept_language_ctx: ContextVar[str] = ContextVar("accept_language", default="")
_accept_encoding_ctx: ContextVar[str] = ContextVar("accept_encoding", default="")
_x_forwarded_for_ctx: ContextVar[str] = ContextVar("x_forwarded_for", default="")
_x_forwarded_proto_ctx: ContextVar[str] = ContextVar("x_forwarded_proto", default="")
_x_forwarded_host_ctx: ContextVar[str] = ContextVar("x_forwarded_host", default="")
_content_length_ctx: ContextVar[str] = ContextVar("content_length", default="")
_http_origin_ctx: ContextVar[str] = ContextVar("http_origin", default="")
_query_string_ctx: ContextVar[str] = ContextVar("query_string", default="")
_server_protocol_ctx: ContextVar[str] = ContextVar("server_protocol", default="")
_request_scheme_ctx: ContextVar[str] = ContextVar("request_scheme", default="")
_server_name_ctx: ContextVar[str] = ContextVar("server_name", default="")

_REQUEST_PATH_MAX_LEN = 256
_REMOTE_ADDR_MAX_LEN = 45
_HTTP_REFERER_MAX_LEN = 256
_HTTP_USER_AGENT_MAX_LEN = 512
_HTTP_HOST_MAX_LEN = 253
_CONTENT_TYPE_MAX_LEN = 128
_ACCEPT_LANGUAGE_MAX_LEN = 256
_ACCEPT_ENCODING_MAX_LEN = 128
_X_FORWARDED_FOR_MAX_LEN = 256
_X_FORWARDED_PROTO_MAX_LEN = 32
_X_FORWARDED_HOST_MAX_LEN = 253
_CONTENT_LENGTH_MAX_LEN = 24
_HTTP_ORIGIN_MAX_LEN = 256
_QUERY_STRING_MAX_LEN = 512
_SERVER_PROTOCOL_MAX_LEN = 32
_REQUEST_SCHEME_MAX_LEN = 16
_SERVER_NAME_MAX_LEN = 253


def set_request_logging_context(
    request_id: str = "",
    tenant_id: str = "",
    user_id: str = "",
    school_id: str = "",
    http_method: str = "",
    request_path: str = "",
    remote_addr: str = "",
    http_referer: str = "",
    http_user_agent: str = "",
    http_host: str = "",
    content_type: str = "",
    accept_language: str = "",
    accept_encoding: str = "",
    x_forwarded_for: str = "",
    x_forwarded_proto: str = "",
    x_forwarded_host: str = "",
    content_length: str = "",
    http_origin: str = "",
    query_string: str = "",
    server_protocol: str = "",
    request_scheme: str = "",
    server_name: str = "",
) -> None:
    """Set context for the current request (called by middleware)."""
    _request_id_ctx.set(request_id or "")
    _tenant_id_ctx.set(tenant_id or "")
    _user_id_ctx.set(user_id or "")
    _school_id_ctx.set(school_id or "")
    _http_method_ctx.set((http_method or "").upper() or "")
    path = (request_path or "").strip() or ""
    if len(path) > _REQUEST_PATH_MAX_LEN:
        path = path[: _REQUEST_PATH_MAX_LEN - 1] + "…"
    _request_path_ctx.set(path)
    addr = (remote_addr or "").strip() or ""
    if len(addr) > _REMOTE_ADDR_MAX_LEN:
        addr = addr[: _REMOTE_ADDR_MAX_LEN - 1] + "…"
    _remote_addr_ctx.set(addr)
    ref = (http_referer or "").strip() or ""
    if len(ref) > _HTTP_REFERER_MAX_LEN:
        ref = ref[: _HTTP_REFERER_MAX_LEN - 1] + "…"
    _http_referer_ctx.set(ref)
    ua = (http_user_agent or "").strip() or ""
    if len(ua) > _HTTP_USER_AGENT_MAX_LEN:
        ua = ua[: _HTTP_USER_AGENT_MAX_LEN - 1] + "…"
    _http_user_agent_ctx.set(ua)
    host = (http_host or "").strip() or ""
    if len(host) > _HTTP_HOST_MAX_LEN:
        host = host[: _HTTP_HOST_MAX_LEN - 1] + "…"
    _http_host_ctx.set(host)
    ct = (content_type or "").strip() or ""
    if len(ct) > _CONTENT_TYPE_MAX_LEN:
        ct = ct[: _CONTENT_TYPE_MAX_LEN - 1] + "…"
    _content_type_ctx.set(ct)
    al = (accept_language or "").strip() or ""
    if len(al) > _ACCEPT_LANGUAGE_MAX_LEN:
        al = al[: _ACCEPT_LANGUAGE_MAX_LEN - 1] + "…"
    _accept_language_ctx.set(al)
    enc = (accept_encoding or "").strip() or ""
    if len(enc) > _ACCEPT_ENCODING_MAX_LEN:
        enc = enc[: _ACCEPT_ENCODING_MAX_LEN - 1] + "…"
    _accept_encoding_ctx.set(enc)
    xff = (x_forwarded_for or "").strip() or ""
    if len(xff) > _X_FORWARDED_FOR_MAX_LEN:
        xff = xff[: _X_FORWARDED_FOR_MAX_LEN - 1] + "…"
    _x_forwarded_for_ctx.set(xff)
    xfp = (x_forwarded_proto or "").strip().lower() or ""
    if len(xfp) > _X_FORWARDED_PROTO_MAX_LEN:
        xfp = xfp[: _X_FORWARDED_PROTO_MAX_LEN - 1] + "…"
    _x_forwarded_proto_ctx.set(xfp)
    xfh = (x_forwarded_host or "").strip().lower() or ""
    if len(xfh) > _X_FORWARDED_HOST_MAX_LEN:
        xfh = xfh[: _X_FORWARDED_HOST_MAX_LEN - 1] + "…"
    _x_forwarded_host_ctx.set(xfh)
    cl_digits = "".join(ch for ch in (content_length or "") if ch.isdigit())
    if len(cl_digits) > _CONTENT_LENGTH_MAX_LEN:
        cl_digits = cl_digits[: _CONTENT_LENGTH_MAX_LEN - 1] + "…"
    _content_length_ctx.set(cl_digits)
    ho = (http_origin or "").strip() or ""
    if len(ho) > _HTTP_ORIGIN_MAX_LEN:
        ho = ho[: _HTTP_ORIGIN_MAX_LEN - 1] + "…"
    _http_origin_ctx.set(ho)
    qs = (query_string or "").strip() or ""
    if len(qs) > _QUERY_STRING_MAX_LEN:
        qs = qs[: _QUERY_STRING_MAX_LEN - 1] + "…"
    _query_string_ctx.set(qs)
    sp = (server_protocol or "").strip() or ""
    if len(sp) > _SERVER_PROTOCOL_MAX_LEN:
        sp = sp[: _SERVER_PROTOCOL_MAX_LEN - 1] + "…"
    _server_protocol_ctx.set(sp)
    sch = (request_scheme or "").strip().lower() or ""
    if len(sch) > _REQUEST_SCHEME_MAX_LEN:
        sch = sch[: _REQUEST_SCHEME_MAX_LEN - 1] + "…"
    _request_scheme_ctx.set(sch)
    sn = (server_name or "").strip() or ""
    if len(sn) > _SERVER_NAME_MAX_LEN:
        sn = sn[: _SERVER_NAME_MAX_LEN - 1] + "…"
    _server_name_ctx.set(sn)


def clear_request_logging_context() -> None:
    """Clear context (called at end of request)."""
    _request_id_ctx.set("")
    _tenant_id_ctx.set("")
    _user_id_ctx.set("")
    _school_id_ctx.set("")
    _during_impersonation_ctx.set(False)
    _impersonated_school_id_ctx.set("")
    _http_method_ctx.set("")
    _request_path_ctx.set("")
    _remote_addr_ctx.set("")
    _http_referer_ctx.set("")
    _http_user_agent_ctx.set("")
    _http_host_ctx.set("")
    _content_type_ctx.set("")
    _accept_language_ctx.set("")
    _accept_encoding_ctx.set("")
    _x_forwarded_for_ctx.set("")
    _x_forwarded_proto_ctx.set("")
    _x_forwarded_host_ctx.set("")
    _content_length_ctx.set("")
    _http_origin_ctx.set("")
    _query_string_ctx.set("")
    _server_protocol_ctx.set("")
    _request_scheme_ctx.set("")
    _server_name_ctx.set("")


def get_current_user_id() -> str:
    """Return the current request's authenticated user PK as a string (or "").

    Set by ``RequestIdLoggingMiddleware`` from ``request.user.pk``. Readable from
    ORM signals / tasks that have no handle on the request object — e.g. the
    compliance audit signals, which run at the ORM layer and otherwise cannot
    attribute a mutation to an actor. Returns "" when unauthenticated or outside
    a request (system / management-command / migration writes).
    """
    return _user_id_ctx.get()


def get_current_school_id() -> str:
    """Return the current request's resolved school PK as a string (or "").

    Companion to :func:`get_current_user_id`; same request-context source.
    """
    return _school_id_ctx.get()


def set_impersonation_logging_context(
    during_impersonation: bool, impersonated_school_id: str = ""
) -> None:
    """Mark the current request as an operator-impersonation session.

    Called by ``RequestIdLoggingMiddleware`` when ``request.session`` carries an
    ``"impersonation"`` block. Read by the compliance audit signals so a mutation
    made while impersonating a tenant is stamped with that fact (the operator is
    already the request user, hence already the audit actor).
    """
    _during_impersonation_ctx.set(bool(during_impersonation))
    _impersonated_school_id_ctx.set((impersonated_school_id or "")[:64])


def get_current_during_impersonation() -> bool:
    """True when the current request is an operator-impersonation session."""
    return bool(_during_impersonation_ctx.get())


def get_current_impersonated_school_id() -> str:
    """School PK (string) being impersonated this request, or "" if none."""
    return _impersonated_school_id_ctx.get()


class RequestContextFilter(logging.Filter):
    """Add request-scoped fields to LogRecord for structured formatters."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = (
            getattr(record, "request_id", None) or _request_id_ctx.get() or "-"
        )
        record.tenant_id = (
            getattr(record, "tenant_id", None) or _tenant_id_ctx.get() or "-"
        )
        record.user_id = getattr(record, "user_id", None) or _user_id_ctx.get() or "-"
        record.school_id = (
            getattr(record, "school_id", None) or _school_id_ctx.get() or "-"
        )
        record.http_method = (
            getattr(record, "http_method", None) or _http_method_ctx.get() or "-"
        )
        record.request_path = (
            getattr(record, "request_path", None) or _request_path_ctx.get() or "-"
        )
        record.remote_addr = (
            getattr(record, "remote_addr", None) or _remote_addr_ctx.get() or "-"
        )
        record.http_referer = (
            getattr(record, "http_referer", None) or _http_referer_ctx.get() or "-"
        )
        record.http_user_agent = (
            getattr(record, "http_user_agent", None) or _http_user_agent_ctx.get() or "-"
        )
        record.http_host = (
            getattr(record, "http_host", None) or _http_host_ctx.get() or "-"
        )
        record.content_type = (
            getattr(record, "content_type", None) or _content_type_ctx.get() or "-"
        )
        record.accept_language = (
            getattr(record, "accept_language", None)
            or _accept_language_ctx.get()
            or "-"
        )
        record.accept_encoding = (
            getattr(record, "accept_encoding", None)
            or _accept_encoding_ctx.get()
            or "-"
        )
        record.x_forwarded_for = (
            getattr(record, "x_forwarded_for", None)
            or _x_forwarded_for_ctx.get()
            or "-"
        )
        record.x_forwarded_proto = (
            getattr(record, "x_forwarded_proto", None)
            or _x_forwarded_proto_ctx.get()
            or "-"
        )
        record.x_forwarded_host = (
            getattr(record, "x_forwarded_host", None)
            or _x_forwarded_host_ctx.get()
            or "-"
        )
        record.content_length = (
            getattr(record, "content_length", None)
            or _content_length_ctx.get()
            or "-"
        )
        record.http_origin = (
            getattr(record, "http_origin", None) or _http_origin_ctx.get() or "-"
        )
        record.query_string = (
            getattr(record, "query_string", None) or _query_string_ctx.get() or "-"
        )
        record.server_protocol = (
            getattr(record, "server_protocol", None)
            or _server_protocol_ctx.get()
            or "-"
        )
        record.request_scheme = (
            getattr(record, "request_scheme", None) or _request_scheme_ctx.get() or "-"
        )
        record.server_name = (
            getattr(record, "server_name", None) or _server_name_ctx.get() or "-"
        )
        return True
