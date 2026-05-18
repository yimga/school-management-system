"""Legacy hash verifier ABC + verifier registry.

The migration cloud preserves credentials from legacy SIS vendors via the
"lazy rehash on first login" pattern (Discourse / Auth0 / Keycloak). On
first successful login we verify against the foreign hash, then
immediately re-hash to the native Argon2 / BCrypt configured in
``settings.PASSWORD_HASHERS`` and clear the legacy fields.

Each per-vendor module in :mod:`apps.accounts.legacy_hashes` defines a
subclass of :class:`LegacyHashVerifier` and registers it via
:func:`register`. The package ``__init__`` exposes a stable surface for the
auth backend: :func:`verify` and :func:`is_supported_algorithm`.

Critical security invariants enforced by tests:

* Constant-time comparisons (``hmac.compare_digest`` or ``bcrypt.checkpw``).
* Verifiers never log the password, the salt, or the stored hash.
* Unknown algorithms return ``None`` from :func:`get_verifier`; the backend
  treats this as "no match" — not as an error — so a corrupted row never
  raises through the auth path.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class VerifierResult:
    """Outcome of a single verify call.

    Attributes:
        matched: True iff the supplied password is the original behind
            ``stored_hash``.
        reason: A short, NON-SENSITIVE audit string (e.g. ``"matched"``,
            ``"bad_password"``, ``"unsupported_param"``). MUST NOT contain
            the password, the hash, or the salt.
    """

    matched: bool
    reason: str


class LegacyHashVerifier(abc.ABC):
    """Base class for a single foreign-vendor hash format."""

    algorithm: str = ""

    @abc.abstractmethod
    def verify(
        self, password: str, stored_hash: str, params: dict
    ) -> VerifierResult:
        """Return whether ``password`` is the pre-image of ``stored_hash``.

        Implementations MUST use constant-time comparison and MUST NOT log
        the password, salt, or stored_hash.
        """


# Module-level registry. Populated by per-vendor modules at import time via
# :func:`register`. Reads happen via :func:`get_verifier`.
_REGISTRY: Dict[str, LegacyHashVerifier] = {}


def register(algorithm: str, verifier: LegacyHashVerifier) -> None:
    """Register ``verifier`` under the algorithm slug.

    Algorithm slugs are stable identifiers stored on the User row
    (``User.legacy_hash_algorithm``) and must match what the migration
    cloud companion app writes during import.
    """
    if not algorithm:
        raise ValueError("algorithm slug must be non-empty")
    _REGISTRY[algorithm] = verifier


def get_verifier(algorithm: str) -> Optional[LegacyHashVerifier]:
    """Look up a verifier; return ``None`` if the slug is not registered."""
    return _REGISTRY.get(algorithm)


def known_algorithms() -> list[str]:
    """Snapshot of registered algorithm slugs (for diagnostics)."""
    return sorted(_REGISTRY.keys())
