"""Guardian-consent URLs (v3.40.0 Agent 11).

Two separate URL namespaces mounted from ``config/urls.py``:

  * ``migration_guardian_consent`` (anonymous; token-in-URL):

        /migration/consent/<raw_token>/                — landing GET
        /migration/consent/<raw_token>/accept/         — accept POST
        /migration/consent/<raw_token>/decline/        — decline POST
        /migration/consent/<raw_token>/revoke/         — revoke POST

  * ``migration_guardian_consent_admin`` (tenant-scoped operator):

        /migration/<uuid:intake_id>/consent/                          — status
        /migration/<uuid:intake_id>/consent/campaign/start/            — start
        /migration/<uuid:intake_id>/consent/<uuid:token_id>/resend/    — resend

The two are kept separate so the anonymous namespace cannot be reverse-
resolved with intake_id semantics (which would expose tenant routing
through reverse(); the explicit grammar avoids accidental coupling).
"""
from __future__ import annotations

from django.urls import path

from . import views_guardian_consent, views_guardian_consent_admin


# ─── Anonymous guardian namespace ────────────────────────────────────────


guardian_anonymous_app_name = "migration_guardian_consent"

guardian_anonymous_urlpatterns = [
    path(  # rbac-allow: intentionally-public-guardian-consent-unguessable-256bit-url-token-credential
        "<str:raw_token>/",
        views_guardian_consent.GuardianConsentLandingView.as_view(),
        name="guardian-consent-landing",
    ),
    path(  # rbac-allow: intentionally-public-guardian-consent-unguessable-256bit-url-token-credential
        "<str:raw_token>/accept/",
        views_guardian_consent.GuardianConsentAcceptView.as_view(),
        name="guardian-consent-accept",
    ),
    path(  # rbac-allow: intentionally-public-guardian-consent-unguessable-256bit-url-token-credential
        "<str:raw_token>/decline/",
        views_guardian_consent.GuardianConsentDeclineView.as_view(),
        name="guardian-consent-decline",
    ),
    path(  # rbac-allow: intentionally-public-guardian-consent-unguessable-256bit-url-token-credential
        "<str:raw_token>/revoke/",
        views_guardian_consent.GuardianConsentRevokeView.as_view(),
        name="guardian-consent-revoke",
    ),
]


# ─── Tenant-scoped operator namespace ────────────────────────────────────


admin_app_name = "migration_guardian_consent_admin"

admin_urlpatterns = [
    path(
        "<uuid:intake_id>/consent/",
        views_guardian_consent_admin.GuardianConsentCampaignStatusView.as_view(),
        name="guardian-consent-campaign-status",
    ),
    path(
        "<uuid:intake_id>/consent/campaign/start/",
        views_guardian_consent_admin.GuardianConsentCampaignStartView.as_view(),
        name="guardian-consent-campaign-start",
    ),
    path(
        "<uuid:intake_id>/consent/<uuid:token_id>/resend/",
        views_guardian_consent_admin.GuardianConsentResendView.as_view(),
        name="guardian-consent-resend",
    ),
]


# Default ``urlpatterns`` for include(); use the anonymous set since
# config/urls.py mounts the two namespaces under distinct path prefixes
# from individual include() calls.
app_name = guardian_anonymous_app_name
urlpatterns = guardian_anonymous_urlpatterns
