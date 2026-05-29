"""v4.00.59 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +15 Tier-1 subdivisions (US-AR/MS/AL/SC/CT/RI/NH, IN-JK/JH/CT, JP-26,
    TH-10, ID-JK, ZA-WC, MX-NLE); SOT >= 349.
T2: OneRoster v1.2 demographics endpoints (list + detail + per-student).
T3: LMS OAuth health beat (pure aggregator + Celery task wired + beat entry).
T4: Operator action buttons on /super/migration/lms/diagnostics/ (force-
    refresh + force-rotate POSTs; bad provider 400; redirect or JSON).
T5: IdP-initiated logout POST-binding (auto-submit HTML form; ?format=json;
    fallback to inline XML when no IdP target set).

Exits 0 on full pass; non-zero on first failure.
"""
from __future__ import annotations

import base64 as _b64
import json as _json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import RequestFactory  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402


def _line(s):  # noqa: ANN001
    print(s, flush=True)


def _ok(name):  # noqa: ANN001
    _line(f"  OK   {name}")


def _fail(name, detail):  # noqa: ANN001
    _line(f"  FAIL {name} :: {detail}")
    sys.exit(1)


def _staff_user():
    User = get_user_model()
    u, _ = User.objects.get_or_create(
        username="smoke-v4-00-59-staff",
        defaults={"email": "smoke@v4-00-59.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


class _NullSession:
    def flush(self): pass
    def __setitem__(self, k, v): pass
    def __getitem__(self, k): raise KeyError(k)


def _bearer_request(rf, method, path, body=None, idem=None):
    kwargs = {"content_type": "application/json", "HTTP_AUTHORIZATION": "Bearer smoke-bearer"}
    if idem:
        kwargs["HTTP_IDEMPOTENCY_KEY"] = idem
    if body is not None:
        kwargs["data"] = _json.dumps(body) if not isinstance(body, (bytes, str)) else body
    req = getattr(rf, method.lower())(path, **kwargs)
    req._dont_enforce_csrf_checks = True
    return req


def run_t1():
    _line("\n[T1] +15 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = [
        "US-AR", "US-MS", "US-AL", "US-SC", "US-CT", "US-RI", "US-NH",
        "IN-JK", "IN-JH", "IN-CT",
        "JP-26", "TH-10", "ID-JK", "ZA-WC", "MX-NLE",
    ]
    for k in new_keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-present-{k}", f"missing or non-dict: {type(e).__name__}")
        for r in ("calendar_system", "school_types", "education_levels", "terminology"):
            if r not in e:
                _fail(f"t1-shape-{k}-{r}", f"missing {r}")
        if not isinstance(e["school_types"], list) or len(e["school_types"]) < 3:
            _fail(f"t1-school-types-{k}", "need >= 3")
        if not isinstance(e["education_levels"], list) or len(e["education_levels"]) < 3:
            _fail(f"t1-education-levels-{k}", "need >= 3")
        _ok(f"t1-{k} shape OK ({len(e['school_types'])} types, {len(e['education_levels'])} levels)")
    if len(COUNTRY_LOCALIZATION) < 349:
        _fail("t1-sot-count", f"expected >= 349, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] OneRoster v1.2 demographics endpoints")
    from apps.api import oneroster_demographics as odm
    rf = RequestFactory()

    # List
    req = _bearer_request(rf, "GET", "/api/roster/v1p2/demographics/")
    resp = odm.demographics_collection(req)
    if resp.status_code != 200:
        _fail("t2-list-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if "demographics" not in body:
        _fail("t2-list-envelope", f"missing demographics key, got {sorted(body)}")
    _ok(f"t2-list 200 envelope=demographics (count={len(body['demographics'])})")

    # Each record has the OneRoster spec keys
    if body["demographics"]:
        rec = body["demographics"][0]
        required = {"sourcedId", "status", "dateLastModified", "birthDate", "sex",
                    "americanIndianOrAlaskaNative", "asian", "blackOrAfricanAmerican",
                    "nativeHawaiianOrOtherPacificIslander", "white",
                    "demographicRaceTwoOrMoreRaces", "hispanicOrLatinoEthnicity",
                    "countryOfBirthCode", "stateOfBirthAbbreviation", "cityOfBirth",
                    "publicSchoolResidenceStatus"}
        missing = required - set(rec.keys())
        if missing:
            _fail("t2-list-shape", f"missing keys: {sorted(missing)}")
        if not rec["sourcedId"].startswith("demo-"):
            _fail("t2-list-sid-prefix", f"got {rec['sourcedId']!r}")
        _ok(f"t2-list shape v1.2 16-field spec all present (sourcedId={rec['sourcedId']})")

    # Detail — bad sid
    req = _bearer_request(rf, "GET", "/api/roster/v1p2/demographics/bad-id/")
    resp = odm.demographic_detail(req, "bad-id")
    if resp.status_code != 400:
        _fail("t2-detail-bad-id", f"expected 400, got {resp.status_code}")
    _ok("t2-detail bad sid -> 400")

    # Detail — not found
    req = _bearer_request(rf, "GET", "/api/roster/v1p2/demographics/demo-99999999/")
    resp = odm.demographic_detail(req, "demo-99999999")
    if resp.status_code != 404:
        _fail("t2-detail-not-found", f"expected 404, got {resp.status_code}")
    _ok("t2-detail not-found -> 404")

    # student demographics — not found
    req = _bearer_request(rf, "GET", "/api/roster/v1p2/students/99999999/demographics/")
    resp = odm.student_demographics(req, "99999999")
    if resp.status_code != 404:
        _fail("t2-student-not-found", f"expected 404, got {resp.status_code}")
    _ok("t2-student demographics not-found -> 404")

    from django.urls import reverse
    p1 = reverse("api:api-roster-v1p2-demographics")
    p2 = reverse("api:api-roster-v1p2-demographic-detail", args=["demo-1"])
    p3 = reverse("api:api-roster-v1p2-student-demographics", args=["1"])
    _ok(f"t2-url-list {p1}")
    _ok(f"t2-url-detail {p2}")
    _ok(f"t2-url-student {p3}")


def run_t3():
    _line("\n[T3] LMS OAuth health beat")
    from apps.integrations_marketplace.lms_oauth_health import (
        sweep_lms_oauth_health, _HEALTH_COURSE_ID, auto_refresh_expired_lms_tokens,
    )
    out = sweep_lms_oauth_health()
    expected_keys = {"considered", "refreshed", "failed", "skipped", "results", "max_rows"}
    missing = expected_keys - set(out.keys())
    if missing:
        _fail("t3-sweep-shape", f"missing {sorted(missing)}")
    _ok(f"t3-sweep shape OK (considered={out['considered']} max_rows={out['max_rows']})")

    if _HEALTH_COURSE_ID != "_health_check":
        _fail("t3-marker", f"got {_HEALTH_COURSE_ID!r}")
    _ok(f"t3-marker {_HEALTH_COURSE_ID}")

    if auto_refresh_expired_lms_tokens is None:
        _fail("t3-celery-task", "shared_task registration is None")
    _ok("t3-celery-task auto_refresh_expired_lms_tokens registered")

    from apps.integrations_marketplace.beat_schedule import get_lms_beat_schedule
    sched = get_lms_beat_schedule()
    if "integrations-lms-oauth-health" not in sched:
        _fail("t3-beat-entry", f"missing entry; got keys={sorted(sched.keys())}")
    entry = sched["integrations-lms-oauth-health"]
    if entry["task"] != "integrations_marketplace.auto_refresh_expired_lms_tokens":
        _fail("t3-beat-task", entry["task"])
    if entry["schedule"] != 900.0:
        _fail("t3-beat-schedule", entry["schedule"])
    _ok(f"t3-beat integrations-lms-oauth-health every {entry['schedule']}s")

    # Env disable
    os.environ["RMC_LMS_OAUTH_HEALTH_BEAT_DISABLED"] = "1"
    sched2 = get_lms_beat_schedule()
    if "integrations-lms-oauth-health" in sched2:
        _fail("t3-beat-disabled", "should have been omitted")
    _ok("t3-beat env disable honored")
    del os.environ["RMC_LMS_OAUTH_HEALTH_BEAT_DISABLED"]


def run_t4():
    _line("\n[T4] Operator action buttons on LMS diagnostics")
    from apps.migration_cloud import views_lms_diagnostics as vld
    rf = RequestFactory()
    user = _staff_user()

    # Missing provider -> 400
    req = rf.post("/super/migration/lms/diagnostics/force-refresh/", {})
    req.user = user
    req._dont_enforce_csrf_checks = True
    resp = vld.lms_diagnostics_force_refresh(req)
    if resp.status_code != 400:
        _fail("t4-refresh-missing", f"got {resp.status_code}")
    _ok("t4-refresh missing provider -> 400")

    # Bad provider -> 400
    req = rf.post("/super/migration/lms/diagnostics/force-refresh/", {"provider": "evil"})
    req.user = user
    req._dont_enforce_csrf_checks = True
    resp = vld.lms_diagnostics_force_refresh(req)
    if resp.status_code != 400:
        _fail("t4-refresh-bad", f"got {resp.status_code}")
    _ok("t4-refresh bad provider -> 400")

    # JSON path
    req = rf.post("/super/migration/lms/diagnostics/force-refresh/",
                  {"provider": "canvas"}, HTTP_ACCEPT="application/json")
    req.user = user
    req._dont_enforce_csrf_checks = True
    resp = vld.lms_diagnostics_force_refresh(req)
    if resp.status_code != 200:
        _fail("t4-refresh-json-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("action") != "force_refresh" or body.get("provider") != "canvas":
        _fail("t4-refresh-body", f"got {body}")
    _ok("t4-refresh JSON canvas -> 200 action+provider OK")

    # Redirect path
    req = rf.post("/super/migration/lms/diagnostics/force-refresh/", {"provider": "moodle"})
    req.user = user
    req._dont_enforce_csrf_checks = True
    resp = vld.lms_diagnostics_force_refresh(req)
    if resp.status_code != 302:
        _fail("t4-refresh-redirect-status", f"got {resp.status_code}")
    if "action=force_refresh" not in resp.get("Location", ""):
        _fail("t4-refresh-redirect-location", resp.get("Location"))
    _ok(f"t4-refresh moodle redirect 302 -> {resp.get('Location')}")

    # Force rotate JSON
    req = rf.post("/super/migration/lms/diagnostics/force-rotate/",
                  {"provider": "google_classroom"}, HTTP_ACCEPT="application/json")
    req.user = user
    req._dont_enforce_csrf_checks = True
    resp = vld.lms_diagnostics_force_rotate(req)
    if resp.status_code != 200:
        _fail("t4-rotate-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("action") != "force_rotate" or body.get("provider") != "google_classroom":
        _fail("t4-rotate-body", f"got {body}")
    _ok(f"t4-rotate JSON google_classroom -> 200")

    from django.urls import reverse
    p1 = reverse("migration_cloud_super:migration_cloud_lms_diagnostics_force_refresh")
    p2 = reverse("migration_cloud_super:migration_cloud_lms_diagnostics_force_rotate")
    _ok(f"t4-url-refresh {p1}")
    _ok(f"t4-url-rotate {p2}")


def run_t5():
    _line("\n[T5] IdP-initiated logout POST-binding")
    from apps.api.saml import sls_idp, _autosubmit_form_html
    rf = RequestFactory()

    # Autosubmit form fragment
    html = _autosubmit_form_html("https://idp.example/slo", "PAYLOAD123", "rs-X")
    for needle in [
        'action="https://idp.example/slo"',
        'name="SAMLResponse" value="PAYLOAD123"',
        'name="RelayState" value="rs-X"',
        "document.getElementById('slo-form').submit()",
        "<noscript>",
    ]:
        if needle not in html:
            _fail("t5-form-fragment", f"missing {needle!r}")
    _ok("t5-form fragment has action+SAMLResponse+RelayState+autosubmit JS+NoScript")

    # End-to-end JSON path
    xml = (
        b'<samlp:LogoutRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        b'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        b'ID="_lr-idp-smoke-1" Version="2.0" IssueInstant="2026-05-29T12:00:00Z">'
        b'<saml:Issuer>https://idp.example/saml</saml:Issuer>'
        b'<saml:NameID>user@example.com</saml:NameID>'
        b'<samlp:SessionIndex>sx-77</samlp:SessionIndex>'
        b'</samlp:LogoutRequest>'
    )
    req = rf.post("/sso/saml/sls/idp/?format=json",
                  data={"SAMLRequest": _b64.b64encode(xml).decode(), "RelayState": "rs-final"})
    req._dont_enforce_csrf_checks = True
    req.session = _NullSession()
    resp = sls_idp(req)
    if resp.status_code != 200:
        _fail("t5-json-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("stage") != "logged_out_idp_initiated":
        _fail("t5-stage", f"got {body.get('stage')}")
    if body.get("binding") != "HTTP-POST":
        _fail("t5-binding", f"got {body.get('binding')}")
    if body.get("relay_state") != "rs-final":
        _fail("t5-relay", f"got {body.get('relay_state')}")
    _ok(f"t5-json 200 stage=logged_out_idp_initiated binding=HTTP-POST relay=rs-final")

    # Missing SAMLRequest -> 400 + session flushed
    req = rf.post("/sso/saml/sls/idp/", data={})
    req._dont_enforce_csrf_checks = True
    req.session = _NullSession()
    resp = sls_idp(req)
    if resp.status_code != 400:
        _fail("t5-missing-req", f"got {resp.status_code}")
    _ok("t5-missing-SAMLRequest -> 400")

    # IdP target set -> HTML auto-submit form
    os.environ["RMC_SAML_IDP_SLO_URL"] = "https://idp.example/saml/slo"
    try:
        req = rf.post("/sso/saml/sls/idp/",
                      data={"SAMLRequest": _b64.b64encode(xml).decode(), "RelayState": "rs-html"})
        req._dont_enforce_csrf_checks = True
        req.session = _NullSession()
        resp = sls_idp(req)
        if resp.status_code != 200:
            _fail("t5-html-status", f"got {resp.status_code}")
        if resp["Content-Type"] != "text/html; charset=utf-8":
            _fail("t5-html-ct", resp["Content-Type"])
        body_str = resp.content.decode("utf-8")
        if 'action="https://idp.example/saml/slo"' not in body_str:
            _fail("t5-html-action", "missing action attr")
        if 'value="rs-html"' not in body_str:
            _fail("t5-html-relay", "missing RelayState")
        if "document.getElementById" not in body_str:
            _fail("t5-html-autosubmit", "missing autosubmit JS")
        _ok(f"t5-html 200 auto-submit form action+relay+JS ({len(resp.content)} bytes)")
    finally:
        del os.environ["RMC_SAML_IDP_SLO_URL"]

    from django.urls import reverse
    p = reverse("sso_saml_sls_idp")
    if not p.endswith("/sso/saml/sls/idp/"):
        _fail("t5-url", p)
    _ok(f"t5-url {p}")


def main():
    run_t1()
    run_t2()
    run_t3()
    run_t4()
    run_t5()
    _line("\nALL GREEN")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        sys.exit(2)
