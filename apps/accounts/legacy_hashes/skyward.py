"""Skyward (Qmlativ / SMS 2.0) auto-detect verifier.

Skyward installations span 30+ years; the credential store reflects that.
Older Qmlativ rows store salted SHA-512 as 128-char hex; newer rows
(post-cloud migration) use bcrypt. Dispatch by prefix / shape.
"""
from __future__ import annotations

import binascii
import hashlib
import hmac

from ._bcrypt_helper import verify_bcrypt
from .base import LegacyHashVerifier, VerifierResult, register


_SHA512_HEX_LEN = 128


def _is_hex(value: str, expected_len: int) -> bool:
    if len(value) != expected_len:
        return False
    try:
        bytes.fromhex(value)
    except (ValueError, binascii.Error):
        return False
    return True


class SkywardAutoDetectVerifier(LegacyHashVerifier):
    """Dispatch to bcrypt or salted SHA-512 based on the stored hash shape."""

    algorithm = "skyward_auto"

    def verify(
        self, password: str, stored_hash: str, params: dict
    ) -> VerifierResult:
        if not password or not stored_hash:
            return VerifierResult(matched=False, reason="empty_input")

        sh = stored_hash.strip()

        # Cloud-era Skyward: bcrypt.
        if sh.startswith(("$2a$", "$2b$", "$2y$")):
            return verify_bcrypt(password, sh)

        # Legacy on-prem Skyward: salted SHA-512 stored as 128-char hex.
        if _is_hex(sh, _SHA512_HEX_LEN):
            salt_raw = (params or {}).get("salt", "")
            if not isinstance(salt_raw, str):
                return VerifierResult(matched=False, reason="missing_salt")
            # Skyward exports typically store the salt as utf-8 text, not hex.
            salt_bytes = salt_raw.encode("utf-8") if salt_raw else b""

            digest = hashlib.sha512(
                salt_bytes + password.encode("utf-8")
            ).hexdigest()

            # Constant-time compare on the hex strings.
            matched = hmac.compare_digest(digest, sh.lower())
            return VerifierResult(
                matched=matched,
                reason="matched" if matched else "bad_password",
            )

        return VerifierResult(matched=False, reason="unrecognized_format")


register("skyward_auto", SkywardAutoDetectVerifier())
