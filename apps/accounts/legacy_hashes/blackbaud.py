"""Blackbaud (Education Management / ON / Whipple Hill) bcrypt verifier."""
from __future__ import annotations

from ._bcrypt_helper import verify_bcrypt
from .base import LegacyHashVerifier, VerifierResult, register


class BlackbaudBcryptVerifier(LegacyHashVerifier):
    """Verifier for Blackbaud-exported bcrypt hashes.

    Blackbaud's auth stores credentials as bcrypt ``$2a$``/``$2b$``
    strings. The full hash string includes the cost factor and salt, so
    ``params`` is unused for this vendor.
    """

    algorithm = "bcrypt"

    def verify(
        self, password: str, stored_hash: str, params: dict
    ) -> VerifierResult:
        return verify_bcrypt(password, stored_hash)


register("bcrypt", BlackbaudBcryptVerifier())
