"""Portal password reset (CEZGP Lane 2 — P2 parent login/session)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.db.models import Q


class PortalPasswordResetForm(PasswordResetForm):
    """Accept username or email — schools often issue username-only parent accounts."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = "Username or email"
        self.fields["email"].widget.attrs.setdefault(
            "placeholder", "parent.username or you@school.edu"
        )

    def get_users(self, email):
        identifier = (email or "").strip()
        if not identifier:
            return []
        User = get_user_model()
        active = User.objects.filter(is_active=True)
        matches = active.filter(
            Q(email__iexact=identifier) | Q(username__iexact=identifier)
        )
        return [user for user in matches if user.has_usable_password()]
