"""Typed, permission-aware navigation contracts for both Django admin sites."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import logging
import re
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.translation import gettext as _


CONTRACT_VERSION = 3
_SAFE_ID = re.compile(r"[^a-z0-9_.:-]+")
logger = logging.getLogger(__name__)


def _stable_id(*parts: object) -> str:
    value = ":".join(str(part or "").strip().lower() for part in parts)
    return _SAFE_ID.sub("-", value).strip("-:")[:180]


def _safe_internal_path(value: object) -> str:
    path = str(value or "").strip()
    return path[:600] if path.startswith("/") and "\n" not in path and "\r" not in path else ""


@dataclass(frozen=True, slots=True)
class AdminDestination:
    id: str
    label: str
    path: str
    group: str
    kind: str = "destination"
    keywords: tuple[str, ...] = ()
    icon: str = "record"
    description: str = ""
    scope: str = ""

    def serialize(self) -> dict[str, Any]:
        value = asdict(self)
        value["keywords"] = list(self.keywords)
        return value


@dataclass(frozen=True, slots=True)
class AdminPageAction:
    id: str
    label: str
    path: str
    kind: str = "navigate"

    def serialize(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AdminPageContract:
    archetype: str
    destination_id: str
    title: str
    path: str
    app_label: str = ""
    model_name: str = ""
    object_id: str = ""
    actions: tuple[AdminPageAction, ...] = ()

    def serialize(self) -> dict[str, Any]:
        value = asdict(self)
        value["actions"] = [action.serialize() for action in self.actions]
        return value


@dataclass(frozen=True, slots=True)
class AdminRecommendation:
    id: str
    title: str
    description: str
    path: str
    reason: str
    reason_code: str
    source_timestamp: str
    dismissible: bool = True
    mandatory: bool = False

    def serialize(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AdminNavigationContext:
    version: int
    admin_site: str
    host_kind: str
    tenant_id: str
    effective_role: str
    permissions: tuple[str, ...]
    destinations: tuple[AdminDestination, ...]
    work_areas: tuple[dict[str, Any], ...]
    page: AdminPageContract
    recommendations: tuple[AdminRecommendation, ...]


@dataclass(frozen=True, slots=True)
class NavigationMutation:
    id: str
    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NavigationConflict:
    expected_revision: int
    actual_revision: int
    state: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class BrowserEvidenceManifest:
    schema_version: int
    git_sha: str
    build_id: str
    cache_bust: str
    service_worker_version: str
    route_manifest_sha256: str
    hosts: tuple[str, ...]
    browsers: tuple[str, ...]
    viewports: tuple[int, ...]
    themes: tuple[str, ...]
    generated_at: str
    expires_at: str


def _reverse(request: HttpRequest, name: str) -> str:
    try:
        return reverse(name, urlconf=getattr(request, "urlconf", None))
    except NoReverseMatch:
        return ""


def _destination(
    *,
    site: str,
    label: object,
    path: object,
    group: object,
    kind: str,
    identity: Sequence[object],
    scope: str = "",
) -> AdminDestination | None:
    clean_path = _safe_internal_path(path)
    clean_label = " ".join(str(label or "").split())[:120]
    if not clean_path or not clean_label:
        return None
    return AdminDestination(
        id=_stable_id(site, *identity),
        label=clean_label,
        path=clean_path,
        group=" ".join(str(group or _("Other")).split())[:100],
        kind=kind,
        keywords=tuple(
            token
            for token in {
                clean_label.lower(),
                str(identity[0] if identity else "").lower(),
                str(identity[1] if len(identity) > 1 else "").lower(),
            }
            if token
        ),
        icon="home" if kind == "home" else ("add" if kind == "action" else "record"),
        description=_('%(kind)s in %(group)s')
        % {"kind": kind.replace("-", " ").title(), "group": str(group or _("Other"))},
        scope=scope,
    )


def build_admin_destination_registry(
    request: HttpRequest,
    admin_site,
    *,
    available_apps: Iterable[Mapping[str, Any]] | None = None,
) -> tuple[tuple[AdminDestination, ...], tuple[dict[str, Any], ...]]:
    """Flatten Django's permission-filtered app list into stable destinations."""

    site = str(admin_site.name)
    scope = "operator" if admin_site.is_platform_site() else "tenant"
    if available_apps is not None:
        apps = list(available_apps)
    else:
        try:
            apps = list(admin_site.get_app_list(request))
        except (LookupError, NoReverseMatch):
            # Direct RequestFactory callers may not have the admin site's URL
            # namespace installed. Runtime ``each_context`` passes its already
            # permission-filtered ``available_apps`` and does not use this path.
            apps = []
    destinations: list[AdminDestination] = []
    work_areas: list[dict[str, Any]] = []
    home = _destination(
        site=site,
        label=_("Admin home"),
        path=_reverse(request, f"{site}:index"),
        group=_("Start"),
        kind="home",
        identity=("home",),
        scope=scope,
    )
    if home:
        destinations.append(home)

    for app in apps:
        app_label = str(app.get("app_label") or "")
        app_name = str(app.get("name") or app_label or _("Application"))
        group = str(app.get("section") or app_name)
        area_ids: list[str] = []
        app_destination = _destination(
            site=site,
            label=app_name,
            path=app.get("app_url"),
            group=group,
            kind="app",
            identity=(app_label, "app"),
            scope=scope,
        )
        if app_destination:
            destinations.append(app_destination)
            area_ids.append(app_destination.id)
        for model in app.get("models") or ():
            if model.get("hidden"):
                continue
            object_name = str(model.get("object_name") or "")
            model_label = str(model.get("name") or object_name)
            list_destination = _destination(
                site=site,
                label=model_label,
                path=model.get("admin_url"),
                group=group,
                kind="model",
                identity=(app_label, object_name, "list"),
                scope=scope,
            )
            if list_destination:
                destinations.append(list_destination)
                area_ids.append(list_destination.id)
            add_destination = _destination(
                site=site,
                label=_("Add %(model)s") % {"model": model_label},
                path=model.get("add_url"),
                group=group,
                kind="action",
                identity=(app_label, object_name, "add"),
                scope=scope,
            )
            if add_destination:
                destinations.append(add_destination)
                area_ids.append(add_destination.id)
        if area_ids:
            work_areas.append(
                {
                    "id": _stable_id(site, "area", group),
                    "label": group,
                    "appLabel": app_label,
                    "destinationIds": area_ids,
                    "path": next((item.path for item in destinations if item.id in area_ids), ""),
                    "icon": (app_label[:1] or "A").upper(),
                }
            )

    # De-duplicate by stable identity without changing Django's permission-aware order.
    unique: dict[str, AdminDestination] = {}
    for item in destinations:
        unique.setdefault(item.id, item)
    return tuple(unique.values()), tuple(work_areas)


def _page_archetype(request: HttpRequest) -> tuple[str, str, str, str]:
    match = getattr(request, "resolver_match", None)
    name = str(getattr(match, "url_name", "") or "")
    kwargs = getattr(match, "kwargs", {}) or {}
    path = request.path
    app_label = str(kwargs.get("app_label") or "")
    model_name = str(kwargs.get("model_name") or "")
    object_id = str(kwargs.get("object_id") or "")
    if request.method == "POST" and request.POST.get("action") == "delete_selected":
        return "delete-selected", app_label, model_name, object_id
    if name in {"index", ""} and path.rstrip("/") == "/admin":
        return "index", app_label, model_name, object_id
    if name == "app_list":
        return "app-index", app_label, model_name, object_id
    for suffix, archetype in (
        ("_changelist", "changelist"),
        ("_add", "add"),
        ("_change", "change"),
        ("_history", "history"),
        ("_delete", "delete"),
    ):
        if name.endswith(suffix):
            prefix = name[: -len(suffix)]
            if "_" in prefix and not app_label:
                app_label, model_name = prefix.split("_", 1)
            return archetype, app_label, model_name, object_id
    return "guided-action", app_label, model_name, object_id


def build_admin_page_contract(
    request: HttpRequest,
    admin_site,
    destinations: Sequence[AdminDestination],
) -> AdminPageContract:
    archetype, app_label, model_name, object_id = _page_archetype(request)
    site = str(admin_site.name)
    by_id = {item.id: item for item in destinations}
    list_id = _stable_id(site, app_label, model_name, "list")
    add_id = _stable_id(site, app_label, model_name, "add")
    list_item = by_id.get(list_id)
    add_item = by_id.get(add_id)
    title = (list_item.label if list_item else "") or str(getattr(admin_site, "index_title", "")) or _("Administration")
    actions: list[AdminPageAction] = []
    if archetype == "changelist" and add_item:
        actions.append(AdminPageAction(add_item.id, add_item.label, add_item.path))
    if archetype in {"add", "change", "history", "delete"} and list_item:
        actions.append(AdminPageAction(list_item.id, _("Back to %(model)s") % {"model": list_item.label}, list_item.path))
    if archetype == "change":
        history_path = request.path.removesuffix("change/") + "history/"
        actions.append(AdminPageAction(_stable_id(site, app_label, model_name, object_id, "history"), _("History"), history_path))
        title = _("Change %(model)s") % {
            "model": (list_item.label if list_item else model_name).rstrip("s")
        }
    elif archetype == "add" and add_item:
        title = add_item.label
    elif archetype == "history":
        record_path = request.path.removesuffix("history/") + "change/"
        actions.insert(
            0,
            AdminPageAction(
                _stable_id(site, app_label, model_name, object_id, "change"),
                _("Back to record"),
                record_path,
            ),
        )
        title = _("%(model)s history") % {
            "model": (list_item.label if list_item else model_name).rstrip("s")
        }
    elif archetype == "delete":
        record_path = request.path.removesuffix("delete/") + "change/"
        actions.insert(
            0,
            AdminPageAction(
                _stable_id(site, app_label, model_name, object_id, "change"),
                _("Back to record"),
                record_path,
            ),
        )
        title = _("Delete %(model)s") % {
            "model": (list_item.label if list_item else model_name).rstrip("s")
        }
    elif archetype == "delete-selected":
        title = _("Delete selected %(model)s") % {
            "model": list_item.label if list_item else model_name
        }
    destination_id = _stable_id(site, app_label or "admin", model_name or "home", archetype, object_id)
    if archetype == "index" and destinations:
        destination_id = destinations[0].id
        title = destinations[0].label
    return AdminPageContract(
        archetype=archetype,
        destination_id=destination_id,
        title=title,
        path=_safe_internal_path(request.get_full_path()) or request.path,
        app_label=app_label,
        model_name=model_name,
        object_id=object_id,
        actions=tuple(actions),
    )


def build_admin_recommendations(
    *,
    page: AdminPageContract,
    destinations: Sequence[AdminDestination],
    is_platform: bool,
) -> tuple[AdminRecommendation, ...]:
    by_id = {item.id: item for item in destinations}
    candidates: list[AdminDestination] = []
    for action in page.actions:
        item = by_id.get(action.id)
        if item:
            candidates.append(item)
    if not candidates and page.archetype == "index" and is_platform:
        # Platform shortcuts exist only on the operator index. Tenant and operator
        # candidates are already isolated by their independent app registries.
        candidates = [item for item in destinations if item.kind in {"app", "model"}][:3]
    recommendations: list[AdminRecommendation] = []
    for item in candidates[:3]:
        recommendations.append(
            AdminRecommendation(
                id=_stable_id("recommendation", page.archetype, item.id),
                title=item.label,
                description=_("Available for this page and your current permissions."),
                path=item.path,
                reason=_("Recommended from the current %(page)s workflow.") % {"page": page.archetype.replace("-", " ")},
                reason_code=f"page_workflow:{page.archetype}",
                source_timestamp=timezone.now().isoformat(),
                dismissible=True,
            )
        )
    return tuple(recommendations)


def build_navigation_context(
    request: HttpRequest,
    admin_site,
    *,
    available_apps: Iterable[Mapping[str, Any]] | None = None,
) -> AdminNavigationContext:
    destinations, work_areas = build_admin_destination_registry(
        request, admin_site, available_apps=available_apps
    )
    page = build_admin_page_contract(request, admin_site, destinations)
    work_areas = tuple(
        {
            **area,
            "current": bool(page.app_label and area.get("appLabel") == page.app_label),
        }
        for area in work_areas
    )
    try:
        recommendations = build_admin_recommendations(
            page=page,
            destinations=destinations,
            is_platform=bool(admin_site.is_platform_site()),
        )
    except (LookupError, TypeError, ValueError):
        trace_id = uuid4().hex
        logger.exception("admin recommendation calculation failed trace_id=%s", trace_id)
        recommendations = ()
    return AdminNavigationContext(
        version=CONTRACT_VERSION,
        admin_site=str(admin_site.name),
        host_kind="operator" if admin_site.is_platform_site() else "tenant",
        tenant_id=str(getattr(getattr(request, "school", None), "pk", "") or ""),
        effective_role=str(
            getattr(getattr(request, "user", None), "role", "")
            or (
                "platform-operator"
                if admin_site.is_platform_site()
                else "tenant-administrator"
            )
        )[:80],
        permissions=tuple(
            sorted(
                getattr(
                    getattr(request, "user", None),
                    "get_all_permissions",
                    lambda: set(),
                )()
            )
        ),
        destinations=destinations,
        work_areas=work_areas,
        page=page,
        recommendations=recommendations,
    )
