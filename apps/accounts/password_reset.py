"""Portal password reset (CEZGP Lane 2 — P2 parent login/session)."""

from __future__ import annotations

import logging

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.db.models import Q
from django.template import loader

logger = logging.getLogger(__name__)


class PortalPasswordResetForm(PasswordResetForm):
    """Accept username or email — schools often issue username-only parent accounts."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The inherited field is an EmailField, which would REJECT a bare
        # username at validation before ``get_users`` ever runs — making the
        # "username or email" promise (and never-activated-owner recovery via
        # username) a lie. Swap to a plain CharField so usernames validate;
        # ``get_users`` already matches on both columns case-insensitively.
        self.fields["email"] = forms.CharField(
            label="Username or email",
            max_length=254,  # magic-number-allow: Django EmailField default max length
            widget=forms.TextInput(
                attrs={
                    "autocomplete": "username",
                    "placeholder": "parent.username or you@school.edu",
                }
            ),
        )

    def _augment_reset_context(self, context: dict) -> dict:
        """Populate the keys the branded reset templates expect.

        Django's ``PasswordResetForm`` builds a stock context — ``uid``,
        ``token``, ``protocol``, ``domain``, ``user``, ``email``, ``site_name``.
        The templates (``emails/password_reset.{txt,html}``) were authored for a
        bespoke sender and reference ``reset_url`` / ``user_name`` /
        ``school_name`` / ``expiry_hours`` — none of which Django supplies. Left
        unset, ``{{ reset_url }}`` renders EMPTY and the security email ships
        with no usable link (the recipient can never reset). Computed here
        because ``send_mail`` runs once per user with that user's
        ``uid``/``token``/``protocol``/``domain`` (the per-user link a static
        ``save(extra_email_context=…)`` could not carry), and the URL is built
        from the request's own host so it is correct on whichever host
        (public / tenant subdomain / manager) served the reset request.
        """
        from django.conf import settings as dj_settings
        from django.urls import NoReverseMatch, reverse

        uid = context.get("uid")
        token = context.get("token")
        protocol = (context.get("protocol") or "https").strip()
        domain = (context.get("domain") or "").strip()
        if uid and token and domain and not context.get("reset_url"):
            try:
                path = reverse(
                    "accounts:password_reset_confirm",
                    kwargs={"uidb64": uid, "token": token},
                )
                context["reset_url"] = f"{protocol}://{domain}{path}"
            except NoReverseMatch:
                logger.warning("accounts.password_reset.reset_url_reverse_failed")
        user = context.get("user")
        if user is not None and not context.get("user_name"):
            name = (user.get_full_name() or "").strip() or (
                user.get_username() or ""
            ).strip()
            context["user_name"] = name or (context.get("email") or "").strip()
        if not context.get("school_name"):
            context["school_name"] = (
                context.get("site_name") or ""
            ).strip() or "RunMyCampus"
        if not context.get("expiry_hours"):
            timeout_seconds = int(
                getattr(dj_settings, "PASSWORD_RESET_TIMEOUT", 259200) or 259200
            )
            context["expiry_hours"] = max(1, timeout_seconds // 3600)
        return context

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
        context = self._augment_reset_context(dict(context))
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
        # Include never-activated owners (created with set_unusable_password at
        # provisioning) — Django's default filter drops them, which silently
        # locks out exactly the new-owner population. The reset-confirm view lets
        # them set a password regardless of current state, so this is their
        # recovery path when the original onboarding link expired.
        return list(matches)
