"""Portal password reset (CEZGP Lane 2 — P2 parent login/session)."""

from __future__ import annotations

import logging

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.views import PasswordResetConfirmView
from django.db.models import Q
from django.template import loader

logger = logging.getLogger(__name__)


class PortalPasswordResetConfirmView(PasswordResetConfirmView):
    """Django's reset-confirm, plus: claiming a NEVER-CLAIMED account activates it.

    A never-claimed account (created with ``set_unusable_password`` at
    provisioning / bulk import) can be ``is_active=False``. ``get_users`` above
    now issues such an account a reset/claim link, but Django's stock confirm
    view only SETS the password — it never flips ``is_active`` — so the owner
    could set a password and STILL be bounced at ``/login/`` by ``is_active`` (the
    exact dead-end reported on a live tenant: "we sent a link, you clicked it, and it still says
    invalid"). Setting a password via the token IS the activation: the link
    proved control of the on-file address.

    We only activate accounts that had NO usable password BEFORE this set, so a
    normal active user's reset is unchanged, and a deactivated account with a real
    password is never silently re-enabled — such an account is never handed a
    token in the first place (``get_users`` excludes it).
    """

    def form_valid(self, form):
        user = getattr(self, "user", None)
        # Captured BEFORE super() saves the new password — reflects the pre-claim
        # (unusable-password) state.
        was_unclaimed = user is not None and not user.has_usable_password()
        response = super().form_valid(form)
        if was_unclaimed and user is not None and not user.is_active:
            user.is_active = True
            try:
                user.save(update_fields=["is_active"])
                logger.info(
                    "accounts.password_reset.activated_on_claim user_id=%s", user.pk
                )
            except Exception:  # noqa: BLE001 — password is already set; never 500 the claim
                logger.warning(
                    "accounts.password_reset.activate_on_claim_failed user_id=%s",
                    getattr(user, "pk", None),
                )
        return response


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
        matches = User.objects.filter(
            Q(email__iexact=identifier) | Q(username__iexact=identifier)
        )
        # Send to active accounts as usual. ALSO include NEVER-CLAIMED accounts
        # (created with set_unusable_password at provisioning / bulk import) even
        # when is_active=False. Django's default filter — and the prior
        # is_active=True filter here — drops them, which silently strands exactly
        # the new-user population: login shows the generic "invalid username or
        # password" wall and the reset email NEVER arrives (the exact report
        # from a live tenant). A never-claimed account has no password to protect and the
        # reset-confirm view is its intended claim path, so this is safe. A
        # DEACTIVATED account WITH a real usable password stays excluded, so
        # disabling an established account still fully locks it (and blocks reset).
        return [u for u in matches if u.is_active or not u.has_usable_password()]
