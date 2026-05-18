"""Legacy hash verifier registry for the migration cloud credential moat.

Imports per-vendor modules to populate :mod:`.base._REGISTRY` at package
import time. Exposes a stable public surface for
:mod:`apps.accounts.auth_backends_legacy`:

* :func:`verify` — verify a password against a stored legacy hash.
* :func:`is_supported_algorithm` — algorithm slug check (no I/O).
* :func:`known_algorithms` — diagnostic snapshot.

See :mod:`apps.accounts.legacy_hashes.base` for the abstract base class
and registration helpers.
"""
from __future__ import annotations

from .base import (
    LegacyHashVerifier,
    VerifierResult,
    get_verifier,
    known_algorithms,
)

# Import per-vendor modules for their register() side effects. Order is
# stable so the registry is deterministic across processes.
from . import powerschool  # noqa: F401  PBKDF2-SHA512
from . import blackbaud  # noqa: F401  bcrypt
from . import veracross  # noqa: F401  bcrypt (distinct slug)
from . import alma  # noqa: F401  bcrypt (distinct slug)
from . import facts  # noqa: F401  bcrypt OR PBKDF2-SHA1 auto-detect
from . import skyward  # noqa: F401  bcrypt OR salted SHA-512 auto-detect


def is_supported_algorithm(algorithm: str) -> bool:
    """Return True iff a verifier is registered for the slug."""
    return get_verifier(algorithm) is not None


def verify(
    algorithm: str, params: dict, stored_hash: str, password: str
) -> bool:
    """Verify ``password`` against ``stored_hash`` under ``algorithm``.

    Returns ``False`` on unknown algorithm, malformed hash, or any
    exception inside the verifier — the auth backend treats a False
    return as "no match", never as "error". This is intentional: a
    corrupted legacy row must never raise through the auth path.
    """
    verifier = get_verifier(algorithm)
    if verifier is None:
        return False
    try:
        result = verifier.verify(password, stored_hash, params or {})
    except (ValueError, TypeError, ImportError):
        # Defensive: a corrupted row shouldn't crash login. ImportError
        # bubbles up only if bcrypt is missing — the operator should see
        # that via the structured docket, not via a 500.
        return False
    return bool(result.matched)


__all__ = [
    "LegacyHashVerifier",
    "VerifierResult",
    "is_supported_algorithm",
    "known_algorithms",
    "verify",
]
