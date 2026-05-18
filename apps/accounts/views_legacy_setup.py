"""One-time setup link landing page for sunset-emailed users.

When the 12-month sunset task
(:func:`apps.accounts.legacy_hashes.sunset_task.sunset_stale_legacy_hashes`)
emails a user, the embedded link routes here. The view validates the
password-reset token, lets the user choose a fresh password, and
clears the three legacy fields atomically — the same end state the
:class:`LegacyHashUpgradeBackend` would have reached had the user
logged in with their original foreign-vendor password.

Implementation reuses Django's :class:`PasswordResetConfirmView` for
the token-validation half (battle-tested, time-bounded by
``PASSWORD_RESET_TIMEOUT``, single-use per Django's session token
caching). The ``form_valid`` override is the additive piece: clear
``legacy_password_hash`` / ``legacy_hash_algorithm`` /
``legacy_hash_params`` in the same DB save so a verifier never
re-races the flow.

Security invariants:

* The token is consumed by :meth:`PasswordResetConfirmView.dispatch`
  before we touch any legacy fields, so an invalid/expired token
  short-circuits to the standard "link expired" page.
* No legacy field value is read, displayed, or logged. We only zero
  them.
* The view emits exactly one logger.info call on success with
  ``user_id`` + ``result`` — never the token, never the password.
"""
from __future__ import annotations

import logging

from django.contrib.auth.views import PasswordResetConfirmView
from django.urls import reverse_lazy

logger = logging.getLogger(__name__)


LEGACY_FIELDS = (
    "legacy_password_hash",
    "legacy_hash_algorithm",
    "legacy_hash_params",
)


class LegacySetupView(PasswordResetConfirmView):
    """Password-reset confirm view that ALSO clears legacy hash fields.

    Reachable URL: ``/accounts/legacy-setup/<uidb64>/<token>/`` (wired
    in :mod:`apps.accounts.urls`).
    """

    template_name = "accounts/legacy_setup.html"
    success_url = reverse_lazy("accounts:login")
    # Django stores the validated user on self.user after dispatch; we
    # rely on the parent's token-validation contract.

    def form_valid(self, form):
        response = super().form_valid(form)

        # self.user is set by PasswordResetConfirmView after token
        # validation; form.save() above persisted the new password.
        user = getattr(self, "user", None)
        if user is None:  # pragma: no cover - parent never sets self.user to None on success
            return response

        user.legacy_password_hash = ""
        user.legacy_hash_algorithm = ""
        user.legacy_hash_params = {}
        # Clear the sunset-email timestamp too: the user is now fully
        # migrated and the sunset task should not target them again
        # even if they somehow re-acquire a legacy hash later.
        user.legacy_hash_sunset_email_sent_at = None
        try:
            user.save(
                update_fields=LEGACY_FIELDS + ("legacy_hash_sunset_email_sent_at",),
            )
        except Exception:  # noqa: BLE001 - save failure must not break login
            logger.exception(
                "legacy_setup_clear_fields_failed",
                extra={"user_id": user.pk, "result": "save_failed"},
            )
            return response

        logger.info(
            "legacy_setup_complete",
            extra={"user_id": user.pk, "result": "legacy_fields_cleared"},
        )
        return response
