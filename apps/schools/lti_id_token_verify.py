"""
LTI 1.3: verify id_token from tool platform (LMS) using JWKS.
public_endpoint_audit §6 — signature verification when lti_tool_jwks_uri is set.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def verify_lti_id_token(
    id_token: str,
    *,
    audience: str,
    jwks_uri: str,
    issuer: str | None = None,
) -> dict[str, Any]:
    """
    Verify RS256/ES256 JWT from tool authorization server.
    Raises jwt exceptions on failure.
    """
    import jwt
    from jwt import PyJWKClient

    jwks_client = PyJWKClient(jwks_uri, cache_keys=True)
    signing_key = jwks_client.get_signing_key_from_jwt(id_token)
    options = {"require": ["exp", "iat", "sub"]}
    kwargs: dict[str, Any] = {
        "algorithms": ["RS256", "ES256", "RS384", "ES384"],
        "audience": audience,
        "options": options,
    }
    if issuer:
        kwargs["issuer"] = issuer
    return jwt.decode(id_token, signing_key.key, **kwargs)


def decode_lti_id_token_safe(
    id_token: str,
    *,
    audience: str,
    cfg: dict,
) -> tuple[dict | None, str | None]:
    """
    If integration.config has lti_tool_jwks_uri (and optionally lti_tool_issuer), verify.
    Else if settings.LTI_REQUIRE_SIGNED_ID_TOKEN is True, fail.
    Else decode unverified (legacy).
    Returns (claims, error_message).
    """
    from django.conf import settings

    jwks_uri = str(cfg.get("lti_tool_jwks_uri") or "").strip()
    tool_issuer = str(cfg.get("lti_tool_issuer") or "").strip() or None
    strict = getattr(settings, "LTI_REQUIRE_SIGNED_ID_TOKEN", False)

    if jwks_uri:
        try:
            claims = verify_lti_id_token(
                id_token,
                audience=audience,
                jwks_uri=jwks_uri,
                issuer=tool_issuer,
            )
            return claims, None
        except Exception as e:
            logger.warning("LTI id_token verify failed: %s", e)
            return None, "invalid_id_token_signature"

    if strict:
        return None, "lti_tool_jwks_uri_required"

    return _decode_payload_unverified(id_token), None


def _decode_payload_unverified(id_token: str) -> dict:
    import base64
    import json
    from binascii import Error as BinasciiError

    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + ("=" * (-len(parts[1]) % 4))
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except (
        ValueError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        BinasciiError,
    ):
        return {}
