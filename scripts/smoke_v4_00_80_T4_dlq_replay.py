"""v4.00.80 Wave 12 T4 — DLQ replay endpoint smoke.

Exercises the staff-only operator surface for ``WebhookDeadLetter``
triage + replay shipped in Wave 12 T4:

  * ``WebhookDeadLetterListView`` — GET list of pending DLQ rows
  * ``WebhookDeadLetterReplayView`` — POST replay one row

Pattern: ``RequestFactory`` + direct view invocation. The Django
``staff_member_required`` decorator gate is verified by checking that
an anonymous request returns a redirect AND that direct dispatch on a
mock-staff user reaches the view body. We do NOT go through the full
middleware stack (the dev settings stack has TenantSuperAdminRequired +
RequireMFA + ModuleAccess gates that need a fully-provisioned SUPERADMIN
session — covered separately by tests in ``apps/migration_cloud/tests``).

Cases:

  1. ``enqueue_dead_letter`` creates a pending row
  2. List view (staff): 200 + the pending row is present in the JSON
  3. List response NEVER includes ``payload_b64`` or ``tenant_schema``
  4. Replay view (staff): 200 + ``replayed: True``
     (note: ``marked_no_live_target`` because no matching subscription)
  5. DLQ row status flipped to ``replayed`` in the DB
  6. Replay AGAIN on same row -> 409 ``not_pending``
  7. Replay on bogus id -> 404 ``not_found``
  8. List (default pending filter) -> replayed row absent
  9. List ``?status=replayed`` -> replayed row present
 10. Anonymous user hits replay -> 302 (staff_member_required default)
"""
import os
import sys

# Use the dev DB (config.settings) — Wave 11 migration 0005 is applied
# there. config.settings_test runs in-memory SQLite which on Windows
# takes 5+ minutes to spin up the 845-migration history; that wait is
# not acceptable for a per-target smoke.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import django  # noqa: E402

django.setup()

import json  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import AnonymousUser  # noqa: E402
from django.test import RequestFactory  # noqa: E402


User = get_user_model()


CASES = 0


def _ok(label):
    global CASES
    CASES += 1
    print(f"[OK {CASES:02d}] {label}")


print("=" * 70)
print("v4.00.80 Wave 12 T4 — DLQ replay endpoint smoke")
print("=" * 70)


# --------------------------------------------------------------------------
# Fixture: a pending DLQ row + a staff user.
# --------------------------------------------------------------------------
from apps.integrations_marketplace import webhook_dead_letter as dlq  # noqa: E402
from apps.integrations_marketplace.models import WebhookDeadLetter  # noqa: E402
from apps.migration_cloud.views_dlq_admin import (  # noqa: E402
    WebhookDeadLetterListView,
    WebhookDeadLetterReplayView,
)


# Clean up any prior smoke fixtures so the count assertions remain stable
# across re-runs.
WebhookDeadLetter.objects.filter(
    provider="test", event_type="grade.pushed",
).delete()


row = dlq.enqueue_dead_letter(
    provider="test",
    event_type="grade.pushed",
    payload=b'{"k":"v"}',
    reason="http_504",
)
assert row is not None, "enqueue_dead_letter returned None"
assert row.status == "pending", row.status
dlq_id = row.pk
_ok(f"enqueue_dead_letter created row id={dlq_id} status=pending")


staff, _ = User.objects.get_or_create(
    username="dlq-smoke-staff",
    defaults={"is_staff": True},
)
if not staff.is_staff:
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])


rf = RequestFactory()


# --------------------------------------------------------------------------
# Case: GET list (staff) returns 200 + pending row present + no leakage.
# --------------------------------------------------------------------------
req = rf.get("/super/migration/operator/dlq/")
req.user = staff
view = WebhookDeadLetterListView.as_view()
resp = view(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert "rows" in body and "count" in body, body
assert body["count"] >= 1, body
matching = [r for r in body["rows"] if r["id"] == dlq_id]
assert len(matching) == 1, matching
row_shape = matching[0]
assert row_shape["provider"] == "test"
assert row_shape["event_type"] == "grade.pushed"
assert row_shape["status"] == "pending"
assert row_shape["last_error_reason"] == "http_504"
assert row_shape["payload_bytes_length"] == len(b'{"k":"v"}')
_ok("GET /operator/dlq/ -> 200 + pending row present")

# Defense-in-depth: response NEVER includes payload_b64 / tenant_schema.
raw = resp.content.decode("utf-8")
assert "payload_b64" not in raw, "payload_b64 leaked in list response"
assert "tenant_schema" not in raw, "tenant_schema leaked in list response"
_ok("list response never includes payload_b64 / tenant_schema")


# --------------------------------------------------------------------------
# Case: POST replay (staff). No subscription -> 200 marked_no_live_target.
# --------------------------------------------------------------------------
req = rf.post(f"/super/migration/operator/dlq/{dlq_id}/replay/")
req.user = staff
view = WebhookDeadLetterReplayView.as_view()
resp = view(req, dlq_id=dlq_id)
assert resp.status_code == 200, (resp.status_code, resp.content[:300])
body = json.loads(resp.content)
assert body["replayed"] is True, body
assert body["dlq_id"] == dlq_id, body
assert body.get("note") == "marked_no_live_target", body
_ok("POST replay (no live subscription) -> 200 marked_no_live_target")


# --------------------------------------------------------------------------
# Case: DLQ row status flipped to replayed in DB.
# --------------------------------------------------------------------------
fresh = WebhookDeadLetter.objects.get(pk=dlq_id)
assert fresh.status == "replayed", fresh.status
assert fresh.last_attempted_at is not None, "last_attempted_at not set"
_ok(f"WebhookDeadLetter(pk={dlq_id}).status == 'replayed' in DB")


# --------------------------------------------------------------------------
# Case: POST replay AGAIN on same row -> 409 not_pending.
# --------------------------------------------------------------------------
req = rf.post(f"/super/migration/operator/dlq/{dlq_id}/replay/")
req.user = staff
resp = view(req, dlq_id=dlq_id)
assert resp.status_code == 409, (resp.status_code, resp.content[:300])
body = json.loads(resp.content)
assert body["error"] == "not_pending", body
assert body["status"] == "replayed", body
_ok("POST replay on already-replayed row -> 409 not_pending")


# --------------------------------------------------------------------------
# Case: POST replay on bogus id -> 404 not_found.
# --------------------------------------------------------------------------
bogus_id = 999_999_999
req = rf.post(f"/super/migration/operator/dlq/{bogus_id}/replay/")
req.user = staff
resp = view(req, dlq_id=bogus_id)
assert resp.status_code == 404, (resp.status_code, resp.content[:300])
body = json.loads(resp.content)
assert body["error"] == "not_found", body
assert body["dlq_id"] == bogus_id, body
_ok("POST replay on bogus id -> 404 not_found")


# --------------------------------------------------------------------------
# Case: GET list AFTER replay (default pending filter) -> row absent.
# --------------------------------------------------------------------------
req = rf.get("/super/migration/operator/dlq/")
req.user = staff
list_view = WebhookDeadLetterListView.as_view()
resp = list_view(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
matching = [r for r in body["rows"] if r["id"] == dlq_id]
assert len(matching) == 0, (
    f"replayed row still appears in pending list: {matching}"
)
_ok("GET /operator/dlq/ (pending) -> replayed row no longer listed")


# --------------------------------------------------------------------------
# Case: GET list ?status=replayed -> row appears.
# --------------------------------------------------------------------------
req = rf.get("/super/migration/operator/dlq/?status=replayed")
req.user = staff
resp = list_view(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
matching = [r for r in body["rows"] if r["id"] == dlq_id]
assert len(matching) == 1, (
    f"replayed row not in ?status=replayed list: count={body.get('count')}"
)
assert matching[0]["status"] == "replayed"
_ok("GET /operator/dlq/?status=replayed -> replayed row listed")


# --------------------------------------------------------------------------
# Case: Park a 2nd row + assert anonymous user POST replay -> 302.
# This exercises the staff_member_required gate at the dispatch level
# (RequestFactory bypasses middleware but @method_decorator(staff_member_required)
# fires on dispatch — the gate IS exercised even via direct view call).
# --------------------------------------------------------------------------
row2 = dlq.enqueue_dead_letter(
    provider="test",
    event_type="grade.pushed",
    payload=b'{"second":"row"}',
    reason="http_503",
)
assert row2 is not None
req = rf.post(f"/super/migration/operator/dlq/{row2.pk}/replay/")
req.user = AnonymousUser()
# Anonymous user must NOT reach our view body — staff_member_required
# returns a redirect (302) to the admin login.
resp = view(req, dlq_id=row2.pk)
assert resp.status_code in (302, 403), (resp.status_code, resp.content[:200])
_ok(f"anonymous POST replay -> {resp.status_code} (staff gate fired)")

# Confirm the anonymous hit DID NOT flip row2's status.
fresh2 = WebhookDeadLetter.objects.get(pk=row2.pk)
assert fresh2.status == "pending", fresh2.status
_ok("anonymous hit left row2 status=pending (untouched)")


# --------------------------------------------------------------------------
# Case: Anonymous GET list -> 302 redirect (same gate).
# --------------------------------------------------------------------------
req = rf.get("/super/migration/operator/dlq/")
req.user = AnonymousUser()
resp = list_view(req)
assert resp.status_code in (302, 403), (resp.status_code, resp.content[:200])
_ok(f"anonymous GET list -> {resp.status_code} (staff gate fired)")


# Cleanup smoke fixtures from the dev DB so re-runs stay idempotent.
WebhookDeadLetter.objects.filter(
    provider="test",
    event_type="grade.pushed",
    pk__in=[dlq_id, row2.pk],
).delete()


print("=" * 70)
print(f"v4.00.80 Wave 12 T4 — DLQ replay smoke OK ({CASES}/{CASES} cases)")
print("=" * 70)
