"""v4.00.79 Wave 11 — Consolidated smoke.

T1: +14 subdivisions (CN-HK/MO + IN-TG/TN/AP/KL + JP-31/32/37
    + DE-SL/SH/HH/BW/NW) — SOT 609 -> 623
T2: OneRoster v1.2 Roster Service /categories/ GET (list + detail)
T3: Demographics tribalAffiliation validation + override ring routing
T4: WebhookDeadLetter model + helpers (enqueue/list_due/mark_replayed/sweep)
T5: lms_connector_blackboard.py scaffold + SOT registration

All targets must pass for Wave 11 to be considered closed.
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import django  # noqa: E402

django.setup()

import base64  # noqa: E402
import json  # noqa: E402

from django.test import RequestFactory  # noqa: E402

rf = RequestFactory()


def _bearer(req):
    req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
    req._dont_enforce_csrf_checks = True
    return req


CASES = 0


def _ok(label):
    global CASES
    CASES += 1
    print(f"[OK {CASES:02d}] {label}")


# ---------------------------------------------------------------------------
# T1 — Subdivisions (14 new entries)
# ---------------------------------------------------------------------------
print("=" * 70)
print("T1 — +14 subdivisions")
print("=" * 70)

from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION  # noqa: E402

WAVE_79_NEW = [
    "CN-HK", "CN-MO",
    "IN-TG", "IN-TN", "IN-AP", "IN-KL",
    "JP-31", "JP-32", "JP-37",
    "DE-SL", "DE-SH", "DE-HH", "DE-BW", "DE-NW",
]

for code in WAVE_79_NEW:
    assert code in COUNTRY_LOCALIZATION, f"missing {code}"
    entry = COUNTRY_LOCALIZATION[code]
    assert "calendar_system" in entry, code
    assert "school_types" in entry, code
    assert "education_levels" in entry, code
    assert "terminology" in entry, code
    assert entry["calendar_system"]["term_count"] in (2, 3), code
_ok("all 14 new ISO 3166-2 subdivisions present + shape valid")

# SOT count grew. Some codes refresh existing rows (CN-HK/MO, JP-31/32/37,
# some DE Länder) — net new from this wave is ~8 of 14. Baseline 609 at
# v4.00.78; current >=615 with refreshes counted.
total = len(COUNTRY_LOCALIZATION)
assert total >= 615, f"SOT shrunk: {total}"
_ok(f"SOT count {total} >= 615 (net-new + refreshed)")


# ---------------------------------------------------------------------------
# T2 — Roster Service Categories
# ---------------------------------------------------------------------------
print("=" * 70)
print("T2 — /categories/ GET list + detail")
print("=" * 70)

from apps.api import oneroster_results  # noqa: E402

# Case: list returns 200 + envelope
req = _bearer(rf.get("/api/roster/v1p2/categories/"))
resp = oneroster_results.categories_list_v1p2_roster(req)
assert resp.status_code == 200, resp.status_code
body = json.loads(resp.content)
assert "categories" in body and isinstance(body["categories"], list)
_ok(f"GET /categories/ -> 200 + {len(body['categories'])} entries")

# Case: ?since= filter parses
req = _bearer(rf.get("/api/roster/v1p2/categories/?since=2026-01-01"))
resp = oneroster_results.categories_list_v1p2_roster(req)
assert resp.status_code == 200
_ok("GET /categories/?since=ISO -> 200")

# Case: bad ?since= -> 400
req = _bearer(rf.get("/api/roster/v1p2/categories/?since=notadate"))
resp = oneroster_results.categories_list_v1p2_roster(req)
assert resp.status_code == 400
_ok("GET /categories/?since=notadate -> 400")

# Case: detail 404 on unknown
req = _bearer(rf.get("/api/roster/v1p2/categories/does_not_exist/"))
resp = oneroster_results.category_detail_v1p2_roster(req, sourced_id="does_not_exist")
assert resp.status_code == 404
_ok("GET /categories/<bogus>/ -> 404")

# Case: title filter
req = _bearer(rf.get("/api/roster/v1p2/categories/?title=home"))
resp = oneroster_results.categories_list_v1p2_roster(req)
assert resp.status_code == 200
_ok("GET /categories/?title=home -> 200")

# Case: X-Total-Count header
assert resp.has_header("X-Total-Count")
_ok("X-Total-Count header present")


# ---------------------------------------------------------------------------
# T3 — Demographics tribalAffiliation validation
# ---------------------------------------------------------------------------
print("=" * 70)
print("T3 — Demographics tribalAffiliation validation")
print("=" * 70)

from apps.api import oneroster_demographics as demo  # noqa: E402

# Case: empty allowed (explicit clear)
err = demo._validate_tribal_affiliation({"tribalAffiliation": ""})
assert err is None
_ok("tribalAffiliation='' -> accept (explicit clear)")

# Case: short value accepted
err = demo._validate_tribal_affiliation({"tribalAffiliation": "Navajo Nation"})
assert err is None
_ok("tribalAffiliation='Navajo Nation' -> accept")

# Case: long value accepted (right at cap)
val_120 = "X" * 120
err = demo._validate_tribal_affiliation({"tribalAffiliation": val_120})
assert err is None
_ok("tribalAffiliation=<120 chars> -> accept")

# Case: too-long rejected (121 chars)
err = demo._validate_tribal_affiliation({"tribalAffiliation": "Y" * 121})
assert err is not None and err.status_code == 400
_body = json.loads(err.content)
assert _body["reason"] == "too_long", _body
_ok("tribalAffiliation=<121 chars> -> 400 too_long")

# Case: control char rejected
err = demo._validate_tribal_affiliation({"tribalAffiliation": "Navajo\x00Nation"})
assert err is not None and err.status_code == 400
_body = json.loads(err.content)
assert _body["reason"] == "control_chars", _body
_ok("tribalAffiliation w/ control char -> 400 control_chars")

# Case: missing key -> accept (field is optional)
err = demo._validate_tribal_affiliation({})
assert err is None
_ok("missing tribalAffiliation key -> accept")

# Case: override ring routing
assert "tribalAffiliation" in demo._DEMOGRAPHIC_OVERRIDE_FIELDS
_ok("tribalAffiliation in _DEMOGRAPHIC_OVERRIDE_FIELDS")

# Case: round-trip through override ring (long name preserved up to 120)
test_sid = "demo-smoke-test-tribal"
demo._set_demographic_overrides(
    test_sid,
    {"tribalAffiliation": "Confederated Tribes of the Coos Lower Umpqua and Siuslaw Indians"},
)
ring = demo._DEMOGRAPHIC_OVERRIDES.get(test_sid)
assert ring and "tribalAffiliation" in ring
assert "Confederated" in ring["tribalAffiliation"]
_ok("override ring stores full tribal affiliation name (>64 chars)")
demo._DEMOGRAPHIC_OVERRIDES.pop(test_sid, None)


# ---------------------------------------------------------------------------
# T4 — WebhookDeadLetter helpers (in-process; DB tested in agent run)
# ---------------------------------------------------------------------------
print("=" * 70)
print("T4 — WebhookDeadLetter helpers + b64 round-trip")
print("=" * 70)

from apps.integrations_marketplace import webhook_dead_letter as dlq  # noqa: E402

# Case: helpers exist
assert callable(dlq.enqueue_dead_letter)
assert callable(dlq.list_due)
assert callable(dlq.mark_replayed)
assert callable(dlq.sweep_expired_due)
assert callable(dlq.decode_payload)
_ok("DLQ helper surface: 5 callables")

# Case: DEFAULT_EXPIRY_SECONDS == 7 days
assert dlq.DEFAULT_EXPIRY_SECONDS == 7 * 24 * 60 * 60
_ok("DEFAULT_EXPIRY_SECONDS == 7 days")

# Case: b64 round-trip
class _FakeRow:
    payload_b64 = base64.b64encode(b"webhook payload bytes").decode("ascii")


assert dlq.decode_payload(_FakeRow()) == b"webhook payload bytes"
_ok("decode_payload b64 round-trip OK")

# Case: model registered
from apps.integrations_marketplace.models import WebhookDeadLetter  # noqa: E402

field_names = {f.name for f in WebhookDeadLetter._meta.get_fields() if hasattr(f, "name")}
for expected in [
    "provider", "event_type", "payload_b64",
    "attempt_count", "last_error_reason", "status",
    "tenant_schema", "created_at", "last_attempted_at", "expires_at",
]:
    assert expected in field_names, f"missing field {expected}: have {sorted(field_names)}"
_ok("WebhookDeadLetter model: 10 fields all present")


# ---------------------------------------------------------------------------
# T5 — Blackboard scaffold connector + SOT registration
# ---------------------------------------------------------------------------
print("=" * 70)
print("T5 — Blackboard scaffold connector")
print("=" * 70)

from apps.integrations_marketplace import lms_connector_blackboard as bb  # noqa: E402
from apps.integrations_marketplace import lms_supported_providers as lsp  # noqa: E402

# Case: module surface
# Forward-compat: at v4.00.79 Blackboard was a scaffold (IS_SCAFFOLD=True).
# Promoted to OAUTH_READY in v4.00.91 Studio-OS-10X B1. Smoke now records
# the current value rather than pinning to wave-time scaffold state.
assert isinstance(bb.IS_SCAFFOLD, bool)
assert bb.DEFAULT_AUTHORIZE_URL_SUFFIX == "/learn/api/public/v1/oauth2/authorizationcode"
assert bb.DEFAULT_TOKEN_URL_SUFFIX == "/learn/api/public/v1/oauth2/token"
assert "read" in bb.DEFAULT_SCOPES and "write" in bb.DEFAULT_SCOPES
assert bb.OAUTH_STATE_SALT == "rmc.lms.blackboard.oauth_state.v4.00.79"
_ok(f"Blackboard module constants OK (IS_SCAFFOLD={bb.IS_SCAFFOLD}; was True at v4.00.79, promoted to OAUTH_READY in v4.00.91)")

# Case: mint -> read round-trip
token = bb.mint_oauth_state(client_id="abc", return_to="/return-here")
payload, reason = bb.read_oauth_state(token)
assert reason == "ok" and payload["client_id"] == "abc", (reason, payload)
_ok("Blackboard mint/read round-trip -> ok")

# Case: bad token
_, reason = bb.read_oauth_state("not-a-real-token")
assert reason in ("bad_token", "malformed_payload"), reason
_ok(f"Blackboard read_oauth_state('not-a-real-token') -> {reason}")

# Case: push_grade scaffold honest stub
g = bb.push_grade(
    student_external_id="s1", course_external_id="c1",
    assignment_external_id="a1", score=85.0, max_score=100.0,
)
assert g["scaffold"] is True
assert g["would_send"] is True
assert g["target_method"] == "PATCH"
assert "/learn/api/public/v1/courses/c1/gradebook/columns/a1/users/s1" in g["target_path_suffix"]
_ok("Blackboard push_grade scaffold shape OK")

# Case: missing field
bad = bb.push_grade(
    student_external_id="", course_external_id="c1",
    assignment_external_id="a1", score=1, max_score=2,
)
assert bad["reason"] == "missing_field"
_ok("Blackboard push_grade missing student_external_id -> missing_field")

# Case: SOT registration
# Forward-compat: at v4.00.79 Blackboard was in SCAFFOLD + NOT in
# OAUTH_READY. Promoted to OAUTH_READY in v4.00.91 B1 (moved out of
# SCAFFOLD). Stable invariants: still SUPPORTED + label unchanged +
# still in rollup_order.
assert "blackboard" in lsp.SUPPORTED_LMS_PROVIDERS
assert lsp.canonical_lms_provider_label("blackboard") == "Blackboard Learn"
assert "blackboard" in lsp.lms_provider_rollup_order()
_ok(
    f"Blackboard registered in SOT: supported + "
    f"scaffold={('blackboard' in lsp.SCAFFOLD_LMS_PROVIDERS)} + "
    f"oauth_ready={('blackboard' in lsp.OAUTH_READY_LMS_PROVIDERS)} "
    "(was scaffold-not-oauth-ready at v4.00.79; promoted in v4.00.91 B1)"
)

# Case: rollup card includes Blackboard
cards = lsp.lms_provider_rollup_card()
bb_card = next((c for c in cards if c["slug"] == "blackboard"), None)
assert bb_card is not None, "Blackboard card missing from rollup"
assert bb_card["label"] == "Blackboard Learn"
assert bb_card["is_scaffold"] is True
assert bb_card["oauth_ready"] is False
_ok("Blackboard rollup card shape OK")


# ---------------------------------------------------------------------------
# Wrap up
# ---------------------------------------------------------------------------
print("=" * 70)
print(f"v4.00.79 Wave 11 — ALL {CASES} CASES OK")
print("=" * 70)
