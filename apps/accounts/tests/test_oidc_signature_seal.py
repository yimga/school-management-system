"""Regression seal: OIDC id_token must be signature-verified (auth-bypass fix).

Bug (2026-06-17 gap analysis): the OIDC callback base64-decoded the id_token with NO
signature verification and trusted email + groups->role, so a forged token granted login
as any user/role (incl. ADMIN). Fix: require the authorization-code exchange (front-channel
id_token is never trusted) and verify the signature against the IdP JWKS via PyJWT.

Hermetic: generates an RSA keypair, signs tokens with PyJWT, and patches PyJWKClient to
serve the public key — no network, no DB.
"""
import datetime
from unittest.mock import MagicMock, patch

import jwt
from jwt.exceptions import PyJWTError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import SimpleTestCase

from apps.accounts.views_oidc import _NoVerificationMaterial, _verify_id_token

_CLIENT_ID = "client-123"
_ISSUER = "https://idp.example.com"


def _gen_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, pub


def _make_token(priv, **overrides):
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": "u1",
        "email": "user@example.com",
        "aud": _CLIENT_ID,
        "iss": _ISSUER,
        "nonce": "N",
        "iat": now,
        "exp": now + datetime.timedelta(hours=1),
    }
    payload.update(overrides)
    return jwt.encode(payload, priv, algorithm="RS256")


class OidcSignatureSealTests(SimpleTestCase):
    def _patch_jwks(self, public_pem):
        signing_key = MagicMock()
        signing_key.key = public_pem
        client = MagicMock()
        client.get_signing_key_from_jwt.return_value = signing_key
        return patch("apps.accounts.views_oidc.PyJWKClient", return_value=client)

    def test_no_material_raises(self):
        # No jwks_uri / issuer / discovery -> cannot verify -> signal caller.
        with self.assertRaises(_NoVerificationMaterial):
            _verify_id_token("a.b.c", cfg={}, client_id=_CLIENT_ID)

    def test_valid_signature_accepted(self):
        priv, pub = _gen_keypair()
        token = _make_token(priv)
        cfg = {"jwks_uri": "https://idp.example.com/jwks", "issuer": _ISSUER}
        with self._patch_jwks(pub):
            claims = _verify_id_token(token, cfg=cfg, client_id=_CLIENT_ID)
        self.assertEqual(claims["email"], "user@example.com")
        self.assertEqual(claims["nonce"], "N")

    def test_forged_signature_rejected(self):
        # Token signed by a DIFFERENT key than the JWKS serves -> rejected.
        _, pub = _gen_keypair()
        attacker_priv, _ = _gen_keypair()
        token = _make_token(attacker_priv, email="ceo@victim.example.com")
        cfg = {"jwks_uri": "https://idp.example.com/jwks", "issuer": _ISSUER}
        with self._patch_jwks(pub):
            with self.assertRaises(PyJWTError):
                _verify_id_token(token, cfg=cfg, client_id=_CLIENT_ID)

    def test_wrong_audience_rejected(self):
        priv, pub = _gen_keypair()
        token = _make_token(priv, aud="some-other-client")
        cfg = {"jwks_uri": "https://idp.example.com/jwks", "issuer": _ISSUER}
        with self._patch_jwks(pub):
            with self.assertRaises(PyJWTError):
                _verify_id_token(token, cfg=cfg, client_id=_CLIENT_ID)

    def test_expired_token_rejected(self):
        priv, pub = _gen_keypair()
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        token = _make_token(priv, iat=past, exp=past + datetime.timedelta(minutes=1))
        cfg = {"jwks_uri": "https://idp.example.com/jwks", "issuer": _ISSUER}
        with self._patch_jwks(pub):
            with self.assertRaises(PyJWTError):
                _verify_id_token(token, cfg=cfg, client_id=_CLIENT_ID)
