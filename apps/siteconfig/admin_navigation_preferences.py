"""Server-owned navigation preferences for Django admin surfaces.

The browser may keep a retry envelope while offline, but the application
database is authoritative.  Preferences are isolated by authenticated user,
hostname and admin-site instance so a shared browser cannot leak tenant links
or operator state into another workspace.
"""

from __future__ import annotations

from hashlib import sha256
import json
import logging
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import DatabaseError, transaction
from django.http import HttpRequest, JsonResponse
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods


logger = logging.getLogger(__name__)

PREFERENCE_NAMESPACE = "_rmc_admin_navigation_v1"
MAX_PREFERENCE_PAYLOAD_BYTES = 32 * 1024
MAX_SCOPES_PER_USER = 80
MAX_PINNED_ITEMS = 8
MAX_RECENT_ITEMS = 10
MAX_LABEL_LENGTH = 100
MAX_PATH_LENGTH = 600

DEFAULT_STATE: dict[str, Any] = {
    "pinned": [],
    "recent": [],
    "compact": False,
    "advancedOpen": False,
    "appsOpen": False,
}
BOOLEAN_KEYS = frozenset({"compact", "advancedOpen", "appsOpen"})


def _safe_host(request: HttpRequest) -> str:
    try:
        host = request.get_host()
    except Exception:  # malformed/untrusted Host must never share a real scope
        host = "invalid-host"
    return host.strip().lower()[:255] or "unknown-host"


def _scope_key(*, host: str, admin_site_name: str) -> str:
    return f"{host.strip().lower()[:255]}|{admin_site_name.strip().lower()[:64]}"


def _public_scope_id(scope_key: str) -> str:
    return "nav-" + sha256(scope_key.encode("utf-8")).hexdigest()[:20]


def _clean_label(value: Any, *, strict: bool) -> str:
    if strict and not isinstance(value, str):
        raise ValidationError("Navigation labels must be strings.")
    label = " ".join(str(value or "").split()).strip()
    if not label:
        if strict:
            raise ValidationError("Navigation labels cannot be empty.")
        return ""
    return label[:MAX_LABEL_LENGTH]


def _clean_admin_path(value: Any, *, strict: bool) -> str:
    if strict and not isinstance(value, str):
        raise ValidationError("Navigation paths must be strings.")
    raw = str(value or "").strip()
    if not raw or len(raw) > MAX_PATH_LENGTH or any(ch in raw for ch in "\r\n\x00"):
        if strict:
            raise ValidationError("Navigation paths are missing or too long.")
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/admin/"):
        if strict:
            raise ValidationError("Only same-host Django admin paths can be saved.")
        return ""
    return urlunsplit(("", "", parsed.path, parsed.query, ""))[:MAX_PATH_LENGTH]


def _clean_entries(value: Any, *, limit: int, strict: bool) -> list[dict[str, str]]:
    if not isinstance(value, list):
        if strict:
            raise ValidationError("Navigation entries must be a list.")
        return []
    if strict and len(value) > limit:
        raise ValidationError(f"At most {limit} navigation entries are allowed.")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value[:limit]:
        if not isinstance(raw, Mapping):
            if strict:
                raise ValidationError("Each navigation entry must be an object.")
            continue
        path = _clean_admin_path(raw.get("path"), strict=strict)
        label = _clean_label(raw.get("label"), strict=strict)
        if not path or not label or path in seen:
            continue
        seen.add(path)
        result.append({"path": path, "label": label})
    return result


def normalize_navigation_state(value: Any, *, strict: bool) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        if strict:
            raise ValidationError("Navigation preferences must be an object.")
        value = {}
    if strict:
        unknown = sorted(set(value) - (BOOLEAN_KEYS | {"pinned", "recent"}))
        if unknown:
            raise ValidationError(
                f"Unknown navigation preference keys: {', '.join(unknown[:10])}."
            )
    state = dict(DEFAULT_STATE)
    state["pinned"] = _clean_entries(
        value.get("pinned", []), limit=MAX_PINNED_ITEMS, strict=strict
    )
    state["recent"] = _clean_entries(
        value.get("recent", []), limit=MAX_RECENT_ITEMS, strict=strict
    )
    for key in BOOLEAN_KEYS:
        raw = value.get(key, False)
        if strict and not isinstance(raw, bool):
            raise ValidationError(f"{key} must be a JSON boolean.")
        state[key] = raw if isinstance(raw, bool) else False
    return state


class AdminNavigationPreferenceService:
    """Read and atomically persist one user's host-scoped navigation state."""

    @staticmethod
    def _preference_model():
        from apps.siteconfig.models_dashboard import DashboardUserPreference

        return DashboardUserPreference

    @classmethod
    def read(cls, *, user, scope_key: str) -> dict[str, Any]:
        if not getattr(user, "is_authenticated", False):
            return dict(DEFAULT_STATE)
        try:
            preference = cls._preference_model().objects.filter(user=user).only(
                "dashboard_layout"
            ).first()
        except DatabaseError:
            logger.warning("admin navigation preferences unavailable", exc_info=True)
            return dict(DEFAULT_STATE)
        layout = preference.dashboard_layout if preference else {}
        namespace = layout.get(PREFERENCE_NAMESPACE, {}) if isinstance(layout, dict) else {}
        stored = namespace.get(scope_key, {}) if isinstance(namespace, dict) else {}
        return normalize_navigation_state(stored, strict=False)

    @classmethod
    def write(cls, *, user, scope_key: str, state: Any) -> dict[str, Any]:
        if not getattr(user, "is_authenticated", False):
            raise ValidationError("Authentication is required.")
        normalized = normalize_navigation_state(state, strict=True)
        Preference = cls._preference_model()
        with transaction.atomic():
            preference, _ = Preference.objects.select_for_update().get_or_create(user=user)
            stored_layout = preference.dashboard_layout
            layout = dict(stored_layout) if isinstance(stored_layout, Mapping) else {}
            stored_namespace = layout.get(PREFERENCE_NAMESPACE)
            namespace = (
                dict(stored_namespace) if isinstance(stored_namespace, Mapping) else {}
            )
            namespace[scope_key] = {
                **normalized,
                "updated_at": timezone.now().isoformat(),
            }
            if len(namespace) > MAX_SCOPES_PER_USER:
                namespace = dict(
                    sorted(
                        namespace.items(),
                        key=lambda item: str(
                            item[1].get("updated_at", "")
                            if isinstance(item[1], Mapping)
                            else ""
                        ),
                        reverse=True,
                    )[:MAX_SCOPES_PER_USER]
                )
            layout[PREFERENCE_NAMESPACE] = namespace
            preference.dashboard_layout = layout
            preference.save(update_fields=["dashboard_layout", "updated_at"])
        logger.info(
            "admin_navigation_preferences_saved user=%s scope=%s pinned=%s recent=%s",
            getattr(user, "pk", None),
            _public_scope_id(scope_key),
            len(normalized["pinned"]),
            len(normalized["recent"]),
        )
        return normalized


def build_admin_navigation_contract(request: HttpRequest, admin_site) -> dict[str, Any]:
    scope_key = _scope_key(host=_safe_host(request), admin_site_name=admin_site.name)
    user = getattr(request, "user", None)
    browser_scope_key = (
        f"{scope_key}|user:{getattr(user, 'pk', 'anonymous')}"
    )
    try:
        endpoint = reverse(
            f"{admin_site.name}:navigation_preferences",
            urlconf=getattr(request, "urlconf", None),
        )
    except NoReverseMatch:
        endpoint = ""
    return {
        "version": 1,
        "scope": _public_scope_id(browser_scope_key),
        "endpoint": endpoint,
        "preferences": AdminNavigationPreferenceService.read(
            user=user, scope_key=scope_key
        ),
        "limits": {"pinned": MAX_PINNED_ITEMS, "recent": MAX_RECENT_ITEMS},
    }


@require_http_methods(["GET", "POST"])
def admin_navigation_preferences_view(
    request: HttpRequest, *, admin_site
) -> JsonResponse:
    """Read or replace the active user's validated navigation preferences."""

    scope_key = _scope_key(host=_safe_host(request), admin_site_name=admin_site.name)
    if request.method == "GET":
        return JsonResponse(
            {
                "ok": True,
                "preferences": AdminNavigationPreferenceService.read(
                    user=request.user, scope_key=scope_key
                ),
            }
        )
    try:
        raw_body = request.body
        if len(raw_body) > MAX_PREFERENCE_PAYLOAD_BYTES:
            return JsonResponse(
                {"ok": False, "error": "The navigation preference payload is too large."},
                status=413,
            )
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except RequestDataTooBig:
        return JsonResponse(
            {"ok": False, "error": "The navigation preference payload is too large."},
            status=413,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid JSON payload."}, status=400)
    if not isinstance(payload, Mapping):
        return JsonResponse(
            {"ok": False, "error": "The request payload must be an object."},
            status=400,
        )
    try:
        state = AdminNavigationPreferenceService.write(
            user=request.user,
            scope_key=scope_key,
            state=payload.get("preferences"),
        )
    except ValidationError as exc:
        return JsonResponse(
            {"ok": False, "error": "; ".join(exc.messages)}, status=400
        )
    except DatabaseError:
        logger.exception("admin navigation preference write failed")
        return JsonResponse(
            {"ok": False, "error": "Navigation preferences could not be saved."},
            status=503,
        )
    return JsonResponse({"ok": True, "preferences": state})
