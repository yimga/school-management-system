"""v4.00.74 smoke."""
from __future__ import annotations
import json as _json
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django  # noqa: E402
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.test import RequestFactory  # noqa: E402


def _line(s): print(s, flush=True)  # noqa: E702
def _ok(name): _line(f"  OK   {name}")  # noqa: E702
def _fail(name, detail):
    _line(f"  FAIL {name} :: {detail}"); sys.exit(1)


def run_t1():
    _line("\n[T1] +14 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    keys = ["QA-DA","SA-01","KW-KU","BH-13","OM-MA","LB-BA","IR-23","IQ-BG",
            "TR-35","TR-16","IL-D","MG-T","MU-PL","BD-D"]
    for k in keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-{k}", "missing")
        _ok(f"t1-{k} OK")
    if len(COUNTRY_LOCALIZATION) < 563:
        _fail("t1-sot-count", f"got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] OneRoster /courses/ endpoint")
    from apps.api import oneroster as mod
    rf = RequestFactory()
    os.environ["RMC_ONEROSTER_BEARER"] = "smoke-bearer"
    try:
        req = rf.get("/api/roster/v1p2/courses/")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.courses(req)
        if resp.status_code != 200:
            _fail("t2-status", f"got {resp.status_code}")
        body = _json.loads(resp.content)
        if "courses" not in body:
            _fail("t2-envelope", str(body))
        _ok(f"t2-/courses/ envelope; n={len(body.get('courses', []))}")

        # Projection shape (when populated).
        for c in body.get("courses", []):
            for k in ("sourcedId","status","title","courseCode","grades","subjects","schoolYearSourcedId"):
                if k not in c:
                    _fail(f"t2-key-{k}", str(c))
        _ok("t2-course projection carries all 7 v1.2 spec keys")
    finally:
        os.environ.pop("RMC_ONEROSTER_BEARER", None)

    from django.urls import reverse, NoReverseMatch
    try:
        url = reverse("api:api-roster-v1p2-courses")
        if not url.endswith("/courses/"):
            _fail("t2-url", url)
        _ok(f"t2-URL: {url}")
    except NoReverseMatch as exc:
        _fail("t2-url", str(exc))


def run_t3():
    _line("\n[T3] white race flag (6th of 7)")
    from apps.api import oneroster_demographics as odm
    if "white" not in odm.RACE_ETHNICITY_BOOL_FIELDS:
        _fail("t3-registered", "missing")
    if len(odm.RACE_ETHNICITY_BOOL_FIELDS) != 6:
        _fail("t3-count", f"expected 6; got {len(odm.RACE_ETHNICITY_BOOL_FIELDS)}")
    _ok(f"t3-6 race/ethnicity flags now: {sorted(odm.RACE_ETHNICITY_BOOL_FIELDS)}")

    for v in (True, False, "true", "no", "1", "0", ""):
        err = odm._validate_race_ethnicity_bool_flags({"white": v})
        if err is not None:
            _fail(f"t3-{v!r}", f"got {err.content}")
    _ok("t3-white accepts bool literals + boolish strings + empty clear")

    err = odm._validate_race_ethnicity_bool_flags({"white": "kinda"})
    if err is None or err.status_code != 400:
        _fail("t3-bad", "expected 400")
    body = _json.loads(err.content)
    if body.get("field") != "white":
        _fail("t3-field-echo", str(body))
    _ok("t3-'kinda' -> 400 not_boolish field=white")


def run_t4():
    _line("\n[T4] webhook_retry_fsm")
    from apps.integrations_marketplace import webhook_retry_fsm as fsm

    if fsm.MAX_ATTEMPTS != 6:
        _fail("t4-max", f"got {fsm.MAX_ATTEMPTS}")
    _ok(f"t4-MAX_ATTEMPTS=6 ; RETRY_SCHEDULE_SECONDS={fsm.RETRY_SCHEDULE_SECONDS}")

    # Schedule is monotonically increasing.
    sched = fsm.RETRY_SCHEDULE_SECONDS
    for i in range(len(sched) - 1):
        if sched[i] >= sched[i + 1]:
            _fail("t4-monotonic", f"got {sched}")
    _ok("t4-schedule monotonically increasing")

    # next_retry_seconds(attempt) shapes.
    if fsm.next_retry_seconds(0) != 60:
        _fail("t4-zero", str(fsm.next_retry_seconds(0)))
    if fsm.next_retry_seconds(1) != 5 * 60:
        _fail("t4-1", str(fsm.next_retry_seconds(1)))
    if fsm.next_retry_seconds(5) != 24 * 60 * 60:
        _fail("t4-5", str(fsm.next_retry_seconds(5)))
    if fsm.next_retry_seconds(6) is not None:
        _fail("t4-6-exhausted", str(fsm.next_retry_seconds(6)))
    if fsm.next_retry_seconds(99) is not None:
        _fail("t4-99-exhausted", str(fsm.next_retry_seconds(99)))
    _ok("t4-next_retry_seconds: 0->60s, 1->5m, 5->24h, 6/99->None (exhausted)")

    # is_exhausted.
    if fsm.is_exhausted(5):
        _fail("t4-not-exhausted-5", "should be False")
    if not fsm.is_exhausted(6):
        _fail("t4-exhausted-6", "should be True")
    _ok("t4-is_exhausted: 5->False, 6->True")

    # retry_schedule_summary shape.
    summary = fsm.retry_schedule_summary()
    if len(summary) != 6:
        _fail("t4-summary-len", str(summary))
    for row in summary:
        for k in ("attempt", "next_retry_seconds", "next_retry_human"):
            if k not in row:
                _fail(f"t4-summary-key-{k}", str(row))
    if summary[0]["next_retry_human"] != "1m":
        _fail("t4-human-1m", str(summary[0]))
    if summary[5]["next_retry_human"] != "1d":
        _fail("t4-human-1d", str(summary[5]))
    _ok("t4-retry_schedule_summary: 6 entries, human strings (1m, 5m, 30m, 2h, 12h, 1d)")


def run_t5():
    _line("\n[T5] SAML HRD per-domain config")
    from apps.api import saml as sm

    # No mapping configured -> fallback to default IdP.
    os.environ.pop("RMC_SAML_HRD_MAPPING", None)
    os.environ.pop("RMC_SAML_IDP_SSO_URL", None)
    target = sm.resolve_idp_target_for_email("user@anywhere.edu")
    if target != "":
        _fail("t5-no-config", f"got {target}")
    _ok("t5-no env config -> empty fallback")

    # Set fallback only.
    os.environ["RMC_SAML_IDP_SSO_URL"] = "https://default-idp.example/sso"
    try:
        target = sm.resolve_idp_target_for_email("user@unknown.edu")
        if target != "https://default-idp.example/sso":
            _fail("t5-fallback", target)
        _ok("t5-unmapped domain -> fallback to RMC_SAML_IDP_SSO_URL")

        # Set HRD mapping.
        os.environ["RMC_SAML_HRD_MAPPING"] = _json.dumps({
            "school.edu": "https://okta.school.edu/sso",
            "partner.edu": "https://login.partner.edu/sso",
            "*.subdistrict.edu": "https://wildcard.example/sso",
        })
        target = sm.resolve_idp_target_for_email("user@school.edu")
        if target != "https://okta.school.edu/sso":
            _fail("t5-school-edu", target)
        _ok("t5-user@school.edu -> okta.school.edu IdP")

        target = sm.resolve_idp_target_for_email("user@partner.edu")
        if target != "https://login.partner.edu/sso":
            _fail("t5-partner", target)
        _ok("t5-user@partner.edu -> partner.edu IdP")

        # Case-insensitive.
        target = sm.resolve_idp_target_for_email("USER@SCHOOL.EDU")
        if target != "https://okta.school.edu/sso":
            _fail("t5-case", target)
        _ok("t5-domain match is case-insensitive")

        # Wildcard suffix.
        target = sm.resolve_idp_target_for_email("user@east.subdistrict.edu")
        if target != "https://wildcard.example/sso":
            _fail("t5-wildcard", target)
        _ok("t5-wildcard *.subdistrict.edu matches east.subdistrict.edu")

        # Unmapped -> fallback.
        target = sm.resolve_idp_target_for_email("user@nowhere.com")
        if target != "https://default-idp.example/sso":
            _fail("t5-unmapped-fallback", target)
        _ok("t5-unmapped @nowhere.com still falls back to default IdP")

        # Malformed email.
        target = sm.resolve_idp_target_for_email("not-an-email")
        if target != "https://default-idp.example/sso":
            _fail("t5-malformed", target)
        _ok("t5-malformed email -> fallback")

        # Summary helper - never leaks IdP URLs.
        summ = sm.hrd_mapping_summary()
        if summ["mapped_domain_count"] != 3:
            _fail("t5-summ-count", str(summ))
        if summ["wildcard_count"] != 1:
            _fail("t5-summ-wc", str(summ))
        # IdP URLs must NOT appear in the summary.
        s_text = _json.dumps(summ)
        for needle in ("okta.school.edu", "login.partner.edu", "wildcard.example"):
            if needle in s_text:
                _fail(f"t5-leak-{needle}", "IdP URL leaked in summary")
        _ok(f"t5-summary safe (mapped={summ['mapped_domain_count']}, wildcards={summ['wildcard_count']}, no URL leak)")
    finally:
        os.environ.pop("RMC_SAML_IDP_SSO_URL", None)
        os.environ.pop("RMC_SAML_HRD_MAPPING", None)


def main():
    run_t1(); run_t2(); run_t3(); run_t4(); run_t5()
    _line("\nALL GREEN")


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(2)
