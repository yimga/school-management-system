"""v3.57.x Wave 8 Agent C — Operator-facing SMTP configuration form.

Backed by ``SiteSettings.email_delivery`` (JSONField added in siteconfig
migration 0184). The form round-trips the JSON shape consumed by
:func:`apps.schoolops.email_delivery.get_resolved_smtp_config`.

Security contract:
  * The password field is ``PasswordInput``; when an operator submits a
    new value we encrypt it via
    :func:`apps.schoolops.email_delivery.encrypt_password_for_storage`
    (Fernet wrap, key resolved through the existing
    ``apps.accounts.legacy_hashes.encryption._get_fernet()`` helper —
    the same key family the migration_cloud companion keypair uses).
  * Blank password on resave = "keep existing encrypted value" — we
    NEVER blow away a configured password just because the operator
    didn't re-type it. To clear the password, the operator unchecks
    ``enabled`` (which makes the resolver ignore the entire override).
  * Plaintext password is NEVER stored anywhere — not on the model,
    not in form ``initial``, not in error messages. The form's
    ``host_password`` field is ``required=False`` and shown empty on
    every GET.
"""
from __future__ import annotations

import logging
from typing import Any

from django import forms
from django.core.exceptions import ValidationError


logger = logging.getLogger(__name__)


_FROM_NAME_MAX = 100
_HOST_MAX = 255
_HOST_USER_MAX = 255


class EmailDeliveryForm(forms.Form):
    """Operator form: edit ``SiteSettings.email_delivery`` JSON blob."""

    enabled = forms.BooleanField(
        required=False,
        initial=False,
        label="Enable operator override",
        help_text=(
            "When checked, RunMyCampus sends via the SMTP server below. "
            "When unchecked, falls back to the environment-configured "
            "SMTP server."
        ),
    )
    host = forms.CharField(
        required=False,
        max_length=_HOST_MAX,
        label="SMTP host",
        help_text='e.g. "smtp.sendgrid.net", "smtp.gmail.com"',
    )
    port = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=65535,
        initial=587,
        label="SMTP port",
        help_text="Typically 587 (STARTTLS) or 465 (SMTPS).",
    )
    use_tls = forms.BooleanField(
        required=False,
        initial=True,
        label="Use STARTTLS",
        help_text="Recommended for port 587. Ignored for 465 (always TLS).",
    )
    host_user = forms.CharField(
        required=False,
        max_length=_HOST_USER_MAX,
        label="SMTP username",
    )
    host_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label="SMTP password",
        help_text=(
            "Leave blank to keep the currently-stored password. "
            "Enter a new value to replace it. The password is encrypted "
            "at rest with the platform Fernet key."
        ),
    )
    default_from_email = forms.EmailField(
        required=False,
        label="Default From: address",
        help_text='e.g. "noreply@yourschool.edu"',
    )
    default_from_name = forms.CharField(
        required=False,
        max_length=_FROM_NAME_MAX,
        label="Default From: name",
        help_text='e.g. "Gilead Tech High". Rendered as "Name <addr>".',
    )
    default_reply_to = forms.EmailField(
        required=False,
        label="Default Reply-To: address",
        help_text="Optional. Where bounce-replies and operator replies land.",
    )
    connection_timeout_seconds = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=120,
        initial=10,
        label="Connection timeout (seconds)",
        help_text=(
            "Per-attempt SMTP socket timeout. Lower = fail-fast on a "
            "dead server; higher = tolerate slow networks. 10s is a "
            "sane default."
        ),
    )

    # v3.58.x Wave 9 Agent M — per-provider bounce-webhook shared secrets.
    # Blank-on-resave preserves the existing value (mirrors host_password).
    webhook_secret_postmark = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label="Postmark webhook secret",
        help_text=(
            "Server-token-style shared secret. Postmark posts an "
            "HMAC-SHA256 signature in X-Postmark-Signature; we verify "
            "with hmac.compare_digest. Leave blank to keep existing."
        ),
    )
    webhook_secret_sendgrid = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label="SendGrid webhook Ed25519 public key",
        help_text=(
            "Twilio SendGrid uses Ed25519 signing. Until pynacl is "
            "wired the verifier accepts deliveries but marks them "
            "signature_unverified=True. Leave blank to keep existing."
        ),
    )
    webhook_secret_ses = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label="SES (via SNS relay) shared secret",
        help_text=(
            "Shared secret used to HMAC the body in your API "
            "Gateway / Lambda SNS-forwarder. Header expected: "
            "X-RMC-SNS-Signature. Leave blank to keep existing."
        ),
    )
    webhook_secret_mailgun = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label="Mailgun webhook signing key",
        help_text=(
            "Mailgun's HMAC-SHA256 protocol over timestamp + token. "
            "Leave blank to keep existing."
        ),
    )

    # ------------------------------------------------------------------
    # JSON ↔ form mapping.
    # ------------------------------------------------------------------

    @classmethod
    def from_json(cls, payload: dict | None, **kwargs):
        """Seed a bound form from a ``SiteSettings.email_delivery`` dict.

        Webhook-secret fields are intentionally NOT seeded — same
        blank-preserves-existing semantics as ``host_password``.
        """
        payload = payload or {}
        initial = {
            "enabled": bool(payload.get("enabled", False)),
            "host": payload.get("host", "") or "",
            "port": int(payload.get("port", 587) or 587),
            "use_tls": bool(payload.get("use_tls", True)),
            "host_user": payload.get("host_user", "") or "",
            # host_password intentionally not seeded — never re-render it.
            "default_from_email": payload.get("default_from_email", "") or "",
            "default_from_name": payload.get("default_from_name", "") or "",
            "default_reply_to": payload.get("default_reply_to", "") or "",
            "connection_timeout_seconds": int(
                payload.get("connection_timeout_seconds", 10) or 10,
            ),
            # webhook_secret_* intentionally NOT seeded.
        }
        kwargs.setdefault("initial", initial)
        return cls(**kwargs)

    def to_json(self, existing_payload: dict | None = None) -> dict:
        """Render a cleaned form into the JSON shape we store on SiteSettings.

        Re-uses the existing encrypted password when the operator left
        the field blank. Encrypts a freshly-entered password via the
        Fernet helper.
        """
        if not self.is_valid():
            raise ValidationError("EmailDeliveryForm.to_json called on invalid form")
        cleaned = self.cleaned_data
        existing = existing_payload or {}

        # Password handling — blank field = keep existing.
        pwd_plain = (cleaned.get("host_password") or "").strip()
        if pwd_plain:
            from apps.schoolops.email_delivery import encrypt_password_for_storage

            pwd_encrypted_b64 = encrypt_password_for_storage(pwd_plain)
        else:
            pwd_encrypted_b64 = (
                existing.get("host_password_encrypted_b64") or ""
            )

        # v3.58.x Wave 9 Agent M — round-trip webhook secrets.
        # Blank submission preserves existing value (mirror host_password).
        existing_secrets = existing.get("webhook_secrets") or {}
        if not isinstance(existing_secrets, dict):
            existing_secrets = {}
        new_secrets = dict(existing_secrets)
        for provider in ("postmark", "sendgrid", "ses", "mailgun"):
            field_key = f"webhook_secret_{provider}"
            submitted = (cleaned.get(field_key) or "").strip()
            if submitted:
                new_secrets[provider] = submitted
            # else: preserve existing (do nothing — already copied above)

        return {
            "enabled": bool(cleaned.get("enabled", False)),
            "host": (cleaned.get("host") or "").strip(),
            "port": int(cleaned.get("port") or 587),
            "use_tls": bool(cleaned.get("use_tls", True)),
            "host_user": (cleaned.get("host_user") or "").strip(),
            "host_password_encrypted_b64": pwd_encrypted_b64,
            "default_from_email": (cleaned.get("default_from_email") or "").strip(),
            "default_from_name": (cleaned.get("default_from_name") or "").strip(),
            "default_reply_to": (cleaned.get("default_reply_to") or "").strip(),
            "connection_timeout_seconds": int(
                cleaned.get("connection_timeout_seconds") or 10,
            ),
            "webhook_secrets": new_secrets,
        }

    def clean(self) -> dict[str, Any]:
        """Cross-field validation.

        When ``enabled`` is True, we require at minimum a host and a
        default-from address — otherwise the resolver would silently
        merge an unusable override on top of the env config.
        """
        cleaned = super().clean()
        if cleaned.get("enabled"):
            if not (cleaned.get("host") or "").strip():
                self.add_error(
                    "host",
                    "Host is required when 'Enable operator override' is checked.",
                )
            if not (cleaned.get("default_from_email") or "").strip():
                self.add_error(
                    "default_from_email",
                    "Default From: address is required when override is enabled.",
                )
        return cleaned


__all__ = ["EmailDeliveryForm"]
