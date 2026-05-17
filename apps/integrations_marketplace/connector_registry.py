"""
Connector registry — single source of truth for first-party external connectors.

This sits on top of `apps.siteconfig.integration_catalog.INTEGRATION_CATALOG`
(which already enumerates payments/messaging/lms providers) and adds the
**auth-flow metadata** needed to actually run an OAuth2 dance, sign a webhook,
or pick the right SMTP/Anymail backend from a `ServiceIntegration` row.

Why a separate file from `integration_catalog.py`:
- `integration_catalog.py` describes *what fields the operator types in* (form
  schema + guardrails) for legacy `Integration` records (per-school FK).
- `connector_registry.py` describes *how the platform talks to the upstream*
  (OAuth endpoints, default scopes, brand, category groups). The fields are
  immutable per release and not operator-editable — they belong in code.

Scope (Wave v2.69):
- Meeting / video:    zoom, microsoft_teams, google_meet, webex
- Calendar:           google_calendar, outlook_calendar
- Productivity mail:  gmail, outlook_mail
- Transactional mail: mailgun, sendgrid, postmark, amazon_ses, sparkpost,
                       brevo, mandrill, mailersend, mailjet, resend, sendinblue
- Chat:               slack, microsoft_teams_chat, discord
- Existing (pass-through from INTEGRATION_CATALOG): whatsapp, push, stripe,
   stripe_platform, badges, lms, email, sms

Every connector advertises:
- slug:               stable identifier; also the `ServiceIntegration.service_name`
                       value when wired (case-insensitive match by resolver)
- label, category, brand_color, icon_kind ("svg"/"emoji"/"img")
- auth_kind:          oauth2 | api_key | webhook | smtp | basic
- For oauth2 connectors: authorize_url, token_url, default_scopes, scope_separator,
                          extra_authorize_params, pkce (bool)
- redirect_path:      generic OAuth callback path (resolved against site domain)
- For api_key connectors: required_config_keys (operator-typed)
- For smtp / anymail mail providers: anymail_backend (Django backend dotted path)
- documentation_url:  upstream "create a connector" page

This is read by:
- `apps.integrations_marketplace.oauth.start_oauth` (begin authorize dance)
- `apps.integrations_marketplace.oauth.complete_oauth` (exchange code → token,
  upsert `ServiceIntegration` with `config={"access_token":..., "refresh_token":..., "scope":...}`)
- `apps.integrations_marketplace.resolver.resolve_connector_config` (cascade lookup)
- `apps.integrations_marketplace.email_backend.PerTenantEmailBackend` (pick
  Anymail subclass + tenant credentials)
- Hub UI (`templates/integrations_marketplace/hub.html`) for the "Connect …"
  catalog.

No values here are operator-editable, so this is the right layer for the 7-layer
cascade's *platform constant* tier. Operator-editable values (credentials,
scope grants, enable flags) all flow into per-school `ServiceIntegration` rows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

CATEGORY_MEETING = "meeting"
CATEGORY_CALENDAR = "calendar"
CATEGORY_MAILBOX = "mailbox"
CATEGORY_TRANSACTIONAL_MAIL = "transactional_mail"
CATEGORY_CHAT = "chat"
CATEGORY_MESSAGING = "messaging"  # SMS / WhatsApp / Push (delegated to integration_catalog)
CATEGORY_PAYMENT = "payment"
CATEGORY_LMS = "lms"
CATEGORY_BADGES = "badges"

CATEGORY_LABELS = {
    CATEGORY_MEETING: "Video meetings",
    CATEGORY_CALENDAR: "Calendars",
    CATEGORY_MAILBOX: "Inbox / mailbox",
    CATEGORY_TRANSACTIONAL_MAIL: "Transactional email",
    CATEGORY_CHAT: "Team chat",
    CATEGORY_MESSAGING: "Messaging (SMS / WhatsApp / Push)",
    CATEGORY_PAYMENT: "Payments",
    CATEGORY_LMS: "LMS",
    CATEGORY_BADGES: "Digital badges",
}


# ---------------------------------------------------------------------------
# Auth kinds
# ---------------------------------------------------------------------------

AUTH_KIND_OAUTH2 = "oauth2"
AUTH_KIND_API_KEY = "api_key"
AUTH_KIND_WEBHOOK = "webhook"
AUTH_KIND_SMTP = "smtp"
AUTH_KIND_BASIC = "basic"


@dataclass(frozen=True)
class Connector:
    slug: str
    label: str
    category: str
    auth_kind: str
    brand_color: str = "#0F62FE"
    icon_kind: str = "svg"
    documentation_url: str = ""
    # OAuth2-specific
    authorize_url: str = ""
    token_url: str = ""
    default_scopes: tuple[str, ...] = ()
    scope_separator: str = " "
    extra_authorize_params: dict[str, str] = field(default_factory=dict)
    pkce: bool = False
    # api_key / smtp specific
    required_config_keys: tuple[str, ...] = ()
    # transactional mail
    anymail_backend: str = ""
    # webhook-only
    webhook_signature_header: str = ""
    webhook_signature_algorithm: str = ""
    # v3.4 — deprecation lifecycle. When True, the hub shows a "Deprecated"
    # badge and `build_authorize_redirect` refuses NEW connections (existing
    # rows keep working so tenants aren't stranded mid-integration).
    deprecated: bool = False
    deprecation_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "label": self.label,
            "category": self.category,
            "category_label": CATEGORY_LABELS.get(self.category, self.category),
            "auth_kind": self.auth_kind,
            "brand_color": self.brand_color,
            "icon_kind": self.icon_kind,
            "documentation_url": self.documentation_url,
            "is_oauth": self.auth_kind == AUTH_KIND_OAUTH2,
            "default_scopes": list(self.default_scopes),
            "required_config_keys": list(self.required_config_keys),
            "anymail_backend": self.anymail_backend,
            "deprecated": bool(self.deprecated),
            "deprecation_note": self.deprecation_note,
        }


# ---------------------------------------------------------------------------
# Registry — one row per supported upstream
#
# OAuth scopes follow the *least-privilege* default. Operators can narrow
# further via per-school ScopeGrant rows (see apps.marketplace.models.ScopeGrant).
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Connector] = {}


def _register(connector: Connector) -> None:
    _REGISTRY[connector.slug] = connector


# -- Video meetings ---------------------------------------------------------

_register(Connector(
    slug="zoom",
    label="Zoom",
    category=CATEGORY_MEETING,
    auth_kind=AUTH_KIND_OAUTH2,
    brand_color="#2D8CFF",
    documentation_url="https://marketplace.zoom.us/docs/guides/build/oauth-app/",
    authorize_url="https://zoom.us/oauth/authorize",
    token_url="https://zoom.us/oauth/token",
    default_scopes=("meeting:write", "meeting:read", "user:read"),
    pkce=True,
))

_register(Connector(
    slug="microsoft_teams",
    label="Microsoft Teams (meetings)",
    category=CATEGORY_MEETING,
    auth_kind=AUTH_KIND_OAUTH2,
    brand_color="#464EB8",
    documentation_url="https://learn.microsoft.com/en-us/graph/auth-v2-user",
    authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    default_scopes=(
        "offline_access",
        "OnlineMeetings.ReadWrite",
        "User.Read",
    ),
    pkce=True,
))

_register(Connector(
    slug="google_meet",
    label="Google Meet",
    category=CATEGORY_MEETING,
    auth_kind=AUTH_KIND_OAUTH2,
    brand_color="#00897B",
    documentation_url="https://developers.google.com/meet/api/guides/overview",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    default_scopes=(
        "https://www.googleapis.com/auth/meetings.space.created",
        "openid",
        "email",
    ),
    extra_authorize_params={"access_type": "offline", "prompt": "consent"},
    pkce=True,
))

_register(Connector(
    slug="webex",
    label="Cisco Webex",
    category=CATEGORY_MEETING,
    auth_kind=AUTH_KIND_OAUTH2,
    brand_color="#00BCEB",
    documentation_url="https://developer.webex.com/docs/integrations",
    authorize_url="https://webexapis.com/v1/authorize",
    token_url="https://webexapis.com/v1/access_token",
    default_scopes=("spark:meetings_write", "spark:meetings_read"),
))


# -- Calendars --------------------------------------------------------------

_register(Connector(
    slug="google_calendar",
    label="Google Calendar",
    category=CATEGORY_CALENDAR,
    auth_kind=AUTH_KIND_OAUTH2,
    brand_color="#4285F4",
    documentation_url="https://developers.google.com/calendar/api/guides/overview",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    default_scopes=(
        "https://www.googleapis.com/auth/calendar.events",
        "openid",
        "email",
    ),
    extra_authorize_params={"access_type": "offline", "prompt": "consent"},
    pkce=True,
))

_register(Connector(
    slug="outlook_calendar",
    label="Outlook Calendar",
    category=CATEGORY_CALENDAR,
    auth_kind=AUTH_KIND_OAUTH2,
    brand_color="#0078D4",
    documentation_url="https://learn.microsoft.com/en-us/graph/outlook-calendar-concept-overview",
    authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    default_scopes=("offline_access", "Calendars.ReadWrite", "User.Read"),
    pkce=True,
))


# -- Mailbox (per-user reading) --------------------------------------------

_register(Connector(
    slug="gmail",
    label="Gmail (mailbox)",
    category=CATEGORY_MAILBOX,
    auth_kind=AUTH_KIND_OAUTH2,
    brand_color="#EA4335",
    documentation_url="https://developers.google.com/gmail/api/auth/scopes",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    default_scopes=(
        "https://www.googleapis.com/auth/gmail.send",
        "openid",
        "email",
    ),
    extra_authorize_params={"access_type": "offline", "prompt": "consent"},
    pkce=True,
))

_register(Connector(
    slug="outlook_mail",
    label="Outlook Mail (mailbox)",
    category=CATEGORY_MAILBOX,
    auth_kind=AUTH_KIND_OAUTH2,
    brand_color="#0078D4",
    documentation_url="https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview",
    authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    default_scopes=("offline_access", "Mail.Send", "Mail.Read", "User.Read"),
    pkce=True,
))


# -- Transactional mail providers (Anymail-backed) -------------------------

_register(Connector(
    slug="mailgun",
    label="Mailgun",
    category=CATEGORY_TRANSACTIONAL_MAIL,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#F06B66",
    documentation_url="https://documentation.mailgun.com/",
    required_config_keys=("api_key", "sender_domain"),
    anymail_backend="anymail.backends.mailgun.EmailBackend",
))

_register(Connector(
    slug="sendgrid",
    label="SendGrid",
    category=CATEGORY_TRANSACTIONAL_MAIL,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#1A82E2",
    documentation_url="https://docs.sendgrid.com/",
    required_config_keys=("api_key",),
    anymail_backend="anymail.backends.sendgrid.EmailBackend",
))

_register(Connector(
    slug="postmark",
    label="Postmark",
    category=CATEGORY_TRANSACTIONAL_MAIL,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#FFDE00",
    documentation_url="https://postmarkapp.com/developer",
    required_config_keys=("server_token",),
    anymail_backend="anymail.backends.postmark.EmailBackend",
))

_register(Connector(
    slug="amazon_ses",
    label="Amazon SES",
    category=CATEGORY_TRANSACTIONAL_MAIL,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#FF9900",
    documentation_url="https://docs.aws.amazon.com/ses/latest/dg/Welcome.html",
    required_config_keys=("access_key_id", "secret_access_key", "region"),
    anymail_backend="anymail.backends.amazon_ses.EmailBackend",
))

_register(Connector(
    slug="sparkpost",
    label="SparkPost",
    category=CATEGORY_TRANSACTIONAL_MAIL,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#FA6423",
    documentation_url="https://developers.sparkpost.com/",
    required_config_keys=("api_key",),
    anymail_backend="anymail.backends.sparkpost.EmailBackend",
))

_register(Connector(
    slug="brevo",
    label="Brevo (Sendinblue)",
    category=CATEGORY_TRANSACTIONAL_MAIL,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#0B996E",
    documentation_url="https://developers.brevo.com/",
    required_config_keys=("api_key",),
    anymail_backend="anymail.backends.brevo.EmailBackend",
))

_register(Connector(
    slug="mandrill",
    label="Mailchimp Transactional (Mandrill)",
    category=CATEGORY_TRANSACTIONAL_MAIL,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#FFE01B",
    documentation_url="https://mailchimp.com/developer/transactional/",
    required_config_keys=("api_key",),
    anymail_backend="anymail.backends.mandrill.EmailBackend",
))

_register(Connector(
    slug="mailersend",
    label="MailerSend",
    category=CATEGORY_TRANSACTIONAL_MAIL,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#3457D5",
    documentation_url="https://developers.mailersend.com/",
    required_config_keys=("api_token",),
    anymail_backend="anymail.backends.mailersend.EmailBackend",
))

_register(Connector(
    slug="mailjet",
    label="Mailjet",
    category=CATEGORY_TRANSACTIONAL_MAIL,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#FEAD0E",
    documentation_url="https://dev.mailjet.com/",
    required_config_keys=("api_key", "secret_key"),
    anymail_backend="anymail.backends.mailjet.EmailBackend",
))

_register(Connector(
    slug="resend",
    label="Resend",
    category=CATEGORY_TRANSACTIONAL_MAIL,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#000000",
    documentation_url="https://resend.com/docs",
    required_config_keys=("api_key",),
    anymail_backend="anymail.backends.resend.EmailBackend",
))

_register(Connector(
    slug="smtp_generic",
    label="Generic SMTP",
    category=CATEGORY_TRANSACTIONAL_MAIL,
    auth_kind=AUTH_KIND_SMTP,
    brand_color="#54595F",
    documentation_url="https://docs.djangoproject.com/en/stable/topics/email/#smtp-backend",
    required_config_keys=("host", "port", "username", "password", "use_tls"),
    anymail_backend="django.core.mail.backends.smtp.EmailBackend",
))


# -- Team chat -------------------------------------------------------------

_register(Connector(
    slug="slack",
    label="Slack",
    category=CATEGORY_CHAT,
    auth_kind=AUTH_KIND_OAUTH2,
    brand_color="#4A154B",
    documentation_url="https://api.slack.com/authentication/oauth-v2",
    authorize_url="https://slack.com/oauth/v2/authorize",
    token_url="https://slack.com/api/oauth.v2.access",
    default_scopes=("chat:write", "channels:read", "groups:read"),
    scope_separator=",",
))

_register(Connector(
    slug="microsoft_teams_chat",
    label="Microsoft Teams (chat)",
    category=CATEGORY_CHAT,
    auth_kind=AUTH_KIND_OAUTH2,
    brand_color="#464EB8",
    documentation_url="https://learn.microsoft.com/en-us/microsoftteams/platform/",
    authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    default_scopes=(
        "offline_access",
        "ChannelMessage.Send",
        "Chat.ReadWrite",
        "User.Read",
    ),
    pkce=True,
))

_register(Connector(
    slug="discord",
    label="Discord",
    category=CATEGORY_CHAT,
    auth_kind=AUTH_KIND_WEBHOOK,
    brand_color="#5865F2",
    documentation_url="https://discord.com/developers/docs/resources/webhook",
    required_config_keys=("webhook_url",),
))


# -- Legacy bridge: surface the existing INTEGRATION_CATALOG providers in the
# hub so operators see one unified catalog. These rows use the same Service-
# Integration backing store; the legacy API Center continues to work side-by-
# side for advanced config (rate limits, fallback channels). Added Wave v2.76.
# --------------------------------------------------------------------------

_register(Connector(
    slug="whatsapp",
    label="WhatsApp Business",
    category=CATEGORY_MESSAGING,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#25D366",
    documentation_url="https://developers.facebook.com/docs/whatsapp/cloud-api/",
    required_config_keys=("phone_number_id", "access_token"),
))

_register(Connector(
    slug="push",
    label="Push notifications",
    category=CATEGORY_MESSAGING,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#6E6E73",
    documentation_url="https://firebase.google.com/docs/cloud-messaging",
    required_config_keys=("provider", "server_key"),
))

_register(Connector(
    slug="sms",
    label="SMS",
    category=CATEGORY_MESSAGING,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#34C759",
    documentation_url="https://www.twilio.com/docs/usage/api",
    required_config_keys=("provider", "account_sid", "auth_token", "from_number"),
))

_register(Connector(
    slug="stripe",
    label="Stripe",
    category=CATEGORY_PAYMENT,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#635BFF",
    documentation_url="https://stripe.com/docs/api",
    required_config_keys=("publishable_key", "secret_key"),
))

_register(Connector(
    slug="badges",
    label="Open Badges",
    category=CATEGORY_BADGES,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#FF6F00",
    documentation_url="https://openbadges.org/",
    required_config_keys=("issuer_id", "issuer_url", "api_key"),
))

_register(Connector(
    slug="lms",
    label="LMS (LTI 1.3)",
    category=CATEGORY_LMS,
    auth_kind=AUTH_KIND_API_KEY,
    brand_color="#F77000",
    documentation_url="https://www.imsglobal.org/spec/lti/v1p3/",
    required_config_keys=("client_id", "deployment_id", "keyset_url", "login_url"),
))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_connector(slug: str) -> Connector | None:
    if not slug:
        return None
    return _REGISTRY.get(str(slug).strip().lower())


def list_connectors() -> list[Connector]:
    return list(_REGISTRY.values())


def list_connectors_by_category() -> dict[str, list[Connector]]:
    grouped: dict[str, list[Connector]] = {}
    for c in _REGISTRY.values():
        grouped.setdefault(c.category, []).append(c)
    return grouped


def list_oauth_connectors() -> list[Connector]:
    return [c for c in _REGISTRY.values() if c.auth_kind == AUTH_KIND_OAUTH2]


def list_transactional_mail_connectors() -> list[Connector]:
    return [c for c in _REGISTRY.values() if c.category == CATEGORY_TRANSACTIONAL_MAIL]


def resolve_oauth_client_credentials(
    slug: str,
) -> tuple[str, str]:
    """
    Read platform-level OAuth client_id/secret from env. Per-school connections
    still ride on these client credentials — the per-school part is the issued
    access_token + refresh_token (stored in ServiceIntegration.config).

    Env naming: `INTEGRATIONS_<UPPER_SLUG>_CLIENT_ID` /
                 `INTEGRATIONS_<UPPER_SLUG>_CLIENT_SECRET`
    e.g. `INTEGRATIONS_ZOOM_CLIENT_ID` / `INTEGRATIONS_ZOOM_CLIENT_SECRET`.

    Returns ("", "") when not configured — caller decides whether to refuse
    the connect or show a "platform owner hasn't registered this app yet"
    message.
    """
    key = (slug or "").strip().upper()
    if not key:
        return ("", "")
    cid = os.getenv(f"INTEGRATIONS_{key}_CLIENT_ID", "").strip()
    secret = os.getenv(f"INTEGRATIONS_{key}_CLIENT_SECRET", "").strip()
    return (cid, secret)


__all__ = [
    "AUTH_KIND_API_KEY",
    "AUTH_KIND_BASIC",
    "AUTH_KIND_OAUTH2",
    "AUTH_KIND_SMTP",
    "AUTH_KIND_WEBHOOK",
    "CATEGORY_BADGES",
    "CATEGORY_CALENDAR",
    "CATEGORY_CHAT",
    "CATEGORY_LABELS",
    "CATEGORY_LMS",
    "CATEGORY_MAILBOX",
    "CATEGORY_MEETING",
    "CATEGORY_MESSAGING",
    "CATEGORY_PAYMENT",
    "CATEGORY_TRANSACTIONAL_MAIL",
    "Connector",
    "get_connector",
    "list_connectors",
    "list_connectors_by_category",
    "list_oauth_connectors",
    "list_transactional_mail_connectors",
    "resolve_oauth_client_credentials",
]
