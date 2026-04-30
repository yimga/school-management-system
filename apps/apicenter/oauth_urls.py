"""Mounted at path('api/v1/oauth/', include(...))."""

from django.urls import path

from apps.apicenter import oauth_views

app_name = "oauth"

urlpatterns = [
    path("token/", oauth_views.OAuthTokenView.as_view(), name="token"),
    path("authorize/", oauth_views.oauth_authorize, name="authorize"),
]
