"""v4.00.81 Wave 13 Target 2 — OneRoster v1.2 Roster Service ScoreScales smoke.

Endpoints under test:
  GET /api/roster/v1p2/scoreScales/
  GET /api/roster/v1p2/scoreScales/<sourced_id>/

Naming note: the existing module had no prior /scoreScales/ binding, but
the new views are nonetheless suffixed ``_v1p2_roster`` to mirror the
Wave 11 T2 categories rename pattern and Wave 12 T2 results rename
pattern. URL names ``api-roster-v1p2-score-scales`` and
``api-roster-v1p2-score-scale-detail`` are stable.

Data source: synthesized from a fixed set of 4 default standard scales
(letter A-F, percent 0-100, pass/fail, rubric 4-point) — there is no
dedicated ScoreScale model in this codebase (``apps.evals.GradingScale``
is school-tenant-scoped and uses a different schema), so the synthetic
default approach (per task spec) is used.
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


# Case 1: list returns 200 + JSON envelope {"scoreScales": [...]}
req = _bearer(rf.get("/api/roster/v1p2/scoreScales/"))
resp = oneroster_results.score_scales_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert "scoreScales" in body, body
assert isinstance(body["scoreScales"], list), type(body["scoreScales"])
assert len(body["scoreScales"]) >= 4, "expected at least 4 default scales, got %d" % len(body["scoreScales"])
# Per-scale projection shape check.
for s in body["scoreScales"]:
    assert "sourcedId" in s, s
    assert s.get("status") == "active", s
    assert "dateLastModified" in s, s
    assert "title" in s, s
    assert s.get("type") in ("categorical", "continuous"), s
    assert isinstance(s.get("scoreValues"), list), s
print("[T2-1] list OK (got %d scales)" % len(body["scoreScales"]))

# Case 2: ?type=categorical filter
req = _bearer(rf.get("/api/roster/v1p2/scoreScales/?type=categorical"))
resp = oneroster_results.score_scales_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert len(body["scoreScales"]) > 0, body
for s in body["scoreScales"]:
    assert s.get("type") == "categorical", s
print("[T2-2] type=categorical filter OK (matched %d)" % len(body["scoreScales"]))

# Case 3: ?title=pass substring filter (case-insensitive)
req = _bearer(rf.get("/api/roster/v1p2/scoreScales/?title=pass"))
resp = oneroster_results.score_scales_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert len(body["scoreScales"]) >= 1, body
for s in body["scoreScales"]:
    assert "pass" in (s.get("title") or "").lower(), s
print("[T2-3] title=pass filter OK (matched %d)" % len(body["scoreScales"]))

# Case 4: bogus sourcedId → 404
req = _bearer(rf.get("/api/roster/v1p2/scoreScales/does_not_exist/"))
resp = oneroster_results.score_scale_detail_v1p2_roster(req, sourced_id="does_not_exist")
assert resp.status_code == 404, resp.status_code
err = json.loads(resp.content)
assert err.get("error") == "not_found", err
assert err.get("sourcedId") == "does_not_exist", err
print("[T2-4] detail 404 OK")

# Case 5: detail by first scale's sourcedId → 200 + envelope {"scoreScale": {...}}
req = _bearer(rf.get("/api/roster/v1p2/scoreScales/"))
resp = oneroster_results.score_scales_list_v1p2_roster(req)
body = json.loads(resp.content)
first = body["scoreScales"][0]
first_sid = first["sourcedId"]
first_title = first["title"]

req2 = _bearer(rf.get("/api/roster/v1p2/scoreScales/%s/" % first_sid))
resp2 = oneroster_results.score_scale_detail_v1p2_roster(req2, sourced_id=first_sid)
assert resp2.status_code == 200, resp2.status_code
body2 = json.loads(resp2.content)
assert "scoreScale" in body2, body2
assert body2["scoreScale"]["sourcedId"] == first_sid, body2
assert body2["scoreScale"]["title"] == first_title, body2
print("[T2-5] detail 200 by first sourcedId OK (title=%s)" % first_title)

# Case 6: X-Total-Count header present
req = _bearer(rf.get("/api/roster/v1p2/scoreScales/"))
resp = oneroster_results.score_scales_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
assert "X-Total-Count" in resp.headers or resp.has_header("X-Total-Count"), dict(resp.headers)
total_count = resp["X-Total-Count"]
assert total_count.isdigit(), total_count
assert int(total_count) >= 4, total_count
print("[T2-6] X-Total-Count header present (= %s)" % total_count)

# Case 7: pagination ?limit=1&offset=0 → 200 with 1 item, X-Total-Count > 1
req = _bearer(rf.get("/api/roster/v1p2/scoreScales/?limit=1&offset=0"))
resp = oneroster_results.score_scales_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert len(body["scoreScales"]) == 1, len(body["scoreScales"])
tc = int(resp["X-Total-Count"])
assert tc > 1, "expected X-Total-Count > 1 for paginated result, got %d" % tc
print("[T2-7] pagination limit=1 offset=0 OK (page=1, total=%d)" % tc)

# Bonus: ?type=<bad> → 400
req = _bearer(rf.get("/api/roster/v1p2/scoreScales/?type=bogus"))
resp = oneroster_results.score_scales_list_v1p2_roster(req)
assert resp.status_code == 400, resp.status_code
err = json.loads(resp.content)
assert err.get("error") == "bad_type", err
print("[T2-8] bad type 400 OK")

print("ALL T2 CASES OK")
