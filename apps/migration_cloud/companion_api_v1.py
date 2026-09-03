"""JWT-authenticated /api/v1/ surface for Companion siblings (Tauri / Docker).

The session-gated HTML mounts under ``/super/migration/companion/`` and
``/portal/configure/migration/companion/`` remain unchanged. These views
implement the contract documented in
``docs/COMPANION_SIBLINGS_HANDSHAKE_AND_CSV_INGEST.md`` so desktop and
container clients can authenticate with ``Authorization: Bearer`` and
complete login → MAA → upload → receipt fetch without a browser session.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib.auth import authenticate, get_user_model
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken

from apps.api.rate_limit import throttle_ip_request
from apps.migration_cloud.companion_receiver import (
    CompanionUploadView,
    MAASignView,
    companion_server_pubkey_view,
    maa_text_view,
)
from apps.migration_cloud.models import CompanionUploadReceipt, MigrationAuthorizationAgreement
from apps.schools.models import School
from apps.schools.tenant_switch_security import user_may_access_school_api

logger = logging.getLogger(__name__)

User = get_user_model()


def _django_request(request) -> HttpRequest:
    return getattr(request, "_request", request)


def _tenant_slug_from_request(request: HttpRequest) -> str:
    header = (request.headers.get("X-Tenant") or request.META.get("HTTP_X_TENANT") or "").strip()
    if header:
        return header
    return (request.GET.get("tenant") or "").strip()


def _lookup_school_by_slug(slug: str) -> School | None:
    if not slug:
        return None
    return School.objects.filter(slug=slug, is_active=True).first()


def bind_companion_tenant(
    request: HttpRequest,
    *,
    require_explicit: bool = False,
) -> tuple[School | None, HttpResponse | None]:
    """Resolve and attach ``request.school`` for a JWT companion call."""
    existing = getattr(request, "school", None) or getattr(request, "tenant", None)
    if existing is not None:
        request.school = existing
        return existing, None

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None, JsonResponse(
            {"ok": False, "error": "Authentication required", "code": "auth_required"},
            status=401,
        )

    slug = _tenant_slug_from_request(request)
    if slug:
        school = _lookup_school_by_slug(slug)
        if school is None:
            return None, JsonResponse(
                {"ok": False, "error": "tenant not found", "code": "tenant_not_found"},
                status=404,
            )
        if not user_may_access_school_api(user, school):
            return None, JsonResponse(
                {"ok": False, "error": "Forbidden", "code": "tenant_forbidden"},
                status=403,
            )
        request.school = school
        return school, None

    if require_explicit:
        return None, JsonResponse(
            {
                "ok": False,
                "error": "tenant query parameter or X-Tenant header required",
                "code": "missing_tenant",
            },
            status=400,
        )

    from apps.migration_cloud.companion_receiver import _request_school

    school = _request_school(request)
    if school is None:
        return None, JsonResponse(
            {"ok": False, "error": "no tenant membership", "code": "no_tenant"},
            status=403,
        )
    request.school = school
    return school, None


def _bind_tenant_for_upload(request: HttpRequest) -> tuple[School | None, HttpResponse | None]:
    school, err = bind_companion_tenant(request, require_explicit=False)
    if school is not None:
        return school, None
    if err is not None:
        metadata_raw = request.POST.get("metadata") or ""
        if not metadata_raw:
            return None, err
        try:
            payload = json.loads(metadata_raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, err
        maa_id = payload.get("maa_id")
        if not isinstance(maa_id, int):
            return None, err
        try:
            maa = MigrationAuthorizationAgreement.objects.select_related("tenant").get(pk=maa_id)
        except MigrationAuthorizationAgreement.DoesNotExist:
            return None, err
        user = request.user
        if not user_may_access_school_api(user, maa.tenant):
            return None, JsonResponse(
                {"ok": False, "error": "Forbidden", "code": "tenant_forbidden"},
                status=403,
            )
        request.school = maa.tenant
        return maa.tenant, None


def _forward_django_response(response: HttpResponse) -> HttpResponse:
    return response


class _CompanionJwtMixin:
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]


class CompanionEmailLoginView(APIView):
    """POST /api/v1/auth/login/ — email + password → bearer token."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    def post(self, request, *args, **kwargs):
        allowed, retry_after = throttle_ip_request(
            _django_request(request),
            scope="api_auth:companion_login",
            max_count=20,
            window_seconds=60,
        )
        if not allowed:
            return Response(
                {
                    "detail": "Too many authentication requests. Try again later.",
                    "retry_after": int(retry_after),
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        email = (request.data.get("email") or "").strip()
        password = request.data.get("password") or ""
        if not email or not password:
            return Response(
                {"ok": False, "error": "email and password required", "code": "missing_credentials"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(
            _django_request(request),
            username=email,
            password=password,
        )
        if user is None:
            logger.info("companion_api_v1.login failed status=401")
            return Response(
                {"ok": False, "error": "Invalid credentials", "code": "invalid_credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)
        logger.info("companion_api_v1.login ok user_id=%s", user.pk)
        return Response(
            {
                "ok": True,
                "token": access,
                "access": access,
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
class CompanionMaaTextApiView(_CompanionJwtMixin, APIView):
    def get(self, request, *args, **kwargs):
        django_request = _django_request(request)
        _, err = bind_companion_tenant(django_request, require_explicit=True)
        if err is not None:
            return _forward_django_response(err)
        return _forward_django_response(maa_text_view(django_request, **kwargs))


@method_decorator(csrf_exempt, name="dispatch")
class CompanionMaaSignApiView(_CompanionJwtMixin, APIView):
    def post(self, request, *args, **kwargs):
        django_request = _django_request(request)
        _, err = bind_companion_tenant(django_request, require_explicit=True)
        if err is not None:
            return _forward_django_response(err)
        return _forward_django_response(
            MAASignView.as_view()(django_request, *args, **kwargs)
        )


@method_decorator(csrf_exempt, name="dispatch")
class CompanionUploadApiView(_CompanionJwtMixin, APIView):
    def post(self, request, *args, **kwargs):
        django_request = _django_request(request)
        if hasattr(request, "FILES"):
            django_request.FILES = request.FILES
        if hasattr(request, "POST"):
            django_request.POST = request.POST
        _, err = _bind_tenant_for_upload(django_request)
        if err is not None:
            return _forward_django_response(err)
        return _forward_django_response(
            CompanionUploadView.as_view()(django_request, *args, **kwargs)
        )


class CompanionServerPubkeyApiView(APIView):
    """GET pubkey — anonymous when ``?tenant=`` is supplied (matches E-8 contract)."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    def get(self, request, *args, **kwargs):
        django_request = _django_request(request)
        if getattr(request, "user", None) and request.user.is_authenticated:
            django_request.user = request.user
        return _forward_django_response(
            companion_server_pubkey_view(django_request, **kwargs)
        )


class CompanionReceiptListApiView(_CompanionJwtMixin, APIView):
    def get(self, request, *args, **kwargs):
        django_request = _django_request(request)
        school, err = bind_companion_tenant(django_request, require_explicit=False)
        if err is not None:
            return _forward_django_response(err)

        receipts = (
            CompanionUploadReceipt.objects.filter(tenant=school)
            .select_related("bundle")
            .order_by("-received_at")[:100]
        )
        payload = [
            {
                "receipt_id": row.pk,
                "bundle_id": row.bundle_id,
                "status": row.bundle.status if row.bundle else "unknown",
                "received_at": row.received_at.isoformat(),
            }
            for row in receipts
        ]
        return Response({"ok": True, "receipts": payload}, status=status.HTTP_200_OK)


class CompanionReceiptDetailApiView(_CompanionJwtMixin, APIView):
    def get(self, request, receipt_id: int, *args, **kwargs):
        django_request = _django_request(request)
        school, err = bind_companion_tenant(django_request, require_explicit=False)
        if err is not None:
            return _forward_django_response(err)

        receipt = (
            CompanionUploadReceipt.objects.filter(pk=receipt_id, tenant=school)
            .select_related("bundle")
            .first()
        )
        if receipt is None:
            return Response(
                {"ok": False, "error": "receipt not found", "code": "receipt_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "ok": True,
                "receipt_id": receipt.pk,
                "bundle_id": receipt.bundle_id,
                "status": receipt.bundle.status if receipt.bundle else "unknown",
                "received_at": receipt.received_at.isoformat(),
            },
            status=status.HTTP_200_OK,
        )
