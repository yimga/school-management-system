"""v4.00.80 Wave 12 Target 2 — OneRoster v1.2 Roster Service Results smoke.

Endpoints under test:
  GET /api/roster/v1p2/results/
  GET /api/roster/v1p2/results/<sourced_id>/

Naming deviation note: the existing module already binds
``oneroster_results.results_list`` / ``result_detail`` to the legacy
v4.00.39 Result-Service path. The Wave 12 T2 views are exposed as
``results_list_v1p2_roster`` / ``result_detail_v1p2_roster`` to avoid
collision; URL names ``api-roster-v1p2-results`` and
``api-roster-v1p2-result-detail`` are stable.
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

from apps.api import oneroster_results  # noqa: E402

rf = RequestFactory()


def _bearer(req):
    req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
    req._dont_enforce_csrf_checks = True
    return req


# Case 1: list returns 200 + JSON envelope {"results": [...]}
req = _bearer(rf.get("/api/roster/v1p2/results/"))
resp = oneroster_results.results_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert "results" in body, body
assert isinstance(body["results"], list), type(body["results"])
print("[T2-1] list OK (got %d results)" % len(body["results"]))

# Case 2: ?since= filter parses
req = _bearer(rf.get("/api/roster/v1p2/results/?since=2026-01-01"))
resp = oneroster_results.results_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
print("[T2-2] since filter OK")

# Case 3: bad ?since= → 400
req = _bearer(rf.get("/api/roster/v1p2/results/?since=notadate"))
resp = oneroster_results.results_list_v1p2_roster(req)
assert resp.status_code == 400, resp.status_code
err = json.loads(resp.content)
assert err.get("error") == "bad_since", err
print("[T2-3] bad since 400 OK")

# Case 4: detail 404 on unknown sourcedId
req = _bearer(rf.get("/api/roster/v1p2/results/does_not_exist/"))
resp = oneroster_results.result_detail_v1p2_roster(req, sourced_id="does_not_exist")
assert resp.status_code == 404, resp.status_code
err = json.loads(resp.content)
assert err.get("error") == "not_found", err
assert err.get("sourcedId") == "does_not_exist", err
print("[T2-4] detail 404 OK")

# Case 5: ?studentSourcedId= filter (no error even if zero matches)
req = _bearer(rf.get("/api/roster/v1p2/results/?studentSourcedId=999999"))
resp = oneroster_results.results_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
# All returned rows should match the requested studentSourcedId.
for r in body["results"]:
    assert (r.get("student") or {}).get("sourcedId") == "999999", r
print("[T2-5] studentSourcedId filter OK (matched %d)" % len(body["results"]))

# Case 6: ?lineItemSourcedId= filter
req = _bearer(rf.get("/api/roster/v1p2/results/?lineItemSourcedId=abc"))
resp = oneroster_results.results_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
for r in body["results"]:
    assert (r.get("lineItem") or {}).get("sourcedId") == "abc", r
print("[T2-6] lineItemSourcedId filter OK (matched %d)" % len(body["results"]))

# Case 7: pagination
req = _bearer(rf.get("/api/roster/v1p2/results/?limit=5&offset=0"))
resp = oneroster_results.results_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert len(body["results"]) <= 5, len(body["results"])
print("[T2-7] pagination OK")

# Case 8: X-Total-Count header present
assert "X-Total-Count" in resp.headers or resp.has_header("X-Total-Count"), dict(resp.headers)
total_count = resp["X-Total-Count"]
assert total_count.isdigit(), total_count
print("[T2-8] X-Total-Count header present (= %s)" % total_count)

print("ALL T2 CASES OK")
