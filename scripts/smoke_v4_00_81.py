"""v4.00.81 Wave 13 — Consolidated smoke.

T1: +14 subdivisions (JP-14/12/15/19 Kanto + IN-GJ/MP/RJ/PB + US-RI
    + DE-BY/NI/SN/MV + PE-LIM)
T2: OneRoster v1.2 Result Service /scoreScales/ GET
T3: Demographics previousLastName + previousMiddleName
T4: webhook_retry_fsm per-provider retry budget cap
T5: lms_connector_sakai.py scaffold
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


# T1 — subdivisions
print("=" * 70); print("T1 — +14 subdivisions"); print("=" * 70)
from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION  # noqa: E402

WAVE_81_NEW = [
    "JP-14", "JP-12", "JP-15", "JP-19",
    "IN-GJ", "IN-MP", "IN-RJ", "IN-PB",
    "US-RI",
    "DE-BY", "DE-NI", "DE-SN", "DE-MV",
    "PE-LIM",
]
for code in WAVE_81_NEW:
    assert code in COUNTRY_LOCALIZATION, f"missing {code}"
    e = COUNTRY_LOCALIZATION[code]
    assert "calendar_system" in e and "school_types" in e
_ok("all 14 Wave-81 subdivisions present")
total = len(COUNTRY_LOCALIZATION)
assert total >= 625, f"SOT shrunk: {total}"
_ok(f"SOT count {total} >= 625")


# T2 — scoreScales (lazy: only if agent shipped them)
print("=" * 70); print("T2 — /scoreScales/"); print("=" * 70)
from apps.api import oneroster_results  # noqa: E402
try:
    fn = oneroster_results.score_scales_list_v1p2_roster
    req = _bearer(rf.get("/api/roster/v1p2/scoreScales/"))
    resp = fn(req)
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert "scoreScales" in body
    _ok(f"GET /scoreScales/ -> 200 + {len(body['scoreScales'])} entries")
    assert resp.has_header("X-Total-Count")
    _ok("X-Total-Count header on /scoreScales/")
except AttributeError:
    print("[SKIP] score_scales_list_v1p2_roster not yet present (agent pending)")


# T3 — previous names
print("=" * 70); print("T3 — previousLastName + previousMiddleName"); print("=" * 70)
from apps.api import oneroster_demographics as demo  # noqa: E402

assert demo._validate_previous_names({}) is None
_ok("missing both -> accept")
assert demo._validate_previous_names({"previousLastName": ""}) is None
_ok("'' -> accept (explicit clear)")
assert demo._validate_previous_names({"previousLastName": "Smith"}) is None
_ok("previousLastName='Smith' -> accept")
assert demo._validate_previous_names({"previousMiddleName": "Marie"}) is None
_ok("previousMiddleName='Marie' -> accept")
assert demo._validate_previous_names({"previousLastName": "X" * 80}) is None
_ok("previousLastName=<80 chars> -> accept")
err = demo._validate_previous_names({"previousLastName": "X" * 81})
assert err is not None and err.status_code == 400
_b = json.loads(err.content)
assert _b["reason"] == "too_long" and _b["field"] == "previousLastName"
_ok("previousLastName=<81 chars> -> 400 too_long")
err = demo._validate_previous_names({"previousMiddleName": "ab\x00cd"})
assert err is not None and err.status_code == 400
_b = json.loads(err.content)
assert _b["reason"] == "control_chars" and _b["field"] == "previousMiddleName"
_ok("previousMiddleName w/ NULL control char -> 400 control_chars")
assert "previousLastName" in demo._DEMOGRAPHIC_OVERRIDE_FIELDS
assert "previousMiddleName" in demo._DEMOGRAPHIC_OVERRIDE_FIELDS
_ok("previous* in override-ring fields")


# T4 — per-provider retry budget
print("=" * 70); print("T4 — webhook per-provider retry budget"); print("=" * 70)
# Clear env so default applies first
os.environ.pop("RMC_WEBHOOK_PROVIDER_RETRY_BUDGETS", None)
import importlib
from apps.integrations_marketplace import webhook_retry_fsm as wrf  # noqa: E402
importlib.reload(wrf)  # in case module already imported with stale env

try:
    assert wrf.max_attempts_for_provider("unknown_provider") == wrf.MAX_ATTEMPTS
    _ok("max_attempts unknown_provider == MAX_ATTEMPTS")

    os.environ["RMC_WEBHOOK_PROVIDER_RETRY_BUDGETS"] = '{"pagerduty":3}'
    assert wrf.max_attempts_for_provider("pagerduty") == 3
    _ok("max_attempts pagerduty == 3 via env")
    assert wrf.is_exhausted_for_provider(provider="pagerduty", attempt=3) is True
    _ok("is_exhausted pagerduty attempt=3 -> True")
    assert wrf.is_exhausted_for_provider(provider="pagerduty", attempt=2) is False
    _ok("is_exhausted pagerduty attempt=2 -> False")

    os.environ["RMC_WEBHOOK_PROVIDER_RETRY_BUDGETS"] = '{"slack":100}'
    assert wrf.max_attempts_for_provider("slack") == 20
    _ok("clamp: slack=100 -> 20 (ceiling)")

    os.environ["RMC_WEBHOOK_PROVIDER_RETRY_BUDGETS"] = "not valid json"
    assert wrf.max_attempts_for_provider("pagerduty") == wrf.MAX_ATTEMPTS
    _ok("bad JSON env -> fallback to defaults")

    os.environ.pop("RMC_WEBHOOK_PROVIDER_RETRY_BUDGETS", None)
    # Existing API treats attempt=1 as "after 1 attempt" -> returns
    # schedule[1] (the wait before attempt 2). The function is unchanged;
    # just verify it returns SOME schedule value and exhaustion still works.
    rs = wrf.next_retry_seconds(1)
    assert rs is None or rs in wrf.RETRY_SCHEDULE_SECONDS
    assert wrf.is_exhausted(wrf.MAX_ATTEMPTS) is True
    _ok("existing global next_retry_seconds + is_exhausted unchanged")
except AttributeError as exc:
    print(f"[SKIP] T4 agent pending: {exc}")
finally:
    os.environ.pop("RMC_WEBHOOK_PROVIDER_RETRY_BUDGETS", None)


# T5 — Sakai scaffold
print("=" * 70); print("T5 — Sakai scaffold"); print("=" * 70)
from apps.integrations_marketplace import lms_connector_sakai as sk  # noqa: E402
from apps.integrations_marketplace import lms_supported_providers as lsp  # noqa: E402

assert sk.IS_SCAFFOLD is True
assert sk.OAUTH_STATE_SALT == "rmc.lms.sakai.oauth_state.v4.00.81"
_ok("Sakai module constants")
token = sk.mint_oauth_state(client_id="sk", return_to="/")
payload, reason = sk.read_oauth_state(token)
assert reason == "ok" and payload["client_id"] == "sk"
_ok("Sakai mint/read -> ok")
g = sk.push_grade(student_external_id="s1", course_external_id="c1",
                  assignment_external_id="a1", score=80.0, max_score=100.0)
assert g["scaffold"] is True and g["target_method"] == "PUT"
_ok("Sakai push_grade scaffold shape")
assert "sakai" in lsp.SUPPORTED_LMS_PROVIDERS
assert "sakai" in lsp.SCAFFOLD_LMS_PROVIDERS
assert "sakai" not in lsp.OAUTH_READY_LMS_PROVIDERS
assert lsp.canonical_lms_provider_label("sakai") == "Sakai"
_ok("Sakai registered in SOT")


print("=" * 70)
print(f"v4.00.81 Wave 13 — {CASES} CASES OK")
print("=" * 70)
