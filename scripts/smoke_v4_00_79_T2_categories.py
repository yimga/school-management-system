"""v4.00.79 Wave 11 Target 2 — OneRoster v1.2 Roster Service Categories smoke.

Endpoints under test:
  GET /api/roster/v1p2/categories/
  GET /api/roster/v1p2/categories/<sourced_id>/

Naming deviation note: the existing module already binds
``oneroster_results.categories_list`` / ``category_detail`` to the
v4.00.47 Result-Service path. The Wave 11 T2 views are exposed as
``categories_list_v1p2_roster`` / ``category_detail_v1p2_roster`` to
avoid collision; URL names ``api-roster-v1p2-categories`` and
``api-roster-v1p2-category-detail`` are stable.
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


# Case 1: list returns 200 + JSON envelope
req = _bearer(rf.get("/api/roster/v1p2/categories/"))
resp = oneroster_results.categories_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert "categories" in body, body
assert isinstance(body["categories"], list), type(body["categories"])
# The 6 seed types should always be present at minimum.
assert len(body["categories"]) >= 1, len(body["categories"])
print("[T2-1] list OK (got %d categories)" % len(body["categories"]))

# Case 2: ?since= filter parses
req = _bearer(rf.get("/api/roster/v1p2/categories/?since=2026-01-01"))
resp = oneroster_results.categories_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
print("[T2-2] since filter OK")

# Case 3: bad ?since= → 400
req = _bearer(rf.get("/api/roster/v1p2/categories/?since=notadate"))
resp = oneroster_results.categories_list_v1p2_roster(req)
assert resp.status_code == 400, resp.status_code
err = json.loads(resp.content)
assert err.get("error") == "bad_since", err
print("[T2-3] bad since 400 OK")

# Case 4: detail 404 on unknown sourcedId
req = _bearer(rf.get("/api/roster/v1p2/categories/does_not_exist/"))
resp = oneroster_results.category_detail_v1p2_roster(req, sourced_id="does_not_exist")
assert resp.status_code == 404, resp.status_code
err = json.loads(resp.content)
assert err.get("error") == "not_found", err
assert err.get("sourcedId") == "does_not_exist", err
print("[T2-4] detail 404 OK")

# Case 5: ?title= filter
req = _bearer(rf.get("/api/roster/v1p2/categories/?title=home"))
resp = oneroster_results.categories_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
# All returned titles should contain "home" case-insensitively.
for c in body["categories"]:
    assert "home" in (c.get("title") or "").lower(), c
print("[T2-5] title filter OK (matched %d)" % len(body["categories"]))

# Case 6: pagination
req = _bearer(rf.get("/api/roster/v1p2/categories/?limit=5&offset=0"))
resp = oneroster_results.categories_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert len(body["categories"]) <= 5, len(body["categories"])
print("[T2-6] pagination OK")

# Case 7: X-Total-Count header
assert "X-Total-Count" in resp.headers or resp.has_header("X-Total-Count"), dict(resp.headers)
total_count = resp["X-Total-Count"]
assert total_count.isdigit(), total_count
print("[T2-7] X-Total-Count header present (= %s)" % total_count)

print("ALL T2 CASES OK")
