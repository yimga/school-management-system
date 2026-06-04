"""v4.00.92 — RFC 8414 OAuth 2.0 Authorization Server Metadata.

Exposes ``/.well-known/oauth-authorization-server`` so OAuth2 clients can
discover the OneRoster v1.2 token endpoint + supported grant types +
scopes WITHOUT operator pre-configuration. Complements the W25 Wave 25
``oneroster_oauth2_token`` module by making the OAuth2 surface
self-describing per RFC 8414 § 3.

The document is JSON-served + anonymous-readable (intentional per RFC
8414 § 3.1 — discovery metadata MUST be retrievable without
authentication). It carries NO secret material — only public surface
descriptions: issuer URL, token endpoint URL, supported grant types,
supported scopes (the IMS roster vocab), and the response signing
algorithm.

The metadata document is cacheable (`Cache-Control: public, max-age=3600`)
so well-behaved clients won't hammer the endpoint on every token
request.
"""
from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, HttpResponse

from apps.api.oneroster_oauth2_token import IMS_ROSTER_SCOPES


def _resolve_issuer(request: HttpRequest) -> str:
    """Return the issuer URL — the base URL the API is served from.

    Falls back to the request's host header if env-derived base URL is
    not configured. Stripped of trailing slash for consistency with the
    rest of the RFC 8414 fields (which are appended paths).
    """
    import os

    explicit = os.environ.get("RMC_ONEROSTER_OAUTH_ISSUER", "").strip()
    if explicit:
        return explicit.rstrip("/")
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    return f"{scheme}://{host}".rstrip("/")


def build_oauth2_authorization_server_metadata(request: HttpRequest) -> dict[str, Any]:
    """Build the RFC 8414 § 3 discovery document.

    Includes ONLY the fields the OneRoster v1.2 client_credentials grant
    actually supports — no padding with unimplemented features (e.g. we
    do NOT advertise authorization_code or refresh_token grants here
    because the OneRoster inbound surface implements only
    client_credentials).
    """
    issuer = _resolve_issuer(request)
    return {
        # Required RFC 8414 § 2 fields.
        "issuer": issuer,
        "token_endpoint": f"{issuer}/api/roster/v1p2/oauth/token/",
        "grant_types_supported": ["client_credentials"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "response_types_supported": ["token"],
        "scopes_supported": sorted(IMS_ROSTER_SCOPES),
        # Per-implementation extensions (RFC 8414 § 2.1 — registration
        # not required for these but they help OneRoster client SDKs).
        "service_documentation": "https://github.com/IMSGlobal/oneroster",
        "ui_locales_supported": ["en", "es", "fr", "de", "ar"],
        # Document the response token shape so SDKs know to use Bearer
        # in subsequent API calls (not e.g. PoP / DPoP).
        "response_token_types_supported": ["Bearer"],
        "token_endpoint_auth_signing_alg_values_supported": ["HS256"],
        # Specify the OneRoster spec we conform to so consumers can
        # detect protocol revisions.
        "oneroster_spec_version": "v1.2",
        # Cache hint for well-behaved clients (RFC 8414 § 3 says metadata
        # is cacheable; we make the freshness window explicit).
        "metadata_cache_duration_seconds": 3600,  # magic-number-allow: duration-seconds
    }


def oauth2_authorization_server_metadata_view(request: HttpRequest) -> HttpResponse:
    """GET /.well-known/oauth-authorization-server

    Per RFC 8414 § 3.1, anonymous-readable. Returns 200 + JSON document.
    Cache-Control: public, max-age=3600.

    Not exposed via DRF — pure JSON HttpResponse so the discovery
    document is parser-stable and doesn't depend on DRF version.
    """
    # rbac-allow: oauth2-discovery-metadata-anonymous-public-readable
    body = build_oauth2_authorization_server_metadata(request)
    response = HttpResponse(
        json.dumps(body, separators=(",", ":")).encode("utf-8"),
        content_type="application/json; charset=utf-8",
    )
    response["Cache-Control"] = "public, max-age=3600"
    response["X-Robots-Tag"] = "noindex"  # discovery doc, not human content
    return response
