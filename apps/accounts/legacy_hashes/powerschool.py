"""PowerSchool legacy hash verifier — PBKDF2-HMAC-SHA512.

PowerSchool's user table stores credentials as PBKDF2-HMAC-SHA512 with a
per-user salt and a server-wide iteration count (historically 50_000;
newer deployments use up to 100_000). The companion-app extractor writes
the raw hash + salt + iteration count into ``User.legacy_password_hash``
and ``User.legacy_hash_params`` so we can verify on first login.

Implementation uses :func:`hashlib.pbkdf2_hmac` from the standard library
— no third-party dependency. Constant-time comparison via
:func:`hmac.compare_digest`.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac

from .base import LegacyHashVerifier, VerifierResult, register


_DEFAULT_ITERATIONS = 50_000
_DKLEN = 64  # SHA-512 output


def _decode_hex_or_b64(value: str) -> bytes:
    """Decode a salt/hash stored as either hex or base64.

    PowerSchool exports vary by vendor tool. We accept both forms so the
    companion app extractor doesn't have to normalize.
    """
    value = (value or "").strip()
    if not value:
        return b""
    # Try hex first (PowerSchool's native format).
    try:
        return bytes.fromhex(value)
    except (ValueError, binascii.Error):
        pass
    # Fall back to base64 (some exports rewrap).
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        return b""


class PowerSchoolPBKDF2SHA512Verifier(LegacyHashVerifier):
    """Verifier for PowerSchool's PBKDF2-HMAC-SHA512 password hashes."""

    algorithm = "pbkdf2_sha512"

    def verify(
        self, password: str, stored_hash: str, params: dict
    ) -> VerifierResult:
        if not password or not stored_hash:
            return VerifierResult(matched=False, reason="empty_input")

        salt_raw = (params or {}).get("salt", "")
        salt = _decode_hex_or_b64(salt_raw) if isinstance(salt_raw, str) else b""
        if not salt:
            return VerifierResult(matched=False, reason="missing_salt")

        iterations = (params or {}).get("iterations", _DEFAULT_ITERATIONS)
        try:
            iterations = int(iterations)
        except (TypeError, ValueError):
            iterations = _DEFAULT_ITERATIONS
        if iterations <= 0:
            iterations = _DEFAULT_ITERATIONS

        expected = _decode_hex_or_b64(stored_hash)
        if not expected:
            return VerifierResult(matched=False, reason="malformed_hash")

        # PBKDF2 output length defaults to the SHA-512 digest size (64 bytes);
        # if the legacy system truncated to a different length, honour that.
        dklen = len(expected) if len(expected) > 0 else _DKLEN

        derived = hashlib.pbkdf2_hmac(
            "sha512",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=dklen,
        )

        if hmac.compare_digest(derived, expected):
            return VerifierResult(matched=True, reason="matched")
        return VerifierResult(matched=False, reason="bad_password")


register("pbkdf2_sha512", PowerSchoolPBKDF2SHA512Verifier())
