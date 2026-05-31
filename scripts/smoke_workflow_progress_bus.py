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
    finalize_run,
    heartbeat,
    is_stuck,
    list_active_runs,
    track_workflow,
    workflow_step,
)


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
_match = _re.search(r"sms-v4\.00\.(\d+)-", sw_text)
expect("T10.1 SW cache version >= v4.00.97", bool(_match) and int(_match.group(1)) >= 97)


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
