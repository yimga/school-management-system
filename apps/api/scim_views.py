"""SCIM 2.0 baseline endpoints (tenant-scoped) for user lifecycle and group sync."""

from __future__ import annotations

import json
import secrets
from typing import Any

from django.http import HttpRequest, JsonResponse, HttpResponse
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.accounts.models import AccessRole, User
from apps.api.rate_limit import throttle_ip_request
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.integration_registry import resolve_service_integration
from apps.integrations_marketplace.models import ServiceIntegration

SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
SCIM_RATE_LIMIT_WINDOW = 60 * 15
SCIM_RATE_LIMIT_MAX = 240


def _json_body(request: HttpRequest) -> dict[str, Any]:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


def _scim_error(detail: str, *, status: int = 400, scim_type: str | None = None):
    payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
        "detail": detail,
        "status": str(status),
    }
    if scim_type:
        payload["scimType"] = scim_type
    return JsonResponse(payload, status=status)


def _scim_rate_limited(request: HttpRequest, scope: str):
    allowed, retry_after = throttle_ip_request(
        request,
        scope=f"scim:{scope}",
        max_count=SCIM_RATE_LIMIT_MAX,
        window_seconds=SCIM_RATE_LIMIT_WINDOW,
    )
    if allowed:
        return None
    response = _scim_error("Too many requests", status=429)
    response["Retry-After"] = str(retry_after)
    return response


def _resolve_school(request: HttpRequest):
    school = getattr(request, "school", None)
    if school:
        return school
    school_slug = (
        (request.GET.get("school_slug") or "").strip()
        or (request.headers.get("X-School-Slug") or "").strip()
    )
    if not school_slug:
        return None
    return School.objects.filter(slug=school_slug, is_active=True).first()


def _resolve_scim_integration(school):
    return resolve_service_integration(
        school,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        service_name="scim",
        name_hints=["scim"],
        allow_legacy_backfill=True,
    )


def _extract_bearer(request: HttpRequest) -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return ""
    return auth[7:].strip()


def _authorize_scim_request(request: HttpRequest):
    school = _resolve_school(request)
    if not school:
        return None, None, _scim_error("School context required", status=400)
    integration = _resolve_scim_integration(school)
    if not integration:
        return None, None, _scim_error("SCIM integration not configured for school", status=503)
    expected = (
        str((integration.config or {}).get("bearer_token") or "").strip()
        or str(integration.client_secret or "").strip()
    )
    provided = _extract_bearer(request)
    if not expected or not provided or not secrets.compare_digest(expected, provided):
        return None, None, _scim_error("Unauthorized", status=403)
    return school, integration, None


def _user_scim_payload(user: User, school) -> dict[str, Any]:
    email = (user.email or "").strip()
    membership = SchoolMembership.objects.filter(user=user, school=school).first()
    role = membership.role if membership else (user.role or User.Role.PARENT)
    return {
        "schemas": [SCIM_USER_SCHEMA],
        "id": str(user.pk),
        "userName": user.username,
        "name": {
            "givenName": user.first_name or "",
            "familyName": user.last_name or "",
        },
        "displayName": (user.get_full_name() or user.username),
        "active": bool(user.is_active),
        "emails": [{"value": email, "primary": True}] if email else [],
        "roles": [{"value": role}],
    }


def _list_response(resources: list[dict[str, Any]], *, start_index: int = 1, total_results: int | None = None):
    payload = {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": int(total_results if total_results is not None else len(resources)),
        "startIndex": int(start_index),
        "itemsPerPage": len(resources),
        "Resources": resources,
    }
    return JsonResponse(payload, status=200)


def _parse_positive_int(raw: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _parse_filter_username(filter_expr: str) -> str:
    """
    Minimal filter support: userName eq "value" OR emails.value eq "value"
    """
    raw = (filter_expr or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    marker = ' eq '
    if marker not in lowered:
        return ""
    lhs, rhs = raw.split(marker, 1)
    key = lhs.strip().lower()
    value = rhs.strip().strip('"').strip("'")
    if key in {"username", "emails.value", "email"}:
        return value
    return ""


@require_http_methods(["GET"])
def scim_service_provider_config(request: HttpRequest):
    rl = _scim_rate_limited(request, "service_provider_config")
    if rl:
        return rl
    school, _, err = _authorize_scim_request(request)
    if err:
        return err
    payload = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": True},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {
                "type": "oauthbearertoken",
                "name": "OAuth Bearer Token",
                "description": f"Bearer token for SCIM on {school.slug}",
            }
        ],
    }
    return JsonResponse(payload, status=200)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def scim_users(request: HttpRequest):
    rl = _scim_rate_limited(request, "users")
    if rl:
        return rl
    school, integration, err = _authorize_scim_request(request)
    if err:
        return err

    if request.method == "GET":
        # RFC 7644/RFC 9865 semantics: startIndex is 1-based, count may be 0, and
        # totalResults reflects filtered total (not page size).
        start_index = _parse_positive_int(
            request.GET.get("startIndex", 1),
            default=1,
            minimum=1,
            maximum=10_000,
        )
        count = _parse_positive_int(
            request.GET.get("count", 100),
            default=100,
            minimum=0,
            maximum=200,
        )
        filter_username = _parse_filter_username(request.GET.get("filter") or "")

        memberships = SchoolMembership.objects.filter(school=school).select_related("user").order_by("user_id")
        if filter_username:
            memberships = memberships.filter(
                Q(user__username__iexact=filter_username)
                | Q(user__email__iexact=filter_username)
            )
        total_results = memberships.count()
        if count == 0:
            memberships = memberships.none()
        else:
            memberships = memberships[(start_index - 1):(start_index - 1 + count)]
        resources = [_user_scim_payload(m.user, school) for m in memberships]
        return _list_response(resources, start_index=start_index, total_results=total_results)

    body = _json_body(request)
    user_name = str(body.get("userName") or "").strip()
    if not user_name:
        return _scim_error("userName is required", status=400, scim_type="invalidValue")
    name = body.get("name") or {}
    given_name = str(name.get("givenName") or "").strip()
    family_name = str(name.get("familyName") or "").strip()
    active = bool(body.get("active", True))

    email = ""
    emails = body.get("emails") or []
    if isinstance(emails, list):
        for item in emails:
            if isinstance(item, dict) and str(item.get("value") or "").strip():
                email = str(item.get("value")).strip().lower()
                break

    default_role = str((integration.config or {}).get("default_role") or User.Role.PARENT).strip().upper()
    valid_roles = {choice[0] for choice in User.Role.choices}
    if default_role not in valid_roles:
        default_role = User.Role.PARENT

    user = User.objects.filter(username__iexact=user_name).first()
    if not user and email:
        user = User.objects.filter(email__iexact=email).first()
    created = False
    if not user:
        user = User.objects.create_user(
            username=user_name,
            email=email,
            first_name=given_name,
            last_name=family_name,
            role=default_role,
            is_active=active,
            password=secrets.token_urlsafe(24),
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        created = True
    else:
        user.email = email or user.email
        user.first_name = given_name or user.first_name
        user.last_name = family_name or user.last_name
        user.is_active = active
        user.save(update_fields=["email", "first_name", "last_name", "is_active"])

    SchoolMembership.objects.get_or_create(
        school=school,
        user=user,
        defaults={"role": user.role or default_role, "is_primary": False},
    )
    payload = _user_scim_payload(user, school)
    return JsonResponse(payload, status=201 if created else 200)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
def scim_user_detail(request: HttpRequest, user_id: str):
    rl = _scim_rate_limited(request, "user_detail")
    if rl:
        return rl
    school, _, err = _authorize_scim_request(request)
    if err:
        return err

    membership = SchoolMembership.objects.filter(school=school, user_id=user_id).select_related("user").first()
    if not membership:
        return _scim_error("User not found for this school", status=404)
    user = membership.user

    if request.method == "GET":
        return JsonResponse(_user_scim_payload(user, school), status=200)

    if request.method == "DELETE":
        user.is_active = False
        user.save(update_fields=["is_active"])
        return HttpResponse(status=204)

    body = _json_body(request)
    if request.method == "PUT":
        user_name = str(body.get("userName") or user.username).strip()
        name = body.get("name") or {}
        emails = body.get("emails") or []
        email = user.email
        if isinstance(emails, list):
            for item in emails:
                if isinstance(item, dict) and str(item.get("value") or "").strip():
                    email = str(item.get("value")).strip().lower()
                    break
        user.username = user_name or user.username
        user.first_name = str(name.get("givenName") or user.first_name).strip()
        user.last_name = str(name.get("familyName") or user.last_name).strip()
        user.email = email
        user.is_active = bool(body.get("active", user.is_active))
        user.save(update_fields=["username", "first_name", "last_name", "email", "is_active"])
        return JsonResponse(_user_scim_payload(user, school), status=200)

    # PATCH
    schemas = body.get("schemas") or []
    if SCIM_PATCH_SCHEMA not in schemas:
        return _scim_error("PATCH must declare PatchOp schema", status=400, scim_type="invalidSyntax")
    for op in body.get("Operations") or []:
        if not isinstance(op, dict):
            continue
        operation = str(op.get("op") or "").strip().lower()
        path = str(op.get("path") or "").strip().lower()
        value = op.get("value")
        if operation in {"replace", "add"} and path in {"active", "user.active"}:
            user.is_active = bool(value)
        elif operation in {"replace", "add"} and path in {"username", "userName".lower()}:
            if str(value or "").strip():
                user.username = str(value).strip()
        elif operation in {"replace", "add"} and path in {"name.givenname"}:
            user.first_name = str(value or "").strip()
        elif operation in {"replace", "add"} and path in {"name.familyname"}:
            user.last_name = str(value or "").strip()
        elif operation in {"replace", "add"} and path in {"emails", "emails.value"}:
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, dict) and str(first.get("value") or "").strip():
                    user.email = str(first.get("value")).strip().lower()
            elif str(value or "").strip():
                user.email = str(value).strip().lower()
    user.save(update_fields=["username", "first_name", "last_name", "email", "is_active"])
    return JsonResponse(_user_scim_payload(user, school), status=200)


def _group_payload(role: AccessRole, school) -> dict[str, Any]:
    members = []
    for user in role.users.filter(school_memberships__school=school).distinct():
        members.append({"value": str(user.pk), "display": user.username})
    return {
        "schemas": [SCIM_GROUP_SCHEMA],
        "id": str(role.pk),
        "displayName": role.name or role.code,
        "members": members,
    }


@require_http_methods(["GET"])
def scim_groups(request: HttpRequest):
    rl = _scim_rate_limited(request, "groups")
    if rl:
        return rl
    school, _, err = _authorize_scim_request(request)
    if err:
        return err
    roles = AccessRole.objects.order_by("code")
    resources = [_group_payload(role, school) for role in roles]
    return _list_response(resources)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
def scim_group_detail(request: HttpRequest, group_id: str):
    rl = _scim_rate_limited(request, "group_detail")
    if rl:
        return rl
    school, _, err = _authorize_scim_request(request)
    if err:
        return err
    role = AccessRole.objects.filter(pk=group_id).first()
    if not role:
        return _scim_error("Group not found", status=404)

    if request.method == "GET":
        return JsonResponse(_group_payload(role, school), status=200)

    body = _json_body(request)
    schemas = body.get("schemas") or []
    if SCIM_PATCH_SCHEMA not in schemas:
        return _scim_error("PATCH must declare PatchOp schema", status=400, scim_type="invalidSyntax")

    for op in body.get("Operations") or []:
        if not isinstance(op, dict):
            continue
        operation = str(op.get("op") or "").strip().lower()
        path = str(op.get("path") or "members").strip().lower()
        value = op.get("value")
        if path != "members":
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if not isinstance(item, dict):
                continue
            user_id = str(item.get("value") or "").strip()
            if not user_id:
                continue
            membership = SchoolMembership.objects.filter(school=school, user_id=user_id).select_related("user").first()
            if not membership:
                continue
            if operation == "add":
                membership.user.roles.add(role)
            elif operation == "remove":
                membership.user.roles.remove(role)

    return JsonResponse(_group_payload(role, school), status=200)
