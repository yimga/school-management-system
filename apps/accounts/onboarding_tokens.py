"""Longer-lived token for first-run ACTIVATION links (owner onboarding, set-password).

An activation/invite link is a different security object from a password-RESET
link: a human has to act on a cold email, so it legitimately lives for days
(industry standard ~7d; Auth0/WorkOS), whereas a reset token is short (<=1h,
OWASP). Both reuse Django's ``PasswordResetTokenGenerator`` machinery, which
reads the single global ``settings.PASSWORD_RESET_TIMEOUT`` — so tightening the
reset window to 1h *also* expires activation links in 1h, locking out exactly
the operator-provisioned owners the welcome email now routes to account setup.

This generator validates the SAME token format with a longer, independently
configurable window. ``make_token`` does not embed the timeout (only
``check_token`` compares against it), so a token minted by
``default_token_generator`` still validates here for ``days`` and at the reset
generator for 1h — the two windows are fully decoupled.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int


def _activation_timeout_seconds() -> int:
    try:
        days = int(getattr(settings, "OWNER_ONBOARDING_TOKEN_DAYS", 7) or 7)
    except (TypeError, ValueError):
        days = 7
    return max(1, days) * 24 * 3600


class ActivationTokenGenerator(PasswordResetTokenGenerator):
    """``PasswordResetTokenGenerator`` with an activation-length validity window.

    Mirrors Django 5.2 ``check_token`` exactly except the final timeout
    comparison uses the activation window instead of
    ``settings.PASSWORD_RESET_TIMEOUT``. The salt/secret/timestamp derivation is
    inherited unchanged, so links already minted by ``default_token_generator``
    validate here too.
    """

    def check_token(self, user, token):
        if not (user and token):
            return False
        try:
            ts_b36, _ = token.split("-")
        except ValueError:
            return False
        try:
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False
        for secret in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(
                self._make_token_with_timestamp(user, ts, secret),
                token,
            ):
                break
        else:
            return False
        if (self._num_seconds(self._now()) - ts) > _activation_timeout_seconds():
            return False
        return True


# Module-level singleton, mirroring django.contrib.auth.tokens.default_token_generator.
activation_token_generator = ActivationTokenGenerator()
