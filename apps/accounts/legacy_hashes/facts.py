"""FACTS Management (RenWeb / SIS / Tuition) auto-detect verifier.

FACTS' user table is a Ship-of-Theseus across RenWeb acquisitions: older
rows are raw PBKDF2-HMAC-SHA1 hex (40 chars / 160 bits, salt + iterations
stored separately), newer rows are bcrypt ``$2a$``/``$2b$``. The companion
app extractor cannot reliably distinguish the two formats at export time,
so we detect by prefix at verify time.
"""
from __future__ import annotations

import binascii
import hashlib
import hmac

from ._bcrypt_helper import verify_bcrypt
from .base import LegacyHashVerifier, VerifierResult, register


_DEFAULT_PBKDF2_SHA1_ITERATIONS = 10_000
_SHA1_HEX_LEN = 40


def _is_hex(value: str, expected_len: int) -> bool:
    if len(value) != expected_len:
        return False
    try:
        bytes.fromhex(value)
    except (ValueError, binascii.Error):
        return False
    return True


class FACTSAutoDetectVerifier(LegacyHashVerifier):
    """Dispatch to bcrypt or PBKDF2-SHA1 based on the stored hash shape."""

    algorithm = "facts_auto"

    def verify(
        self, password: str, stored_hash: str, params: dict
    ) -> VerifierResult:
        if not password or not stored_hash:
            return VerifierResult(matched=False, reason="empty_input")

        sh = stored_hash.strip()

        # Newer FACTS rows: bcrypt format.
        if sh.startswith(("$2a$", "$2b$", "$2y$")):
            return verify_bcrypt(password, sh)

        # Older RenWeb rows: PBKDF2-HMAC-SHA1 stored as hex.
        if _is_hex(sh, _SHA1_HEX_LEN):
            salt_raw = (params or {}).get("salt", "")
            if not isinstance(salt_raw, str) or not salt_raw:
                return VerifierResult(matched=False, reason="missing_salt")
            try:
                salt = bytes.fromhex(salt_raw)
            except (ValueError, binascii.Error):
                # Allow utf-8 salt as fallback (some RenWeb exports do this).
                salt = salt_raw.encode("utf-8")

            iterations = (params or {}).get(
                "iterations", _DEFAULT_PBKDF2_SHA1_ITERATIONS
            )
            try:
                iterations = int(iterations)
            except (TypeError, ValueError):
                iterations = _DEFAULT_PBKDF2_SHA1_ITERATIONS
            if iterations <= 0:
                iterations = _DEFAULT_PBKDF2_SHA1_ITERATIONS

            expected = bytes.fromhex(sh)
            derived = hashlib.pbkdf2_hmac(
                "sha1",
                password.encode("utf-8"),
                salt,
                iterations,
                dklen=len(expected),
            )
            matched = hmac.compare_digest(derived, expected)
            return VerifierResult(
                matched=matched,
                reason="matched" if matched else "bad_password",
            )

        return VerifierResult(matched=False, reason="unrecognized_format")


register("facts_auto", FACTSAutoDetectVerifier())
