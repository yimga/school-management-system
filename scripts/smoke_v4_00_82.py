"""v4.00.82 Wave 14 — Consolidated smoke.

T1: +14 subdivisions (RU-MOS/VLG/TA/BA + PL-MA/WP + CZ-72 + AT-3/7 +
    HU-PE + RO-B + BG-22 + RS-00 + HR-21)
T2: OneRoster v1.2 /users/delta/ endpoint w/ ?modifiedSince= (per-T2 smoke)
T3: Demographics gradeLevels (CEDS) + subjectCodes (SCED)
T4: LMS OAuth Prometheus text exporter (per-T4 smoke)
T5: lms_connector_itslearning.py scaffold
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


# T1
print("=" * 70); print("T1 — +14 subdivisions"); print("=" * 70)
from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION  # noqa: E402

WAVE_82_NEW = [
    "RU-MOS", "RU-VLG", "RU-TA", "RU-BA",
    "PL-MA", "PL-WP", "CZ-72",
    "AT-3", "AT-7", "HU-PE",
    "RO-B", "BG-22", "RS-00", "HR-21",
]
for code in WAVE_82_NEW:
    assert code in COUNTRY_LOCALIZATION, f"missing {code}"
_ok("all 14 Wave-82 subdivisions present")
total = len(COUNTRY_LOCALIZATION)
assert total >= 632, f"SOT shrunk: {total}"
_ok(f"SOT count {total} >= 632")


# T3 — gradeLevels + subjectCodes
print("=" * 70); print("T3 — gradeLevels + subjectCodes"); print("=" * 70)
from apps.api import oneroster_demographics as demo  # noqa: E402

# gradeLevels
assert demo._validate_grade_levels({}) is None
_ok("missing gradeLevels -> accept")
assert demo._validate_grade_levels({"gradeLevels": ""}) is None
assert demo._validate_grade_levels({"gradeLevels": []}) is None
_ok("empty gradeLevels -> accept (explicit clear)")
assert demo._validate_grade_levels({"gradeLevels": "09,10,11,12"}) is None
_ok("gradeLevels CSV string '09,10,11,12' -> accept")
assert demo._validate_grade_levels({"gradeLevels": ["KG", "01", "02"]}) is None
_ok("gradeLevels list ['KG','01','02'] -> accept")
assert demo._validate_grade_levels({"gradeLevels": ["IT", "PK", "KG", "PS", "UG", "AE"]}) is None
_ok("gradeLevels accepts non-numeric CEDS codes (IT/PK/KG/PS/UG/AE)")
err = demo._validate_grade_levels({"gradeLevels": ["XX"]})
assert err is not None and err.status_code == 400
assert json.loads(err.content)["reason"] == "value_not_in_ceds_vocab"
_ok("gradeLevels=['XX'] -> 400 not in CEDS vocab")
err = demo._validate_grade_levels({"gradeLevels": ["01"] * 14})
assert err is not None and err.status_code == 400
assert json.loads(err.content)["reason"] == "too_many_items"
_ok("gradeLevels 14 items -> 400 too_many_items (max 13)")
err = demo._validate_grade_levels({"gradeLevels": 42})
assert err is not None and err.status_code == 400
assert json.loads(err.content)["reason"] == "expected_list_or_csv"
_ok("gradeLevels=42 (int) -> 400 expected_list_or_csv")

# subjectCodes
assert demo._validate_subject_codes({}) is None
assert demo._validate_subject_codes({"subjectCodes": []}) is None
_ok("empty subjectCodes -> accept")
assert demo._validate_subject_codes({"subjectCodes": ["01001", "02001", "03001"]}) is None
_ok("subjectCodes 3 SCED codes -> accept")
assert demo._validate_subject_codes({"subjectCodes": "01001,02001"}) is None
_ok("subjectCodes CSV -> accept")
err = demo._validate_subject_codes({"subjectCodes": ["X" * 21]})
assert err is not None and err.status_code == 400
assert json.loads(err.content)["reason"] == "code_too_long"
_ok("subjectCodes <21-char code> -> 400 code_too_long")
err = demo._validate_subject_codes({"subjectCodes": ["01\x01" ]})
assert err is not None and err.status_code == 400
assert json.loads(err.content)["reason"] == "control_chars"
_ok("subjectCodes w/ control char -> 400 control_chars")
err = demo._validate_subject_codes({"subjectCodes": ["01001"] * 31})
assert err is not None and err.status_code == 400
assert json.loads(err.content)["reason"] == "too_many_items"
_ok("subjectCodes 31 items -> 400 too_many_items (max 30)")

# Override ring routing
assert "gradeLevels" in demo._DEMOGRAPHIC_OVERRIDE_FIELDS
assert "subjectCodes" in demo._DEMOGRAPHIC_OVERRIDE_FIELDS
_ok("gradeLevels + subjectCodes in override ring fields")

# Round-trip list -> comma-joined string
test_sid = "demo-smoke-test-arrays"
demo._set_demographic_overrides(
    test_sid,
    {"gradeLevels": ["09", "10", "11", "12"],
     "subjectCodes": ["01001", "02001"]},
)
ring = demo._DEMOGRAPHIC_OVERRIDES.get(test_sid)
assert ring and ring.get("gradeLevels") == "09,10,11,12"
assert ring.get("subjectCodes") == "01001,02001"
_ok("override ring stores list as comma-joined")
demo._DEMOGRAPHIC_OVERRIDES.pop(test_sid, None)


# T5 — Itslearning scaffold
print("=" * 70); print("T5 — Itslearning scaffold"); print("=" * 70)
from apps.integrations_marketplace import lms_connector_itslearning as il  # noqa: E402
from apps.integrations_marketplace import lms_supported_providers as lsp  # noqa: E402

# Forward-compat: at v4.00.82 Itslearning was a scaffold; promoted to
# OAUTH_READY in v4.00.91 Studio-OS-10X B4. Smoke records current state.
assert isinstance(il.IS_SCAFFOLD, bool)
assert "oauth.itslearning.com" in il.DEFAULT_AUTHORIZE_URL  # cloud, not per-instance
assert il.OAUTH_STATE_SALT == "rmc.lms.itslearning.oauth_state.v4.00.82"
_ok(f"Itslearning module constants (IS_SCAFFOLD={il.IS_SCAFFOLD}; was True at v4.00.82, promoted in v4.00.91)")
token = il.mint_oauth_state(client_id="il", return_to="/")
payload, reason = il.read_oauth_state(token)
assert reason == "ok" and payload["client_id"] == "il"
_ok("Itslearning mint/read -> ok")
g = il.push_grade(student_external_id="s1", course_external_id="c1",
                  assignment_external_id="a1", score=88.0, max_score=100.0)
assert g["scaffold"] is True and g["target_method"] == "POST"
_ok("Itslearning push_grade scaffold shape")
assert "itslearning" in lsp.SUPPORTED_LMS_PROVIDERS
assert "itslearning" in lsp.SCAFFOLD_LMS_PROVIDERS
assert "itslearning" not in lsp.OAUTH_READY_LMS_PROVIDERS
assert lsp.canonical_lms_provider_label("itslearning") == "Itslearning"
_ok("Itslearning registered in SOT")


# T2 + T4 placeholders — covered by their per-target smokes
print("=" * 70); print("T2 + T4 import check"); print("=" * 70)
try:
    from apps.api import oneroster as _ors
    assert hasattr(_ors, "users_delta_v1p2")
    _ok("users_delta_v1p2 view exists")
except (ImportError, AttributeError) as exc:
    print(f"[SKIP] T2 view not present: {exc}")

try:
    from apps.integrations_marketplace import lms_oauth_metrics as _mom
    assert hasattr(_mom, "render_prometheus_metrics")
    _ok("render_prometheus_metrics exists")
except (ImportError, AttributeError) as exc:
    print(f"[SKIP] T4 exporter not present: {exc}")


print("=" * 70)
print(f"v4.00.82 Wave 14 — {CASES} CASES OK")
print("=" * 70)
