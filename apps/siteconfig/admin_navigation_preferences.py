"""Revisioned, server-owned Django-admin navigation preferences.

The API accepts semantic mutations rather than stale whole-state snapshots.
Every mutation is scoped by user, normalized hostname and admin-site namespace;
compare-and-swap revisions make multiple tabs and offline replay deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import logging
import re
from time import monotonic
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

from django.core import signing
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import DatabaseError, transaction
from django.http import HttpRequest, JsonResponse
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.siteconfig.admin_navigation_contracts import (
    AdminDestination,
    AdminNavigationContext,
    build_navigation_context,
)


logger = logging.getLogger(__name__)

PREFERENCE_NAMESPACE = "_rmc_admin_navigation_v1"  # migration/read compatibility
CONTRACT_VERSION = 3
MAX_PREFERENCE_PAYLOAD_BYTES = 32 * 1024
MAX_PINNED_ITEMS = 8
MAX_RECENT_ITEMS = 10
MAX_DISMISSED_RECOMMENDATIONS = 40
MAX_EXPANSIONS = 40
MAX_MUTATION_HISTORY = 64
MAX_LABEL_LENGTH = 120
MAX_PATH_LENGTH = 600
_MUTATION_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")
_EXPANSION_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_PAGE_DESTINATION_SALT = "rmc.admin-navigation.page-destination.v3"

DEFAULT_STATE: dict[str, Any] = {
    "pinned": [],
    "recent": [],
    "mode": "expanded",
    "focus": False,
    "expansions": {},
    "dismissedRecommendations": [],
}


def _safe_host_value(value: object) -> str:
    raw = str(value or "").strip().lower().rstrip(".")
    try:
        host = urlsplit(f"//{raw}").hostname or "unknown-host"
    except ValueError:
        host = "invalid-host"
    return host[:255]


def _safe_host(request: HttpRequest) -> str:
    try:
        return _safe_host_value(request.get_host())
    except Exception:  # malformed/untrusted Host must never share a real scope
        return "invalid-host"


def _scope_key(*, host: str, admin_site_name: str) -> str:
    return f"{_safe_host_value(host)}|{str(admin_site_name).strip().lower()[:64]}"


def _split_scope_key(scope_key: str) -> tuple[str, str]:
    host, separator, admin_site = str(scope_key or "").rpartition("|")
    if not separator:
        raise ValidationError("Navigation preference scope is invalid.")
    return _safe_host_value(host), admin_site.strip().lower()[:64]


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


def _clean_internal_path(value: Any, *, strict: bool, admin_only: bool = False) -> str:
    if strict and not isinstance(value, str):
        raise ValidationError("Navigation paths must be strings.")
    raw = str(value or "").strip()
    if not raw or len(raw) > MAX_PATH_LENGTH or any(ch in raw for ch in "\r\n\x00"):
        if strict:
            raise ValidationError("Navigation paths are missing or too long.")
        return ""
    parsed = urlsplit(raw)
    valid_root = parsed.path.startswith("/admin/") if admin_only else parsed.path.startswith("/")
    if parsed.scheme or parsed.netloc or not valid_root:
        if strict:
            raise ValidationError("Only permitted same-host paths can be saved.")
        return ""
    return urlunsplit(("", "", parsed.path, parsed.query, ""))[:MAX_PATH_LENGTH]


def _legacy_destination_id(path: str) -> str:
    return "legacy:" + sha256(path.encode("utf-8")).hexdigest()[:20]


def _clean_entry(value: Any, *, strict: bool, admin_only: bool = False) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        if strict:
            raise ValidationError("Each navigation entry must be an object.")
        return None
    path = _clean_internal_path(value.get("path"), strict=strict, admin_only=admin_only)
    label = _clean_label(value.get("label"), strict=strict)
    destination_id = str(value.get("id") or "").strip()[:180]
    if not path or not label:
        return None
    return {"id": destination_id or _legacy_destination_id(path), "path": path, "label": label}


def _clean_entries(value: Any, *, limit: int, strict: bool, admin_only: bool = False) -> list[dict[str, str]]:
    if not isinstance(value, list):
        if strict:
            raise ValidationError("Navigation entries must be a list.")
        return []
    if strict and len(value) > limit:
        raise ValidationError(f"At most {limit} navigation entries are allowed.")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value[:limit]:
        entry = _clean_entry(raw, strict=strict, admin_only=admin_only)
        if not entry or entry["id"] in seen:
            continue
        seen.add(entry["id"])
        result.append(entry)
    return result


def normalize_navigation_state(value: Any, *, strict: bool) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        if strict:
            raise ValidationError("Navigation preferences must be an object.")
        value = {}
    allowed = set(DEFAULT_STATE) | {"compact", "advancedOpen", "appsOpen", "updated_at"}
    if strict:
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValidationError(f"Unknown navigation preference keys: {', '.join(unknown[:10])}.")
    state = dict(DEFAULT_STATE)
    state["pinned"] = _clean_entries(value.get("pinned", []), limit=MAX_PINNED_ITEMS, strict=strict, admin_only=strict)
    state["recent"] = _clean_entries(value.get("recent", []), limit=MAX_RECENT_ITEMS, strict=strict, admin_only=strict)
    mode = value.get("mode", "compact" if value.get("compact") else "expanded")
    if strict and mode not in {"expanded", "compact"}:
        raise ValidationError("mode must be expanded or compact.")
    state["mode"] = mode if mode in {"expanded", "compact"} else "expanded"
    focus = value.get("focus", False)
    if strict and not isinstance(focus, bool):
        raise ValidationError("focus must be a JSON boolean.")
    state["focus"] = focus if isinstance(focus, bool) else False
    expansions = value.get("expansions", {})
    if not isinstance(expansions, Mapping):
        if strict:
            raise ValidationError("expansions must be an object.")
        expansions = {}
    cleaned_expansions: dict[str, bool] = {}
    for key, expanded in list(expansions.items())[:MAX_EXPANSIONS]:
        key = str(key)
        if _EXPANSION_KEY.fullmatch(key) and isinstance(expanded, bool):
            cleaned_expansions[key] = expanded
    if "advancedOpen" in value:
        cleaned_expansions.setdefault("advanced", bool(value.get("advancedOpen")))
    if "appsOpen" in value:
        cleaned_expansions.setdefault("models", bool(value.get("appsOpen")))
    state["expansions"] = cleaned_expansions
    dismissed = value.get("dismissedRecommendations", [])
    if not isinstance(dismissed, list):
        if strict:
            raise ValidationError("dismissedRecommendations must be a list.")
        dismissed = []
    state["dismissedRecommendations"] = [
        str(item)[:180]
        for item in dismissed[:MAX_DISMISSED_RECOMMENDATIONS]
        if isinstance(item, str) and item.strip()
    ]
    return state


def _entry_from_destination(destination: AdminDestination) -> dict[str, str]:
    return {"id": destination.id, "path": destination.path, "label": destination.label}


def _resolve_entries(state: Mapping[str, Any], registry: Mapping[str, AdminDestination]) -> dict[str, Any]:
    resolved = normalize_navigation_state(state, strict=False)
    by_path = {item.path: item for item in registry.values()}
    for key in ("pinned", "recent"):
        entries: list[dict[str, str]] = []
        seen: set[str] = set()
        for entry in resolved[key]:
            destination = registry.get(entry["id"]) or by_path.get(entry["path"])
            # Missing registry entries are preserved in the database as
            # diagnostics but never returned to a browser after permissions or
            # routing change. Stable IDs make this fail-closed without erasing
            # evidence needed to investigate a removed destination.
            if destination and destination.id not in seen:
                seen.add(destination.id)
                entries.append(_entry_from_destination(destination))
        resolved[key] = entries
    return resolved


def _canonicalize_saved_entries(
    state: Mapping[str, Any], registry: Mapping[str, AdminDestination]
) -> dict[str, Any]:
    """Upgrade legacy path identities while retaining unavailable diagnostics."""

    canonical = normalize_navigation_state(state, strict=False)
    by_path = {item.path: item for item in registry.values()}
    for key in ("pinned", "recent"):
        entries: list[dict[str, str]] = []
        seen: set[str] = set()
        for entry in canonical[key]:
            destination = registry.get(entry["id"]) or by_path.get(entry["path"])
            value = _entry_from_destination(destination) if destination else entry
            if value["id"] not in seen:
                seen.add(value["id"])
                entries.append(value)
        canonical[key] = entries
    return canonical


def _legacy_view_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the exact v1 shape to callers still using ``read``/POST."""
    normalized = normalize_navigation_state(state, strict=False)
    return {
        "pinned": [{"path": item["path"], "label": item["label"]} for item in normalized["pinned"]],
        "recent": [{"path": item["path"], "label": item["label"]} for item in normalized["recent"]],
        "compact": normalized["mode"] == "compact",
        "advancedOpen": bool(normalized["expansions"].get("advanced")),
        "appsOpen": bool(normalized["expansions"].get("models")),
    }


@dataclass(slots=True)
class NavigationRevisionConflict(Exception):
    expected_revision: int
    actual_revision: int
    state: Mapping[str, Any]


class AdminNavigationPreferenceService:
    """Read, migrate and atomically mutate one navigation scope."""

    @staticmethod
    def _preference_model():
        from apps.siteconfig.models_dashboard import AdminNavigationPreference

        return AdminNavigationPreference

    @staticmethod
    def _legacy_model():
        from apps.siteconfig.models_dashboard import DashboardUserPreference

        return DashboardUserPreference

    @classmethod
    def _legacy_state(cls, *, user, host: str, admin_site: str) -> dict[str, Any] | None:
        # Same savepoint contract as read_envelope below: this runs AFTER that
        # read on the fallback path, so without its own savepoint it is the
        # second query to die on an already-aborted Postgres transaction.
        try:
            with transaction.atomic(savepoint=True):
                legacy = cls._legacy_model().objects.filter(user=user).only("dashboard_layout").first()
        except DatabaseError:
            return None
        layout = legacy.dashboard_layout if legacy else {}
        namespace = layout.get(PREFERENCE_NAMESPACE, {}) if isinstance(layout, dict) else {}
        raw = namespace.get(_scope_key(host=host, admin_site_name=admin_site)) if isinstance(namespace, dict) else None
        return normalize_navigation_state(raw, strict=False) if isinstance(raw, Mapping) else None

    @classmethod
    def _get_or_create_locked(cls, *, user, host: str, admin_site: str):
        Preference = cls._preference_model()
        preference, created = Preference.objects.select_for_update().get_or_create(
            user=user,
            host=host,
            admin_site=admin_site,
            defaults={"schema_version": CONTRACT_VERSION, "state": dict(DEFAULT_STATE)},
        )
        if created:
            legacy = cls._legacy_state(user=user, host=host, admin_site=admin_site)
            if legacy:
                preference.state = legacy
                preference.revision = 1
                preference.save(update_fields=["state", "revision", "updated_at"])
        return preference

    @classmethod
    def read_envelope(cls, *, user, host: str, admin_site: str) -> dict[str, Any]:
        if not getattr(user, "is_authenticated", False):
            return {"revision": 0, "state": dict(DEFAULT_STATE)}
        host = _safe_host_value(host)
        admin_site = str(admin_site).strip().lower()[:64]
        # savepoint=True is load-bearing, not decoration. Catching a database
        # error does NOT make the connection usable again on PostgreSQL: the
        # transaction stays aborted and EVERY later query raises
        # InFailedSqlTransaction, so swallowing this read turns one missing
        # table into a 500 further down the request. SQLite does not behave
        # that way, which is exactly why this survived local testing: the
        # admin add page renders 200 on SQLite and dies on Postgres. Rolling
        # back to a savepoint is what actually lets the request continue.
        try:
            with transaction.atomic(savepoint=True):
                preference = cls._preference_model().objects.filter(user=user, host=host, admin_site=admin_site).only("revision", "state").first()
        except DatabaseError:
            logger.warning("admin navigation preferences unavailable", exc_info=True)
            return {"revision": 0, "state": dict(DEFAULT_STATE)}
        if preference:
            return {"revision": int(preference.revision), "state": normalize_navigation_state(preference.state, strict=False)}
        legacy = cls._legacy_state(user=user, host=host, admin_site=admin_site)
        return {"revision": 0, "state": legacy or dict(DEFAULT_STATE)}

    @classmethod
    def read(cls, *, user, scope_key: str) -> dict[str, Any]:
        host, admin_site = _split_scope_key(scope_key)
        return _legacy_view_state(
            cls.read_envelope(user=user, host=host, admin_site=admin_site)["state"]
        )

    @classmethod
    def write(cls, *, user, scope_key: str, state: Any) -> dict[str, Any]:
        """Compatibility replacement for the v1 API; new clients use ``mutate``."""
        if not getattr(user, "is_authenticated", False):
            raise ValidationError("Authentication is required.")
        host, admin_site = _split_scope_key(scope_key)
        normalized = normalize_navigation_state(state, strict=True)
        with transaction.atomic():
            preference = cls._get_or_create_locked(user=user, host=host, admin_site=admin_site)
            preference.state = normalized
            preference.revision = int(preference.revision) + 1
            preference.schema_version = CONTRACT_VERSION
            preference.save(update_fields=["state", "revision", "schema_version", "updated_at"])
        return _legacy_view_state(normalized)

    @classmethod
    def mutate(
        cls,
        *,
        user,
        host: str,
        admin_site: str,
        expected_revision: int,
        mutation: Mapping[str, Any],
        destinations: Sequence[AdminDestination],
        recommendation_ids: set[str],
    ) -> dict[str, Any]:
        started_at = monotonic()
        if not getattr(user, "is_authenticated", False):
            raise ValidationError("Authentication is required.")
        mutation_id = str(mutation.get("id") or "")
        mutation_type = str(mutation.get("type") or "")
        payload = mutation.get("payload", {})
        if not _MUTATION_ID.fullmatch(mutation_id):
            raise ValidationError("A valid mutation id is required.")
        if not isinstance(payload, Mapping):
            raise ValidationError("Mutation payload must be an object.")
        try:
            expected_revision = int(expected_revision)
        except (TypeError, ValueError) as exc:
            raise ValidationError("expected_revision must be an integer.") from exc
        host = _safe_host_value(host)
        admin_site = str(admin_site).strip().lower()[:64]
        registry = {item.id: item for item in destinations}
        with transaction.atomic():
            preference = cls._get_or_create_locked(user=user, host=host, admin_site=admin_site)
            applied = [str(value) for value in (preference.applied_mutation_ids or []) if isinstance(value, str)]
            current = _canonicalize_saved_entries(preference.state, registry)
            if mutation_id in applied:
                return {"revision": int(preference.revision), "state": _resolve_entries(current, registry), "duplicate": True}
            if expected_revision != int(preference.revision):
                raise NavigationRevisionConflict(expected_revision, int(preference.revision), _resolve_entries(current, registry))
            updated = cls._apply_mutation(
                current,
                mutation_type=mutation_type,
                payload=payload,
                registry=registry,
                recommendation_ids=recommendation_ids,
            )
            preference.state = updated
            preference.revision = int(preference.revision) + 1
            preference.schema_version = CONTRACT_VERSION
            preference.applied_mutation_ids = (applied + [mutation_id])[-MAX_MUTATION_HISTORY:]
            preference.save(update_fields=["state", "revision", "schema_version", "applied_mutation_ids", "updated_at"])
        logger.info(
            "admin_navigation_mutated scope=%s mutation=%s revision=%s duration_ms=%s",
            _public_scope_id(_scope_key(host=host, admin_site_name=admin_site)),
            mutation_type,
            preference.revision,
            round((monotonic() - started_at) * 1000, 2),
        )
        return {"revision": int(preference.revision), "state": _resolve_entries(updated, registry), "duplicate": False}

    @classmethod
    def _apply_mutation(
        cls,
        state: Mapping[str, Any],
        *,
        mutation_type: str,
        payload: Mapping[str, Any],
        registry: Mapping[str, AdminDestination],
        recommendation_ids: set[str],
    ) -> dict[str, Any]:
        updated = normalize_navigation_state(state, strict=False)
        destination_id = str(payload.get("destinationId") or "")[:180]
        if mutation_type in {"pin", "remember_recent"}:
            destination = registry.get(destination_id)
            if destination is None:
                raise ValidationError("The destination is unavailable or not permitted.")
            key = "pinned" if mutation_type == "pin" else "recent"
            limit = MAX_PINNED_ITEMS if key == "pinned" else MAX_RECENT_ITEMS
            entries = [entry for entry in updated[key] if entry["id"] != destination_id]
            if mutation_type == "pin" and len(entries) >= limit:
                raise ValidationError(f"At most {limit} pinned destinations are allowed.")
            entry = _entry_from_destination(destination)
            updated[key] = ([entry] + entries)[:limit] if key == "recent" else (entries + [entry])[:limit]
        elif mutation_type == "unpin":
            updated["pinned"] = [entry for entry in updated["pinned"] if entry["id"] != destination_id]
        elif mutation_type == "move_pin":
            try:
                index = int(payload.get("index"))
            except (TypeError, ValueError) as exc:
                raise ValidationError("Pin position must be an integer.") from exc
            entries = list(updated["pinned"])
            current_index = next((i for i, item in enumerate(entries) if item["id"] == destination_id), -1)
            if current_index < 0:
                raise ValidationError("Only an existing pin can be moved.")
            entry = entries.pop(current_index)
            entries.insert(max(0, min(index, len(entries))), entry)
            updated["pinned"] = entries
        elif mutation_type == "clear_recent":
            updated["recent"] = []
        elif mutation_type == "set_mode":
            mode = str(payload.get("mode") or "")
            if mode not in {"expanded", "compact"}:
                raise ValidationError("mode must be expanded or compact.")
            updated["mode"] = mode
        elif mutation_type == "set_focus":
            enabled = payload.get("enabled")
            if not isinstance(enabled, bool):
                raise ValidationError("Focus state must be a JSON boolean.")
            updated["focus"] = enabled
        elif mutation_type == "set_expansion":
            key = str(payload.get("key") or "")
            expanded = payload.get("expanded")
            if not _EXPANSION_KEY.fullmatch(key) or not isinstance(expanded, bool):
                raise ValidationError("Expansion state is invalid.")
            expansions = dict(updated["expansions"])
            expansions[key] = expanded
            updated["expansions"] = dict(list(expansions.items())[-MAX_EXPANSIONS:])
        elif mutation_type == "dismiss_recommendation":
            recommendation_id = str(payload.get("recommendationId") or "")[:180]
            if recommendation_id not in recommendation_ids:
                raise ValidationError("The recommendation is unavailable.")
            values = [value for value in updated["dismissedRecommendations"] if value != recommendation_id]
            updated["dismissedRecommendations"] = (values + [recommendation_id])[-MAX_DISMISSED_RECOMMENDATIONS:]
        elif mutation_type == "reset":
            updated = dict(DEFAULT_STATE)
        else:
            raise ValidationError("Unsupported navigation mutation type.")
        return normalize_navigation_state(updated, strict=False)


def _context_registry(context: AdminNavigationContext) -> tuple[AdminDestination, ...]:
    destinations = list(context.destinations)
    if context.page.destination_id not in {item.id for item in destinations}:
        destinations.append(
            AdminDestination(
                id=context.page.destination_id,
                label=context.page.title,
                path=context.page.path,
                group="Current page",
                kind="record" if context.page.object_id else "page",
            )
        )
    return tuple(destinations)


def _page_destination_token(*, request: HttpRequest, site: str, destination: AdminDestination) -> str:
    return signing.dumps(
        {
            "user": getattr(getattr(request, "user", None), "pk", None),
            "host": _safe_host(request),
            "site": site,
            "id": destination.id,
            "label": destination.label,
            "path": destination.path,
            "group": destination.group,
            "kind": destination.kind,
        },
        salt=_PAGE_DESTINATION_SALT,
        compress=True,
    )


def _destination_from_token(*, request: HttpRequest, site: str, token: object) -> AdminDestination:
    try:
        value = signing.loads(str(token or ""), salt=_PAGE_DESTINATION_SALT, max_age=86400)
    except signing.BadSignature as exc:
        raise ValidationError("The page destination token is invalid or expired.") from exc
    expected = {
        "user": getattr(getattr(request, "user", None), "pk", None),
        "host": _safe_host(request),
        "site": site,
    }
    if not isinstance(value, Mapping) or any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise ValidationError("The page destination token belongs to another admin scope.")
    path = _clean_internal_path(value.get("path"), strict=True, admin_only=True)
    label = _clean_label(value.get("label"), strict=True)
    destination_id = str(value.get("id") or "")[:180]
    if not destination_id:
        raise ValidationError("The page destination token is incomplete.")
    return AdminDestination(
        id=destination_id,
        label=label,
        path=path,
        group=str(value.get("group") or "Current page")[:100],
        kind=str(value.get("kind") or "page")[:30],
    )


def build_admin_navigation_contract(request: HttpRequest, admin_site, *, available_apps=None) -> dict[str, Any]:
    context = build_navigation_context(request, admin_site, available_apps=available_apps)
    host = _safe_host(request)
    site = str(admin_site.name)
    user = getattr(request, "user", None)
    envelope = AdminNavigationPreferenceService.read_envelope(user=user, host=host, admin_site=site)
    registry = {item.id: item for item in _context_registry(context)}
    state = _resolve_entries(envelope["state"], registry)
    dismissed = set(state["dismissedRecommendations"])
    try:
        endpoint = reverse(f"{site}:navigation_preferences", urlconf=getattr(request, "urlconf", None))
    except NoReverseMatch:
        endpoint = ""
    browser_scope = f"{_scope_key(host=host, admin_site_name=site)}|user:{getattr(user, 'pk', 'anonymous')}"
    page_payload = context.page.serialize()
    current_destination = registry.get(context.page.destination_id)
    if current_destination:
        page_payload["pinToken"] = _page_destination_token(
            request=request, site=site, destination=current_destination
        )
    return {
        "version": CONTRACT_VERSION,
        "scope": _public_scope_id(browser_scope),
        "hostKind": context.host_kind,
        "adminSite": context.admin_site,
        "context": {
            "tenantId": context.tenant_id,
            "effectiveRole": context.effective_role,
            "permissionCount": len(context.permissions),
            "permissionDigest": sha256("\n".join(context.permissions).encode("utf-8")).hexdigest()[:16],
            "pageArchetype": context.page.archetype,
        },
        "endpoint": endpoint,
        "revision": envelope["revision"],
        "preferences": state,
        "destinations": [item.serialize() for item in context.destinations],
        "workAreas": list(context.work_areas),
        "page": page_payload,
        "recommendations": [item.serialize() for item in context.recommendations if item.id not in dismissed],
        "limits": {"pinned": MAX_PINNED_ITEMS, "recent": MAX_RECENT_ITEMS},
        "strings": {
            "localReady": _("Local ready"),
            "offlineReady": _("Offline changes queued"),
            "syncing": _("Saving navigation"),
            "conflict": _("Navigation changed in another tab; rebasing"),
            "saveFailed": _("Navigation could not be saved"),
            "noResults": _("No permitted destinations match your search."),
            "pinFull": _("Pinned is full (%(limit)s).") % {"limit": MAX_PINNED_ITEMS},
            "commandTitle": _("Admin command palette"),
            "commandSubtitle": _("Permission-aware pages, records and actions"),
            "searchPlaceholder": _("Search pages, records and actions…"),
            "actions": _("Actions"),
            "records": _("Records"),
            "pages": _("Pages"),
            "pin": _("Pin"),
            "unpin": _("Unpin"),
            "pinThisPage": _("Pin this page"),
            "unpinThisPage": _("Unpin this page"),
            "compact": _("Compact"),
            "expanded": _("Expanded"),
            "retry": _("Retry"),
            "movePinUp": _("Move pin up"),
            "movePinDown": _("Move pin down"),
            "removePin": _("Remove pin"),
            "reset": _("Reset navigation"),
            "resetConfirm": _("Reset your navigation preferences for this admin workspace? No records or permissions will be changed."),
            "scope": _("Scope"),
        },
    }


def _json_payload(request: HttpRequest) -> Mapping[str, Any]:
    try:
        raw_body = request.body
        if len(raw_body) > MAX_PREFERENCE_PAYLOAD_BYTES:
            raise RequestDataTooBig
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except RequestDataTooBig as exc:
        raise ValidationError("The navigation preference payload is too large.", code="payload_too_large") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Invalid JSON payload.", code="invalid_json") from exc
    if not isinstance(payload, Mapping):
        raise ValidationError("The request payload must be an object.", code="invalid_payload")
    return payload


def _error_response(exc: ValidationError, *, default_status: int = 400) -> JsonResponse:
    code = getattr(exc, "code", "invalid_request") or "invalid_request"
    status = 413 if code == "payload_too_large" else default_status
    return JsonResponse({"ok": False, "code": code, "error": "; ".join(exc.messages)}, status=status)


@require_http_methods(["GET", "PATCH", "POST"])
def admin_navigation_preferences_view(request: HttpRequest, *, admin_site) -> JsonResponse:
    """Read state, apply a v3 semantic mutation, or accept a v1 replacement."""

    host = _safe_host(request)
    site = str(admin_site.name)
    if request.method == "GET":
        envelope = AdminNavigationPreferenceService.read_envelope(user=request.user, host=host, admin_site=site)
        return JsonResponse({"ok": True, "revision": envelope["revision"], "preferences": envelope["state"]})
    try:
        payload = _json_payload(request)
        if request.method == "POST":
            state = AdminNavigationPreferenceService.write(
                user=request.user,
                scope_key=_scope_key(host=host, admin_site_name=site),
                state=payload.get("preferences"),
            )
            envelope = AdminNavigationPreferenceService.read_envelope(user=request.user, host=host, admin_site=site)
            return JsonResponse({"ok": True, "revision": envelope["revision"], "preferences": state, "legacy": True})
        context = build_navigation_context(request, admin_site, available_apps=admin_site.get_app_list(request))
        destinations = list(_context_registry(context))
        mutation_payload = payload.get("mutation") if isinstance(payload.get("mutation"), Mapping) else {}
        mutation_data = mutation_payload.get("payload") if isinstance(mutation_payload.get("payload"), Mapping) else {}
        destination_id = str(mutation_data.get("destinationId") or "")
        if destination_id and destination_id not in {item.id for item in destinations} and mutation_payload.get("type") in {"pin", "remember_recent"}:
            signed_destination = _destination_from_token(
                request=request,
                site=site,
                token=mutation_data.get("destinationToken"),
            )
            if signed_destination.id != destination_id:
                raise ValidationError("The page destination token does not match the requested destination.")
            destinations.append(signed_destination)
        result = AdminNavigationPreferenceService.mutate(
            user=request.user,
            host=host,
            admin_site=site,
            expected_revision=payload.get("expected_revision"),
            mutation=mutation_payload,
            destinations=tuple(destinations),
            recommendation_ids={
                item.id
                for item in context.recommendations
                if item.dismissible and not item.mandatory
            },
        )
    except NavigationRevisionConflict as exc:
        return JsonResponse(
            {"ok": False, "code": "revision_conflict", "expected_revision": exc.expected_revision, "revision": exc.actual_revision, "preferences": exc.state},
            status=409,
        )
    except ValidationError as exc:
        return _error_response(exc)
    except DatabaseError:
        logger.exception("admin navigation preference write failed")
        return JsonResponse(
            {"ok": False, "code": "preference_store_unavailable", "error": "Navigation preferences could not be saved."},
            status=503,
        )
    return JsonResponse(
        {"ok": True, "revision": result["revision"], "preferences": result["state"], "duplicate": result["duplicate"]}
    )
