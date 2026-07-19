"""Athletics tenant URL configuration (mounted at ``athletics/`` in config.tenant_urls).

Coach console, family surface, academic-leadership admin console, and the anonymous
token-in-URL participation-consent pages. The two ``consent/`` routes are anonymous by
design (guardian follows an emailed link; lookup is by sha256 of the token) — marked
``# rbac-allow:`` the same way the people transfer-consent routes are in config/urls.py.
"""

from django.urls import path

from apps.athletics import views


app_name = "athletics"


urlpatterns = [
    # ── Coach console ──────────────────────────────────────────────────────
    path("", views.coach_dashboard, name="coach_dashboard"),
    path("teams/<int:team_id>/", views.coach_team_detail, name="coach_team_detail"),
    path(
        "teams/<int:team_id>/eligibility/",
        views.coach_eligibility,
        name="coach_eligibility",
    ),
    path("teams/<int:team_id>/fixtures/", views.coach_fixtures, name="coach_fixtures"),
    path(
        "teams/<int:team_id>/fixtures/schedule/",
        views.coach_schedule_fixture,
        name="coach_schedule_fixture",
    ),
    path(
        "teams/<int:team_id>/members/add/",
        views.coach_add_member,
        name="coach_add_member",
    ),
    path(
        "fixtures/<int:fixture_id>/result/",
        views.coach_record_result,
        name="coach_record_result",
    ),
    path(
        "fixtures/<int:fixture_id>/cancel/",
        views.coach_cancel_fixture,
        name="coach_cancel_fixture",
    ),
    path(
        "memberships/<int:membership_id>/request-consent/",
        views.coach_request_consent,
        name="coach_request_consent",
    ),
    path(
        "memberships/<int:membership_id>/record-clearance/",
        views.coach_record_clearance,
        name="coach_record_clearance",
    ),
    # ── Family surface (student self / parent's children) ──────────────────
    path("my-team/", views.family_my_team, name="family_my_team"),
    # ── Academic-leadership admin console ──────────────────────────────────
    path("admin/seasons/", views.admin_seasons, name="admin_seasons"),
    path("admin/fixtures/", views.admin_fixtures, name="admin_fixtures"),
    path("admin/clubs/", views.admin_clubs, name="admin_clubs"),
    path(
        "admin/clubs/<int:club_id>/",
        views.admin_club_detail,
        name="admin_club_detail",
    ),
    path(
        "admin/clubs/<int:club_id>/enroll/",
        views.admin_club_enroll,
        name="admin_club_enroll",
    ),
    path(
        "admin/club-memberships/<int:membership_id>/withdraw/",
        views.admin_club_withdraw,
        name="admin_club_withdraw",
    ),
    # ── Anonymous guardian participation-consent pages (token-in-URL) ──────
    path(  # rbac-allow: anonymous-by-design-consent-token-in-url-sha256-lookup
        "consent/",
        views.participation_consent_public,
        name="participation_consent_public",
    ),
    path(  # rbac-allow: anonymous-by-design-consent-token-in-url-sha256-lookup
        "consent/decide/",
        views.participation_consent_decide,
        name="participation_consent_decide",
    ),
]
