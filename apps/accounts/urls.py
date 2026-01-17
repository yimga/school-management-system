from django.urls import path

from .views import login_view, logout_view, redirect_view

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("redirect/", redirect_view, name="redirect"),
]
