"""
Platform surface SOT — named URLs and client config for operator + tenant shells.

Cascade: tenant ``backend_feature_flags`` (+ ``platform_client_urls`` overrides)
→ platform runtime → env (deployment only).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from django.conf import settings as dj_settings
from django.urls import NoReverseMatch, reverse

from apps.portal.ai_chrome_config import _effective_flags, resolve_ai_chrome_config
from apps.siteconfig.realtime_capabilities import (
    resolve_web_server_mode,
    sse_streams_client_enabled,
    wal_stream_client_enabled,
)

logger = logging.getLogger(__name__)

PLATFORM_SURFACE_VERSION = "v4.00.97"

_REQUEST_CACHE_ATTR = "_rmc_platform_surface_request_cache"


def _request_surface_cache(request) -> dict[str, Any] | None:
    """Per-request memo for URL catalog + surface config (context processor calls 3×)."""
    if request is None:
        return None
    cache = getattr(request, _REQUEST_CACHE_ATTR, None)
    if cache is None or not isinstance(cache, dict):
        cache = {}
        setattr(request, _REQUEST_CACHE_ATTR, cache)
    return cache

# (payload_key, django_url_name, optional urlconf — None uses request.urlconf)
_API_URL_CATALOG: tuple[tuple[str, str, str | None], ...] = (
    ("api_health", "api_health", None),
    ("csrf_token", "api_csrf_token", None),
    ("health", "health", None),
    ("ai_line_interpret", "api:ai-line-interpret", None),
    ("ai_command_bar", "api:ai-command-bar", None),
    ("ai_feedback", "api:ai-feedback", None),
    ("ai_setup_assistant", "api:ai-setup-assistant", None),
    ("ai_workflow_draft", "api:ai-workflow-draft", None),
    ("command_bar_actions", "command_bar_actions", None),
    ("permission_snapshot", "api:offline-permission-snapshot", None),
    ("offline_delta", "api:offline-delta", None),
    ("offline_replay_batch", "api:offline-replay-batch", None),
    ("offline_queue_metrics", "api:offline-queue-metrics", None),
    ("offline_encryption_key", "api:offline-encryption-key", None),
    ("offline_prefetch_urls", "api:offline-prefetch-urls", None),
    ("entity_students", "api:entity-student-list", None),
    ("entity_students_bulk_preview", "api:entity-student-bulk-preview", None),
    ("entity_students_bulk_commit", "api:entity-student-bulk-commit", None),
    ("entity_students_bulk_assign", "api:entity-student-bulk-assign", None),
    ("entity_guardians_bulk_preview", "api:entity-guardian-bulk-preview", None),
    ("entity_guardians_bulk_commit", "api:entity-guardian-bulk-commit", None),
    ("entity_teachers", "api:entity-teacher-list", None),
    ("entity_classrooms", "api:entity-classroom-list", None),
    ("attendance", "api:attendance-list", None),
    ("session_claims", "api:session-claims", None),
    ("portal_preferences", "api:portal-preferences", None),
    ("control_plane_preferences", "api_control_plane_preferences", "manager"),
    ("teacher_hover", "api:api-teacher-hover", None),
    ("theme_preference", "set_theme_preference", None),
    ("friction_ingest", "api_friction_ingest", None),
    ("client_event", "client_event_capture", None),
    ("admissions_intake_schema", "api:admissions-intake-schema", None),
    ("admissions_applicant_scores", "api:admissions-applicant-scores", None),
    ("notifications_self_capture", "api:notification-self-capture", None),
    ("me_schools", "api_v1:me-schools", None),
    ("me_switch_school", "api_v1:me-switch-school", None),
    ("crdt_apply", "api_v1:crdt-apply", None),
    ("kb_search", "portal:kb_search_inline", None),
    ("kb_offline_pack", "portal:kb_offline_pack", None),
    ("support_quick_create", "portal:support_quick_create", None),
    ("activities", "api_activities", None),
    ("admin_dashboard", "api:admin-dashboard", None),
    ("sync_bundle_upload", "api:sync-bundle-upload", None),
    ("wizard_cache_telemetry", "setup_studio:wizard_cache_telemetry", None),
    ("tenant_domains", "api_domains_list_or_create", None),
    ("super_wedge_list", "api:super-wedge-list", None),
)

__all__ = [
    "PLATFORM_SURFACE_VERSION",
    "resolve_platform_surface_config",
    "platform_surface_config_json",
    "resolve_sms_offline_config",
    "sms_offline_config_json",
    "filter_assist_dock_slots",
    "resolve_api_urls",
]


def _reverse(name: str, *, urlconf: str | None = None, kwargs: dict | None = None) -> str:
    try:
        kw = kwargs or {}
        if urlconf:
            return reverse(name, urlconf=urlconf, kwargs=kw)
        return reverse(name, kwargs=kw)
    except NoReverseMatch:
        logger.debug("platform_surface_config: NoReverseMatch for %s", name)
        return ""


def _flag(flags: dict[str, Any], key: str, default: Any) -> Any:
    if key in flags:
        return flags[key]
    return default


def _merge_platform_client_urls(flags: dict[str, Any], urls: dict[str, str]) -> dict[str, str]:
    raw = flags.get("platform_client_urls")
    if not isinstance(raw, dict):
        return urls
    merged = dict(urls)
    for key, value in raw.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            merged[str(key)] = text
    return merged


def resolve_api_urls(request) -> dict[str, str]:
    """Host-aware named API paths for client modules."""
    cache = _request_surface_cache(request)
    if cache is not None and "api_urls" in cache:
        return cache["api_urls"]

    urlconf = getattr(request, "urlconf", None)
    host_kind = getattr(request, "public_host_kind", "") or ""
    flags = _effective_flags(request)

    urls: dict[str, str] = {}
    for key, name, hint in _API_URL_CATALOG:
        conf = urlconf
        if hint == "manager":
            from django.conf import settings

            conf = getattr(settings, "MANAGER_URLCONF", None) or conf
        urls[key] = _reverse(name, urlconf=conf)

    if host_kind == "manager":
        urls["search"] = _reverse("manager_search_api", urlconf=urlconf)
    else:
        urls["search"] = _reverse("api:global-search", urlconf=urlconf)

    loc = _reverse(
        "api_v1:localization-country-pack",
        urlconf=urlconf,
        kwargs={"country_code": "__CC__"},
    )
    if loc:
        urls["localization_country"] = loc.replace("__CC__", "{country_code}")

    job_status = _reverse(
        "api_v1:migration-job-status",
        urlconf=urlconf,
        kwargs={"job_id": "__JOB__"},
    )
    if job_status:
        urls["migration_job_status"] = job_status.replace("__JOB__", "{job_id}")

    layout_tpl = _reverse(
        "api:dashboard-layout", urlconf=urlconf, kwargs={"page": "__PAGE__"}
    )
    if layout_tpl:
        urls["dashboard_layout"] = layout_tpl.replace("__PAGE__", "{page}")

    urls["dashboard_available_widgets"] = _reverse(
        "api:dashboard-available-widgets", urlconf=urlconf
    )

    notif_tpl = _reverse(
        "api:notification-read", urlconf=urlconf, kwargs={"pk": 0}
    )
    if notif_tpl:
        urls["notification_read"] = re.sub(r"/0/read/", "/{notification_id}/read/", notif_tpl)

    from django.conf import settings as dj_settings

    manager_conf = getattr(dj_settings, "MANAGER_URLCONF", None)
    inc_tpl = _reverse(
        "api_platform_incident_status",
        urlconf=manager_conf,
        kwargs={"incident_id": "00000000-0000-0000-0000-000000000000"},
    )
    if inc_tpl:
        urls["observability_incident_status"] = inc_tpl.replace(
            "00000000-0000-0000-0000-000000000000", "{incident_id}"
        )

    if not urls.get("health"):
        urls["health"] = "/health/"

    urls = _merge_platform_client_urls(flags, urls)
    if cache is not None:
        cache["api_urls"] = urls
    return urls


def _offline_urls_for_request(request) -> dict[str, str | None]:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {}
    urlconf = getattr(request, "urlconf", None)
    keys = (
        ("sync_queue", "portal:offline_sync_queue"),
        ("conflicts", "portal:offline_sync_conflicts"),
        ("enqueue", "portal:api_offline_enqueue"),
        ("process", "portal:api_offline_process"),
        ("token_mint", "api:devices-offline-token"),
        ("permission_snapshot", "api:offline-permission-snapshot"),
        ("delta", "api:offline-delta"),
        ("replay_batch", "api:offline-replay-batch"),
        ("queue_metrics", "api:offline-queue-metrics"),
        ("encryption_key", "api:offline-encryption-key"),
        ("prefetch_urls", "api:offline-prefetch-urls"),
    )
    out: dict[str, str | None] = {}
    for label, name in keys:
        out[label] = _reverse(name, urlconf=urlconf) or None
    return out


def _hydrate_endpoints(request) -> list[dict[str, str]]:
    urls = resolve_api_urls(request)
    catalog = (
        ("entity_students", "students", "student"),
        ("attendance", "attendance", "attendance"),
        ("entity_classrooms", "classrooms", "classroom"),
        ("kb_offline_pack", "kb_articles", "kb_article"),
    )
    endpoints: list[dict[str, str]] = []
    for key, store, normalizer in catalog:
        endpoint_url = urls.get(key) or ""
        if endpoint_url:
            endpoints.append(
                {"url": endpoint_url, "store": store, "normalizer": normalizer}
            )
    return endpoints


def _wal_stream_client_enabled() -> bool:
    return wal_stream_client_enabled()


def _sse_streams_client_enabled() -> bool:
    return sse_streams_client_enabled()


def resolve_sms_offline_config(
    request,
    *,
    site: Any = None,
    backend_flags: dict[str, Any] | None = None,
    offline_enabled_for_school: bool = False,
    offline_delivery_client: dict[str, Any] | None = None,
) -> dict[str, Any]:
    flags = backend_flags if backend_flags is not None else _effective_flags(request)
    delivery = offline_delivery_client or {}
    offline_urls = _offline_urls_for_request(request)
    api_urls = resolve_api_urls(request)

    reachability = str(flags.get("reachability_url") or "").strip() or api_urls.get(
        "health", "/health/"
    )
    path = (getattr(request, "path", "") or "").lower()
    parent_shell = "/portal/parent" in path or "/parent/dashboard" in path

    deployment = (
        getattr(dj_settings, "RMC_DEPLOYMENT_PROFILE", None) or "online"
    ).strip().lower()
    ai_needs_network = deployment not in ("edge",)
    host_kind = getattr(request, "public_host_kind", "") or ""

    def _yn(key: str, default: bool = True) -> bool:
        return bool(_flag(flags, key, default))

    queue_encryption_enabled = bool(offline_enabled_for_school) and _yn(
        "enable_offline_queue_encryption", True
    )

    delta_url = offline_urls.get("delta") or api_urls.get("offline_delta") or ""

    return {
        "enabled": bool(offline_enabled_for_school),
        "pwaEnabled": _yn("enable_portal_pwa", True),
        "formQueueEnabled": _yn("enable_offline_form_queue", True),
        "attendanceSyncEnabled": _yn("enable_offline_attendance_sync", True),
        "gradeSyncEnabled": _yn("enable_offline_grade_sync", True),
        "homeworkSyncEnabled": _yn("enable_offline_homework_sync", True),
        "migrationCloudUploadSyncEnabled": _yn(
            "enable_offline_migration_cloud_upload", True
        ),
        "backgroundSyncEnabled": _yn("enable_offline_background_sync", True),
        "requestPersistentStorage": _yn("request_persistent_browser_storage", True),
        "reachabilityUrl": reachability,
        "hydrate": True,
        "dripWhenWeak": True,
        "reduceActivityLowPower": bool(flags.get("reduce_activity_low_power")),
        "entitySyncEnabled": flags.get("offline_entity_sync") is not False,
        "requestsSyncEnabled": flags.get("offline_requests_sync") is not False,
        "apiSyncEnabled": True,
        "paymentSyncEnabled": _yn("enable_offline_payment_sync", True),
        "offlineEnqueueUrl": offline_urls.get("enqueue"),
        "offlineProcessUrl": offline_urls.get("process"),
        "offlineConflictsUrl": offline_urls.get("conflicts"),
        "offlineTokenMintUrl": offline_urls.get("token_mint"),
        "permissionSnapshotUrl": offline_urls.get("permission_snapshot")
        or api_urls.get("permission_snapshot"),
        "offlineReplayBatchUrl": offline_urls.get("replay_batch")
        or api_urls.get("offline_replay_batch"),
        "offlineQueueMetricsUrl": offline_urls.get("queue_metrics")
        or api_urls.get("offline_queue_metrics"),
        "offlinePrefetchUrls": offline_urls.get("prefetch_urls")
        or api_urls.get("offline_prefetch_urls"),
        "deltaEndpointUrl": delta_url,
        "hydrateEndpoints": _hydrate_endpoints(request),
        "hubBaseUrl": str(
            delivery.get("hubBaseUrl") or flags.get("hub_base_url") or ""
        ),
        "maxQueueItems": int(delivery.get("maxQueueItems") or 500),
        "meshEnabled": bool(delivery.get("meshEnabled")),
        "deploymentProfile": deployment,
        "aiNeedsNetwork": ai_needs_network,
        "prefetchAtHour": flags.get("prefetch_at_hour"),
        "parentPortalShell": parent_shell,
        "operatorControlPlaneShell": host_kind == "manager",
        "csrfTokenUrl": api_urls.get("csrf_token") or "",
        # Path the service worker watches to purge the authenticated read-cache
        # (DYNAMIC_CACHE) on logout — prevents the previous user's cached PII
        # being served to the next user on a shared school device.
        "logoutPath": _reverse("accounts:logout") or _reverse("logout"),
        # Identity of the signed-in user. The WAL outbox stamps each queued write
        # with this so a shared device cannot ship user A's queued offline writes
        # over user B's socket (the server rejects author/socket mismatches).
        "currentUserId": str(
            getattr(getattr(request, "user", None), "pk", "") or ""
        ),
        # The current tenant's WAL tenant_hash. The WAL offline client asserts this
        # on every envelope; it must equal the value the server derives from the
        # authenticated socket scope (sha256(str(school.id))[:12]) in
        # apps/wal_stream/consumers.py, else the server rejects tenant_mismatch and
        # the whole WAL rail is dead-on-arrival. The client cannot compute it from
        # the opaque rmc_rls_jwt cookie, so it reads this server-provided value.
        "tenantHash": wal_tenant_hash_for_request(request),
        # Do not ask for a session encryption key when the effective runtime
        # has disabled offline mode.  The API enforces the same condition;
        # emitting an unconditional URL made every authenticated shell issue a
        # predictable 403 and report a broken resource.
        "encryptOutbox": queue_encryption_enabled,
        "enableQueueEncryption": queue_encryption_enabled,
        "encryptionKeyUrl": (
            offline_urls.get("encryption_key")
            or api_urls.get("offline_encryption_key")
            or ""
        )
        if queue_encryption_enabled
        else "",
        "walStreamEnabled": _wal_stream_client_enabled(),
        "sseStreamsEnabled": _sse_streams_client_enabled(),
        "webServerMode": resolve_web_server_mode(),
        "ingestionManifest": _ingestion_manifest_for_request(request),
    }


def _ingestion_manifest_for_request(request) -> dict[str, Any]:
    """Country blueprint lexicon for offline Migration Cloud preflight."""
    school = getattr(request, "school", None)
    if school is None:
        return {}
    try:
        from apps.migration_cloud.ingestion_lexicon import (
            compile_offline_ingestion_manifest_for_school,
        )

        return compile_offline_ingestion_manifest_for_school(school)
    except (ImportError, AttributeError, TypeError, ValueError):
        return {}


def wal_tenant_hash_for_request(request) -> str:
    """The current tenant's WAL ``tenant_hash`` for the offline config island.

    Equals ``School.tenant_hash`` (``sha256(str(school.id))[:12]``) — the SAME
    value ``apps/wal_stream/consumers.py`` derives from the authenticated socket
    scope. Exposing it lets the offline client assert the CORRECT tenant_hash on
    WAL envelopes instead of a host-derived guess that never matched (which got
    every real-browser envelope rejected ``tenant_mismatch``, killing the rail).
    Empty when there is no resolved tenant.
    """
    school = getattr(request, "school", None)
    if school is None:
        return ""
    return str(getattr(school, "tenant_hash", "") or "")


def sms_offline_config_json(
    request,
    *,
    site: Any = None,
    backend_flags: dict[str, Any] | None = None,
    offline_enabled_for_school: bool = False,
    offline_delivery_client: dict[str, Any] | None = None,
) -> str:
    payload = resolve_sms_offline_config(
        request,
        site=site,
        backend_flags=backend_flags,
        offline_enabled_for_school=offline_enabled_for_school,
        offline_delivery_client=offline_delivery_client,
    )
    return json.dumps(payload, separators=(",", ":"))


def filter_assist_dock_slots(slots: list, flags: dict[str, Any]) -> list:
    out = []
    for slot in slots:
        req = (getattr(slot, "requires_feature", None) or "").strip()
        if not req:
            out.append(slot)
            continue
        if bool(flags.get(req, True)):
            out.append(slot)
    return out


def _assist_dock_ui(flags: dict[str, Any]) -> dict[str, str]:
    raw = flags.get("assist_dock_ui")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if v is not None}


def resolve_platform_surface_config(request) -> dict[str, Any]:
    cache = _request_surface_cache(request)
    if cache is not None and "platform_surface" in cache:
        return cache["platform_surface"]

    flags = _effective_flags(request)
    ai = resolve_ai_chrome_config(request)
    urls = resolve_api_urls(request)
    dock_ui = _assist_dock_ui(flags)

    payload = {
        "version": PLATFORM_SURFACE_VERSION,
        "urls": urls,
        "ai": ai,
        "cmdk": {
            "ai_line_url": urls.get("ai_line_interpret") or "",
            "api_url": urls.get("ai_command_bar") or "",
            "actions_url": urls.get("command_bar_actions") or "",
        },
        "assist_dock_ui": dock_ui,
        "flags": {
            "enable_ai_help_assistant": bool(
                _flag(flags, "enable_ai_help_assistant", True)
            ),
            "enable_ai_copilot_query_api": bool(
                _flag(flags, "enable_ai_copilot_query_api", True)
            ),
        },
    }
    if cache is not None:
        cache["platform_surface"] = payload
    return payload


def platform_surface_config_json(request) -> str:
    cache = _request_surface_cache(request)
    if cache is not None and "platform_surface_json" in cache:
        return cache["platform_surface_json"]
    payload = json.dumps(
        resolve_platform_surface_config(request), separators=(",", ":")
    )
    if cache is not None:
        cache["platform_surface_json"] = payload
    return payload
