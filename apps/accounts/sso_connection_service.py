"""Self-serve SSO connection service (F5b) — presets + OIDC discovery + upsert.

Pure, Django-light logic behind the tenant-admin "Connect SSO" wizard
(``views_sso_admin``). A connection is persisted as a per-school
``ServiceIntegration`` (service_type=OAUTH) row — the same row the login page's
SSO buttons (``_get_login_sso_integrations``) and the OIDC/SAML views
(``views_oidc``/``views_saml``) already consume.

Provider presets pre-fill the OIDC discovery URL for the common IdPs so the
admin only pastes a client id + secret; ``fetch_oidc_discovery`` then resolves
the real authorization/token/jwks endpoints so the connection works end to end
(``oidc_start`` needs ``authorization_endpoint``, ``oidc_callback`` needs
``token_endpoint`` — neither is discovered at request time).
"""

from __future__ import annotations

import json
import logging
from urllib.parse import urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Provider presets. ``idp_type`` decides oidc_start vs saml_start on the login
# page; ``label`` is the default button text (SSO_LABEL_MAP already maps
# google/microsoft too). No secrets or per-school values live here.
SSO_PROVIDER_PRESETS: dict[str, dict] = {
    "google": {
        "label": "Google",
        "idp_type": "oidc",
        "discovery_url": "https://accounts.google.com/.well-known/openid-configuration",
        "scope": "openid email profile",
    },
    "microsoft": {
        "label": "Microsoft",
        "idp_type": "oidc",
        # {tenant} = Entra tenant id/domain, or "organizations"/"common".
        "discovery_url_template": "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration",
        "default_tenant": "organizations",
        "scope": "openid email profile",
        "needs_tenant": True,
    },
    "okta": {
        "label": "Okta",
        "idp_type": "oidc",
        "scope": "openid email profile",
        "needs_issuer": True,
    },
    "oidc": {
        "label": "OpenID Connect",
        "idp_type": "oidc",
        "scope": "openid email profile",
    },
    "saml": {
        "label": "SAML 2.0",
        "idp_type": "saml",
    },
}

_DISCOVERY_KEYS = (
    "authorization_endpoint",
    "token_endpoint",
    "jwks_uri",
    "issuer",
    "end_session_endpoint",
    "userinfo_endpoint",
)


def provider_choices() -> list[tuple[str, str]]:
    """(key, label) pairs for the provider picker, common IdPs first."""
    order = ["google", "microsoft", "okta", "oidc", "saml"]
    return [(k, SSO_PROVIDER_PRESETS[k]["label"]) for k in order if k in SSO_PROVIDER_PRESETS]


def preset_idp_type(preset_key: str) -> str:
    return SSO_PROVIDER_PRESETS.get(preset_key, {}).get("idp_type", "oidc")


def resolve_discovery_url(
    preset_key: str,
    *,
    discovery_url: str = "",
    issuer: str = "",
    tenant: str = "",
) -> str:
    """Resolve the OIDC discovery URL from an explicit value, a preset, or an issuer."""
    if (discovery_url or "").strip():
        return discovery_url.strip()
    preset = SSO_PROVIDER_PRESETS.get(preset_key, {})
    if preset.get("discovery_url"):
        return str(preset["discovery_url"])
    if preset.get("discovery_url_template"):
        t = (tenant or "").strip() or str(preset.get("default_tenant") or "organizations")
        return str(preset["discovery_url_template"]).format(tenant=t)
    iss = (issuer or "").strip()
    if iss:
        return iss.rstrip("/") + "/.well-known/openid-configuration"
    return ""


def fetch_oidc_discovery(discovery_url: str, *, timeout: int = 10) -> dict:
    """Fetch + validate an OIDC ``.well-known/openid-configuration`` document.

    Returns ``{"ok": True, "endpoints": {...}}`` on success or
    ``{"ok": False, "error": "..."}``. Never raises. Requires https.
    """
    url = (discovery_url or "").strip()
    if not url:
        return {"ok": False, "error": "No discovery URL provided."}
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return {"ok": False, "error": "Discovery URL must use https."}
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - admin-entered IdP discovery URL
            doc = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "error": f"Could not reach the IdP discovery URL ({exc.__class__.__name__}).",
        }
    if not isinstance(doc, dict):
        return {"ok": False, "error": "Discovery response was not a JSON object."}
    endpoints = {k: str(doc.get(k) or "").strip() for k in _DISCOVERY_KEYS if doc.get(k)}
    if not endpoints.get("authorization_endpoint") or not endpoints.get("token_endpoint"):
        return {
            "ok": False,
            "error": "Discovery document is missing the authorization or token endpoint.",
        }
    return {"ok": True, "endpoints": endpoints}
