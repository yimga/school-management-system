"""v4.00.82 Wave 14 Target 2 — OneRoster v1.2 users delta endpoint smoke.

Endpoint under test:
  GET /api/roster/v1p2/users/delta/?modifiedSince=<ISO>

Per IMS v1.2 spec  4.13.4 ("Pagination and updates"), the delta surface
returns BOTH added/modified rows (status="active") AND tombstoned deletes
(status="tobedeleted") since the supplied watermark.

Honest deferred:
  Hard deletes (Model.delete()) leave no audit trail and CANNOT produce
  tombstones. Tombstones are synthesized from User.is_active=False rows
  using last_login / date_joined as the modification anchor.
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

from django.test import RequestFactory  # noqa: E402

from apps.api import oneroster  # noqa: E402

rf = RequestFactory()


def _bearer(req):
    req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
    req._dont_enforce_csrf_checks = True
    return req


# Case 1: missing modifiedSince -> 400 missing_param
req = _bearer(rf.get("/api/roster/v1p2/users/delta/"))
resp = oneroster.users_delta_v1p2(req)
assert resp.status_code == 400, resp.status_code
body = json.loads(resp.content)
assert body.get("error") == "missing_param", body
assert body.get("param") == "modifiedSince", body
print("[T2-1] missing modifiedSince -> 400 missing_param OK")

# Case 1b: empty modifiedSince -> 400 missing_param
req = _bearer(rf.get("/api/roster/v1p2/users/delta/?modifiedSince="))
resp = oneroster.users_delta_v1p2(req)
assert resp.status_code == 400, resp.status_code
body = json.loads(resp.content)
assert body.get("error") == "missing_param", body
print("[T2-1b] empty modifiedSince -> 400 missing_param OK")

# Case 2: unparseable modifiedSince -> 400 bad_modified_since
req = _bearer(rf.get("/api/roster/v1p2/users/delta/?modifiedSince=notadate"))
resp = oneroster.users_delta_v1p2(req)
assert resp.status_code == 400, resp.status_code
body = json.loads(resp.content)
assert body.get("error") == "bad_modified_since", body
assert body.get("value") == "notadate", body
print("[T2-2] bad modifiedSince -> 400 bad_modified_since OK")

# Case 3: valid modifiedSince (deep past) -> 200 + envelope {"users": [...]}
req = _bearer(rf.get("/api/roster/v1p2/users/delta/?modifiedSince=2020-01-01"))
resp = oneroster.users_delta_v1p2(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert "users" in body, body
assert isinstance(body["users"], list), type(body["users"])
print("[T2-3] modifiedSince=2020-01-01 -> 200 + envelope OK (got %d users)" % len(body["users"]))

# Case 4: far-future modifiedSince -> 200 with empty list + X-Total-Count=0
req = _bearer(rf.get("/api/roster/v1p2/users/delta/?modifiedSince=2099-01-01"))
resp = oneroster.users_delta_v1p2(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert body.get("users") == [], body
assert resp["X-Total-Count"] == "0", resp["X-Total-Count"]
assert resp["X-Active-Count"] == "0", resp["X-Active-Count"]
assert resp["X-Tombstone-Count"] == "0", resp["X-Tombstone-Count"]
print("[T2-4] far-future modifiedSince -> 200 empty users + X-Total-Count=0 OK")

# Case 5: X-Active-Count + X-Tombstone-Count headers present (deep-past query)
req = _bearer(rf.get("/api/roster/v1p2/users/delta/?modifiedSince=2020-01-01"))
resp = oneroster.users_delta_v1p2(req)
assert resp.status_code == 200, resp.status_code
assert resp.has_header("X-Total-Count"), dict(resp.headers)
assert resp.has_header("X-Active-Count"), dict(resp.headers)
assert resp.has_header("X-Tombstone-Count"), dict(resp.headers)
total = int(resp["X-Total-Count"])
active = int(resp["X-Active-Count"])
tombstone = int(resp["X-Tombstone-Count"])
assert active + tombstone == total, "%d + %d != %d" % (active, tombstone, total)
print("[T2-5] headers present: total=%d active=%d tombstone=%d OK" % (total, active, tombstone))

# Case 6: at least one returned user has status active OR tobedeleted (if any users at all)
req = _bearer(rf.get("/api/roster/v1p2/users/delta/?modifiedSince=2020-01-01"))
resp = oneroster.users_delta_v1p2(req)
body = json.loads(resp.content)
if body["users"]:
    statuses = {u.get("status") for u in body["users"]}
    assert statuses.issubset({"active", "tobedeleted"}), statuses
    assert "active" in statuses or "tobedeleted" in statuses, statuses
    # All emitted rows MUST include sourcedId + dateLastModified per spec.
    for u in body["users"]:
        assert "sourcedId" in u, u
        assert "dateLastModified" in u, u
    print("[T2-6] status enum + sourcedId + dateLastModified shape OK (statuses=%s)" % statuses)
else:
    # Acceptable: empty user table in dev. Verified the envelope shape in case 3.
    print("[T2-6] no users in db -> shape vacuously OK")

# Case 7: pagination ?limit=5&offset=0 -> 200, page <= 5
req = _bearer(rf.get("/api/roster/v1p2/users/delta/?modifiedSince=2020-01-01&limit=5&offset=0"))
resp = oneroster.users_delta_v1p2(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert len(body["users"]) <= 5, len(body["users"])
assert resp["X-Limit"] == "5", resp["X-Limit"]
assert resp["X-Offset"] == "0", resp["X-Offset"]
print("[T2-7] pagination limit=5 offset=0 -> page<=5 OK")

# Bonus: ISO with Z suffix (UTC) is accepted
req = _bearer(rf.get("/api/roster/v1p2/users/delta/?modifiedSince=2020-01-01T00:00:00Z"))
resp = oneroster.users_delta_v1p2(req)
assert resp.status_code == 200, resp.status_code
print("[T2-8] ISO Z suffix accepted -> 200 OK")

# Bonus: ISO with +00:00 offset is accepted
req = _bearer(rf.get("/api/roster/v1p2/users/delta/?modifiedSince=2020-01-01T00:00:00+00:00"))
resp = oneroster.users_delta_v1p2(req)
assert resp.status_code == 200, resp.status_code
print("[T2-9] ISO +00:00 offset accepted -> 200 OK")

print("ALL T2 CASES OK")
