"""Veracross bcrypt verifier — distinct slug, same underlying format."""
from __future__ import annotations

from ._bcrypt_helper import verify_bcrypt
from .base import LegacyHashVerifier, VerifierResult, register


class VeracrossBcryptVerifier(LegacyHashVerifier):
    """Verifier for Veracross-exported bcrypt hashes.

    Kept as a distinct algorithm slug from generic ``bcrypt`` so that
    migration-cloud audit logs can attribute "this user came from
    Veracross" without re-reading the source vendor field. Verification
    logic is identical to Blackbaud / Alma.
    """

    algorithm = "veracross_bcrypt"

    def verify(
        self, password: str, stored_hash: str, params: dict
    ) -> VerifierResult:
        return verify_bcrypt(password, stored_hash)


register("veracross_bcrypt", VeracrossBcryptVerifier())
