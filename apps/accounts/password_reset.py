"""Portal password reset (CEZGP Lane 2 — P2 parent login/session)."""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.db.models import Q
from django.template import loader

logger = logging.getLogger(__name__)


class PortalPasswordResetForm(PasswordResetForm):
    """Accept username or email — schools often issue username-only parent accounts."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = "Username or email"
        self.fields["email"].widget.attrs.setdefault(
            "placeholder", "parent.username or you@school.edu"
        )

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        """Route the reset email through the reliability layer (audit H1).

        Django's default ``send_mail`` calls ``EmailMultiAlternatives.send()``
        directly — unaudited, un-retried, invisible on the email-health
        dashboard. Password reset is a security-critical email, so we render
        the same templates but dispatch via ``send_transactional`` (retry +
        EmailDeliveryEvent audit). ``allow_suppressed=True`` because a reset
        is a user-initiated security action that must reach even an address
        previously suppressed for marketing.
        """
        subject = "".join(loader.render_to_string(subject_template_name, context).splitlines())
        body = loader.render_to_string(email_template_name, context)
        html_body = (
            loader.render_to_string(html_email_template_name, context)
            if html_email_template_name
            else None
        )
        try:
            from apps.schoolops.email_delivery import send_transactional

            send_transactional(
                subject=subject,
                body=body,
                to=[to_email],
                html_body=html_body,
                from_email=from_email,
                priority="transactional",
                allow_suppressed=True,
            )
        except Exception as exc:  # noqa: BLE001 — fall back to Django's path
            logger.warning(
                "accounts.password_reset.audited_send_failed err_type=%s "
                "falling_back_to_django",
                type(exc).__name__,
            )
            super().send_mail(
                subject_template_name,
                email_template_name,
                context,
                from_email,
                to_email,
                html_email_template_name=html_email_template_name,
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
