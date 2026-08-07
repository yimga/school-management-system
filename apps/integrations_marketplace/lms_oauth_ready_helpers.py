"""v4.00.91 Studio-OS-10X W1 Pillar B1-B4 — Shared OAUTH_READY contract helpers.

Each scaffold-tier connector promotes to OAUTH_READY by re-exporting three
functions whose payloads + error taxonomies match the v4.00.89 Schoology /
D2L pattern. To avoid 4× duplication (Blackboard / PowerSchool / Sakai /
Itslearning), the OAUTH_READY contract lives here and per-provider modules
register themselves via :func:`make_oauth_ready_helpers`.

Live outbound (real HTTP calls) is gated behind a per-provider env flag:
``RMC_<PROVIDER>_OAUTH_LIVE_OUTBOUND``. Absent / unset / falsy → returns
``status: "dry_run_scaffold"`` envelopes with the *intended request shape*
so callers can unit-test their payload assembly without hitting the network.
Setting the env to ``"true"`` flips into live-HTTP mode (where production
adapters route to the v4.00.90 ``oauth_live_path_helpers`` infrastructure
for RFC-6749 error decode, Retry-After parsing, token-expiry checks).

The contract:
  * ``exchange_authorization_code_for_token(*, state, code, ...)`` →
        ``{status, provider, access_token (redacted), expires_in,
           issued_at_iso, scope, audit_id}``
  * ``refresh_access_token(*, refresh_token, ...)`` → mirror of exchange
  * ``push_grade_live(*, student_external_id, course_external_id,
        assignment_external_id, score, max_score)`` → ``{status,
        target_method, target_path_suffix, body}``

All three NEVER log secrets (access_token / refresh_token / client_secret /
code / api_key / private_key / signature_text / authorization-code / state
/ nonce / id_token / DPoP-proof). Token correlation uses
SHA-256[:12] hash so audit rows stay useful without leaking material.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _hash_token(token: str) -> str:
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8", errors="replace")).hexdigest()[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _live_outbound_enabled(env_var: str) -> bool:
    raw = os.environ.get(env_var, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _absolutize_endpoint(url: str, base_url: str = "") -> str | None:
    """Return an absolute http(s) endpoint, or None if one cannot be formed.

    blackboard / powerschool / sakai carry their token + grade paths as SUFFIXES
    of an operator-supplied per-tenant base_url (never a bare host), so posting the
    raw relative path to ``requests`` raised ``MissingSchema`` the moment live
    outbound was enabled. Resolve the relative suffix against the base_url; if the
    result still has no scheme, return None so the caller reports an honest config
    error instead of crashing.
    """
    from urllib.parse import urljoin, urlparse

    url = (url or "").strip()
    if urlparse(url).scheme in ("http", "https"):
        return url
    base = (base_url or "").strip()
    if base and urlparse(base).scheme in ("http", "https"):
        joined = urljoin(base, url)
        if urlparse(joined).scheme in ("http", "https"):
            return joined
    return None


def make_oauth_ready_helpers(
    *,
    provider_slug: str,
    live_env_var: str,
    token_url: str,
    grade_push_path_builder=None,
    grade_push_method: str = "PUT",
) -> dict[str, Any]:
    """Return a dict of three callables ready to bind into a provider module.

    Each provider then does::

        _helpers = make_oauth_ready_helpers(
            provider_slug="blackboard",
            live_env_var="RMC_BLACKBOARD_OAUTH_LIVE_OUTBOUND",
            token_url=DEFAULT_TOKEN_URL,
            grade_push_path_builder=lambda c, a, s: f"/.../{c}/.../{a}/.../{s}",
        )
        exchange_authorization_code_for_token = _helpers["exchange"]
        refresh_access_token = _helpers["refresh"]
        push_grade_live = _helpers["push_grade_live"]
    """

    def exchange_authorization_code_for_token(
        *,
        state: str,
        code: str,
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not code:
            return {"status": "bad_request", "provider": provider_slug, "reason": "missing_code"}
        if not state:
            return {"status": "bad_request", "provider": provider_slug, "reason": "missing_state"}
        live = _live_outbound_enabled(live_env_var)
        audit_id = _hash_token(code)
        if not live:
            return {
                "status": "dry_run_scaffold",
                "provider": provider_slug,
                "token_url": token_url,
                "audit_id": audit_id,
                "would_send": {
                    "method": "POST",
                    "endpoint": token_url,
                    "form_keys": ["grant_type", "code", "redirect_uri", "client_id"],
                    "grant_type": "authorization_code",
                },
                "live_env_var": live_env_var,
                "note": "set env to 'true' to enable live HTTP outbound",
            }
        # Live path delegates to oauth_live_path_helpers for RFC-6749 decode.
        try:
            from apps.integrations_marketplace.oauth_live_path_helpers import (
                decode_oauth2_error_response,
                parse_retry_after,
            )
            import requests
        except ImportError as exc:
            return {"status": "live_outbound_unavailable", "provider": provider_slug,
                    "reason": f"deps_missing:{exc}"}
        endpoint = _absolutize_endpoint(token_url, str(_kwargs.get("base_url") or ""))
        if endpoint is None:
            return {"status": "config_error", "provider": provider_slug,
                    "reason": "relative_token_url_requires_base_url",
                    "token_url": token_url, "audit_id": audit_id}
        try:
            resp = requests.post(
                endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            return {"status": "network_error", "provider": provider_slug, "reason": str(exc)[:120],
                    "audit_id": audit_id}
        if resp.status_code >= 400:
            err = decode_oauth2_error_response(resp.text or "")
            return {
                "status": "oauth_error",
                "provider": provider_slug,
                "http_status": resp.status_code,
                "oauth_error_code": err.get("error", "upstream_error_unknown"),
                "oauth_error_description": err.get("error_description", "")[:256],
                "retry_after_seconds": parse_retry_after(resp.headers.get("Retry-After")),
                "audit_id": audit_id,
            }
        try:
            body = resp.json()
        except ValueError:
            return {"status": "bad_response", "provider": provider_slug, "reason": "non_json_response",
                    "audit_id": audit_id}
        return {
            "status": "ok",
            "provider": provider_slug,
            "access_token_hash": _hash_token(body.get("access_token", "")),
            "refresh_token_hash": _hash_token(body.get("refresh_token", "")),
            "expires_in": body.get("expires_in"),
            "issued_at_iso": _now_iso(),
            "scope": body.get("scope", ""),
            "audit_id": audit_id,
        }

    def refresh_access_token(
        *,
        refresh_token: str,
        client_id: str = "",
        client_secret: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not refresh_token:
            return {"status": "bad_request", "provider": provider_slug, "reason": "missing_refresh_token"}
        live = _live_outbound_enabled(live_env_var)
        audit_id = _hash_token(refresh_token)
        if not live:
            return {
                "status": "dry_run_scaffold",
                "provider": provider_slug,
                "token_url": token_url,
                "audit_id": audit_id,
                "would_send": {
                    "method": "POST",
                    "endpoint": token_url,
                    "form_keys": ["grant_type", "refresh_token", "client_id"],
                    "grant_type": "refresh_token",
                },
                "live_env_var": live_env_var,
            }
        try:
            from apps.integrations_marketplace.oauth_live_path_helpers import (
                decode_oauth2_error_response,
                parse_retry_after,
            )
            import requests
        except ImportError as exc:
            return {"status": "live_outbound_unavailable", "provider": provider_slug,
                    "reason": f"deps_missing:{exc}"}
        endpoint = _absolutize_endpoint(token_url, str(_kwargs.get("base_url") or ""))
        if endpoint is None:
            return {"status": "config_error", "provider": provider_slug,
                    "reason": "relative_token_url_requires_base_url",
                    "token_url": token_url, "audit_id": audit_id}
        try:
            resp = requests.post(
                endpoint,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            return {"status": "network_error", "provider": provider_slug, "reason": str(exc)[:120],
                    "audit_id": audit_id}
        if resp.status_code >= 400:
            err = decode_oauth2_error_response(resp.text or "")
            return {
                "status": "oauth_error",
                "provider": provider_slug,
                "http_status": resp.status_code,
                "oauth_error_code": err.get("error", "upstream_error_unknown"),
                "oauth_error_description": err.get("error_description", "")[:256],
                "retry_after_seconds": parse_retry_after(resp.headers.get("Retry-After")),
                "audit_id": audit_id,
            }
        try:
            body = resp.json()
        except ValueError:
            return {"status": "bad_response", "provider": provider_slug, "reason": "non_json_response"}
        return {
            "status": "ok",
            "provider": provider_slug,
            "access_token_hash": _hash_token(body.get("access_token", "")),
            "refresh_token_hash": _hash_token(body.get("refresh_token", "")),
            "expires_in": body.get("expires_in"),
            "issued_at_iso": _now_iso(),
            "audit_id": audit_id,
        }

    def push_grade_live(
        *,
        student_external_id: str,
        course_external_id: str,
        assignment_external_id: str,
        score: float,
        max_score: float,
        access_token: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        # Same input validation as the v4.00.82 scaffolds.
        if not student_external_id:
            return {"status": "bad_request", "provider": provider_slug, "reason": "missing_field",
                    "field": "student_external_id"}
        if not course_external_id:
            return {"status": "bad_request", "provider": provider_slug, "reason": "missing_field",
                    "field": "course_external_id"}
        if not assignment_external_id:
            return {"status": "bad_request", "provider": provider_slug, "reason": "missing_field",
                    "field": "assignment_external_id"}
        if grade_push_path_builder is None:
            path_suffix = f"/grades/{course_external_id}/{assignment_external_id}/{student_external_id}"
        else:
            path_suffix = grade_push_path_builder(course_external_id, assignment_external_id, student_external_id)
        body = {
            "student_external_id": student_external_id,
            "score": score,
            "max_score": max_score,
        }
        live = _live_outbound_enabled(live_env_var)
        if not live:
            return {
                "status": "dry_run_scaffold",
                "provider": provider_slug,
                "target_method": grade_push_method,
                "target_path_suffix": path_suffix,
                "body": body,
                "live_env_var": live_env_var,
            }
        try:
            import requests
        except ImportError as exc:
            return {"status": "live_outbound_unavailable", "provider": provider_slug,
                    "reason": f"deps_missing:{exc}"}
        if not access_token:
            return {"status": "bad_request", "provider": provider_slug, "reason": "missing_access_token"}
        endpoint = _absolutize_endpoint(path_suffix, str(_kwargs.get("base_url") or ""))
        if endpoint is None:
            return {"status": "config_error", "provider": provider_slug,
                    "reason": "relative_grade_path_requires_base_url",
                    "target_path_suffix": path_suffix}
        try:
            resp = requests.request(
                grade_push_method,
                endpoint,
                json=body,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            return {"status": "network_error", "provider": provider_slug, "reason": str(exc)[:120]}
        if resp.status_code >= 400:
            return {"status": "upstream_error", "provider": provider_slug,
                    "http_status": resp.status_code}
        return {"status": "ok", "provider": provider_slug, "http_status": resp.status_code,
                "issued_at_iso": _now_iso()}

    return {
        "exchange": exchange_authorization_code_for_token,
        "refresh": refresh_access_token,
        "push_grade_live": push_grade_live,
    }
