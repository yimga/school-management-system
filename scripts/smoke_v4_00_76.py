"""v4.00.76 smoke."""
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
    keys = ["SE-AB","SE-O","NO-03","NO-46","DK-84","FI-18","IE-D",
            "GB-SCT","GB-WLS","GB-NIR","PL-MZ","CZ-10","AT-9","HU-BU"]
    for k in keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-{k}", "missing")
        _ok(f"t1-{k} OK")
    if len(COUNTRY_LOCALIZATION) < 583:
        _fail("t1-sot-count", f"got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] OneRoster /enrollments/ endpoint")
    from apps.api import oneroster as mod
    rf = RequestFactory()
    os.environ["RMC_ONEROSTER_BEARER"] = "smoke-bearer"
    try:
        req = rf.get("/api/roster/v1p2/enrollments/")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.enrollments(req)
        if resp.status_code != 200:
            _fail("t2-status", f"got {resp.status_code}")
        body = _json.loads(resp.content)
        if "enrollments" not in body:
            _fail("t2-envelope", str(body))
        _ok(f"t2-/enrollments/ envelope; n={len(body.get('enrollments', []))}")

        # Verify projection shape if populated.
        for it in body.get("enrollments", []):
            for k in ("sourcedId","status","role","userSourcedId","classSourcedId",
                      "schoolSourcedId","beginDate","endDate"):
                if k not in it:
                    _fail(f"t2-key-{k}", str(it))
        _ok("t2-enrollment projection carries 8 spec keys (when populated)")

        # ?since= filter shouldn't error.
        req = rf.get("/api/roster/v1p2/enrollments/?since=2026-01-01")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.enrollments(req)
        if resp.status_code != 200:
            _fail("t2-since", f"got {resp.status_code}")
        _ok("t2-?since= filter applies w/o error")
    finally:
        os.environ.pop("RMC_ONEROSTER_BEARER", None)

    from django.urls import reverse, NoReverseMatch
    try:
        url = reverse("api:api-roster-v1p2-enrollments")
        if not url.endswith("/enrollments/"):
            _fail("t2-url", url)
        _ok(f"t2-URL: {url}")
    except NoReverseMatch as exc:
        _fail("t2-url", str(exc))


def run_t3():
    _line("\n[T3] Demographics middleName validation")
    from apps.api import oneroster_demographics as odm

    # Missing + empty -> None.
    if odm._validate_middle_name({}) is not None:
        _fail("t3-missing", "expected None")
    if odm._validate_middle_name({"middleName": ""}) is not None:
        _fail("t3-empty", "expected None")
    _ok("t3-missing + empty middleName -> None (explicit clear)")

    # Normal names + unicode + punctuation accepted.
    for name in ("James", "Mária", "O'Brien", "Jean-Luc", "Maria-João",
                  "K", "A" * 80):  # exact boundary
        err = odm._validate_middle_name({"middleName": name})
        if err is not None:
            _fail(f"t3-good-{name[:10]}", f"got {err.content}")
    _ok("t3-7 names incl unicode + exactly 80 chars accepted")

    # 81 chars rejected.
    err = odm._validate_middle_name({"middleName": "A" * 81})
    if err is None or err.status_code != 400:
        _fail("t3-too-long", "expected 400")
    body = _json.loads(err.content)
    if body.get("reason") != "too_long":
        _fail("t3-too-long-reason", str(body))
    if body.get("received_length") != 81:
        _fail("t3-len-echo", str(body))
    _ok("t3-81 chars -> 400 too_long (received_length echoed)")

    # Control chars rejected.
    for bad in ("James\x00Hidden", "Mária\nLine2", "\t-prefix"):
        err = odm._validate_middle_name({"middleName": bad})
        if err is None or err.status_code != 400:
            _fail(f"t3-ctrl-{bad!r}", f"got {err}")
        body = _json.loads(err.content)
        if body.get("reason") != "control_chars":
            _fail(f"t3-ctrl-reason-{bad!r}", str(body))
    _ok("t3-control chars (NUL, LF, TAB) -> 400 control_chars")

    # E2E via _parse_demographic_payload.
    body_bytes = _json.dumps({"demographic": {"middleName": "James"}}).encode("utf-8")
    inner, err = odm._parse_demographic_payload(body_bytes)
    if err is not None:
        _fail("t3-e2e", f"got {err}")
    _ok("t3-_parse_demographic_payload accepts middleName='James'")


def run_t4():
    _line("\n[T4] Token rotation chain retention plan")
    from apps.integrations_marketplace import lms_token_rotation_retention as r

    # Defaults.
    os.environ.pop("RMC_LMS_TOKEN_ROTATION_RETENTION_YEARS", None)
    os.environ.pop("RMC_LMS_TOKEN_ROTATION_KEEP_TAIL", None)
    if r.resolve_retention_years() != 2:
        _fail("t4-default-years", str(r.resolve_retention_years()))
    if r.resolve_keep_tail() != 5:
        _fail("t4-default-tail", str(r.resolve_keep_tail()))
    _ok("t4-defaults: years=2, keep_tail=5")

    # Env override.
    os.environ["RMC_LMS_TOKEN_ROTATION_RETENTION_YEARS"] = "7"
    os.environ["RMC_LMS_TOKEN_ROTATION_KEEP_TAIL"] = "10"
    try:
        if r.resolve_retention_years() != 7:
            _fail("t4-env-years", str(r.resolve_retention_years()))
        if r.resolve_keep_tail() != 10:
            _fail("t4-env-tail", str(r.resolve_keep_tail()))
        _ok("t4-env override: years=7, keep_tail=10")
    finally:
        os.environ.pop("RMC_LMS_TOKEN_ROTATION_RETENTION_YEARS", None)
        os.environ.pop("RMC_LMS_TOKEN_ROTATION_KEEP_TAIL", None)

    # Plan w/ explicit years=3.
    plan = r.compute_rotation_chain_retention_plan(years=3)
    if plan["years"] != 3:
        _fail("t4-plan-years", str(plan))
    if not plan["cutoff_iso"]:
        _fail("t4-plan-cutoff", str(plan))
    if plan["retain_forever"] is not False:
        _fail("t4-plan-retain", str(plan))
    _ok(f"t4-plan years=3: cutoff_iso={plan['cutoff_iso'][:10]} retain_forever=False")

    # years=0 -> retain forever short-circuit.
    plan = r.compute_rotation_chain_retention_plan(years=0)
    if plan["retain_forever"] is not True:
        _fail("t4-zero", str(plan))
    if plan["cutoff_iso"] != "":
        _fail("t4-zero-cutoff", str(plan))
    _ok("t4-years=0 -> retain_forever=True (short-circuit)")

    # is_chain_row_purgeable.
    from django.utils import timezone as _tz
    from datetime import timedelta
    now = _tz.now()
    cutoff = now - timedelta(days=730)  # 2y ago
    old_row = now - timedelta(days=1000)  # 2.7y ago
    new_row = now - timedelta(days=100)   # 100d ago

    if not r.is_chain_row_purgeable(created_at=old_row, position_from_head=6, cutoff_dt=cutoff, keep_tail=5):
        _fail("t4-purge-old-far", "expected True")
    _ok("t4-old row + position>keep_tail -> purgeable")

    if r.is_chain_row_purgeable(created_at=old_row, position_from_head=3, cutoff_dt=cutoff, keep_tail=5):
        _fail("t4-keep-tail-protected", "expected False (within tail)")
    _ok("t4-row within keep_tail -> NOT purgeable (protected)")

    if r.is_chain_row_purgeable(created_at=new_row, position_from_head=6, cutoff_dt=cutoff, keep_tail=5):
        _fail("t4-recent-protected", "expected False (recent)")
    _ok("t4-recent row -> NOT purgeable (post-cutoff)")

    if r.is_chain_row_purgeable(created_at=None, position_from_head=10, cutoff_dt=cutoff, keep_tail=5):
        _fail("t4-none-cad", "expected False (defensive)")
    _ok("t4-None created_at -> NOT purgeable (defensive)")


def run_t5():
    _line("\n[T5] D2L push_grade scaffold w/ would_send payload")
    from apps.integrations_marketplace import lms_connector_d2l as d2l

    # Happy path.
    out = d2l.push_grade(base_url="https://b.example", access_token="t",
                         course_id="ou-1234", user_id="u-5678",
                         score=92.5, max_score=100.0,
                         grade_object_id="ge-99", comment="Great work")
    if out.get("reason") != "scaffold_not_wired":
        _fail("t5-reason", str(out))
    if "would_send" not in out:
        _fail("t5-would-send", str(out))
    if out["would_send"]["method"] != "PUT":
        _fail("t5-method", str(out))
    if "/d2l/api/le/1.66/ou-1234/grades/ge-99/values/u-5678" not in out["would_send"]["endpoint"]:
        _fail("t5-endpoint", str(out))
    body = out["would_send"]["body"]
    if body["GradeObjectType"] != 1:
        _fail("t5-type", str(body))
    if body["PointsNumerator"] != 92.5 or body["PointsDenominator"] != 100.0:
        _fail("t5-points", str(body))
    if body["Comments"]["Content"] != "Great work":
        _fail("t5-comment", str(body))
    _ok("t5-D2L happy-path scaffold returns PUT endpoint + GradeObjectType=1 + Numerator/Denominator body")

    # Missing course_id rejected.
    out = d2l.push_grade(base_url="x", access_token="t",
                         course_id="", user_id="u", score=10, max_score=10)
    if out.get("reason") != "missing_required_field":
        _fail("t5-missing", str(out))
    _ok("t5-missing course_id -> reason=missing_required_field")

    # Non-numeric.
    out = d2l.push_grade(base_url="x", access_token="t",
                         course_id="c", user_id="u", score="N/A", max_score=10)
    if out.get("reason") != "score_not_numeric":
        _fail("t5-non-num", str(out))
    _ok("t5-non-numeric score -> reason=score_not_numeric")

    # Exceeds max.
    out = d2l.push_grade(base_url="x", access_token="t",
                         course_id="c", user_id="u", score=200, max_score=100)
    if out.get("reason") != "score_exceeds_max":
        _fail("t5-exceed", str(out))
    _ok("t5-score 200 > max 100 -> reason=score_exceeds_max")

    # Identical error taxonomy as Schoology (cross-provider operator UX consistency).
    from apps.integrations_marketplace import lms_connector_schoology as sg
    out_d2l = d2l.push_grade(base_url="x", access_token="t",
                              course_id="", user_id="u", score=5, max_score=10)
    out_sg = sg.push_grade(base_url="x", access_token="t",
                            course_id="", user_id="u", score=5, max_score=10)
    if out_d2l["reason"] != out_sg["reason"]:
        _fail("t5-cross-taxonomy", f"D2L={out_d2l['reason']} Schoology={out_sg['reason']}")
    _ok("t5-D2L + Schoology share identical error reason taxonomy (cross-provider UX consistency)")


def main():
    run_t1(); run_t2(); run_t3(); run_t4(); run_t5()
    _line("\nALL GREEN")


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(2)
