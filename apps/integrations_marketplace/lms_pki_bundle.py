"""v4.00.78 — LMS PKI bundle export helper.

When an operator needs to hand off their LMS connector configuration to
counsel (incident response), to a successor admin, or to a downstream
auditor, they want a single self-describing bundle: which providers are
configured, which are scaffold, what the canonical OAuth endpoints are,
what the public-key fingerprints look like (NEVER the private keys or
client secrets), and which Celery beats sweep them.

This module exports the bundle SAFELY — secrets are excluded by
construction (no env / setting reads of the *_SECRET / *_PRIVATE_KEY
pattern). The bundle is JSON-serializable and operator-facing.

Surface:
  * ``build_lms_pki_bundle()`` -> dict
  * ``bundle_fingerprint(bundle)`` -> str  — SHA-256[:16] of the canonical
    JSON form. Useful for tamper-evident hand-off receipts.

Bundle shape:
  {
    "generated_at": "...",
    "schema_version": "v4.00.78",
    "providers": [
      {
        "slug": "canvas",
        "label": "Canvas LMS",
        "maturity": "production",
        "oauth_ready": True,
        "is_scaffold": False,
        "authorize_url": "<provider-specific or empty>",
        "token_url": "<provider-specific or empty>",
        "default_scopes": [...],
      },
      ...
    ],
    "beats_in_use": ["integrations-lms-token-refresh", ...],
    "audit_tables": ["LMSDiagActionAudit", "LMSPushGradeAudit"],
    "retention_default_years": 7,
    "notes": ["..."],
  }
"""
from __future__ import annotations

import hashlib
import json
import logging

logger = logging.getLogger(__name__)


SCHEMA_VERSION = "v4.00.78"


def _provider_endpoints(slug: str) -> dict:
    """Return ``{authorize_url, token_url, default_scopes}`` per provider
    using the in-tree connector modules where available. Scaffold
    providers expose the same shape (per v4.00.69+ design)."""
    if slug == "canvas":
        # Canvas authorize/token URLs are operator-instance-specific
        # (per-school subdomain). Expose the spec-required path suffixes only.
        return {
            "authorize_url_suffix": "/login/oauth2/auth",
            "token_url_suffix": "/login/oauth2/token",
            "default_scopes": ["url:GET|/api/v1/courses", "url:POST|/api/v1/courses/:course_id/assignments"],
        }
    if slug == "moodle":
        return {
            "authorize_url_suffix": "/login/oauth2.php",
            "token_url_suffix": "/login/token.php",
            "default_scopes": [],
        }
    if slug in ("google_classroom", "google"):
        return {
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "default_scopes": [
                "https://www.googleapis.com/auth/classroom.courses.readonly",
                "https://www.googleapis.com/auth/classroom.coursework.students",
            ],
        }
    if slug == "schoology":
        try:
            from apps.integrations_marketplace import lms_connector_schoology as sg
            return {
                "authorize_url": sg.DEFAULT_AUTHORIZE_URL,
                "token_url": sg.DEFAULT_TOKEN_URL,
                "default_scopes": [],
            }
        except Exception:  # noqa: BLE001
            return {}
    if slug == "d2l_brightspace":
        try:
            from apps.integrations_marketplace import lms_connector_d2l as d2l
            return {
                "authorize_url": d2l.DEFAULT_AUTHORIZE_URL,
                "token_url": d2l.DEFAULT_TOKEN_URL,
                "default_scopes": list(d2l.DEFAULT_SCOPES),
            }
        except Exception:  # noqa: BLE001
            return {}
    return {}


def build_lms_pki_bundle() -> dict:
    """Build the operator-facing PKI bundle. NEVER raises."""
    try:
        from apps.integrations_marketplace import lms_supported_providers as lsp
        provider_slugs = list(lsp.lms_provider_rollup_order())
        cards = lsp.lms_provider_rollup_card()
        cards_by_slug = {c["slug"]: c for c in cards}
    except Exception as exc:  # noqa: BLE001
        logger.debug("pki bundle: lsp unavailable: %s", exc)
        provider_slugs = []
        cards_by_slug = {}

    providers = []
    for slug in provider_slugs:
        card = cards_by_slug.get(slug, {})
        endpoints = _provider_endpoints(slug)
        providers.append({
            "slug": slug,
            "label": card.get("label", slug),
            "maturity": card.get("maturity", "unknown"),
            "oauth_ready": card.get("oauth_ready", False),
            "is_scaffold": card.get("is_scaffold", False),
            **endpoints,
        })

    from django.utils import timezone as _tz
    return {
        "generated_at": _tz.now().isoformat(),
        "schema_version": SCHEMA_VERSION,
        "providers": providers,
        "beats_in_use": [
            "integrations-lms-token-refresh",
            "integrations-lms-token-rotation",
            "integrations-lms-oauth-health",
            "integrations-lms-oauth-auto-prune",
            "integrations-lms-audit-retention",
            "integrations-purge-lms-diag-action-rows",
        ],
        "audit_tables": ["LMSDiagActionAudit", "LMSPushGradeAudit"],
        "retention_default_years": 7,
        "notes": [
            "Bundle excludes secrets by construction — only public endpoint "
            "URLs + scope strings + provider maturity pills. Safe to attach "
            "to counsel hand-off PDFs.",
            "Use bundle_fingerprint() to mint a tamper-evident receipt.",
        ],
    }


def bundle_fingerprint(bundle: dict) -> str:
    """Return ``sha256(canonical-json-of-bundle)[:16]``. Stable across
    Python versions because we sort keys + use compact separators."""
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
