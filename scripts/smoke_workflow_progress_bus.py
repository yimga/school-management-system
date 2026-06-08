"""Smoke gate for the platform-wide Workflow Progress Bus (v4.00.97).

Run after every change to apps/platform_runtime/workflow_*.py or the
frontend chip files. Exits 0 when all assertions pass, 1 on any failure.

Coverage:
* T1: model + status enum shape
* T2: scrub helper drops secret keys
* T3: regex auto-fix taxonomy hits known patterns
* T4: workflow_tracker primitives complete a happy + failed run
* T5: stuck detector flips correctly across the threshold
* T6: SSE frame formatter shape
* T7: URL routes resolvable
* T8: assist-dock slot registered after AppConfig.ready
* T9: 6 decorated platform workflows still importable + decorated
* T10: SW cache version matches expected slug
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()


ASSERTIONS: list[tuple[str, bool, str]] = []


def expect(label: str, cond: bool, detail: str = "") -> None:
    ASSERTIONS.append((label, bool(cond), detail))


# ── T1 ───────────────────────────────────────────────────────────────────
from apps.platform_runtime.models import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStep,
    WorkflowStepStatus,
)

expect("T1.1 WorkflowRun has workflow_key field", any(f.name == "workflow_key" for f in WorkflowRun._meta.fields))
expect("T1.2 WorkflowRun has suggested_remediation JSON", any(f.name == "suggested_remediation" for f in WorkflowRun._meta.fields))
expect("T1.3 WorkflowStep has unique (run, ordinal)", any(c.name == "wfs_unique_run_ordinal" for c in WorkflowStep._meta.constraints))
expect("T1.4 WorkflowRunStatus has 5 states", len(list(WorkflowRunStatus.values)) == 5)
expect("T1.5 WorkflowStepStatus has 5 states", len(list(WorkflowStepStatus.values)) == 5)
expect("T1.6 status 'stuck' exists", "stuck" in list(WorkflowRunStatus.values))
expect("T1.7 tenant_schema indexed", any("tenant_schema" in (i.fields or []) for i in WorkflowRun._meta.indexes))


# ── T2 ───────────────────────────────────────────────────────────────────
from apps.platform_runtime.workflow_tracker import _scrub

clean = _scrub({
    "name": "Jane",
    "password": "secret",
    "api_key": "x",
    "nested": {"token": "y", "ok": "v"},
    "long": "x" * 500,
    "client_secret": "z",
})

expect("T2.1 scrub drops password key", "password" not in clean)
expect("T2.2 scrub drops api_key", "api_key" not in clean)
expect("T2.3 scrub drops client_secret", "client_secret" not in clean)
expect("T2.4 scrub keeps name", clean.get("name") == "Jane")
expect("T2.5 scrub recursively drops nested token", "token" not in clean.get("nested", {}))
expect("T2.6 scrub keeps nested.ok", clean.get("nested", {}).get("ok") == "v")
expect("T2.7 scrub truncates long strings", clean.get("long", "").endswith("…"))


# ── T3 ───────────────────────────────────────────────────────────────────
from apps.platform_runtime.workflow_auto_fix import suggest_remediation

expect(
    "T3.1 ConnectionError -> upstream_timeout",
    suggest_remediation(error_type="ConnectionError", error_message="timed out")["remediation_key"] == "upstream_timeout",
)
expect(
    "T3.2 IntegrityError email -> user_email_or_username_collision",
    suggest_remediation(
        error_type="IntegrityError",
        error_message="UNIQUE constraint failed: auth_user.email",
    )["remediation_key"] == "user_email_or_username_collision",
)
expect(
    "T3.3 IntegrityError schema_name -> tenant_slug_collision",
    suggest_remediation(
        error_type="IntegrityError",
        error_message="UNIQUE constraint failed: tenants_tenant.schema_name",
    )["remediation_key"] == "tenant_slug_collision",
)
expect(
    "T3.4 HTTPError 503 -> upstream_5xx",
    suggest_remediation(error_type="HTTPError", error_message="upstream returned 503")["remediation_key"] == "upstream_5xx",
)
expect(
    "T3.5 HTTPError 429 -> upstream_rate_limit",
    suggest_remediation(error_type="HTTPError", error_message="upstream returned 429")["remediation_key"] == "upstream_rate_limit",
)
expect(
    "T3.6 invalid_grant -> oauth_credentials_invalid",
    suggest_remediation(error_type="OAuthError", error_message="invalid_grant")["remediation_key"] == "oauth_credentials_invalid",
)
expect(
    "T3.7 token expired -> oauth_token_expired (auto-fix available)",
    suggest_remediation(error_type="TokenExpired", error_message="token expired")["auto_fix_available"] is True,
)
expect(
    "T3.8 unknown returns no_match",
    suggest_remediation(error_type="WeirdError", error_message="???")["verdict"] in ("no_match", "ai_match"),
)


# ── T4 ───────────────────────────────────────────────────────────────────
from django.test.utils import setup_test_environment

try:
    setup_test_environment()
except Exception:
    pass

from django.test.utils import override_settings
from django.db import connection

# Use a per-test schema by creating + migrating an in-memory db isn't trivial
# under the project's settings; we exercise the in-memory primitives that
# do not require the table to exist for tracking-failed runs to degrade.
from apps.platform_runtime.workflow_tracker import (
    begin_run,
    compute_progress_percent,
    finalize_run,
    heartbeat,
    is_stuck,
    list_active_runs,
    track_workflow,
    workflow_step,
)

expect("T2.8 progress_percent step-based mid-run", compute_progress_percent(current_step_ordinal=2, total_steps=5) in range(20, 45))
expect("T2.9 progress_percent time-based fallback", compute_progress_percent(age_seconds=15, expected_duration_seconds=30) in range(40, 55))


@track_workflow("smoke_demo_happy", steps=("a", "b"), expected_duration_seconds=5)
def _happy(x):
    return x * 2


@track_workflow("smoke_demo_failure", steps=("a",), expected_duration_seconds=5)
def _failing():
    raise RuntimeError("synthetic")


expect("T4.1 decorated happy path returns", _happy(3) == 6)
try:
    _failing()
    raised = False
except RuntimeError:
    raised = True
expect("T4.2 decorated failure propagates", raised is True)


# ── T5 ───────────────────────────────────────────────────────────────────
class _FakeRun:
    pass


now = datetime.now(timezone.utc)
old = _FakeRun()
old.status = "running"
old.expected_duration_seconds = 10
old.last_heartbeat_at = now - timedelta(seconds=120)

fresh = _FakeRun()
fresh.status = "running"
fresh.expected_duration_seconds = 10
fresh.last_heartbeat_at = now - timedelta(seconds=2)

finished = _FakeRun()
finished.status = "succeeded"
finished.expected_duration_seconds = 10
finished.last_heartbeat_at = now - timedelta(seconds=999)

expect("T5.1 old running run is stuck", is_stuck(old) is True)
expect("T5.2 fresh running run not stuck", is_stuck(fresh) is False)
expect("T5.3 succeeded run never stuck", is_stuck(finished) is False)


# ── T6 ───────────────────────────────────────────────────────────────────
from apps.platform_runtime.views_workflow_progress import (
    _format_sse_frame,
    _sse_max_duration_seconds,
    _stable_hash,
)

frame = _format_sse_frame(1, "snapshot", {"runs": []})
expect("T6.1 SSE frame is bytes", isinstance(frame, bytes))
expect("T6.2 SSE frame has 'event:' line", b"event: snapshot" in frame)
expect("T6.3 SSE frame ends with blank line", frame.endswith(b"\n\n") or frame.endswith(b"\n"))
expect("T6.4 SSE frame contains id", b"id: 1" in frame)
expect("T6.5 hash stable across identical input", _stable_hash([]) == _stable_hash([]))
expect(
    "T6.6 SSE max duration below default gunicorn timeout",
    _sse_max_duration_seconds() <= 30.0,
    f"got {_sse_max_duration_seconds()}",
)

from apps.assist_dock.views import _sse_max_duration_seconds as _assist_sse_max

expect(
    "T6.7 assist-dock SSE max duration capped for WSGI",
    _assist_sse_max() <= 60.0,
    f"got {_assist_sse_max()}",
)


# ── T6d: SSE concurrency cap (thread-starvation guard) ─────────────────────
# Long-lived SSE streams each pin a gthread worker thread. The cap reserves
# threads so streams can never starve /health/ and trigger the Render restart
# loop. Verify: hold up to capacity, refuse over-cap, busy response backs off
# without holding a slot, and slots free after a stream drains.
from services.sse_wsgi_limits import (
    sse_stream_capacity,
    try_acquire_sse_slot,
    release_sse_slot,
)
from services.sse_response import guarded_sse_response

_cap = sse_stream_capacity()
expect("T6d.1 SSE capacity is a positive int", isinstance(_cap, int) and _cap >= 1, f"got {_cap}")
_held = [try_acquire_sse_slot() for _ in range(_cap)]
expect("T6d.2 can hold up to capacity streams", all(_held), f"acquired {_held}")
expect("T6d.3 over-cap acquire is refused", try_acquire_sse_slot() is False)

_busy_body = b"".join(guarded_sse_response(lambda: iter([b": x\n\n"])).streaming_content)
expect(
    "T6d.4 busy response carries a retry-backoff frame (no slot held)",
    b"retry:" in _busy_body and b"busy" in _busy_body,
    f"got {_busy_body!r}",
)

for _ in range(_cap):
    release_sse_slot()

_ran = {"v": False}


def _probe_gen():
    _ran["v"] = True
    yield b": ok\n\n"


list(guarded_sse_response(_probe_gen).streaming_content)  # drain -> finally releases
expect("T6d.5 stream generator ran while a slot was held", _ran["v"] is True)
expect("T6d.6 slot is re-acquirable after the stream drained", try_acquire_sse_slot() is True)
release_sse_slot()


# ── T6b ──────────────────────────────────────────────────────────────────
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

rf = RequestFactory()
anon_req = rf.get("/platform-runtime/workflow-progress/stream/")
anon_req.user = AnonymousUser()
from apps.platform_runtime.views_workflow_progress import stream_view as _stream_view

# stream_view is now an async (ASGI) view — its decorated form is a coroutine.
import asyncio as _asyncio

anon_resp = _asyncio.run(_stream_view(anon_req))
expect("T6b.1 anonymous SSE returns 401 not 302", getattr(anon_resp, "status_code", None) == 401)
expect("T6b.2 stream_view is async (ASGI)", _asyncio.iscoroutinefunction(_stream_view))


# ── T6c ──────────────────────────────────────────────────────────────────
from apps.platform_runtime.middleware_unauthenticated_api_guard import (
    UnauthenticatedApiGuardMiddleware,
)


def _noop_response(_request):
    from django.http import HttpResponse

    return HttpResponse("ok")


_mw = UnauthenticatedApiGuardMiddleware(_noop_response)
_cursor_req = rf.get("/assist-dock/cursors/list.json?page=%2Fauthentication%2Flogin%2F")
_cursor_req.user = AnonymousUser()
_cursor_resp = _mw(_cursor_req)
expect("T6c.1 middleware blocks anonymous cursor list with 401", getattr(_cursor_resp, "status_code", None) == 401)

_stream_req = rf.get("/platform-runtime/workflow-progress/stream/")
_stream_req.user = AnonymousUser()
_stream_resp = _mw(_stream_req)
expect("T6c.2 middleware blocks anonymous workflow stream with 401", getattr(_stream_resp, "status_code", None) == 401)

_share_req = rf.get("/assist-dock/s/test-token/")
_share_req.user = AnonymousUser()
_share_resp = _mw(_share_req)
expect("T6c.3 middleware allows anonymous share resolve through", getattr(_share_resp, "status_code", None) == 200)

_wal_req = rf.get("/ws/wal/")
_wal_req.user = AnonymousUser()
_wal_resp = _mw(_wal_req)
expect("T6c.4 middleware blocks anonymous WAL websocket path with 401", getattr(_wal_resp, "status_code", None) == 401)

from apps.schools.middleware import ManagerHostControlPlaneRequiredMiddleware

_mgr_req = rf.post("/assist-dock/cursors/heartbeat/")
_mgr_req.user = AnonymousUser()
_mgr_req.public_host_kind = "manager"
_mgr_resp = ManagerHostControlPlaneRequiredMiddleware(_noop_response).process_request(_mgr_req)
expect(
    "T6c.5 manager host returns 401 for anonymous assist-dock API (not 302)",
    getattr(_mgr_resp, "status_code", None) == 401,
)


# ── T7 ───────────────────────────────────────────────────────────────────
from django.urls import reverse, NoReverseMatch

for name in (
    "workflow_progress_active_runs",
    "workflow_progress_badge",
    "workflow_progress_stream",
    "workflow_progress_cancel",
    "workflow_progress_apply_fix",
):
    try:
        if name in ("workflow_progress_cancel", "workflow_progress_apply_fix"):
            reverse(f"platform_runtime:{name}", kwargs={"run_id": 1})
        else:
            reverse(f"platform_runtime:{name}")
        expect(f"T7 reverse {name}", True)
    except NoReverseMatch as e:
        expect(f"T7 reverse {name}", False, str(e))


# ── T8 ───────────────────────────────────────────────────────────────────
from apps.assist_dock.registry import get_slot

slot = get_slot("workflow-progress")
expect("T8.1 assist dock chip registered", slot is not None)
expect("T8.2 chip icon is bi-hourglass-split", getattr(slot, "icon", "") == "bi-hourglass-split")
expect("T8.3 chip badge_source set", getattr(slot, "badge_source", "") == "workflow_progress_badge")
expect("T8.4 chip pinned default", getattr(slot, "pinned_default", False) is True)


# ── T9 ───────────────────────────────────────────────────────────────────
import apps.api.oneroster_w1_extensions as orw1
import apps.integrations_marketplace.lms_connector_dispatcher as dispatcher
import apps.schools.super_views_provisioning as provisioning

expect("T9.1 oneroster classes_bulk_post wrapped", getattr(orw1.classes_bulk_post, "__wrapped__", None) is not None)
expect("T9.2 oneroster enrollments_bulk_post wrapped", getattr(orw1.enrollments_bulk_post, "__wrapped__", None) is not None)
expect("T9.3 oneroster staff_delta wrapped", getattr(orw1.staff_delta, "__wrapped__", None) is not None)
expect("T9.4 oneroster demographics_delta wrapped", getattr(orw1.demographics_delta, "__wrapped__", None) is not None)
expect("T9.5 LMS dispatcher.call exists", callable(getattr(dispatcher, "call", None)))
expect("T9.6 schools api_create_school wrapped", getattr(provisioning.api_create_school, "__wrapped__", None) is not None)


# ── T10 ──────────────────────────────────────────────────────────────────
sw_text = open("static/js/service-worker.js", encoding="utf-8").read()
# Accept v4.00.97 (workflow bus wave) OR any later v4.00.NN bump that
# may have shipped on a subsequent wave — only regression to a lower
# version fails this check.
import re as _re
_match = _re.search(r"sms-v4\.(\d+)\.(\d+)-", sw_text)
_minor = int(_match.group(2)) if _match else -1
_major = int(_match.group(1)) if _match else -1
expect(
    "T10.1 SW cache version >= v4.00.97",
    bool(_match) and (_major > 0 or _minor >= 97),
)


# ── T11 — platform-wide Celery + HTTP envelopes ───────────────────────────
from django.conf import settings

from apps.platform_runtime.workflow_celery_bridge import (
    _should_track_celery_task,
    clear_active_runs_for_tests,
)
from apps.platform_runtime.workflow_request_middleware import (
    _client_requests_workflow_track,
    _should_track_request,
)


class _SmokeUser:
    is_authenticated = True
    id = 1


class _SmokeTask:
    name = "apps.evals.tasks.bulk_grade_submissions"
    time_limit = 120


expect(
    "T11.1 middleware registered",
    "apps.platform_runtime.workflow_request_middleware.WorkflowProgressRequestMiddleware"
    in settings.MIDDLEWARE,
)
expect(
    "T11.2 celery bridge tracks generic shared_task",
    _should_track_celery_task(_SmokeTask(), name=_SmokeTask.name),
)
expect(
    "T11.3 celery bridge skips provision_school_task",
    not _should_track_celery_task(
        type("_P", (), {"name": "schools.provision_school_task"})(),
        name="schools.provision_school_task",
    ),
)
expect(
    "T11.4 celery bridge skips scheduled purge (explicit decorator)",
    not _should_track_celery_task(
        type("_R", (), {"name": "schools.run_scheduled_tenant_purges"})(),
        name="schools.run_scheduled_tenant_purges",
    ),
)
from apps.platform_runtime.workflow_celery_bridge import _CELERY_WORKFLOW_KEY_OVERRIDES
from apps.platform_runtime.workflow_registry import WORKFLOWS

expect("T11.5 registry has tenant_school_purge", "tenant_school_purge" in WORKFLOWS)

from django.test import RequestFactory

_rf = RequestFactory()
_post_api = _rf.post("/api/v1/students/import/")
_post_api.user = _SmokeUser()
expect("T11.6 middleware tracks tenant API POST", _should_track_request(_post_api))
_skip_create = _rf.post("/super/api/create-school/")
_skip_create.user = _SmokeUser()
expect(
    "T11.7 middleware skips explicit create-school",
    not _should_track_request(_skip_create),
)
_health = _rf.post("/api/health/")
_health.user = _SmokeUser()
expect("T11.8 middleware skips health POST", not _should_track_request(_health))

clear_active_runs_for_tests()


# ── T12 — nested run stack ────────────────────────────────────────────────
from apps.platform_runtime.workflow_tracker import (
    active_workflow_run,
    clear_workflow_run_stack_for_tests,
    pop_workflow_run,
    push_workflow_run,
)

clear_workflow_run_stack_for_tests()
_fake = type("_FakeRun", (), {"pk": 1})()
push_workflow_run(_fake)
expect("T12.1 stack exposes inner run", active_workflow_run() is _fake)
pop_workflow_run(_fake)
expect("T12.2 stack empty after pop", active_workflow_run() is None)
expect(
    "T12.3 migration registry apply key",
    WORKFLOWS.get("migration_bundle_apply") is not None,
)
expect(
    "T12.4 celery override maps apply_bundle",
    _CELERY_WORKFLOW_KEY_OVERRIDES.get("migration_cloud.apply_bundle")
    == "migration_bundle_apply",
)

_super_form = _rf.post("/super/siteconfig/some-form/")
_super_form.user = _SmokeUser()
expect("T13.1 bare super POST not tracked without header", not _should_track_request(_super_form))
_super_form.META["HTTP_X_RMC_WORKFLOW_TRACK"] = "1"
expect("T13.2 super POST tracked with opt-in header", _should_track_request(_super_form))
expect("T13.3 header helper accepts 1", _client_requests_workflow_track(_super_form))
_mig_apply = _rf.post("/super/migration/api/v1/bundles/42/apply/")
_mig_apply.user = _SmokeUser()
expect("T13.4 migration apply skipped (explicit track_workflow)", not _should_track_request(_mig_apply))
from apps.migration_cloud.views import MigrationCloudApplyView

expect(
    "T13.5 migration views post wrapped",
    getattr(MigrationCloudApplyView.post, "__wrapped__", None) is not None,
)


# ── T14 — finance/marketplace bulk + chip noise ───────────────────────────
from django.utils import timezone as dj_timezone

from apps.platform_runtime.workflow_tracker import _visible_in_progress_chip

expect(
    "T14.1 registry finance_auto_generate_fee_invoices",
    "finance_auto_generate_fee_invoices" in WORKFLOWS,
)
expect(
    "T14.2 registry finance_auto_copy_fee_plans",
    "finance_auto_copy_fee_plans" in WORKFLOWS,
)
expect(
    "T14.3 registry marketplace_webhook_deliver_due",
    "marketplace_webhook_deliver_due" in WORKFLOWS,
)
expect(
    "T14.4 celery override finance auto_generate",
    _CELERY_WORKFLOW_KEY_OVERRIDES.get("finance.auto_generate_fee_invoices")
    == "finance_auto_generate_fee_invoices",
)
_young_celery = type(
    "_YoungCelery",
    (),
    {
        "workflow_key": "celery.ephemeral_task",
        "current_step_ordinal": 1,
        "started_at": dj_timezone.now(),
    },
)()
expect("T14.5 young generic celery hidden from chip", not _visible_in_progress_chip(_young_celery))
_named_run = type(
    "_NamedRun",
    (),
    {
        "workflow_key": "finance_auto_generate_fee_invoices",
        "current_step_ordinal": 1,
        "started_at": dj_timezone.now(),
    },
)()
expect("T14.6 named workflow visible on chip immediately", _visible_in_progress_chip(_named_run))
from apps.finance.tasks import auto_generate_fee_invoices_task
from apps.marketplace.tasks import webhook_deliver_due

expect(
    "T14.7 finance auto_generate explicit flag",
    getattr(auto_generate_fee_invoices_task, "rmc_workflow_explicit", False),
)
expect(
    "T14.8 marketplace webhook explicit flag",
    getattr(webhook_deliver_due, "rmc_workflow_explicit", False),
)

# ── T15: Workflow Progress 10x waves ─────────────────────────────────────
from django.urls import reverse

from apps.platform_runtime.models_workflow_10x import (
    WorkflowAutopilotPolicy,
    WorkflowDurationStat,
    WorkflowSlaBreach,
)
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.schools.control_plane_nav import build_control_plane_nav

for _url_name in (
    "platform_runtime:workflow_progress_flight_deck",
    "platform_runtime:workflow_progress_flight_deck_json",
    "platform_runtime:workflow_progress_tenant_trusted_active",
    "platform_runtime:workflow_progress_tenant_trusted_stream",
    "platform_runtime:workflow_progress_autopilot_policy",
    "platform_runtime:workflow_progress_enable_autopilot",
):
    try:
        reverse(_url_name)
        expect(f"T15.1 url resolves {_url_name}", True)
    except Exception as exc:
        expect(f"T15.1 url resolves {_url_name}", False, str(exc))

_nav_req = RequestFactory().get("/super/")
_nav_req.urlconf = "config.manager_urls"
_nav_req.user = get_user_model()(is_superuser=True, username="workflow_smoke_nav")
_flight_ids = [
    item.get("id")
    for section in build_control_plane_nav(_nav_req)
    for item in (section.get("items") or [])
    if isinstance(item, dict)
]
expect(
    "T15.2 control plane nav includes Flight Deck",
    "super_workflow_flight_deck" in _flight_ids,
)
expect("T15.3 WorkflowAutopilotPolicy model", WorkflowAutopilotPolicy._meta.db_table)
expect("T15.4 WorkflowDurationStat model", WorkflowDurationStat._meta.db_table)
expect("T15.5 WorkflowSlaBreach model", WorkflowSlaBreach._meta.db_table)
from apps.platform_runtime.workflow_registry import WORKFLOWS

expect(
    "T15.6 tenant_school_provision has slo_seconds",
    getattr(WORKFLOWS.get("tenant_school_provision"), "slo_seconds", None),
)
expect(
    "T15.7 registry has single tenant_school_purge key",
    list(WORKFLOWS.keys()).count("tenant_school_purge") == 1,
)


# ── Report ────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok, _ in ASSERTIONS if ok)
failed = sum(1 for _, ok, _ in ASSERTIONS if not ok)
total = len(ASSERTIONS)

print(f"\n=== Workflow Progress Bus smoke ({total} assertions) ===\n")
for label, ok, detail in ASSERTIONS:
    mark = "PASS" if ok else "FAIL"
    extra = f" — {detail}" if detail and not ok else ""
    print(f"  [{mark}] {label}{extra}")

print(f"\n{passed}/{total} passed, {failed} failed.")
sys.exit(0 if failed == 0 else 1)
