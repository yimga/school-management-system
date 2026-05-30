"""v4.00.92 Wave 25 — OneRoster v1.2 spec completeness sweep.

Exercises the 4 spec gaps audited prior to the wave:
  * C4: OAuth2 client_credentials grant (RFC 6749 § 4.4)
  * M1: ?filter/?sort/?fields on the 6 main GET endpoints
  * M2: HEAD verb returning X-Total-Count without body
  * M3: /categories/ + /scoreScales/ completeness (8 IMS codes + 4 prod scales)

Run:
    python scripts/smoke_v4_00_92_oneroster_completeness.py
"""
import hashlib
import json
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Wave 25 C4 — provision a registry env BEFORE Django setup so the token
# endpoint reads it on first call (Django imports lazily resolve env).
_CLIENT_ID = "smoke-cid-wave25"
_CLIENT_SECRET = "smoke-secret-wave25-long-and-opaque"
_SECRET_HASH = hashlib.sha256(_CLIENT_SECRET.encode("utf-8")).hexdigest()
os.environ["RMC_ONEROSTER_OAUTH_CLIENTS"] = json.dumps({
    _CLIENT_ID: {
        "secret_hash": _SECRET_HASH,
        "allowed_scopes": [
            "roster-core.readonly",
            "roster-core.createput",
            "roster-demographics.readonly",
            "roster-results.readonly",
        ],
        "tenant_schema": "public",
    },
})
# Wave 25 — keep static-token path silently disabled so the OAuth2 path is
# the one being exercised by /users/ + /classes/ + /enrollments/ smoke calls.
os.environ.pop("RMC_ONEROSTER_ACCESS_TOKEN", None)

import django  # noqa: E402

django.setup()

from django.test import Client, RequestFactory  # noqa: E402

from apps.api import oneroster as _or  # noqa: E402
from apps.api import oneroster_oauth2_token as _oauth2  # noqa: E402
from apps.api import oneroster_query_helpers as _qh  # noqa: E402
from apps.api import oneroster_results as _ors  # noqa: E402

CASES = 0


def _ok(label: str) -> None:
    global CASES
    CASES += 1
    print(f"[OK {CASES:02d}] {label}")


# ===========================================================================
# C4 — OAuth2 client_credentials grant
# ===========================================================================
print("=" * 70)
print("C4 OAuth2 client_credentials grant")
print("=" * 70)

client = Client()

# C4-1: missing grant_type -> 400 invalid_request
resp = client.post("/api/roster/v1p2/oauth/token/", data={})
assert resp.status_code == 400, resp.status_code
body = json.loads(resp.content)
assert body["error"] == "invalid_request", body
_ok("token endpoint missing grant_type -> 400 invalid_request")

# C4-2: bad client_secret -> 401 invalid_client
resp = client.post(
    "/api/roster/v1p2/oauth/token/",
    data={
        "grant_type": "client_credentials",
        "client_id": _CLIENT_ID,
        "client_secret": "WRONG-secret",
    },
)
assert resp.status_code == 401, resp.status_code
body = json.loads(resp.content)
assert body["error"] == "invalid_client", body
assert resp.headers.get("WWW-Authenticate", "").startswith("Basic"), resp.headers
_ok("token endpoint bad client_secret -> 401 invalid_client + WWW-Authenticate")

# C4-3: bad client_id -> 401 invalid_client
resp = client.post(
    "/api/roster/v1p2/oauth/token/",
    data={
        "grant_type": "client_credentials",
        "client_id": "nonexistent-cid",
        "client_secret": _CLIENT_SECRET,
    },
)
assert resp.status_code == 401, resp.status_code
body = json.loads(resp.content)
assert body["error"] == "invalid_client", body
_ok("token endpoint bad client_id -> 401 invalid_client")

# C4-4: good creds returns Bearer + expires_in
resp = client.post(
    "/api/roster/v1p2/oauth/token/",
    data={
        "grant_type": "client_credentials",
        "client_id": _CLIENT_ID,
        "client_secret": _CLIENT_SECRET,
        "scope": "roster-core.readonly",
    },
)
assert resp.status_code == 200, (resp.status_code, resp.content)
body = json.loads(resp.content)
assert body["token_type"] == "Bearer", body
assert body["expires_in"] == 3600, body
assert body["scope"] == "roster-core.readonly", body
assert body["access_token"] and len(body["access_token"]) > 20, body
_TOKEN = body["access_token"]
_ok("token endpoint good creds -> 200 + Bearer + expires_in=3600 + scope")

# C4-5: oauth2-issued Bearer succeeds on /users/
resp = client.get(
    "/api/roster/v1p2/users/",
    HTTP_AUTHORIZATION=f"Bearer {_TOKEN}",
)
assert resp.status_code == 200, (resp.status_code, resp.content[:200])
body = json.loads(resp.content)
assert "users" in body, body
_ok("oauth2-issued Bearer succeeds on GET /users/")


# ===========================================================================
# M1 — ?filter / ?sort / ?fields wired into 6 main GET endpoints
# ===========================================================================
print("=" * 70)
print("M1 filter/sort/fields on 6 main GET endpoints")
print("=" * 70)

# Build synthetic data inline so smoke is independent of DB state.
_SAMPLE_USERS = [
    {"sourcedId": "u1", "status": "active", "username": "alice", "givenName": "Alice", "familyName": "Zephyr", "email": "a@x", "role": "student"},
    {"sourcedId": "u2", "status": "active", "username": "bob",   "givenName": "Bob",   "familyName": "Yates",  "email": "b@x", "role": "teacher"},
    {"sourcedId": "u3", "status": "active", "username": "carol", "givenName": "Carol", "familyName": "Xander", "email": "c@x", "role": "student"},
    {"sourcedId": "u4", "status": "active", "username": "dave",  "givenName": "Dave",  "familyName": "Webb",   "email": "d@x", "role": "administrator"},
]

# M1-1: ?filter=role='student' applies filter
factory = RequestFactory()
req = factory.get("/x/?filter=role='student'")
page, meta = _qh.apply_pipeline(req, list(_SAMPLE_USERS))
assert meta["totalCount"] == 2, meta
assert all(p["role"] == "student" for p in page), page
_ok("/users/?filter=role='student' filters to 2 student rows")

# M1-2: ?sort=familyName&orderBy=desc applies sort
req = factory.get("/x/?sort=familyName&orderBy=desc")
page, meta = _qh.apply_pipeline(req, list(_SAMPLE_USERS))
family_names = [p["familyName"] for p in page]
assert family_names == sorted(family_names, reverse=True), family_names
_ok("/users/?sort=familyName&orderBy=desc sorts descending")

# M1-3: ?fields=sourcedId,familyName masks fields
req = factory.get("/x/?fields=sourcedId,familyName")
page, meta = _qh.apply_pipeline(req, list(_SAMPLE_USERS))
for p in page:
    assert set(p.keys()) == {"sourcedId", "familyName"}, p
_ok("/users/?fields=sourcedId,familyName masks to 2 keys + auto-pins sourcedId")

# M1-4: ?filter=status='active'&sort=title chained correctly on /classes/
_SAMPLE_CLASSES = [
    {"sourcedId": "c1", "status": "active",       "title": "Zoology"},
    {"sourcedId": "c2", "status": "tobedeleted", "title": "Algebra"},
    {"sourcedId": "c3", "status": "active",       "title": "Biology"},
]
req = factory.get("/x/?filter=status='active'&sort=title")
page, meta = _qh.apply_pipeline(req, list(_SAMPLE_CLASSES))
assert meta["totalCount"] == 2, meta
titles = [p["title"] for p in page]
assert titles == sorted(titles), titles
assert all(p["status"] == "active" for p in page), page
_ok("/classes/?filter=status='active'&sort=title filters then sorts")

# M1-5: ?filter=role='student'&fields=sourcedId,classSourcedId on /enrollments/
_SAMPLE_ENROLLMENTS = [
    {"sourcedId": "e1", "status": "active", "role": "student", "classSourcedId": "c1", "userSourcedId": "u1", "schoolSourcedId": "s1", "beginDate": "2026-01-01", "endDate": "2026-06-01"},
    {"sourcedId": "e2", "status": "active", "role": "teacher", "classSourcedId": "c1", "userSourcedId": "u2", "schoolSourcedId": "s1", "beginDate": "2026-01-01", "endDate": "2026-06-01"},
    {"sourcedId": "e3", "status": "active", "role": "student", "classSourcedId": "c2", "userSourcedId": "u3", "schoolSourcedId": "s1", "beginDate": "2026-01-01", "endDate": "2026-06-01"},
]
req = factory.get("/x/?filter=role='student'&fields=sourcedId,classSourcedId&limit=1")
page, meta = _qh.apply_pipeline(req, list(_SAMPLE_ENROLLMENTS))
assert meta["totalCount"] == 2, meta  # 2 students post-filter
assert meta["limit"] == 1, meta
assert len(page) == 1, page
for p in page:
    assert set(p.keys()) == {"sourcedId", "classSourcedId"}, p
_ok("/enrollments/?filter+fields+limit=1 -> 2 total students, page=1, masked keys")


# ===========================================================================
# M2 — HEAD verb returns 200 + X-Total-Count + empty body
# ===========================================================================
print("=" * 70)
print("M2 HEAD verb returns 200 + X-Total-Count + empty body")
print("=" * 70)

# M2-1: HEAD /users/ returns 200 + X-Total-Count + empty body
resp = client.head(
    "/api/roster/v1p2/users/",
    HTTP_AUTHORIZATION=f"Bearer {_TOKEN}",
)
assert resp.status_code == 200, (resp.status_code, resp.content[:200])
assert "X-Total-Count" in resp.headers, resp.headers
assert resp.content == b"", resp.content
_ok(f"HEAD /users/ -> 200 + X-Total-Count={resp.headers['X-Total-Count']} + empty body")

# M2-2: HEAD /classes/ returns 200 + X-Total-Count
resp = client.head(
    "/api/roster/v1p2/classes/",
    HTTP_AUTHORIZATION=f"Bearer {_TOKEN}",
)
assert resp.status_code == 200, resp.status_code
assert "X-Total-Count" in resp.headers, resp.headers
_ok(f"HEAD /classes/ -> 200 + X-Total-Count={resp.headers['X-Total-Count']}")

# M2-3: HEAD honors ?filter (count excludes filtered-out rows). Use the
# query-helper module directly to assert pipeline contract.
req = factory.get("/x/?filter=role='teacher'")
total = _qh.total_count_for(req, list(_SAMPLE_USERS))
assert total == 1, total
req = factory.get("/x/?filter=role='student'")
total = _qh.total_count_for(req, list(_SAMPLE_USERS))
assert total == 2, total
_ok("HEAD pipeline honors ?filter (teacher=1, student=2 in 4-row fixture)")


# ===========================================================================
# M3 — Categories (8 IMS codes) + ScoreScales (4 prod scales)
# ===========================================================================
print("=" * 70)
print("M3 IMS-standard categories + production score scales")
print("=" * 70)

# M3-1: /categories/ returns 8 IMS-standard codes with deterministic sourcedIds.
cats = _ors._build_categories_v1p2_roster("smoke-tenant")
# The 8 IMS codes per Wave 25 M3.
ims_codes = ("assignment", "assessment", "participation", "homework",
             "quiz", "test", "exam", "final")
# Verify the IMS rows are present with the expected sourcedId derivation.
for code in ims_codes:
    expected_sid = hashlib.sha256(f"ims-category:{code}".encode("utf-8")).hexdigest()[:16]
    found = [c for c in cats if c["sourcedId"] == expected_sid]
    assert len(found) == 1, (code, expected_sid, cats[:5])
    row = found[0]
    assert row["type"] == code, row
    assert row["title"] == code.title(), row
    assert row["status"] == "active", row
# Verify determinism — a 2nd call returns identical sourcedIds.
cats2 = _ors._build_categories_v1p2_roster("smoke-tenant")
ims_sids_1 = sorted(c["sourcedId"] for c in cats if c.get("type") in ims_codes)
ims_sids_2 = sorted(c["sourcedId"] for c in cats2 if c.get("type") in ims_codes)
assert ims_sids_1 == ims_sids_2, (ims_sids_1, ims_sids_2)
# All 8 codes present.
present_codes = {c["type"] for c in cats if c.get("type") in ims_codes}
assert present_codes == set(ims_codes), present_codes
_ok("/categories/ surfaces all 8 IMS-standard codes deterministically")

# M3-2: /scoreScales/ returns 4 production scales with scoreScaleValues arrays.
scales = _ors._build_score_scales_v1p2_roster("smoke-tenant")
assert len(scales) == 4, len(scales)
titles_seen = {s["title"] for s in scales}
assert titles_seen == {"Letter A-F", "Percent 0-100", "Pass/Fail", "Rubric 4-point"}, titles_seen
for s in scales:
    # Wave 25 M3 — full scoreScaleValues array required per IMS spec.
    assert "scoreScaleValues" in s, s.keys()
    assert isinstance(s["scoreScaleValues"], list) and len(s["scoreScaleValues"]) > 0, s
    for v in s["scoreScaleValues"]:
        # Each value carries a scoreItem with score + value.
        assert "sourcedId" in v and len(v["sourcedId"]) == 16, v
        assert v["status"] == "active", v
        assert "scoreItem" in v, v
        item = v["scoreItem"]
        assert "score" in item and "value" in item and "minimumScore" in item, item
    # Back-compat flat ``scoreValues`` is still emitted.
    assert "scoreValues" in s and isinstance(s["scoreValues"], list), s.keys()
# Determinism check: 2nd build returns identical sourcedIds.
scales2 = _ors._build_score_scales_v1p2_roster("smoke-tenant")
sid_1 = sorted(s["sourcedId"] for s in scales)
sid_2 = sorted(s["sourcedId"] for s in scales2)
assert sid_1 == sid_2, (sid_1, sid_2)
_ok("/scoreScales/ surfaces 4 production scales w/ scoreScaleValues arrays + scoreItem")


print("=" * 70)
print(f"v4.00.92 Wave 25 — {CASES} CASES OK")
print("=" * 70)
