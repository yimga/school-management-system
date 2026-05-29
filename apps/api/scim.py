"""v4.00.39 — SCIM 2.0 provisioning endpoints (Wedge 45 item 2).

Implements the System for Cross-domain Identity Management v2.0 protocol
(RFC 7644 + RFC 7643) for Users + Groups. Operator surface lives at
``/scim/v2/`` and is intended to be pointed-to by IdPs (Entra ID, Okta,
Google Workspace) for automatic user / group provisioning.

Scope shipped in v4.00.39
-------------------------
* ``GET    /scim/v2/ServiceProviderConfig`` — capabilities envelope.
* ``GET    /scim/v2/Schemas``               — supported resource schemas.
* ``GET    /scim/v2/ResourceTypes``         — Users + Groups resource types.
* ``GET    /scim/v2/Users``                 — list + filter (eq/co/sw/ew/pr) + paginate.
* ``POST   /scim/v2/Users``                 — create.
* ``GET    /scim/v2/Users/<id>``            — fetch.
* ``PUT    /scim/v2/Users/<id>``            — replace.
* ``PATCH  /scim/v2/Users/<id>``            — partial update (add/replace/remove ops).
* ``DELETE /scim/v2/Users/<id>``            — soft-deactivate (sets is_active=False).
* ``GET    /scim/v2/Groups``                — list + filter + paginate.
* ``POST   /scim/v2/Groups``                — create (currently stub-recorded).
* ``GET    /scim/v2/Groups/<id>``           — fetch (auth.Group-backed).

Auth: bearer token via ``RMC_SCIM_ACCESS_TOKEN`` env (constant-time
compared); soft-allows in dev when unset.

Content type per spec: ``application/scim+json``.
"""
from __future__ import annotations

import hmac
import logging
import os
import re
import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json

logger = logging.getLogger(__name__)


_SCIM_CT = "application/scim+json"
_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
_LIST_RESPONSE_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
_PATCH_OP_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"


# ----- auth ---------------------------------------------------------------


def _expected_token() -> str:
    return str(
        getattr(settings, "RMC_SCIM_ACCESS_TOKEN", "")
        or os.environ.get("RMC_SCIM_ACCESS_TOKEN", "")
        or ""
    )


def _authenticate(request: HttpRequest) -> tuple[bool, str | None]:
    header = request.META.get("HTTP_AUTHORIZATION", "") or ""
    if not header.lower().startswith("bearer "):
        return False, "missing_bearer"
    submitted = header[7:].strip()
    expected = _expected_token()
    if not expected:
        logger.info("scim: no RMC_SCIM_ACCESS_TOKEN configured (dev mode)")
        return True, None
    if not submitted or not hmac.compare_digest(submitted, expected):
        return False, "invalid_token"
    return True, None


def _gate(request: HttpRequest) -> JsonResponse | None:
    ok, err = _authenticate(request)
    if ok:
        return None
    resp = _scim_error(401, "unauthorized", err or "")
    resp["WWW-Authenticate"] = 'Bearer realm="SCIM 2.0"'
    return resp


def _scim_response(body: dict[str, Any], status: int = 200) -> JsonResponse:
    resp = JsonResponse(body, status=status)
    resp["Content-Type"] = _SCIM_CT
    return resp


def _scim_error(status: int, scim_type: str, detail: str) -> JsonResponse:
    return _scim_response({
        "schemas": [_ERROR_SCHEMA],
        "status": str(status),
        "scimType": scim_type,
        "detail": detail or scim_type,
    }, status=status)


# ----- shaping ------------------------------------------------------------


def _user_to_scim(u) -> dict[str, Any]:
    return {
        "schemas": [_USER_SCHEMA],
        "id": str(u.pk),
        "externalId": getattr(u, "username", "") or "",
        "userName": getattr(u, "username", "") or "",
        "name": {
            "givenName": getattr(u, "first_name", "") or "",
            "familyName": getattr(u, "last_name", "") or "",
            "formatted": (getattr(u, "get_full_name", lambda: "")() or "").strip(),
        },
        "displayName": (getattr(u, "get_full_name", lambda: "")() or "") or getattr(u, "username", ""),
        "emails": ([{
            "value": getattr(u, "email", "") or "",
            "primary": True,
            "type": "work",
        }] if getattr(u, "email", "") else []),
        "active": bool(getattr(u, "is_active", True)),
        "meta": {
            "resourceType": "User",
            "location": f"/scim/v2/Users/{u.pk}",
        },
    }


def _group_to_scim(g) -> dict[str, Any]:
    return {
        "schemas": [_GROUP_SCHEMA],
        "id": str(g.pk),
        "displayName": getattr(g, "name", "") or "",
        "members": [
            {"value": str(m.pk), "type": "User", "display": getattr(m, "username", "") or ""}
            for m in g.user_set.all()[:200]
        ],
        "meta": {
            "resourceType": "Group",
            "location": f"/scim/v2/Groups/{g.pk}",
        },
    }


# ----- filter parsing (subset: eq, co, sw, ew, pr) -----------------------


_FILTER_RE = re.compile(
    r"""^\s*(?P<attr>[A-Za-z][\w\.]*)\s+(?P<op>eq|co|sw|ew|pr)(?:\s+"(?P<val>[^"]*)")?\s*$""",
    re.IGNORECASE,
)

_USER_ATTR_MAP = {
    "username": "username",
    "username__exact": "username",
    "useremail": "email",
    "emails.value": "email",
    "active": "is_active",
    "name.givenname": "first_name",
    "name.familyname": "last_name",
    "displayname": "first_name",
}


def _apply_user_filter(qs, raw: str):
    if not raw:
        return qs, None
    m = _FILTER_RE.match(raw)
    if not m:
        return qs, f"unparseable_filter: {raw}"
    attr = _USER_ATTR_MAP.get(m.group("attr").lower())
    op = m.group("op").lower()
    val = m.group("val") or ""
    if not attr:
        return qs, f"unknown_attribute: {m.group('attr')}"
    if op == "eq":
        if attr == "is_active":
            return qs.filter(**{attr: val.lower() in ("true", "1", "yes")}), None
        return qs.filter(**{attr: val}), None
    if op == "co":
        return qs.filter(**{f"{attr}__icontains": val}), None
    if op == "sw":
        return qs.filter(**{f"{attr}__istartswith": val}), None
    if op == "ew":
        return qs.filter(**{f"{attr}__iendswith": val}), None
    if op == "pr":
        return qs.exclude(**{attr: ""}), None
    return qs, f"unsupported_operator: {op}"


def _paginate(request: HttpRequest, qs, total: int) -> tuple[list[Any], dict[str, int]]:
    try:
        start = int(request.GET.get("startIndex") or 1)
    except (ValueError, TypeError):
        start = 1
    try:
        count = int(request.GET.get("count") or 100)
    except (ValueError, TypeError):
        count = 100
    start = max(1, start)
    count = max(0, min(1000, count))
    items = list(qs[start - 1 : start - 1 + count]) if count else []
    return items, {"startIndex": start, "itemsPerPage": len(items), "totalResults": total}


# ----- payload extraction -------------------------------------------------


def _scim_body(request: HttpRequest) -> dict[str, Any] | None:
    try:
        if not request.body:
            return None
        return json.loads(request.body)
    except (ValueError, TypeError):
        return None


def _extract_user_fields(payload: dict[str, Any]) -> dict[str, str]:
    name = payload.get("name") or {}
    emails = payload.get("emails") or []
    primary_email = ""
    for e in emails:
        if isinstance(e, dict) and e.get("primary"):
            primary_email = str(e.get("value") or "")
            break
    if not primary_email and emails and isinstance(emails[0], dict):
        primary_email = str(emails[0].get("value") or "")
    return {
        "username": str(payload.get("userName") or "")[:150],
        "first_name": str(name.get("givenName") or "")[:150],
        "last_name": str(name.get("familyName") or "")[:150],
        "email": primary_email[:254],
        "is_active": payload.get("active") if "active" in payload else True,
    }


# ----- endpoints: Service Provider Config / Schemas / ResourceTypes ----


@require_http_methods(["GET"])
def service_provider_config(request):
    g = _gate(request)
    if g is not None:
        return g
    return _scim_response({
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "documentationUri": "https://runmycampus.com/docs/scim",
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 1000},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {"name": "Bearer Token", "description": "Authentication via HTTP Bearer token.", "specUri": "https://tools.ietf.org/html/rfc6750", "type": "oauthbearertoken"}
        ],
    })


@require_http_methods(["GET"])
def schemas(request):
    g = _gate(request)
    if g is not None:
        return g
    return _scim_response({
        "schemas": [_LIST_RESPONSE_SCHEMA],
        "totalResults": 2,
        "Resources": [
            {"id": _USER_SCHEMA, "name": "User", "description": "SCIM 2.0 User"},
            {"id": _GROUP_SCHEMA, "name": "Group", "description": "SCIM 2.0 Group"},
        ],
    })


@require_http_methods(["GET"])
def resource_types(request):
    g = _gate(request)
    if g is not None:
        return g
    return _scim_response({
        "schemas": [_LIST_RESPONSE_SCHEMA],
        "totalResults": 2,
        "Resources": [
            {"id": "User", "name": "User", "endpoint": "/Users", "schema": _USER_SCHEMA},
            {"id": "Group", "name": "Group", "endpoint": "/Groups", "schema": _GROUP_SCHEMA},
        ],
    })


# ----- Users --------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET", "POST"])
def users_collection(request):
    g = _gate(request)
    if g is not None:
        return g
    User = get_user_model()
    if request.method == "GET":
        qs = User.objects.all().order_by("pk")  # tenant-isolation-allow: scim-list-platform-scope-bearer-auth-required
        flt = request.GET.get("filter") or ""
        qs, err = _apply_user_filter(qs, flt)
        if err:
            return _scim_error(400, "invalidFilter", err)
        total = qs.count()
        items, page = _paginate(request, qs, total)
        return _scim_response({
            "schemas": [_LIST_RESPONSE_SCHEMA],
            "totalResults": page["totalResults"],
            "startIndex": page["startIndex"],
            "itemsPerPage": page["itemsPerPage"],
            "Resources": [_user_to_scim(u) for u in items],
        })

    payload = _scim_body(request)
    if not payload:
        return _scim_error(400, "invalidSyntax", "bad json")
    fields = _extract_user_fields(payload)
    if not fields["username"]:
        return _scim_error(400, "invalidValue", "userName required")
    if User.objects.filter(username=fields["username"]).exists():  # tenant-isolation-allow: scim-collision-check-platform
        return _scim_error(409, "uniqueness", "userName already exists")
    obj = User.objects.create_user(  # tenant-isolation-allow: scim-create-platform
        username=fields["username"],
        email=fields["email"],
        first_name=fields["first_name"],
        last_name=fields["last_name"],
    )
    if fields["is_active"] is False:
        obj.is_active = False
        obj.save(update_fields=["is_active"])
    return _scim_response(_user_to_scim(obj), status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
def user_detail(request, user_id: str):
    g = _gate(request)
    if g is not None:
        return g
    User = get_user_model()
    obj = User.objects.filter(pk=user_id).first()  # tenant-isolation-allow: scim-detail-platform
    if obj is None:
        return _scim_error(404, "notFound", f"user_id={user_id}")
    if request.method == "GET":
        return _scim_response(_user_to_scim(obj))
    if request.method == "PUT":
        payload = _scim_body(request)
        if not payload:
            return _scim_error(400, "invalidSyntax", "bad json")
        fields = _extract_user_fields(payload)
        for field, raw in fields.items():
            if field == "is_active":
                obj.is_active = bool(raw) if raw is not None else obj.is_active
                continue
            if raw is None:
                continue
            if hasattr(obj, field):
                setattr(obj, field, raw)
        obj.save()
        return _scim_response(_user_to_scim(obj))
    if request.method == "PATCH":
        payload = _scim_body(request)
        if not isinstance(payload, dict):
            return _scim_error(400, "invalidSyntax", "bad json")
        ops = payload.get("Operations") or []
        if not isinstance(ops, list):
            return _scim_error(400, "invalidSyntax", "Operations must be a list")
        changed = False
        for op in ops:
            if not isinstance(op, dict):
                continue
            opname = str(op.get("op") or "").lower()
            path = str(op.get("path") or "").strip()
            value = op.get("value")
            if opname in ("add", "replace"):
                if path == "active" or path.lower() == "active":
                    obj.is_active = bool(value)
                    changed = True
                elif path.lower() in ("username", "username"):
                    obj.username = str(value)[:150]
                    changed = True
                elif path.lower() in ("name.givenname",):
                    obj.first_name = str(value)[:150]
                    changed = True
                elif path.lower() in ("name.familyname",):
                    obj.last_name = str(value)[:150]
                    changed = True
                elif path.lower().startswith("emails"):
                    if isinstance(value, list) and value:
                        first = value[0]
                        if isinstance(first, dict):
                            obj.email = str(first.get("value") or "")[:254]
                            changed = True
                    elif isinstance(value, str):
                        obj.email = value[:254]
                        changed = True
                elif not path and isinstance(value, dict):
                    # PATCH without path → apply nested replace
                    fields = _extract_user_fields(value)
                    for k, v in fields.items():
                        if v is None:
                            continue
                        if k == "is_active":
                            obj.is_active = bool(v)
                        elif hasattr(obj, k):
                            setattr(obj, k, v)
                    changed = True
            elif opname == "remove":
                if path.lower() == "active":
                    obj.is_active = False
                    changed = True
        if changed:
            obj.save()
        return _scim_response(_user_to_scim(obj))
    # DELETE
    obj.is_active = False
    obj.save(update_fields=["is_active"])
    resp = JsonResponse({}, status=204)
    resp["Content-Type"] = _SCIM_CT
    return resp


# ----- Groups -------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET", "POST"])
def groups_collection(request):
    g = _gate(request)
    if g is not None:
        return g
    if request.method == "GET":
        qs = Group.objects.all().order_by("pk")
        flt = (request.GET.get("filter") or "").strip()
        if flt:
            m = _FILTER_RE.match(flt)
            if m and m.group("attr").lower() in ("displayname", "name") and m.group("op").lower() == "eq":
                qs = qs.filter(name=m.group("val") or "")
            elif m and m.group("op").lower() == "co":
                qs = qs.filter(name__icontains=m.group("val") or "")
            else:
                return _scim_error(400, "invalidFilter", flt)
        total = qs.count()
        items, page = _paginate(request, qs, total)
        return _scim_response({
            "schemas": [_LIST_RESPONSE_SCHEMA],
            "totalResults": page["totalResults"],
            "startIndex": page["startIndex"],
            "itemsPerPage": page["itemsPerPage"],
            "Resources": [_group_to_scim(g) for g in items],
        })
    payload = _scim_body(request)
    if not payload:
        return _scim_error(400, "invalidSyntax", "bad json")
    name = str(payload.get("displayName") or "").strip()[:150]
    if not name:
        return _scim_error(400, "invalidValue", "displayName required")
    obj, created = Group.objects.get_or_create(name=name)
    members = payload.get("members") or []
    if isinstance(members, list) and members:
        User = get_user_model()
        member_ids = [m.get("value") for m in members if isinstance(m, dict)]
        users = User.objects.filter(pk__in=member_ids)
        obj.user_set.set(users)
    return _scim_response(_group_to_scim(obj), status=201 if created else 200)


@csrf_exempt
@require_http_methods(["GET"])
def group_detail(request, group_id: str):
    g = _gate(request)
    if g is not None:
        return g
    obj = Group.objects.filter(pk=group_id).first()
    if obj is None:
        return _scim_error(404, "notFound", f"group_id={group_id}")
    return _scim_response(_group_to_scim(obj))
