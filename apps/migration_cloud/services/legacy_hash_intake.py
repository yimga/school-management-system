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
    legacy_hash_created_at_source: Optional[Any] = None,
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
        legacy_hash_created_at_source: v3.33.0 — when the source SIS
            exposes a "password last set" timestamp (PowerSchool's
            ``PasswordChanged`` column, Blackbaud SKY's
            ``PasswordLastChanged``, etc.), the extractor passes the
            vendor-reported value here. We use it as the sunset anchor
            so a hash that's been "stale" at the vendor for 11 months
            does not get a fresh 12-month grace clock on intake. Falls
            back to ``timezone.now()`` when not provided (most vendors
            do NOT expose this — see ``VENDOR_COVERAGE.md``).

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

    # Resolve the sunset anchor. Vendor-provided timestamps win when
    # present; otherwise we anchor to "now" so the 12-month sunset
    # clock starts at intake. Defensive: if the caller hands us a
    # naive value or a string, fall back to "now" rather than raising
    # — the lander shouldn't fail intake on a type quirk in the
    # vendor payload.
    #
    # v3.34.0 — extended to accept ISO-8601 strings from the per-vendor
    # extractors (the Companion bundle emits string timestamps via
    # JSON), and to clamp future-dated values to now() with a structured
    # warning (clock skew on the vendor server is real; Blackbaud /
    # Alma have been observed emitting timestamps slightly ahead of
    # UTC). The clamp is defensive — a future anchor would make the
    # sunset clock fire "in the future", which the cron skips silently.
    now = timezone.now()
    anchor = now
    _anchor_clamped_future = False
    _anchor_parsed_from_string = False
    if legacy_hash_created_at_source is not None:
        from datetime import datetime as _dt
        from datetime import timedelta as _td

        candidate = None
        if isinstance(legacy_hash_created_at_source, _dt):
            candidate = legacy_hash_created_at_source
        elif (
            isinstance(legacy_hash_created_at_source, str)
            and legacy_hash_created_at_source.strip()
        ):
            raw = legacy_hash_created_at_source.strip()
            # Normalize the common "...Z" UTC suffix for fromisoformat.
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            try:
                candidate = _dt.fromisoformat(raw)
                _anchor_parsed_from_string = True
            except (ValueError, TypeError):
                candidate = None

        if candidate is not None:
            # Make sure we store an aware datetime.
            if timezone.is_naive(candidate):
                try:
                    candidate = timezone.make_aware(candidate)
                except Exception:  # noqa: BLE001
                    candidate = None

        if candidate is not None:
            # Future-date clamp (clock-skew protection). Allow a
            # 60-second forward tolerance to avoid noisy warnings for
            # rows generated within the same minute as intake.
            if candidate > now + _td(seconds=60):
                _anchor_clamped_future = True
                # Emit a structured warning — operator-visible, NEVER
                # contains hash / salt / password material.
                logger.warning(
                    "legacy_hash_intake_anchor_clamped_future",
                    extra={
                        "user_id": getattr(user, "pk", None),
                        "algorithm": algorithm,
                        "source_vendor": source_vendor or "unspecified",
                        "skew_seconds": int(
                            (candidate - now).total_seconds()
                        ),
                        "result": "anchor_clamped_to_now",
                    },
                )
                anchor = now
            else:
                anchor = candidate

    try:
        with transaction.atomic():
            user.legacy_password_hash = hash_value
            user.legacy_hash_algorithm = algorithm
            user.legacy_hash_params = params_dict
            user.legacy_hash_created_at = anchor
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
            "anchor_from_vendor": legacy_hash_created_at_source is not None,
            "anchor_parsed_from_string": _anchor_parsed_from_string,
            "anchor_clamped_future": _anchor_clamped_future,
            "result": "stored",
        },
    )
    return True


__all__ = [
    "INTAKE_FIELDS",
    "store_legacy_hash",
]
