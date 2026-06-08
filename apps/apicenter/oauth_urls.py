"""Mounted at path('api/v1/oauth/', include(...))."""

from django.urls import path

from apps.apicenter import oauth_views

app_name = "oauth"

urlpatterns = [
    # rbac-allow: oauth-client-credentials-token-exchange-rfc6749
    path("token/", oauth_views.OAuthTokenView.as_view(), name="token"),
    path("authorize/", oauth_views.oauth_authorize, name="authorize"),
]
