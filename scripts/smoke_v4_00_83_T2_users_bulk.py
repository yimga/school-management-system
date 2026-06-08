"""v4.00.83 Wave 15 Target 2 — OneRoster v1.2 bulk POST /users/ smoke.

Endpoint under test:
  POST /api/roster/v1p2/users/bulk/

Per OneRoster v1.2 bulk-batch semantics, the endpoint accepts a JSON body
of the shape {"users": [<user_payload>, ...]} (max 500 entries) and
returns 207 Multi-Status with per-row {sourcedId, status, reason?} plus
a summary counters block.

Valid rows are persisted through the canonical OneRoster user upsert and
return status="created" or status="updated". Invalid rows return
status="error" without aborting the rest of the batch.
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Make this script runnable from anywhere (path of project root).
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import django  # noqa: E402

django.setup()

import json  # noqa: E402
import uuid  # noqa: E402

from django.core.cache import cache  # noqa: E402
from django.test import RequestFactory  # noqa: E402

from apps.api import oneroster  # noqa: E402

rf = RequestFactory()


def _bearer(req, idem_key=None):
    req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
    if idem_key is not None:
        req.META["HTTP_IDEMPOTENCY_KEY"] = idem_key
    req._dont_enforce_csrf_checks = True
    return req


def _post(body, idem_key=None, content_type="application/json"):
    if isinstance(body, (dict, list)):
        raw = json.dumps(body).encode("utf-8")
    elif isinstance(body, bytes):
        raw = body
    else:
        raw = (body or "").encode("utf-8")
    req = rf.post(
        "/api/roster/v1p2/users/bulk/",
        data=raw,
        content_type=content_type,
    )
    return _bearer(req, idem_key=idem_key)


# Case 1: POST without Idempotency-Key -> 428 missing_idempotency_key
req = _post({"users": []})
resp = oneroster.users_bulk_post(req)
assert resp.status_code == 428, resp.status_code
body = json.loads(resp.content)
assert body.get("error") == "missing_idempotency_key", body
print("[T2-1] missing Idempotency-Key -> 428 missing_idempotency_key OK")

# Case 2: POST with Idempotency-Key but malformed body (not JSON) -> 400 bad_json
req = _post(b"this-is-not-json", idem_key="smoke-key-c2-" + uuid.uuid4().hex)
resp = oneroster.users_bulk_post(req)
assert resp.status_code == 400, resp.status_code
body = json.loads(resp.content)
assert body.get("error") == "bad_json", body
print("[T2-2] malformed body -> 400 bad_json OK")

# Case 3: POST with body missing "users" key -> 400 missing_users_key
req = _post({"not_users": []}, idem_key="smoke-key-c3-" + uuid.uuid4().hex)
resp = oneroster.users_bulk_post(req)
assert resp.status_code == 400, resp.status_code
body = json.loads(resp.content)
assert body.get("error") == "missing_users_key", body
print("[T2-3] missing 'users' key -> 400 missing_users_key OK")

# Case 4: POST with {"users": []} -> 207 + empty results + total=0
req = _post({"users": []}, idem_key="smoke-key-c4-" + uuid.uuid4().hex)
resp = oneroster.users_bulk_post(req)
assert resp.status_code == 207, resp.status_code
body = json.loads(resp.content)
assert body.get("results") == [], body
assert body.get("summary", {}).get("total") == 0, body
assert body.get("summary", {}).get("created") == 0, body
assert body.get("summary", {}).get("updated") == 0, body
assert body.get("summary", {}).get("skipped") == 0, body
assert body.get("summary", {}).get("error") == 0, body
print("[T2-4] empty users -> 207 + empty results + total=0 OK")

# Case 5: POST with 3-user payload -> 207 + 3 results + summary.total=3
three_users = {
    "users": [
        {
            "sourcedId": "u-001",
            "givenName": "Ada",
            "familyName": "Lovelace",
            "role": "student",
            "orgSourcedIds": ["sch-1"],
        },
        {
            "sourcedId": "u-002",
            "givenName": "Alan",
            "familyName": "Turing",
            "role": "teacher",
            "orgSourcedIds": ["sch-1"],
        },
        {
            "sourcedId": "u-003",
            "givenName": "Grace",
            "familyName": "Hopper",
            "role": "administrator",
            "orgSourcedIds": ["sch-1"],
        },
    ]
}
req = _post(three_users, idem_key="smoke-key-c5-" + uuid.uuid4().hex)
resp = oneroster.users_bulk_post(req)
assert resp.status_code == 207, resp.status_code
body = json.loads(resp.content)
assert len(body["results"]) == 3, body
assert body["summary"]["total"] == 3, body
# Existing rows may report updated when this smoke is rerun against a retained DB.
for r in body["results"]:
    assert r["status"] in ("created", "updated"), r
assert body["summary"]["created"] + body["summary"]["updated"] == 3, body
print("[T2-5] 3-user payload -> 207 + 3 persisted results + summary.total=3 OK")

# Case 6: POST with too many users (501) -> 400 too_many_users
many = {"users": [{"sourcedId": f"u-{i}", "givenName": "G",
                   "familyName": "F", "role": "student"} for i in range(501)]}
req = _post(many, idem_key="smoke-key-c6-" + uuid.uuid4().hex)
resp = oneroster.users_bulk_post(req)
assert resp.status_code == 400, resp.status_code
body = json.loads(resp.content)
assert body.get("error") == "too_many_users", body
assert body.get("received_count") == 501, body
assert body.get("max_count") == 500, body
print("[T2-6] 501 users -> 400 too_many_users OK")

# Case 7: POST with same Idempotency-Key + same body -> 207 + Idempotency-Replay: true
replay_key = "smoke-key-c7-" + uuid.uuid4().hex
# Pre-clear any stale cache for this key (defensive — uuid should make this unique anyway)
cache.delete(oneroster._bulk_users_idem_cache_key(replay_key))

req = _post(three_users, idem_key=replay_key)
resp1 = oneroster.users_bulk_post(req)
assert resp1.status_code == 207, resp1.status_code
body1 = json.loads(resp1.content)
# Replay: same key, same body
req = _post(three_users, idem_key=replay_key)
resp2 = oneroster.users_bulk_post(req)
assert resp2.status_code == 207, resp2.status_code
assert resp2.has_header("Idempotency-Replay"), dict(resp2.headers)
assert resp2["Idempotency-Replay"] == "true", resp2["Idempotency-Replay"]
body2 = json.loads(resp2.content)
assert body1 == body2, "replay body diverged"
print("[T2-7] replay with same key+body -> 207 + Idempotency-Replay: true OK")

# Case 8: POST with same Idempotency-Key + DIFFERENT body -> 409 idempotency_key_conflict
different = {
    "users": [
        {
            "sourcedId": "u-999",
            "givenName": "Different",
            "familyName": "Person",
            "role": "student",
        }
    ]
}
req = _post(different, idem_key=replay_key)
resp = oneroster.users_bulk_post(req)
assert resp.status_code == 409, resp.status_code
body = json.loads(resp.content)
assert body.get("error") == "idempotency_key_conflict", body
print("[T2-8] same key + different body -> 409 idempotency_key_conflict OK")

# Case 9: POST with valid body returns each result with sourcedId echoed
echo_payload = {
    "users": [
        {"sourcedId": "echo-A", "givenName": "A", "familyName": "B",
         "role": "student"},
        {"sourcedId": "echo-B", "givenName": "C", "familyName": "D",
         "role": "teacher"},
    ]
}
req = _post(echo_payload, idem_key="smoke-key-c9-" + uuid.uuid4().hex)
resp = oneroster.users_bulk_post(req)
assert resp.status_code == 207, resp.status_code
body = json.loads(resp.content)
sids = [r["sourcedId"] for r in body["results"]]
assert sids == ["echo-A", "echo-B"], sids
print("[T2-9] sourcedIds echoed back: %s OK" % sids)

# Case 10: invalid row (missing role) -> per-row status=error + summary.error counter
mixed = {
    "users": [
        {"sourcedId": "ok-1", "givenName": "G", "familyName": "F",
         "role": "student"},
        {"sourcedId": "bad-1", "givenName": "G", "familyName": "F"},  # missing role
        {"sourcedId": "bad-2", "givenName": "G", "familyName": "F",
         "role": "wizard"},  # bad role
    ]
}
req = _post(mixed, idem_key="smoke-key-c10-" + uuid.uuid4().hex)
resp = oneroster.users_bulk_post(req)
assert resp.status_code == 207, resp.status_code
body = json.loads(resp.content)
assert body["results"][0]["status"] in ("created", "updated"), body["results"][0]
assert body["results"][1]["status"] == "error", body["results"][1]
assert body["results"][1]["reason"] == "missing_role", body["results"][1]
assert body["results"][2]["status"] == "error", body["results"][2]
assert body["results"][2]["reason"] == "bad_role", body["results"][2]
assert body["summary"]["error"] == 2, body
assert body["summary"]["created"] + body["summary"]["updated"] == 1, body
assert body["summary"]["total"] == 3, body
print("[T2-10] mixed payload validation: 1 persisted + 2 errors OK")

print("ALL T2 CASES OK")
