from django.urls import path

from .views import login_view, logout_view, redirect_view, rbac_dashboard
from .views_mfa import mfa_setup, mfa_verify

app_name = "accounts"

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("redirect/", redirect_view, name="redirect"),
    path("rbac/", rbac_dashboard, name="rbac"),
    path("mfa/setup/", mfa_setup, name="mfa_setup"),
    path("mfa/verify/", mfa_verify, name="mfa_verify"),
]
