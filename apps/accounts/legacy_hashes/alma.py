"""Alma SIS bcrypt verifier — distinct slug, same underlying format."""
from __future__ import annotations

from ._bcrypt_helper import verify_bcrypt
from .base import LegacyHashVerifier, VerifierResult, register


class AlmaBcryptVerifier(LegacyHashVerifier):
    """Verifier for Alma-SIS-exported bcrypt hashes.

    Distinct slug from generic ``bcrypt`` so migration-cloud audit logs
    can attribute provenance without re-reading the source vendor field.
    """

    algorithm = "alma_bcrypt"

    def verify(
        self, password: str, stored_hash: str, params: dict
    ) -> VerifierResult:
        return verify_bcrypt(password, stored_hash)


register("alma_bcrypt", AlmaBcryptVerifier())
