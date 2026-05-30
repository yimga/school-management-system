"""v4.00.80 Wave 12 T4 — DLQ replay endpoint smoke.

Exercises the staff-only operator surface for ``WebhookDeadLetter``
triage + replay shipped in Wave 12 T4:

  * ``GET  /super/migration/operator/dlq/`` — list pending rows JSON
  * ``POST /super/migration/operator/dlq/<id>/replay/`` — replay one row

Uses ``config.settings_test`` (in-memory SQLite) so the smoke runs
self-contained on Windows without touching the dev DB.

Cases:

  1. Smoke harness: ``enqueue_dead_letter`` creates a pending row
  2. List endpoint returns 200 + the pending row is present
  3. List endpoint never includes ``payload_b64`` or ``tenant_schema``
  4. POST replay endpoint with staff user -> 200 + ``replayed: True``
     (note: ``marked_no_live_target`` because no subscription in fixture)
  5. DLQ row status flipped to ``replayed`` in the DB
  6. POST replay again on same row -> 409 ``not_pending``
  7. POST replay on bogus id -> 404 ``not_found``
  8. GET list AFTER replay -> 200 + the replayed row is NO LONGER in
     the pending list (status_filter=pending default)
  9. GET list AFTER replay with ``?status=replayed`` -> 200 + replayed
     row IS in that filter
 10. Non-staff user POSTing replay -> 302 redirect (Django's
     staff_member_required default)
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import django  # noqa: E402

django.setup()

import json  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402


# In-memory SQLite needs schema spin-up before any ORM call.
call_command("migrate", "--run-syncdb", verbosity=0)


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
# Fixture: a pending DLQ row + a staff user + a non-staff user.
# --------------------------------------------------------------------------
from apps.integrations_marketplace import webhook_dead_letter as dlq  # noqa: E402
from apps.integrations_marketplace.models import WebhookDeadLetter  # noqa: E402

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


staff = User.objects.create_user(
    username="dlq-smoke-staff",
    password="x",
    is_staff=True,
)
non_staff = User.objects.create_user(
    username="dlq-smoke-nonstaff",
    password="x",
    is_staff=False,
)


# --------------------------------------------------------------------------
# Case: GET list (staff) returns 200 + pending row present + no leakage.
# --------------------------------------------------------------------------
client = Client()
client.force_login(staff)

resp = client.get("/super/migration/operator/dlq/")
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
resp = client.post(f"/super/migration/operator/dlq/{dlq_id}/replay/")
assert resp.status_code == 200, (resp.status_code, resp.content)
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
resp = client.post(f"/super/migration/operator/dlq/{dlq_id}/replay/")
assert resp.status_code == 409, (resp.status_code, resp.content)
body = json.loads(resp.content)
assert body["error"] == "not_pending", body
assert body["status"] == "replayed", body
_ok("POST replay on already-replayed row -> 409 not_pending")


# --------------------------------------------------------------------------
# Case: POST replay on bogus id -> 404 not_found.
# --------------------------------------------------------------------------
resp = client.post("/super/migration/operator/dlq/999999/replay/")
assert resp.status_code == 404, (resp.status_code, resp.content)
body = json.loads(resp.content)
assert body["error"] == "not_found", body
_ok("POST replay on bogus id -> 404 not_found")


# --------------------------------------------------------------------------
# Case: GET list AFTER replay (default pending filter) -> row absent.
# --------------------------------------------------------------------------
resp = client.get("/super/migration/operator/dlq/")
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
resp = client.get("/super/migration/operator/dlq/?status=replayed")
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
matching = [r for r in body["rows"] if r["id"] == dlq_id]
assert len(matching) == 1, f"replayed row not in ?status=replayed list: {body}"
assert matching[0]["status"] == "replayed"
_ok("GET /operator/dlq/?status=replayed -> replayed row listed")


# --------------------------------------------------------------------------
# Case: Non-staff user POST replay -> 302 redirect to login.
# --------------------------------------------------------------------------
# Park a fresh pending row to exercise the staff gate against.
row2 = dlq.enqueue_dead_letter(
    provider="test",
    event_type="grade.pushed",
    payload=b'{"second":"row"}',
    reason="http_503",
)
assert row2 is not None
client_ns = Client()
client_ns.force_login(non_staff)
resp = client_ns.post(f"/super/migration/operator/dlq/{row2.pk}/replay/")
assert resp.status_code in (302, 403), (resp.status_code, resp.content[:200])
# Django's staff_member_required default is a 302 to the admin login.
_ok(f"non-staff POST replay -> {resp.status_code} (gated)")

# Confirm the non-staff hit DID NOT flip row2's status.
fresh2 = WebhookDeadLetter.objects.get(pk=row2.pk)
assert fresh2.status == "pending", fresh2.status
_ok("non-staff hit left row2 status=pending (untouched)")


# --------------------------------------------------------------------------
# Case: Non-staff GET list -> 302 redirect (same gate).
# --------------------------------------------------------------------------
resp = client_ns.get("/super/migration/operator/dlq/")
assert resp.status_code in (302, 403), (resp.status_code, resp.content[:200])
_ok(f"non-staff GET list -> {resp.status_code} (gated)")


print("=" * 70)
print(f"v4.00.80 Wave 12 T4 — DLQ replay smoke OK ({CASES}/{CASES} cases)")
print("=" * 70)
