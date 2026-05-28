"""Set per-request regional DB alias when ENABLE_MULTI_REGION (batch 1535)."""

from __future__ import annotations

from django.conf import settings

from apps.platform_runtime.dynamic_db_routing import (
    clear_request_db_alias,
    resolve_school_db_alias,
    set_request_db_alias,
)


class RegionalDatabaseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "ENABLE_MULTI_REGION", False):
            return self.get_response(request)
        alias = None
        school = getattr(request, "school", None)
        if school is not None:
            alias = resolve_school_db_alias(school)
        if alias:
            set_request_db_alias(alias)
        try:
            return self.get_response(request)
        finally:
            clear_request_db_alias()
