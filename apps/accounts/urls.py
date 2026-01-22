from django.urls import path

from .views import backend_dashboard, claim_invite, login_view, logout_view, redirect_view, rbac_dashboard

app_name = "accounts"

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("redirect/", redirect_view, name="redirect"),
    path("rbac/", rbac_dashboard, name="rbac"),
    path("backend/", backend_dashboard, name="backend_dashboard"),
    path("claim-invite/", claim_invite, name="claim_invite"),
    path("backend-dashboard/", backend_dashboard, name="backend_dashboard_alias"),
]
