"""Tenant-scoped operator URLs for guardian consent (v3.40.0 Agent 11).

Companion to ``urls_guardian_consent`` — the anonymous namespace is
kept separate from this admin namespace so reverse-resolve grammars
do not accidentally compose.

Mounted from ``config/urls.py`` at ``/migration/`` (overlaps with
Agent 7's ``/migration/`` but uses distinct path segments
``/<uuid>/consent/...`` that do not collide with Agent 7's
``/<uuid>/sign-maa/``, ``/<uuid>/status/``, ``/<uuid>/abandon/``).
"""
from __future__ import annotations

from . import urls_guardian_consent

app_name = "migration_guardian_consent_admin"

urlpatterns = urls_guardian_consent.admin_urlpatterns
