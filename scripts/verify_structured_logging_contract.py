#!/usr/bin/env python3
"""Observability depth gate: structured logging contract remains wired in settings.

v2: middleware ordering, filter factory path, and logging_context implementation present.
v3: logging_context exposes clear_request_logging_context (request teardown symmetry).
v4: When ``LOG_JSON=1``, ``JsonFormatter`` ``fmt`` must still reference the same
    LogRecord keys (``request_id``, ``tenant_id``, ``user_id``, ``school_id``) that
    ``RequestContextFilter`` sets; otherwise JSON lines may omit structured context.
v5 (batch 16 #152): ``http_method`` must appear on ``LogRecord`` via
    ``RequestContextFilter`` and in both ``verbose_request`` and ``json`` formatters.
v6 (batch 17 #167): ``request_path`` (truncated URL path, no query string) on
    ``LogRecord`` and in both formatters; middleware sets it from ``request.path``.
v7 (batch 23 #257): ``remote_addr`` (``REMOTE_ADDR``, truncated) on ``LogRecord`` and in
    both formatters; middleware passes client IP into ``set_request_logging_context``.
v8 (batch 24 #272): ``http_referer`` (``HTTP_REFERER``, truncated) on ``LogRecord`` and in
    both formatters; middleware passes referer into ``set_request_logging_context``;
    ``clear_request_logging_context`` must reset ``_http_referer_ctx``; when ``LOG_JSON=1``,
    the ``json`` formatter ``fmt`` must include ``%(http_referer)s`` (parity with
    ``RequestContextFilter``).
v9 (batch 25 #287): ``http_user_agent`` (``HTTP_USER_AGENT``, truncated) on ``LogRecord`` and
    in both formatters; ``clear_request_logging_context`` resets ``_http_user_agent_ctx``;
    JSON ``fmt`` includes ``%(http_user_agent)s``.
v10 (batch 27 #317): ``http_host`` (``get_host()`` / ``HTTP_HOST``, truncated) on ``LogRecord``
    and in both formatters; ``clear_request_logging_context`` resets ``_http_host_ctx``;
    JSON ``fmt`` includes ``%(http_host)s``. ``content_type`` uses ``_content_type_ctx`` teardown
    in the same clear function (formatters already reference ``%(content_type)s``).
v11 (batch 27 #317): ``accept_language`` (``HTTP_ACCEPT_LANGUAGE``, truncated) on ``LogRecord`` and
    in both formatters; ``clear_request_logging_context`` resets ``_accept_language_ctx``;
    JSON ``fmt`` includes ``%(accept_language)s``.
v12 (batch 28 #332): ``accept_encoding`` (``HTTP_ACCEPT_ENCODING``, truncated) on ``LogRecord`` and
    in both formatters; ``clear_request_logging_context`` resets ``_accept_encoding_ctx``;
    JSON ``fmt`` includes ``%(accept_encoding)s``.
v13 (batch 29 #347): ``x_forwarded_for`` (``HTTP_X_FORWARDED_FOR``, truncated) on ``LogRecord`` and
    in both formatters; ``clear_request_logging_context`` resets ``_x_forwarded_for_ctx``;
    JSON ``fmt`` includes ``%(x_forwarded_for)s``.
v14 (batch 30 #362): ``x_forwarded_proto`` (``HTTP_X_FORWARDED_PROTO``, lowercased, truncated) on
    ``LogRecord`` and in both formatters; ``clear_request_logging_context`` resets
    ``_x_forwarded_proto_ctx``; JSON ``fmt`` includes ``%(x_forwarded_proto)s``.
v15 (batch 31 #377): ``content_length`` (``CONTENT_LENGTH`` digits-only, ``_CONTENT_LENGTH_MAX_LEN``)
    on ``LogRecord`` and in both formatters; ``clear_request_logging_context`` resets
    ``_content_length_ctx``; JSON ``fmt`` includes ``%(content_length)s``.
v16 (batch 32 #392): ``x_forwarded_host`` (``HTTP_X_FORWARDED_HOST``, lowercased, truncated) on
    ``LogRecord`` and in both formatters; ``clear_request_logging_context`` resets
    ``_x_forwarded_host_ctx``; JSON ``fmt`` includes ``%(x_forwarded_host)s``.
v17 (batch 33 #407): ``http_origin`` (``HTTP_ORIGIN``, truncated) on ``LogRecord`` and in both
    formatters; ``clear_request_logging_context`` resets ``_http_origin_ctx``; JSON ``fmt`` includes
    ``%(http_origin)s``.
v18 (batch 34 #422): ``query_string`` (``QUERY_STRING``, truncated, ``_QUERY_STRING_MAX_LEN``) on
    ``LogRecord`` and in both formatters; ``clear_request_logging_context`` resets
    ``_query_string_ctx``; JSON ``fmt`` includes ``%(query_string)s``.
v19 (batch 35 #437): ``server_protocol`` (``SERVER_PROTOCOL``, truncated, ``_SERVER_PROTOCOL_MAX_LEN``) on
    ``LogRecord`` and in both formatters; ``clear_request_logging_context`` resets
    ``_server_protocol_ctx``; JSON ``fmt`` includes ``%(server_protocol)s``.
v20 (batch 35 #437): ``request_scheme`` (``request.scheme``, lowercased, ``_REQUEST_SCHEME_MAX_LEN``) on
    ``LogRecord`` and in both formatters; ``clear_request_logging_context`` resets
    ``_request_scheme_ctx``; JSON ``fmt`` includes ``%(request_scheme)s``.
v21 (batch 36 #452): ``server_name`` (``SERVER_NAME``, truncated, ``_SERVER_NAME_MAX_LEN``) on
    ``LogRecord`` and in both formatters; ``clear_request_logging_context`` resets
    ``_server_name_ctx``; JSON ``fmt`` includes ``%(server_name)s``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "config" / "settings.py"
LOGGING_CONTEXT = ROOT / "apps" / "observability" / "logging_context.py"


def main() -> int:
    errors: list[str] = []
    if not SETTINGS.is_file():
        errors.append("config/settings.py missing")
        return _fail(errors)
    if not LOGGING_CONTEXT.is_file():
        errors.append("apps/observability/logging_context.py missing")
        return _fail(errors)

    ctx_text = LOGGING_CONTEXT.read_text(encoding="utf-8", errors="replace")
    if "class RequestContextFilter" not in ctx_text:
        errors.append("logging_context.py missing RequestContextFilter class")
    if "def clear_request_logging_context" not in ctx_text:
        errors.append("logging_context.py missing clear_request_logging_context")
    if "record.http_method" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.http_method (batch 16 #152)"
        )
    if "record.request_path" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.request_path (batch 17 #167)"
        )
    if "record.remote_addr" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.remote_addr (batch 23 #257)"
        )
    if "record.http_referer" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.http_referer (batch 24 #272)"
        )
    if "record.http_user_agent" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.http_user_agent (batch 25 #287)"
        )
    if "record.http_host" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.http_host (batch 27 #317)"
        )
    if "record.content_type" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.content_type"
        )
    if "record.accept_language" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.accept_language"
        )
    if "record.accept_encoding" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.accept_encoding"
        )
    if "record.x_forwarded_for" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.x_forwarded_for (batch 29 #347)"
        )
    if "record.x_forwarded_proto" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.x_forwarded_proto (batch 30 #362)"
        )
    if "record.content_length" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.content_length (batch 31 #377)"
        )
    if "record.http_origin" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.http_origin (batch 33 #407)"
        )
    if "record.query_string" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.query_string (batch 34 #422)"
        )
    if "record.server_protocol" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.server_protocol (batch 35 #437)"
        )
    if "record.request_scheme" not in ctx_text:
        errors.append(
            "logging_context.py RequestContextFilter must set record.request_scheme (batch 35 #437 v20)"
        )
    idx_clear = ctx_text.find("def clear_request_logging_context")
    if idx_clear != -1:
        end_clear = ctx_text.find("\n\n", idx_clear)
        clear_fn = ctx_text[idx_clear : end_clear if end_clear != -1 else len(ctx_text)]
        if "_http_referer_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _http_referer_ctx (batch 24 #272)"
            )
        if "_http_host_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _http_host_ctx (batch 27 #317)"
            )
        if "_content_type_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _content_type_ctx"
            )
        if "_accept_language_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _accept_language_ctx (batch 27 #317)"
            )
        if "_accept_encoding_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _accept_encoding_ctx (batch 28 #332)"
            )
        if "_x_forwarded_for_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _x_forwarded_for_ctx (batch 29 #347)"
            )
        if "_x_forwarded_proto_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _x_forwarded_proto_ctx (batch 30 #362)"
            )
        if "_x_forwarded_host_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _x_forwarded_host_ctx (batch 32 #392)"
            )
        if "_content_length_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _content_length_ctx (batch 31 #377)"
            )
        if "_http_origin_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _http_origin_ctx (batch 33 #407)"
            )
        if "_query_string_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _query_string_ctx (batch 34 #422)"
            )
        if "_server_protocol_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _server_protocol_ctx (batch 35 #437)"
            )
        if "_request_scheme_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _request_scheme_ctx (batch 35 #437 v20)"
            )
        if "_server_name_ctx.set" not in clear_fn:
            errors.append(
                "logging_context.py clear_request_logging_context must reset _server_name_ctx (batch 36 #452)"
            )

    text = SETTINGS.read_text(encoding="utf-8", errors="replace")
    required_tokens = (
        "apps.observability.middleware.RequestIdLoggingMiddleware",
        "apps.observability.middleware.ObservabilityMiddleware",
        "%(request_id)s",
        "%(tenant_id)s",
        "%(user_id)s",
        "%(school_id)s",
        "%(http_method)s",
        "%(remote_addr)s",
        "%(http_referer)s",
        "%(http_user_agent)s",
        "%(http_host)s",
        "%(content_type)s",
        "%(accept_language)s",
        "%(accept_encoding)s",
        "%(x_forwarded_for)s",
        "%(x_forwarded_proto)s",
        "%(content_length)s",
        "%(http_origin)s",
        "%(query_string)s",
        "%(server_protocol)s",
        "%(request_scheme)s",
        "%(server_name)s",
        "\"request_context\"",
        "apps.observability.logging_context.RequestContextFilter",
    )
    for token in required_tokens:
        if token not in text:
            errors.append(f"config/settings.py missing logging contract token: {token!r}")

    j0 = text.find('"json"')
    if j0 != -1:
        j1 = text.find('"handlers"', j0)
        json_chunk = text[j0 : j1 if j1 != -1 else len(text)]
        for key in (
            "%(request_id)s",
            "%(tenant_id)s",
            "%(user_id)s",
            "%(school_id)s",
            "%(http_method)s",
            "%(request_path)s",
            "%(remote_addr)s",
            "%(http_referer)s",
            "%(http_user_agent)s",
            "%(http_host)s",
            "%(content_type)s",
            "%(accept_language)s",
            "%(accept_encoding)s",
            "%(x_forwarded_for)s",
            "%(x_forwarded_proto)s",
            "%(x_forwarded_host)s",
            "%(content_length)s",
            "%(http_origin)s",
            "%(query_string)s",
            "%(server_protocol)s",
            "%(request_scheme)s",
            "%(server_name)s",
        ):
            if key not in json_chunk:
                errors.append(
                    f"LOGGING formatters json fmt must include {key!r} when using "
                    "LOG_JSON=1 (RequestContextFilter parity; batch 15 #142 / batch 27 #317)"
                )

    idx_req = text.find("RequestIdLoggingMiddleware")
    idx_obs = text.find("ObservabilityMiddleware")
    if idx_req != -1 and idx_obs != -1 and idx_req > idx_obs:
        errors.append(
            "RequestIdLoggingMiddleware must appear before ObservabilityMiddleware in settings.py"
        )

    if not _console_handler_uses_request_context(text):
        errors.append(
            'LOGGING_HANDLERS["console"] must set "filters": ["request_context"] '
            "(propagates request_id/tenant_id/user_id/school_id onto LogRecord)"
        )

    if errors:
        return _fail(errors)

    print(
        "verify_structured_logging_contract: PASS "
        "(middleware order + request_context filter + verbose_request + json fmt tokens + "
        "school_id + http_method + request_path + remote_addr + http_referer + "
        "http_user_agent + http_host + content_type + accept_language + accept_encoding + "
        "x_forwarded_for + x_forwarded_proto + x_forwarded_host + content_length + "
        "http_origin + query_string + server_protocol + request_scheme + server_name + logging_context teardown hook)"
    )
    return 0


def _console_handler_uses_request_context(text: str) -> bool:
    """Console StreamHandler must wire RequestContextFilter (not only the file handler)."""
    start = text.find("LOGGING_HANDLERS = {")
    if start == -1:
        return False
    stop = text.find("\n\n# Optional per-file", start)
    if stop == -1:
        block = text[start:]
    else:
        block = text[start:stop]
    return bool(
        re.search(
            r'"console"\s*:\s*\{[^{}]*"filters"\s*:\s*\[\s*"request_context"\s*\][^{}]*\}',
            block,
            re.DOTALL,
        )
    )


def _fail(errors: list[str]) -> int:
    print("verify_structured_logging_contract: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
