"""Email-or-username authentication backend (2026-06-08).

New owners sign up with an EMAIL but the account is provisioned with
``username = email.split("@")[0]`` — a username they were never shown. The
login form even labels the field for an email. Without this backend, login
matches ``USERNAME_FIELD`` (username) only, so the email they typed is rejected
and they're stranded.

This backend accepts EITHER the username or the email as the login identifier.
It sits after ``LegacyHashUpgradeBackend`` and before the stock ``ModelBackend``
in ``AUTHENTICATION_BACKENDS``; a username login still resolves identically, and
an email login now resolves too.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameModelBackend(ModelBackend):
    """``ModelBackend`` that resolves the identifier by username OR email."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or password is None:
            return None

        identifier = username.strip()
        qs = UserModel._default_manager.filter(
            Q(**{f"{UserModel.USERNAME_FIELD}__iexact": identifier})
            | Q(email__iexact=identifier)
        )
        user = None
        # Prefer an exact username match when an email is shared by >1 account.
        for candidate in qs:
            if getattr(candidate, UserModel.USERNAME_FIELD, "").lower() == identifier.lower():
                user = candidate
                break
        if user is None:
            user = qs.first()

        if user is None:
            # Run the default hasher once to keep timing consistent (mirrors
            # Django's ModelBackend.authenticate anti-enumeration behaviour).
            UserModel().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
