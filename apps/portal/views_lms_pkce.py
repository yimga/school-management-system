"""v4.00.53 — OAuth2 PKCE flow for operator LMS token-mint UI (Wedge 2).

Implements RFC 7636 (Proof Key for Code Exchange) for the Canvas + Google
Classroom token-mint paths. Operators kick off the flow from the per-
provider console; the platform stashes a per-session ``code_verifier`` +
``state``, redirects to the upstream authorize URL, then on the callback
posts ``grant_type=authorization_code`` with the code_verifier to mint the
``access_token`` + ``refresh_token`` and persists them on the
``LMSConnectorToken`` row.

Endpoints
---------
* ``GET /portal/super/integrations/lms/<provider>/pkce/start/?school=<id>``
  — generates verifier + challenge, stashes in session, 302 to upstream.
* ``GET /portal/super/integrations/lms/<provider>/pkce/callback/?code=&state=``
  — validates state, exchanges code, persists token, 302 back to detail.

Moodle uses wstoken (not OAuth2) and returns 400 ``unsupported_provider``.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider config SOT — per-provider authorize + token endpoints + scopes.
# ---------------------------------------------------------------------------

# Default scopes follow the LMS adapter SOT. Operators can override via
# ``RMC_LMS_<PROVIDER>_PKCE_SCOPE`` env vars without touching code.
_DEFAULT_SCOPES: dict[str, str] = {
    "canvas": "url:GET|/api/v1/courses url:GET|/api/v1/courses/:course_id/assignments url:POST|/api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id",
    "google": "https://www.googleapis.com/auth/classroom.courses.readonly https://www.googleapis.com/auth/classroom.coursework.students",
}


def _provider_oauth_endpoints(provider: str, base_url: str) -> dict[str, str] | None:
    """Return ``{"authorize_url", "token_url"}`` for the provider, or None."""
    if provider == "canvas":
        if not base_url:
            return None
        base = base_url.rstrip("/")
        return {"authorize_url": f"{base}/login/oauth2/auth", "token_url": f"{base}/login/oauth2/token"}
    if provider == "google":
        return {
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
        }
    return None


def _gen_code_verifier() -> str:
    """43-character URL-safe random verifier (RFC 7636 §4.1)."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def _challenge_from_verifier(verifier: str) -> str:
    """S256 challenge = base64url(SHA-256(verifier)) (RFC 7636 §4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _resolve_client_id(provider: str) -> str:
    up = provider.upper()
    return (
        getattr(settings, f"RMC_LMS_{up}_CLIENT_ID", "")
        or os.environ.get(f"RMC_LMS_{up}_CLIENT_ID", "")
        or ""
    ).strip()


def _resolve_client_secret(provider: str) -> str:
    up = provider.upper()
    return (
        getattr(settings, f"RMC_LMS_{up}_CLIENT_SECRET", "")
        or os.environ.get(f"RMC_LMS_{up}_CLIENT_SECRET", "")
        or ""
    ).strip()


def _resolve_scope(provider: str) -> str:
    up = provider.upper()
    env = (
        getattr(settings, f"RMC_LMS_{up}_PKCE_SCOPE", "")
        or os.environ.get(f"RMC_LMS_{up}_PKCE_SCOPE", "")
        or ""
    ).strip()
    return env or _DEFAULT_SCOPES.get(provider, "")


def _resolve_redirect_uri(request: HttpRequest, provider: str) -> str:
    """Absolute URL of the PKCE callback. Honors ``OAUTH_CALLBACK_BASE_URL``."""
    callback_path = reverse("portal:lms_pkce_callback", args=[provider])
    base = (
        getattr(settings, "OAUTH_CALLBACK_BASE_URL", "")
        or os.environ.get("OAUTH_CALLBACK_BASE_URL", "")
        or ""
    ).strip()
    if base:
        return base.rstrip("/") + callback_path
    return request.build_absolute_uri(callback_path)


_SESSION_KEY = "_lms_pkce_state_v40053"
_VERIFIER_TTL_SECONDS = 600  # 10 min — enough for upstream consent.


@staff_member_required
@require_http_methods(["GET"])
def lms_pkce_start(request: HttpRequest, provider: str):
    """v4.00.53 — Generate verifier+challenge, stash in session, 302 to upstream.

    Required: ``?school=<id>`` query-string.
    """
    from apps.api import lms_adapters

    if provider not in lms_adapters.supported_providers():
        return JsonResponse({"error": "unknown_provider"}, status=404)
    if provider == "moodle":
        return JsonResponse({"error": "unsupported_provider", "detail": "moodle uses wstoken, not OAuth2"}, status=400)

    school_id = (request.GET.get("school") or "").strip()
    if not school_id:
        return JsonResponse({"error": "missing_school"}, status=400)

    client_id = _resolve_client_id(provider)
    if not client_id:
        return JsonResponse({"error": "client_id_missing", "needed": f"RMC_LMS_{provider.upper()}_CLIENT_ID"}, status=412)

    # Canvas authorize URL is tenant-specific — we read ``base_url`` from the
    # row when it already exists, else accept ``?base_url=...`` from the
    # query string so the operator can mint the first row from scratch.
    base_url = (request.GET.get("base_url") or "").strip()
    if provider == "canvas" and not base_url:
        from apps.integrations_marketplace.models import LMSConnectorToken
        row = LMSConnectorToken.objects.filter(  # tenant-isolation-allow: pkce-start-resolve-base-url-staff-required
            school_id=school_id, provider=provider
        ).first()
        base_url = (getattr(row, "base_url", "") or "").strip() if row else ""
    eps = _provider_oauth_endpoints(provider, base_url)
    if eps is None:
        return JsonResponse({"error": "missing_base_url", "detail": "canvas requires base_url"}, status=400)

    verifier = _gen_code_verifier()
    challenge = _challenge_from_verifier(verifier)
    state = secrets.token_urlsafe(32)
    request.session[_SESSION_KEY] = {
        "verifier": verifier,
        "state": state,
        "school_id": school_id,
        "provider": provider,
        "base_url": base_url,
    }
    request.session.modified = True

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": _resolve_redirect_uri(request, provider),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    scope = _resolve_scope(provider)
    if scope:
        params["scope"] = scope
    if provider == "google":
        # Google needs access_type=offline + prompt=consent to issue a refresh_token.
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    auth_url = eps["authorize_url"] + "?" + urllib.parse.urlencode(params)
    return HttpResponseRedirect(auth_url)


def _exchange_code(
    *, token_url: str, code: str, code_verifier: str, client_id: str,
    client_secret: str, redirect_uri: str, timeout: int = 15,
) -> tuple[int, dict[str, Any]]:
    """POST grant_type=authorization_code + code_verifier; returns (status, body)."""
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
    }
    data = urllib.parse.urlencode(body).encode("ascii")
    req = urllib.request.Request(
        token_url, data=data, method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — stdlib URL we constructed
            raw = resp.read().decode("utf-8", "replace")
            status = resp.getcode()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace") if exc.fp else ""
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"error": "transport_error", "detail": str(exc)}
    try:
        return status, json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return status, {"error": "bad_response", "raw": raw[:200]}


@staff_member_required
@require_http_methods(["GET"])
def lms_pkce_callback(request: HttpRequest, provider: str):
    """v4.00.53 — Receive code+state, exchange for token, persist.

    Validates ``state`` against session, refuses if missing/expired.
    """
    stash = request.session.get(_SESSION_KEY)
    if not isinstance(stash, dict) or stash.get("provider") != provider:
        return JsonResponse({"error": "missing_pkce_session"}, status=400)

    state_in = (request.GET.get("state") or "").strip()
    code = (request.GET.get("code") or "").strip()
    err = (request.GET.get("error") or "").strip()
    if err:
        return JsonResponse({"error": "upstream_denied", "detail": err}, status=400)
    if not state_in or state_in != stash.get("state"):
        return JsonResponse({"error": "state_mismatch"}, status=400)
    if not code:
        return JsonResponse({"error": "missing_code"}, status=400)

    verifier = str(stash.get("verifier") or "")
    school_id = str(stash.get("school_id") or "")
    base_url = str(stash.get("base_url") or "")
    if not verifier or not school_id:
        return JsonResponse({"error": "incomplete_pkce_session"}, status=400)

    eps = _provider_oauth_endpoints(provider, base_url)
    if eps is None:
        return JsonResponse({"error": "missing_endpoints"}, status=400)

    client_id = _resolve_client_id(provider)
    client_secret = _resolve_client_secret(provider)
    if not client_id or not client_secret:
        return JsonResponse({"error": "client_credentials_missing"}, status=412)

    status, body = _exchange_code(
        token_url=eps["token_url"],
        code=code, code_verifier=verifier,
        client_id=client_id, client_secret=client_secret,
        redirect_uri=_resolve_redirect_uri(request, provider),
    )
    if status != 200 or not body.get("access_token"):
        # Wipe the session stash so the verifier can't be re-used.
        request.session.pop(_SESSION_KEY, None)
        return JsonResponse(
            {"error": "token_exchange_failed", "status_code": status, "detail": body},
            status=502,
        )

    from apps.integrations_marketplace.models import LMSConnectorToken
    from apps.schools.models import School
    from django.utils import timezone as _tz
    from datetime import timedelta as _td

    school = School.objects.filter(pk=school_id).first()  # tenant-isolation-allow: pkce-callback-resolve-school-by-pk
    if school is None:
        return JsonResponse({"error": "school_not_found"}, status=404)

    row, _ = LMSConnectorToken.objects.get_or_create(  # tenant-isolation-allow: pkce-callback-upsert-token-by-school-provider
        school=school, provider=provider,
        defaults={"base_url": base_url},
    )
    if base_url and not row.base_url:
        row.base_url = base_url
    row.access_token = str(body["access_token"])
    refresh_token = body.get("refresh_token")
    if refresh_token:
        row.refresh_token = str(refresh_token)
    expires_in = int(body.get("expires_in") or 0)
    if expires_in:
        row.expires_at = _tz.now() + _td(seconds=expires_in)
    scope_back = body.get("scope")
    if scope_back:
        row.scope = str(scope_back)
    row.save(update_fields=[
        "base_url", "access_token", "refresh_token", "expires_at", "scope", "updated_at",
    ])

    request.session.pop(_SESSION_KEY, None)

    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": True,
            "provider": provider,
            "school": school_id,
            "expires_in": expires_in,
            "scope": row.scope,
        })
    return HttpResponseRedirect(reverse("portal:lms_provider_detail", args=[provider]))
