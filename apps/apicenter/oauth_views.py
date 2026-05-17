"""OAuth2 authorize + token endpoints (developer platform)."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.apicenter.models import DeveloperApplication
from apps.apicenter.oauth_service import (
    consume_authorization_code,
    create_authorization_code,
    exchange_refresh_token,
    issue_token_pair,
    parse_token_request_body,
    verify_client_credentials,
)


def _oauth_error(error: str, description: str = "", status: int = 400):
    body = {"error": error}
    if description:
        body["error_description"] = description
    return JsonResponse(body, status=status)


@method_decorator(csrf_exempt, name="dispatch")
class OAuthTokenView(View):
    """
    POST /api/v1/oauth/token
    grant_type=authorization_code | client_credentials | refresh_token
    """

    def post(self, request):
        params = parse_token_request_body(request)
        grant = (params.get("grant_type") or "").strip()
        client_id = (params.get("client_id") or "").strip()
        client_secret = (params.get("client_secret") or "").strip()

        if grant == "client_credentials":
            if not client_id or not client_secret:
                return _oauth_error(
                    "invalid_request", "client_id and client_secret required", 400
                )
            app = verify_client_credentials(client_id, client_secret)
            if app is None:
                return _oauth_error("invalid_client", "Invalid credentials", 401)
            tokens = issue_token_pair(app, user=None)
            return JsonResponse(
                {
                    "access_token": tokens["access_token"],
                    "token_type": "Bearer",
                    "expires_in": tokens["expires_in"],
                    "refresh_token": tokens["refresh_token"],
                    "scope": tokens["scope"],
                }
            )

        if grant == "refresh_token":
            refresh = (params.get("refresh_token") or "").strip()
            if not refresh or not client_id or not client_secret:
                return _oauth_error(
                    "invalid_request",
                    "refresh_token, client_id, and client_secret required",
                    400,
                )
            app = verify_client_credentials(client_id, client_secret)
            if app is None:
                return _oauth_error("invalid_client", "Invalid credentials", 401)
            out = exchange_refresh_token(refresh, app)
            if out is None:
                return _oauth_error("invalid_grant", "Invalid refresh token", 400)
            return JsonResponse(
                {
                    "access_token": out["access_token"],
                    "token_type": "Bearer",
                    "expires_in": out["expires_in"],
                    "refresh_token": out["refresh_token"],
                    "scope": out["scope"],
                }
            )

        if grant == "authorization_code":
            code = (params.get("code") or "").strip()
            redirect_uri = (params.get("redirect_uri") or "").strip()
            if not code or not redirect_uri or not client_id or not client_secret:
                return _oauth_error(
                    "invalid_request",
                    "code, redirect_uri, client_id, and client_secret required",
                    400,
                )
            app = verify_client_credentials(client_id, client_secret)
            if app is None:
                return _oauth_error("invalid_client", "Invalid credentials", 401)
            consumed = consume_authorization_code(
                code, application=app, redirect_uri=redirect_uri
            )
            if consumed is None:
                return _oauth_error("invalid_grant", "Invalid or expired code", 400)
            user, scope = consumed
            tokens = issue_token_pair(app, user=user, scope=scope)
            return JsonResponse(
                {
                    "access_token": tokens["access_token"],
                    "token_type": "Bearer",
                    "expires_in": tokens["expires_in"],
                    "refresh_token": tokens["refresh_token"],
                    "scope": tokens["scope"],
                }
            )

        return _oauth_error(
            "unsupported_grant_type",
            "Supported: client_credentials, refresh_token, authorization_code",
            400,
        )


@require_GET
@login_required
def oauth_authorize(request):
    """
    GET /api/v1/oauth/authorize — browser login flow (authorization code).
    """
    client_id = (request.GET.get("client_id") or "").strip()
    redirect_uri = (request.GET.get("redirect_uri") or "").strip()
    response_type = (request.GET.get("response_type") or "").strip()
    state = (request.GET.get("state") or "").strip()
    scope = (request.GET.get("scope") or "").strip()

    if response_type != "code":
        return _oauth_error(
            "unsupported_response_type", "Only response_type=code is supported", 400
        )
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    app = DeveloperApplication.objects.filter(
        client_id=client_id, is_active=True
    ).first()
    if app is None:
        return _oauth_error("invalid_client", "Unknown client_id", 400)
    allowed = app.redirect_uris or []
    if redirect_uri not in allowed:
        return _oauth_error(
            "invalid_request", "redirect_uri is not registered for this client", 400
        )

    code = create_authorization_code(
        application=app,
        user=request.user,
        redirect_uri=redirect_uri,
        scope=scope,
    )
    parsed = urlparse(redirect_uri)
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    q["code"] = code
    if state:
        q["state"] = state
    new_query = urlencode(q)
    target = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )
    return HttpResponseRedirect(target)
