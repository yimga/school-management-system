"""Auth backend that transparently verifies legacy-vendor password hashes.

This implements the "password preservation moat" from the migration-cloud
strategic direction: when a school migrates from PowerSchool / Blackbaud /
Veracross / FACTS / Skyward / Alma, the companion-app extractor writes
the foreign hash + algorithm slug + algorithm params onto the User row
(``legacy_password_hash``, ``legacy_hash_algorithm``, ``legacy_hash_params``).

On first login:

1. We look up the user by username (cross-tenant — auth is system-wide).
2. If the row has a legacy hash AND its algorithm is registered, we
   verify against the legacy hash.
3. On match, we immediately re-hash the password through
   ``user.set_password`` (Argon2 per ``settings.PASSWORD_HASHERS``) and
   clear all three legacy fields in a single ``update_fields`` save.
4. On mismatch (or unknown algorithm, or no legacy hash at all), we fall
   through to the standard Django :class:`ModelBackend`.

The result is invisible to the user — they sign in with their existing
password and never see a "reset required" screen.

Security invariants enforced by tests:

* Logger receives only ``user_id`` + ``result`` + ``algorithm``; never the
  password, the stored hash, or the salt.
* Bare ``except:`` is forbidden (CLAUDE.md ``scan_bare_except`` gate).
* No ``print()`` (CLAUDE.md ``scan_print_statements`` gate).
"""
from __future__ import annotations

import logging
from typing import Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db import DatabaseError
from django.utils import timezone

from .legacy_hashes import verify as verify_legacy_hash

logger = logging.getLogger(__name__)


# Field names cleared atomically on a successful legacy verification +
# re-hash. Kept as a module constant so tests can assert the exact set.
LEGACY_FIELDS = (
    "legacy_password_hash",
    "legacy_hash_algorithm",
    "legacy_hash_params",
)


class LegacyHashUpgradeBackend(ModelBackend):
    """ModelBackend that opportunistically verifies legacy foreign hashes.

    Must be ordered BEFORE ``django.contrib.auth.backends.ModelBackend`` in
    :setting:`AUTHENTICATION_BACKENDS` so the legacy path runs first.
    """

    def authenticate(
        self,
        request,
        username: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs,
    ):
        if not username or not password:
            # Match Django's behaviour: a missing credential is "not me".
            return super().authenticate(
                request, username=username, password=password, **kwargs
            )

        UserModel = get_user_model()
        username_field = UserModel.USERNAME_FIELD

        try:
            # tenant-isolation-allow: auth-layer-system-wide-user-table-lookup
            user = UserModel.objects.filter(
                **{username_field: username}
            ).first()
        except DatabaseError:
            # If the auth table query itself fails we cannot recover here.
            # Fall through so Django's ModelBackend produces the same
            # error surface it always has.
            return super().authenticate(
                request, username=username, password=password, **kwargs
            )

        if user is None:
            # Run the parent path so timing characteristics match the
            # "user does not exist" branch in stock Django (it hashes a
            # dummy password). This is the documented mitigation.
            return super().authenticate(
                request, username=username, password=password, **kwargs
            )

        legacy_hash = getattr(user, "legacy_password_hash", "") or ""
        legacy_algo = getattr(user, "legacy_hash_algorithm", "") or ""

        if legacy_hash and legacy_algo:
            # v3.29: defensive backfill of legacy_hash_created_at for
            # rows imported before the field existed. The sunset task
            # falls back to date_joined when this is NULL, so a missing
            # value isn't load-bearing — but stamping it here gives the
            # 12-month clock an honest anchor relative to "first sight"
            # of the foreign hash rather than the account-creation
            # timestamp (which can predate the migration by years).
            if getattr(user, "legacy_hash_created_at", None) is None:
                try:
                    user.legacy_hash_created_at = timezone.now()
                    user.save(update_fields=("legacy_hash_created_at",))
                except DatabaseError:
                    # Non-fatal — the sunset job tolerates NULL anchors.
                    logger.info(
                        "legacy_hash_created_at_backfill_failed",
                        extra={"user_id": user.pk, "result": "save_failed"},
                    )
            legacy_params = getattr(user, "legacy_hash_params", {}) or {}
            matched = verify_legacy_hash(
                legacy_algo, legacy_params, legacy_hash, password
            )
            if matched:
                # Re-hash to native (Argon2 per PASSWORD_HASHERS) and
                # clear the legacy fields in one atomic save.
                user.set_password(password)
                user.legacy_password_hash = ""
                user.legacy_hash_algorithm = ""
                user.legacy_hash_params = {}
                try:
                    user.save(
                        update_fields=("password",) + LEGACY_FIELDS
                    )
                except DatabaseError:
                    # Log + fail open: if the save fails the user is
                    # still authenticated for this request, but the
                    # legacy fields remain so we'll re-attempt on the
                    # next login. Never log password / hash / salt.
                    logger.exception(
                        "legacy_hash_upgrade_save_failed",
                        extra={
                            "user_id": user.pk,
                            "algorithm": legacy_algo,
                            "result": "save_failed",
                        },
                    )
                    return user if self.user_can_authenticate(user) else None

                logger.info(
                    "legacy_hash_upgrade_success",
                    extra={
                        "user_id": user.pk,
                        "algorithm": legacy_algo,
                        "result": "upgraded",
                    },
                )
                return user if self.user_can_authenticate(user) else None

            # Legacy hash present but password did not match. Log the
            # outcome (no secrets) and fall through to ModelBackend in
            # case the user has BOTH a native password and a legacy
            # hash (rare but possible during dual-auth windows).
            logger.info(
                "legacy_hash_upgrade_no_match",
                extra={
                    "user_id": user.pk,
                    "algorithm": legacy_algo,
                    "result": "no_match",
                },
            )

        # Standard Django path.
        return super().authenticate(
            request, username=username, password=password, **kwargs
        )
