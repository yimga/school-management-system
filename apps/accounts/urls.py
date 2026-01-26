from django.urls import path

from .views import (
    backend_dashboard,
    backend_entity_import,
    backend_entity_console,
    claim_invite,
    login_view,
    logout_view,
    redirect_view,
    rbac_dashboard,
    user_documentation,
    user_messages,
    user_notifications,
    user_profile,
)
from .views_mfa import mfa_setup, mfa_verify

app_name = "accounts"

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("redirect/", redirect_view, name="redirect"),
    path("profile/", user_profile, name="user_profile"),
    path("notifications/", user_notifications, name="user_notifications"),
    path("messages/", user_messages, name="user_messages"),
    path("documentation/", user_documentation, name="user_documentation"),
    path("rbac/", rbac_dashboard, name="rbac"),
    path("backend/", backend_dashboard, name="backend_dashboard"),
    path("backend-dashboard/", backend_dashboard, name="backend_dashboard_alt"),
    path("backend/import/", backend_entity_import, name="backend_entity_import"),
    path("backend/entities/", backend_entity_console, name="backend_entity_console"),
    path("claim-invite/", claim_invite, name="claim_invite"),
    path("mfa/setup/", mfa_setup, name="mfa_setup"),
    path("mfa/verify/", mfa_verify, name="mfa_verify"),
]
