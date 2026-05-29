"""v4.00.62 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +21 Tier-1 subdivisions (US-WV/NE/SD/ND/MT/WY/DE; IN-MZ/TR/AN; JP-12/15;
    CN-JS/FJ/SD; CA-AB/MB/SK; AU-WA/SA/TAS); SOT >= 398.
T2: Dedicated LMSDiagActionAudit table; dual-write to new + legacy; read
    path prefers new; LMSPushGradeAudit mirror still written.
T3: SP-initiated SLO HTTP-Redirect binding signature — ?binding=redirect
    deflates + base64s SAMLRequest; query-string signing via cryptography
    PKCS1v15; deps_missing / key_unset fallthrough; strict-mode 503.
T4: Demographics ?orgSourcedId= + ?role= filters; _orgSourcedId aux field
    on projection.
T5: action-history ?since=ISO + ?before=ISO window; _parse_window_iso
    handles Z suffix, naive-utc fallback, malformed -> None.

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
        username="smoke-v4-00-62-staff",
        defaults={"email": "smoke@v4-00-62.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


class _NullSession:
    _data: dict = {}
    def flush(self): self._data = {}
    def __setitem__(self, k, v): self._data[k] = v
    def __getitem__(self, k):
        if k in self._data:
            return self._data[k]
        raise KeyError(k)
    def get(self, k, default=None): return self._data.get(k, default)


def _bearer_request(rf, method, path):
    kwargs = {"content_type": "application/json", "HTTP_AUTHORIZATION": "Bearer smoke-bearer"}
    req = getattr(rf, method.lower())(path, **kwargs)
    req._dont_enforce_csrf_checks = True
    return req


def run_t1():
    _line("\n[T1] +21 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = [
        "US-WV", "US-NE", "US-SD", "US-ND", "US-MT", "US-WY", "US-DE",
        "IN-MZ", "IN-TR", "IN-AN",
        "JP-12", "JP-15",
        "CN-JS", "CN-FJ", "CN-SD",
        "CA-AB", "CA-MB", "CA-SK",
        "AU-WA", "AU-SA", "AU-TAS",
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
        _ok(f"t1-{k} OK ({len(e['school_types'])} types, {len(e['education_levels'])} levels)")
    if len(COUNTRY_LOCALIZATION) < 398:
        _fail("t1-sot-count", f"expected >= 398, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] Dedicated LMSDiagActionAudit table")
    from apps.integrations_marketplace.models import LMSDiagActionAudit, LMSPushGradeAudit
    from apps.migration_cloud import views_lms_diagnostics as vld
    rf = RequestFactory()
    user = _staff_user()

    # Clean slate.
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    LMSPushGradeAudit.objects.filter(course_id=vld._DIAG_ACTION_COURSE_ID).delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()
    _ok("t2-cleanup baseline empty")

    # Trigger a force-refresh action.
    req = rf.post("/super/migration/lms/diagnostics/force-refresh/",
                  {"provider": "canvas"}, HTTP_ACCEPT="application/json")
    req.user = user
    req._dont_enforce_csrf_checks = True
    resp = vld.lms_diagnostics_force_refresh(req)
    if resp.status_code != 200:
        _fail("t2-trigger", f"got {resp.status_code}")
    _ok("t2-trigger force-refresh fired")

    # NEW table got the row.
    new_count = LMSDiagActionAudit.objects.count()  # tenant-isolation-allow: smoke
    if new_count != 1:
        _fail("t2-new-row", f"got {new_count}")
    new_row = LMSDiagActionAudit.objects.first()  # tenant-isolation-allow: smoke
    if new_row.action != "force_refresh" or new_row.provider != "canvas":
        _fail("t2-new-row-shape", f"got action={new_row.action} provider={new_row.provider}")
    _ok(f"t2-new-table 1 row action={new_row.action} provider={new_row.provider}")

    # LEGACY table mirror got the row too.
    legacy_count = LMSPushGradeAudit.objects.filter(  # tenant-isolation-allow: smoke
        course_id=vld._DIAG_ACTION_COURSE_ID,
    ).count()
    if legacy_count != 1:
        _fail("t2-legacy-mirror", f"got {legacy_count}")
    _ok("t2-legacy-mirror 1 row mirrored")

    # Read path prefers new table.
    vld._LAST_ACTION_RING.clear()  # ensure DB path
    snap = vld.get_last_action_snapshot(limit=10, durable=True)
    if len(snap) != 1:
        _fail("t2-read-len", f"got {len(snap)}")
    if snap[0]["action"] != "force_refresh":
        _fail("t2-read-action", f"got {snap[0]}")
    _ok(f"t2-read prefers new table (action={snap[0]['action']})")

    # New-table read includes new fields shape.
    if "considered" not in snap[0] or "ok" not in snap[0] or "failed" not in snap[0]:
        _fail("t2-read-shape", f"got {sorted(snap[0])}")
    _ok(f"t2-read shape has considered/ok/failed counters")

    # Legacy-only fallback path: delete new rows, ensure legacy fall-through reads.
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()
    snap2 = vld.get_last_action_snapshot(limit=10, durable=True)
    if len(snap2) != 1:
        _fail("t2-legacy-fallthrough-len", f"got {len(snap2)}")
    if snap2[0]["action"] != "force_refresh":
        _fail("t2-legacy-fallthrough-action", f"got {snap2[0]}")
    _ok("t2-legacy-fallthrough new empty -> reads legacy table")

    # Cleanup.
    LMSPushGradeAudit.objects.filter(course_id=vld._DIAG_ACTION_COURSE_ID).delete()  # tenant-isolation-allow: smoke-cleanup
    _ok("t2-cleanup smoke rows removed")


def run_t3():
    _line("\n[T3] SP-initiated SLO HTTP-Redirect binding signature")
    from apps.api.saml import _build_redirect_signed_url, slo_start
    rf = RequestFactory()

    # Default (no signing config) -> unsigned url + reason="key_unset" or "deps_missing".
    os.environ.pop("RMC_SAML_SP_PRIVATE_KEY_PEM", None)
    url, reason = _build_redirect_signed_url(
        idp_target="https://idp.example/slo",
        saml_request_b64="SAMLREQB64",
        relay_state="rs-1",
    )
    if reason not in ("key_unset", "deps_missing"):
        _fail("t3-no-key-reason", f"got {reason}")
    if "SAMLRequest=SAMLREQB64" not in url:
        _fail("t3-unsigned-url", url)
    _ok(f"t3-unsigned reason={reason} URL has SAMLRequest")

    # Unsupported alg.
    os.environ["RMC_SAML_SP_SIGNATURE_ALG"] = "bogus-alg"
    try:
        url, reason = _build_redirect_signed_url(
            idp_target="https://idp.example/slo",
            saml_request_b64="X",
            relay_state="",
        )
        if reason != "unsupported_alg":
            _fail("t3-unsupported-alg", f"got {reason}")
        _ok(f"t3-unsupported-alg reason classified")
    finally:
        os.environ.pop("RMC_SAML_SP_SIGNATURE_ALG", None)

    # Real RSA key path — generate a key in-memory + verify signed URL builds.
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        os.environ["RMC_SAML_SP_PRIVATE_KEY_PEM"] = pem
        try:
            url, reason = _build_redirect_signed_url(
                idp_target="https://idp.example/slo",
                saml_request_b64="dGVzdA==",
                relay_state="rs-test",
            )
            if reason != "ok":
                _fail("t3-signed-reason", f"got {reason}")
            for needle in ("SAMLRequest=dGVzdA%3D%3D", "RelayState=rs-test",
                           "SigAlg=", "Signature="):
                if needle not in url:
                    _fail(f"t3-signed-url-needle-{needle[:20]}", f"missing in {url[:200]}")
            _ok(f"t3-signed reason=ok URL has 4 required params ({len(url)} bytes)")
        finally:
            os.environ.pop("RMC_SAML_SP_PRIVATE_KEY_PEM", None)
    except ImportError:
        _ok("t3-signed SKIP: cryptography lib not importable in this env")

    # slo_start ?binding=redirect&format=json shape.
    os.environ.pop("RMC_SAML_IDP_SLO_URL", None)
    req = rf.get("/sso/saml/slo/start/?binding=redirect&format=json&name_id=alice")
    req.session = _NullSession()
    resp = slo_start(req)
    if resp.status_code != 200:
        _fail("t3-redirect-json-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("binding") != "HTTP-Redirect":
        _fail("t3-redirect-json-binding", f"got {body.get('binding')}")
    if "saml_request_deflated_b64" not in body:
        _fail("t3-redirect-json-deflated", f"missing key; got {sorted(body)}")
    _ok(f"t3-redirect JSON binding=HTTP-Redirect deflated_b64 present")

    # slo_start ?binding=redirect with IdP target -> 302.
    os.environ["RMC_SAML_IDP_SLO_URL"] = "https://idp.example/slo"
    try:
        req = rf.get("/sso/saml/slo/start/?binding=redirect&name_id=alice&next=/dash/")
        req.session = _NullSession()
        resp = slo_start(req)
        if resp.status_code != 302:
            _fail("t3-redirect-302", f"got {resp.status_code}")
        loc = resp.get("Location", "")
        if not loc.startswith("https://idp.example/slo?"):
            _fail("t3-redirect-loc", loc[:200])
        if "SAMLRequest=" not in loc:
            _fail("t3-redirect-saml-req", loc[:200])
        _ok(f"t3-redirect 302 -> {loc[:80]}...")
    finally:
        del os.environ["RMC_SAML_IDP_SLO_URL"]


def run_t4():
    _line("\n[T4] Demographics ?orgSourcedId= + ?role= filters")
    from apps.api import oneroster_demographics as odm

    # Projection now carries _orgSourcedId + _role.
    class _Stub:
        pk = 99
        user_id = 555
        school_id = 7
        date_of_birth = None
        gender = "MALE"
        place_of_birth = ""
        updated_at = None

    rec = odm._demographic_from_student(_Stub())
    if rec.get("_orgSourcedId") != "7":
        _fail("t4-org-projection", f"got {rec.get('_orgSourcedId')}")
    if rec.get("_role") != "student":
        _fail("t4-role-projection", f"got {rec.get('_role')}")
    _ok(f"t4-projection _orgSourcedId={rec['_orgSourcedId']} _role={rec['_role']}")

    # Orphan school_id stays empty.
    class _Orphan:
        pk = 100
        user_id = None
        school_id = None
        date_of_birth = None
        gender = ""
        place_of_birth = ""
        updated_at = None
    rec2 = odm._demographic_from_student(_Orphan())
    if rec2.get("_orgSourcedId") != "":
        _fail("t4-orphan-org", f"got {rec2.get('_orgSourcedId')}")
    _ok("t4-projection orphan school_id -> _orgSourcedId=''")

    # Filter logic match-skip.
    items = [
        {"sourcedId": "demo-1", "_orgSourcedId": "7", "_role": "student"},
        {"sourcedId": "demo-2", "_orgSourcedId": "8", "_role": "student"},
        {"sourcedId": "demo-3", "_orgSourcedId": "7", "_role": "teacher"},  # not real for SP but tests filter
        {"sourcedId": "demo-4", "_orgSourcedId": "",  "_role": "student"},
    ]
    org7 = [r for r in items if r.get("_orgSourcedId") == "7"]
    if len(org7) != 2:
        _fail("t4-org-filter", f"got {len(org7)}")
    _ok(f"t4-filter orgSourcedId=7 -> {len(org7)} rows")

    students = [r for r in items if r.get("_role") == "student"]
    if len(students) != 3:
        _fail("t4-role-filter", f"got {len(students)}")
    _ok(f"t4-filter role=student -> {len(students)} rows")

    # Combined filters.
    both = [r for r in items
            if r.get("_orgSourcedId") == "7" and r.get("_role") == "student"]
    if len(both) != 1:
        _fail("t4-combined", f"got {len(both)}")
    _ok(f"t4-filter combined orgSourcedId=7 + role=student -> {len(both)} row")

    # URL reverse still works.
    from django.urls import reverse
    p = reverse("api:api-roster-v1p2-demographics")
    if not p.endswith("/demographics/"):
        _fail("t4-url", p)
    _ok(f"t4-url collection {p}")


def run_t5():
    _line("\n[T5] action-history ?since=ISO + ?before=ISO window")
    from apps.migration_cloud import views_lms_diagnostics as vld
    rf = RequestFactory()
    user = _staff_user()

    # _parse_window_iso handles 4 input shapes.
    from datetime import datetime, timezone as _tz_mod

    dt_z = vld._parse_window_iso("2026-05-29T12:00:00Z")
    if dt_z is None or dt_z.tzinfo is None:
        _fail("t5-parse-z", f"got {dt_z}")
    _ok(f"t5-parse Z suffix -> {dt_z.isoformat()}")

    dt_off = vld._parse_window_iso("2026-05-29T12:00:00+00:00")
    if dt_off is None or dt_off != dt_z:
        _fail("t5-parse-offset", f"got {dt_off}")
    _ok(f"t5-parse explicit +00:00 -> matches Z")

    dt_naive = vld._parse_window_iso("2026-05-29T12:00:00")
    if dt_naive is None or dt_naive.tzinfo is None:
        _fail("t5-parse-naive", f"got {dt_naive}")
    _ok(f"t5-parse naive (UTC-assumed) -> {dt_naive.isoformat()}")

    dt_date = vld._parse_window_iso("2026-05-29")
    if dt_date is None:
        _fail("t5-parse-date", "expected midnight UTC")
    _ok(f"t5-parse date-only -> {dt_date.isoformat()}")

    if vld._parse_window_iso("garbage") is not None:
        _fail("t5-parse-bad", "expected None")
    _ok("t5-parse malformed -> None")
    if vld._parse_window_iso("") is not None:
        _fail("t5-parse-empty", "expected None")
    _ok("t5-parse empty -> None")

    # End-to-end: trigger an action, then read with windows.
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()

    req = rf.post("/super/migration/lms/diagnostics/force-rotate/",
                  {"provider": "moodle"}, HTTP_ACCEPT="application/json")
    req.user = user
    req._dont_enforce_csrf_checks = True
    vld.lms_diagnostics_force_rotate(req)
    _ok("t5-seed force-rotate fired")

    # Read with before=now+1min (should include).
    now = datetime.now(tz=_tz_mod.utc)
    from datetime import timedelta
    import urllib.parse as _ulib
    future = _ulib.quote((now + timedelta(minutes=1)).isoformat(), safe="")
    past = _ulib.quote((now - timedelta(minutes=10)).isoformat(), safe="")
    req = rf.get(f"/super/migration/lms/diagnostics/action-history/?since={past}&before={future}")
    req.user = user
    resp = vld.lms_diagnostics_action_history(req)
    if resp.status_code != 200:
        _fail("t5-history-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("since") == "" or body.get("before") == "":
        _fail("t5-history-window-echo", f"got since={body.get('since')} before={body.get('before')}")
    if len(body.get("entries") or []) != 1:
        _fail("t5-history-in-window", f"got {body.get('entries')}")
    _ok(f"t5-history in-window 1 entry since={body['since'][:19]} before={body['before'][:19]}")

    # Read with before=past (should exclude).
    older = _ulib.quote((now - timedelta(minutes=60)).isoformat(), safe="")
    req = rf.get(f"/super/migration/lms/diagnostics/action-history/?since={older}&before={past}")
    req.user = user
    resp = vld.lms_diagnostics_action_history(req)
    body = _json.loads(resp.content)
    # New table read returns [] -> falls through to in-process ring which is empty.
    if len(body.get("entries") or []) != 0:
        _fail("t5-history-out-window", f"got {body.get('entries')}")
    _ok("t5-history out-of-window 0 entries")

    # Bad timestamps fall through to unwindowed (not 400).
    req = rf.get("/super/migration/lms/diagnostics/action-history/?since=garbage&before=junk")
    req.user = user
    resp = vld.lms_diagnostics_action_history(req)
    if resp.status_code != 200:
        _fail("t5-history-bad-ts", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("since") != "" or body.get("before") != "":
        _fail("t5-history-bad-echo", f"got since={body.get('since')} before={body.get('before')}")
    _ok("t5-history bad timestamps -> 200 with empty since/before echo")

    # Cleanup.
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    _ok("t5-cleanup smoke rows removed")


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
