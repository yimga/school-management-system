"""Shared bcrypt verification helper used by Blackbaud, Veracross, and Alma.

Tries the native ``bcrypt`` C-extension first (fastest, what production
should ship); falls back to ``passlib.hash.bcrypt`` for environments
where only passlib is installed; raises a clear ImportError if neither
is available.

Constant-time comparison is handled inside ``bcrypt.checkpw`` /
``passlib.hash.bcrypt.verify`` — we never compare hash strings directly.
"""
from __future__ import annotations

from .base import VerifierResult


def _checkpw(password: str, stored_hash: str) -> bool:
    """Verify ``password`` against a bcrypt-format ``stored_hash``."""
    pw_bytes = password.encode("utf-8")
    hash_bytes = stored_hash.encode("utf-8")
    try:
        import bcrypt  # type: ignore[import-not-found]
    except ImportError:
        pass
    else:
        try:
            return bool(bcrypt.checkpw(pw_bytes, hash_bytes))
        except (ValueError, TypeError):
            return False

    try:
        from passlib.hash import bcrypt as passlib_bcrypt  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "Bcrypt verification requires either the 'bcrypt' or 'passlib' "
            "package. Install one: pip install bcrypt"
        ) from exc

    try:
        return bool(passlib_bcrypt.verify(password, stored_hash))
    except (ValueError, TypeError):
        return False


def verify_bcrypt(password: str, stored_hash: str) -> VerifierResult:
    """Verify a bcrypt-style hash. Returns a non-sensitive VerifierResult."""
    if not password or not stored_hash:
        return VerifierResult(matched=False, reason="empty_input")
    if not stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        return VerifierResult(matched=False, reason="not_bcrypt_format")
    matched = _checkpw(password, stored_hash)
    return VerifierResult(
        matched=matched,
        reason="matched" if matched else "bad_password",
    )
