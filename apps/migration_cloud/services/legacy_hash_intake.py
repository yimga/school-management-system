"""Canonical write-site for foreign-vendor legacy hashes (v3.32.0).

When a per-vendor extractor (PowerSchool, Blackbaud, Veracross, Alma,
FACTS, Skyward) pulls a user's password hash off the source SIS and
hands it to the platform, it goes through :func:`store_legacy_hash`.
The helper:

  * Validates the algorithm slug against the registered verifier set
    (:mod:`apps.accounts.legacy_hashes`) — unknown algorithms are
    rejected at intake rather than silently stored and failing first
    login.
  * Writes all four legacy fields atomically:
    ``legacy_password_hash``, ``legacy_hash_algorithm``,
    ``legacy_hash_params``, ``legacy_hash_created_at``. The fourth
    field anchors the 12-month sunset clock (see
    :mod:`apps.accounts.legacy_hashes.sunset_task`); without it the
    sunset job falls back to ``date_joined`` which can predate the
    migration by years.
  * Emits a structured log line with counts + algorithm name + source
    vendor — never the hash, salt, password, or any other byte that
    could enable an offline attack.

Defensive backfill in :mod:`apps.accounts.auth_backends_legacy` still
stamps ``legacy_hash_created_at`` on first verifier hit for rows
imported before v3.32.0; that path stays as belt-and-suspenders for
historical data.

This module is a **service** — landers in
:mod:`apps.migration_cloud.landers` call it; the User model is touched
indirectly via :func:`django.contrib.auth.get_user_model`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Locally-mirrored set of fields touched by the intake helper. Kept as
# a module constant so tests can assert the exact set without re-reading
# the model. Mirrors LEGACY_FIELDS in :mod:`apps.accounts.auth_backends_legacy`
# plus the v3.29 anchor column.
INTAKE_FIELDS = (
    "legacy_password_hash",
    "legacy_hash_algorithm",
    "legacy_hash_params",
    "legacy_hash_created_at",
)


def _validate_inputs(
    hash_value: str,
    algorithm: str,
    params_dict: Optional[dict],
) -> dict:
    """Type/shape-check the inputs. Raises ``ValueError`` on failure.

    Returns the cleaned ``params_dict`` (or ``{}`` if None).
    """
    if not isinstance(hash_value, str) or not hash_value:
        raise ValueError("hash_value must be a non-empty string")
    if not isinstance(algorithm, str) or not algorithm:
        raise ValueError("algorithm must be a non-empty string")
    if params_dict is None:
        params_dict = {}
    if not isinstance(params_dict, dict):
        raise ValueError("params_dict must be a dict")
    # Algorithm slug must be one of the registered verifiers. We import
    # locally so this module remains importable from migrations / mgmt
    # commands that might not need the verifier registry loaded.
    from apps.accounts.legacy_hashes import is_supported_algorithm

    if not is_supported_algorithm(algorithm):
        raise ValueError(
            f"algorithm {algorithm!r} is not registered in "
            f"apps.accounts.legacy_hashes"
        )
    return params_dict


def store_legacy_hash(
    user: Any,
    hash_value: str,
    algorithm: str,
    params_dict: Optional[dict] = None,
    source_vendor: str = "",
) -> bool:
    """Canonical write site for a foreign-vendor legacy hash.

    Args:
        user: The User instance (already persisted; we save by pk).
            tenant isolation is the caller's responsibility — the
            intake lander has already resolved this user under its
            tenant context.
        hash_value: The vendor's stored hash text. NEVER LOGGED.
        algorithm: A slug registered in
            :mod:`apps.accounts.legacy_hashes` (e.g. ``"pbkdf2_sha512"``,
            ``"bcrypt"``, ``"veracross_bcrypt"``).
        params_dict: Algorithm-specific parameters (salt, iterations,
            etc.). Whitelisted by the verifier; we don't second-guess
            its shape here.
        source_vendor: Human-readable source SIS identifier
            (``"powerschool"``, ``"blackbaud"``, etc.) — logged for
            operator visibility, NEVER part of the verify path.

    Returns:
        ``True`` on success, ``False`` on DB failure (logged
        without secrets).

    Raises:
        ``ValueError`` on type/shape problems (programmer error — not
        catchable by callers as a "retry me" signal).
    """
    params_dict = _validate_inputs(hash_value, algorithm, params_dict)

    UserModel = get_user_model()
    if not isinstance(user, UserModel):
        raise ValueError(
            f"user must be a {UserModel.__name__} instance, got {type(user).__name__}"
        )

    now = timezone.now()
    try:
        with transaction.atomic():
            user.legacy_password_hash = hash_value
            user.legacy_hash_algorithm = algorithm
            user.legacy_hash_params = params_dict
            user.legacy_hash_created_at = now
            user.save(update_fields=INTAKE_FIELDS)
    except DatabaseError:
        logger.exception(
            "legacy_hash_intake_save_failed",
            extra={
                "user_id": getattr(user, "pk", None),
                "algorithm": algorithm,
                "source_vendor": source_vendor,
                "result": "save_failed",
            },
        )
        return False

    # Structured log — counts + algorithm name + vendor slug only. No
    # hash bytes, no salt, no password, no params content.
    logger.info(
        "legacy_hash_intake_stored",
        extra={
            "user_id": getattr(user, "pk", None),
            "algorithm": algorithm,
            "source_vendor": source_vendor or "unspecified",
            "params_keys": sorted(params_dict.keys()),
            "result": "stored",
        },
    )
    return True


__all__ = [
    "INTAKE_FIELDS",
    "store_legacy_hash",
]
