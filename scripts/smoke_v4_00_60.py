"""v4.00.60 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +15 Tier-1 subdivisions (US-IA/KS/WI/OR/IN; IN-BR/MN/NL; JP-22; PH-NCR;
    VN-SG; TR-34; UA-30; MX-JAL2; BR-BA); SOT >= 364.
T2: OneRoster v1.2 demographics POST/PUT write coverage with
    Idempotency-Key contract + override-ring round-trip.
T3: LMS connector auto-prune on refresh_revoked (sweep + Celery task +
    beat entry + env disable + dry-run).
T4: /super/migration/lms/diagnostics/ last-action history panel
    (ring-buffer + JSON endpoint + totals).
T5: SP-initiated SLO at /sso/saml/slo/{start,callback}/ (build
    LogoutRequest auto-submit form + parse LogoutResponse).

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
        username="smoke-v4-00-60-staff",
        defaults={"email": "smoke@v4-00-60.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


class _NullSession:
    _data = {}
    def flush(self): self._data = {}
    def __setitem__(self, k, v): self._data[k] = v
    def __getitem__(self, k):
        if k in self._data:
            return self._data[k]
        raise KeyError(k)
    def get(self, k, default=None): return self._data.get(k, default)


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
        "US-IA", "US-KS", "US-WI", "US-OR", "US-IN",
        "IN-BR", "IN-MN", "IN-NL",
        "JP-22", "PH-NCR", "VN-SG", "TR-34", "UA-30",
        "MX-JAL2", "BR-BA",
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
    if len(COUNTRY_LOCALIZATION) < 364:
        _fail("t1-sot-count", f"expected >= 364, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] OneRoster v1.2 demographics POST/PUT writes")
    from apps.api import oneroster_demographics as odm
    rf = RequestFactory()

    # 428 — missing Idempotency-Key on POST.
    req = _bearer_request(rf, "POST", "/api/roster/v1p2/demographics/put/",
                          body={"demographic": {"studentSourcedId": "1", "sex": "male"}})
    resp = odm.post_demographic(req)
    if resp.status_code != 428:
        _fail("t2-post-missing-idem", f"got {resp.status_code}")
    _ok("t2-post missing Idempotency-Key -> 428")

    # 400 — POST with no body.
    req = _bearer_request(rf, "POST", "/api/roster/v1p2/demographics/put/", idem="ik-empty-1")
    resp = odm.post_demographic(req)
    if resp.status_code != 400:
        _fail("t2-post-empty", f"got {resp.status_code}")
    _ok("t2-post empty body -> 400")

    # 400 — POST with no envelope.
    req = _bearer_request(rf, "POST", "/api/roster/v1p2/demographics/put/",
                          body={"foo": 1}, idem="ik-no-env-1")
    resp = odm.post_demographic(req)
    if resp.status_code != 400:
        _fail("t2-post-no-env", f"got {resp.status_code}")
    _ok("t2-post no demographic envelope -> 400")

    # 400 — POST missing studentSourcedId AND sourcedId.
    req = _bearer_request(rf, "POST", "/api/roster/v1p2/demographics/put/",
                          body={"demographic": {"sex": "male"}}, idem="ik-no-stu-1")
    resp = odm.post_demographic(req)
    if resp.status_code != 400:
        _fail("t2-post-no-student", f"got {resp.status_code}")
    _ok("t2-post missing student sourced id -> 400")

    # 404 — POST with studentSourcedId that doesn't resolve.
    req = _bearer_request(rf, "POST", "/api/roster/v1p2/demographics/put/",
                          body={"demographic": {"studentSourcedId": "999999999", "sex": "male"}},
                          idem="ik-bad-stu-1")
    resp = odm.post_demographic(req)
    if resp.status_code != 404:
        _fail("t2-post-not-found", f"got {resp.status_code}")
    _ok("t2-post student not found -> 404")

    # 428 — missing Idempotency-Key on PUT.
    req = _bearer_request(rf, "PUT", "/api/roster/v1p2/demographics/demo-1/put/")
    resp = odm.put_demographic(req, "demo-1")
    if resp.status_code != 428:
        _fail("t2-put-missing-idem", f"got {resp.status_code}")
    _ok("t2-put missing Idempotency-Key -> 428")

    # 400 — PUT with bad sourced_id (no demo- prefix).
    req = _bearer_request(rf, "PUT", "/api/roster/v1p2/demographics/bad-id/put/",
                          body={"demographic": {"sex": "male"}}, idem="ik-bad-sid-1")
    resp = odm.put_demographic(req, "bad-id")
    if resp.status_code != 400:
        _fail("t2-put-bad-sid", f"got {resp.status_code}")
    _ok("t2-put bad sourced id -> 400")

    # 404 — PUT to non-existent demo-pk.
    req = _bearer_request(rf, "PUT", "/api/roster/v1p2/demographics/demo-999999/put/",
                          body={"demographic": {"sex": "male"}}, idem="ik-no-row-1")
    resp = odm.put_demographic(req, "demo-999999")
    if resp.status_code != 404:
        _fail("t2-put-not-found", f"got {resp.status_code}")
    _ok("t2-put not-found -> 404")

    # Override ring round-trip: pure-function test (no DB row required).
    odm._set_demographic_overrides("demo-42", {
        "americanIndianOrAlaskaNative": "no",
        "asian": "yes",
        "hispanicOrLatinoEthnicity": "no",
        "countryOfBirthCode": "US",
        "stateOfBirthAbbreviation": "CA",
    })
    if "demo-42" not in odm._DEMOGRAPHIC_OVERRIDES:
        _fail("t2-override-ring", "demo-42 missing")
    stored = odm._DEMOGRAPHIC_OVERRIDES["demo-42"]
    if stored.get("asian") != "yes" or stored.get("countryOfBirthCode") != "US":
        _fail("t2-override-values", f"got {stored}")
    _ok(f"t2-override-ring stored 5 fields for demo-42")

    # 409 — Idempotency-Key collision with different payload.
    from django.core.cache import cache
    cache.set("roster:demographics:idempo:post:ik-collide-1",
              {"payload_hash": "different-hash-deliberate", "status": 200,
               "response_body": {"demographic": {}}}, 60)
    req = _bearer_request(rf, "POST", "/api/roster/v1p2/demographics/put/",
                          body={"demographic": {"studentSourcedId": "1", "sex": "male"}},
                          idem="ik-collide-1")
    resp = odm.post_demographic(req)
    if resp.status_code != 409:
        _fail("t2-collision", f"got {resp.status_code}")
    _ok("t2-post idem collision -> 409")

    # URL reverses.
    from django.urls import reverse
    p1 = reverse("api:api-roster-v1p2-post-demographic")
    p2 = reverse("api:api-roster-v1p2-put-demographic", args=["demo-1"])
    if not p1.endswith("/demographics/put/"):
        _fail("t2-url-post", p1)
    if not p2.endswith("/demographics/demo-1/put/"):
        _fail("t2-url-put", p2)
    _ok(f"t2-url-post {p1}")
    _ok(f"t2-url-put {p2}")


def run_t3():
    _line("\n[T3] LMS connector auto-prune on refresh_revoked")
    from apps.integrations_marketplace.lms_oauth_auto_prune import (
        sweep_lms_oauth_auto_prune, _PRUNE_COURSE_ID,
        auto_prune_revoked_lms_tokens, DEFAULT_MAX_ROWS,
    )

    out = sweep_lms_oauth_auto_prune()
    expected = {"considered", "pruned", "kept", "skipped", "results", "max_rows", "dry_run"}
    missing = expected - set(out.keys())
    if missing:
        _fail("t3-sweep-shape", f"missing {sorted(missing)}")
    if out["dry_run"] is not False:
        _fail("t3-dry-run-default", f"got {out['dry_run']}")
    _ok(f"t3-sweep shape OK considered={out['considered']} pruned={out['pruned']} dry_run={out['dry_run']}")

    if _PRUNE_COURSE_ID != "_auto_prune":
        _fail("t3-marker", f"got {_PRUNE_COURSE_ID!r}")
    _ok(f"t3-marker {_PRUNE_COURSE_ID}")

    if auto_prune_revoked_lms_tokens is None:
        _fail("t3-celery-task", "shared_task registration is None")
    _ok("t3-celery-task auto_prune_revoked_lms_tokens registered")

    if DEFAULT_MAX_ROWS != 500:
        _fail("t3-default-max-rows", f"got {DEFAULT_MAX_ROWS}")
    _ok(f"t3-default-max-rows {DEFAULT_MAX_ROWS}")

    # Dry-run env override.
    os.environ["RMC_LMS_OAUTH_AUTO_PRUNE_DRY_RUN"] = "1"
    try:
        out2 = sweep_lms_oauth_auto_prune()
        if out2["dry_run"] is not True:
            _fail("t3-dry-run-env", f"got {out2['dry_run']}")
        _ok("t3-dry-run env override honored")
    finally:
        del os.environ["RMC_LMS_OAUTH_AUTO_PRUNE_DRY_RUN"]

    # Explicit dry-run kwarg.
    out3 = sweep_lms_oauth_auto_prune(dry_run=True, max_rows=10)
    if out3["dry_run"] is not True or out3["max_rows"] != 10:
        _fail("t3-explicit-kwargs", f"got {out3}")
    _ok(f"t3-explicit kwargs dry_run=True max_rows=10")

    # Beat entry presence.
    from apps.integrations_marketplace.beat_schedule import get_lms_beat_schedule
    sched = get_lms_beat_schedule()
    if "integrations-lms-oauth-auto-prune" not in sched:
        _fail("t3-beat-entry", f"missing entry; got keys={sorted(sched.keys())}")
    entry = sched["integrations-lms-oauth-auto-prune"]
    if entry["task"] != "integrations_marketplace.auto_prune_revoked_lms_tokens":
        _fail("t3-beat-task", entry["task"])
    _ok(f"t3-beat integrations-lms-oauth-auto-prune wired -> {entry['task']}")

    # Env disable.
    os.environ["RMC_LMS_OAUTH_AUTO_PRUNE_BEAT_DISABLED"] = "1"
    try:
        sched2 = get_lms_beat_schedule()
        if "integrations-lms-oauth-auto-prune" in sched2:
            _fail("t3-beat-disabled", "should have been omitted")
        _ok("t3-beat env disable honored")
    finally:
        del os.environ["RMC_LMS_OAUTH_AUTO_PRUNE_BEAT_DISABLED"]


def run_t4():
    _line("\n[T4] Diagnostics 'Last action history' panel")
    from apps.migration_cloud import views_lms_diagnostics as vld
    rf = RequestFactory()
    user = _staff_user()

    # Reset the ring for a clean baseline.
    vld._LAST_ACTION_RING.clear()

    # Empty snapshot.
    snap = vld.get_last_action_snapshot(limit=10)
    if snap != []:
        _fail("t4-empty-snapshot", f"got {snap}")
    _ok("t4-empty-snapshot []")

    # Record a force_refresh action (mimics the view path).
    req = rf.post("/super/migration/lms/diagnostics/force-refresh/", {"provider": "canvas"},
                  HTTP_ACCEPT="application/json")
    req.user = user
    req._dont_enforce_csrf_checks = True
    resp = vld.lms_diagnostics_force_refresh(req)
    if resp.status_code != 200:
        _fail("t4-refresh-trigger", f"got {resp.status_code}")
    if not vld._LAST_ACTION_RING:
        _fail("t4-record-1", "ring still empty after force-refresh")
    _ok(f"t4-record-1 ring len={len(vld._LAST_ACTION_RING)}")

    # Record a force_rotate action.
    req = rf.post("/super/migration/lms/diagnostics/force-rotate/",
                  {"provider": "google_classroom"}, HTTP_ACCEPT="application/json")
    req.user = user
    req._dont_enforce_csrf_checks = True
    resp = vld.lms_diagnostics_force_rotate(req)
    if resp.status_code != 200:
        _fail("t4-rotate-trigger", f"got {resp.status_code}")
    if len(vld._LAST_ACTION_RING) != 2:
        _fail("t4-record-2", f"ring len={len(vld._LAST_ACTION_RING)}")
    _ok(f"t4-record-2 ring len=2")

    # Snapshot newest-first.
    snap = vld.get_last_action_snapshot(limit=10)
    if len(snap) != 2:
        _fail("t4-snapshot-len", f"got {len(snap)}")
    if snap[0]["action"] != "force_rotate" or snap[1]["action"] != "force_refresh":
        _fail("t4-snapshot-order", f"got {[s['action'] for s in snap]}")
    if not snap[0].get("actor_hash"):
        _fail("t4-actor-hash", "missing actor hash")
    _ok(f"t4-snapshot order=newest-first actor_hash={snap[0]['actor_hash']}")

    # Totals.
    totals = vld._action_totals()
    if totals.get("total") != 2:
        _fail("t4-totals-total", f"got {totals}")
    if totals["by_action"].get("force_refresh") != 1:
        _fail("t4-totals-by-action", f"got {totals['by_action']}")
    _ok(f"t4-totals total=2 by_action={totals['by_action']}")

    # JSON endpoint.
    req = rf.get("/super/migration/lms/diagnostics/action-history/?limit=5")
    req.user = user
    resp = vld.lms_diagnostics_action_history(req)
    if resp.status_code != 200:
        _fail("t4-json-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if "entries" not in body or "totals" not in body:
        _fail("t4-json-shape", f"got {sorted(body.keys())}")
    if len(body["entries"]) != 2:
        _fail("t4-json-entries", f"got {len(body['entries'])}")
    _ok(f"t4-json 200 entries={len(body['entries'])} totals={body['totals']['total']}")

    # JSON endpoint honors limit.
    for i in range(5):
        vld._record_action(request=req, action="force_refresh", provider="canvas", summary={"considered": i})
    req = rf.get("/super/migration/lms/diagnostics/action-history/?limit=3")
    req.user = user
    resp = vld.lms_diagnostics_action_history(req)
    body = _json.loads(resp.content)
    if body["limit"] != 3 or len(body["entries"]) != 3:
        _fail("t4-json-limit", f"limit={body['limit']} entries={len(body['entries'])}")
    _ok(f"t4-json limit=3 enforced ({len(body['entries'])} entries)")

    # URL reverses.
    from django.urls import reverse
    p = reverse("migration_cloud_super:migration_cloud_lms_diagnostics_action_history")
    _ok(f"t4-url {p}")


def run_t5():
    _line("\n[T5] SP-initiated SLO (LogoutRequest + LogoutResponse callback)")
    from apps.api.saml import (
        slo_start, slo_callback,
        _build_saml_logout_request, _parse_saml_logout_response,
    )
    rf = RequestFactory()

    # Build LogoutRequest pure-function.
    xml = _build_saml_logout_request(
        name_id="alice@example.com",
        session_index="sx-42",
        issuer="rmc-sp",
        destination="https://idp.example/slo",
    )
    if b"<samlp:LogoutRequest" not in xml:
        _fail("t5-build-root", "missing LogoutRequest root")
    if b"alice@example.com" not in xml:
        _fail("t5-build-name-id", "missing NameID")
    if b"sx-42" not in xml:
        _fail("t5-build-session-idx", "missing SessionIndex")
    if b"https://idp.example/slo" not in xml:
        _fail("t5-build-destination", "missing Destination")
    if b"<saml:Issuer>rmc-sp</saml:Issuer>" not in xml:
        _fail("t5-build-issuer", "missing Issuer")
    _ok(f"t5-build LogoutRequest ({len(xml)} bytes) carries Issuer+NameID+SessionIndex+Destination")

    # Build without session_index (only NameID).
    xml2 = _build_saml_logout_request(
        name_id="bob@example.com", session_index="",
        issuer="rmc-sp", destination="",
    )
    if b"SessionIndex" in xml2:
        _fail("t5-build-no-sessionidx", "should have been omitted")
    _ok("t5-build session_index omitted when empty")

    # slo_start ?format=json with no IdP target -> 503 fallback OR JSON depending on
    # whether RMC_SAML_IDP_SLO_URL is set; with env clear, json path always works.
    os.environ.pop("RMC_SAML_IDP_SLO_URL", None)
    req = rf.get("/sso/saml/slo/start/?format=json&name_id=alice@example.com&session_index=sx-1&next=/dashboard")
    req.session = _NullSession()
    resp = slo_start(req)
    if resp.status_code != 200:
        _fail("t5-start-json-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("stage") != "logout_request_built":
        _fail("t5-start-stage", f"got {body.get('stage')}")
    if body.get("name_id") != "alice@example.com":
        _fail("t5-start-name-id", f"got {body.get('name_id')}")
    if body.get("session_index") != "sx-1":
        _fail("t5-start-session-idx", f"got {body.get('session_index')}")
    if body.get("relay_state") != "/dashboard":
        _fail("t5-start-relay", f"got {body.get('relay_state')}")
    if body.get("binding") != "HTTP-POST":
        _fail("t5-start-binding", f"got {body.get('binding')}")
    if not body.get("logout_request_b64"):
        _fail("t5-start-b64", "missing logout_request_b64")
    _ok(f"t5-start JSON stage=logout_request_built binding=HTTP-POST relay=/dashboard")

    # slo_start HTML path with no IdP target -> 503.
    req = rf.get("/sso/saml/slo/start/")
    req.session = _NullSession()
    resp = slo_start(req)
    if resp.status_code != 503:
        _fail("t5-start-html-no-idp", f"got {resp.status_code}")
    _ok("t5-start without IdP target -> 503 (idp_slo_target_missing)")

    # slo_start HTML path with IdP target -> auto-submit form.
    os.environ["RMC_SAML_IDP_SLO_URL"] = "https://idp.example/slo"
    try:
        req = rf.get("/sso/saml/slo/start/?name_id=carol@x.org&next=/courses/")
        req.session = _NullSession()
        resp = slo_start(req)
        if resp.status_code != 200:
            _fail("t5-start-html-status", f"got {resp.status_code}")
        if resp["Content-Type"] != "text/html; charset=utf-8":
            _fail("t5-start-html-ct", resp["Content-Type"])
        body_str = resp.content.decode("utf-8")
        if 'action="https://idp.example/slo"' not in body_str:
            _fail("t5-start-html-action", "missing action attr")
        if 'name="SAMLRequest"' not in body_str:
            _fail("t5-start-html-saml-req", "missing SAMLRequest field")
        if 'value="/courses/"' not in body_str:
            _fail("t5-start-html-relay", "missing RelayState")
        if "slo-start-form" not in body_str:
            _fail("t5-start-html-form-id", "missing form id")
        _ok(f"t5-start HTML 200 auto-submit form with SAMLRequest+RelayState+JS ({len(resp.content)} bytes)")
    finally:
        del os.environ["RMC_SAML_IDP_SLO_URL"]

    # Parse LogoutResponse pure-function.
    success_xml = (
        b'<samlp:LogoutResponse xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        b'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        b'ID="_lr-resp-1" Version="2.0" IssueInstant="2026-05-29T12:00:00Z" '
        b'InResponseTo="_rmc-lr-sp-abc123">'
        b'<saml:Issuer>https://idp.example</saml:Issuer>'
        b'<samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
        b'</samlp:LogoutResponse>'
    )
    parsed = _parse_saml_logout_response(_b64.b64encode(success_xml).decode())
    if parsed.get("error"):
        _fail("t5-parse-error", parsed["error"])
    if not parsed.get("status_code", "").endswith(":Success"):
        _fail("t5-parse-status", parsed.get("status_code"))
    if parsed.get("in_response_to") != "_rmc-lr-sp-abc123":
        _fail("t5-parse-in-response-to", parsed.get("in_response_to"))
    _ok(f"t5-parse LogoutResponse status={parsed['status_code']} in_response_to={parsed['in_response_to']}")

    # Failed Status code on LogoutResponse.
    fail_xml = success_xml.replace(b":status:Success", b":status:Responder")
    parsed_f = _parse_saml_logout_response(_b64.b64encode(fail_xml).decode())
    if parsed_f.get("status_code", "").endswith(":Success"):
        _fail("t5-parse-fail", parsed_f.get("status_code"))
    _ok(f"t5-parse non-Success status={parsed_f['status_code']}")

    # slo_callback JSON path with successful LogoutResponse.
    req = rf.post("/sso/saml/slo/callback/?format=json",
                  data={"SAMLResponse": _b64.b64encode(success_xml).decode(),
                        "RelayState": "/dashboard"})
    req._dont_enforce_csrf_checks = True
    req.session = _NullSession()
    resp = slo_callback(req)
    if resp.status_code != 200:
        _fail("t5-callback-json-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("stage") != "logged_out_sp_initiated":
        _fail("t5-callback-stage", f"got {body.get('stage')}")
    if not body.get("success"):
        _fail("t5-callback-success", f"got {body}")
    if body.get("relay_state") != "/dashboard":
        _fail("t5-callback-relay", f"got {body.get('relay_state')}")
    _ok(f"t5-callback JSON 200 stage=logged_out_sp_initiated relay=/dashboard")

    # slo_callback with NON-success Status -> 401.
    req = rf.post("/sso/saml/slo/callback/",
                  data={"SAMLResponse": _b64.b64encode(fail_xml).decode()})
    req._dont_enforce_csrf_checks = True
    req.session = _NullSession()
    resp = slo_callback(req)
    if resp.status_code != 401:
        _fail("t5-callback-non-success", f"got {resp.status_code}")
    _ok("t5-callback non-Success Status -> 401")

    # slo_callback missing SAMLResponse -> 400.
    req = rf.post("/sso/saml/slo/callback/", data={})
    req._dont_enforce_csrf_checks = True
    req.session = _NullSession()
    resp = slo_callback(req)
    if resp.status_code != 400:
        _fail("t5-callback-missing", f"got {resp.status_code}")
    _ok("t5-callback missing SAMLResponse -> 400")

    # slo_callback redirects on success when format != json.
    req = rf.post("/sso/saml/slo/callback/",
                  data={"SAMLResponse": _b64.b64encode(success_xml).decode(),
                        "RelayState": "/landing/"})
    req._dont_enforce_csrf_checks = True
    req.session = _NullSession()
    resp = slo_callback(req)
    if resp.status_code != 302:
        _fail("t5-callback-redirect-status", f"got {resp.status_code}")
    loc = resp.get("Location", "")
    if loc != "/landing/":
        _fail("t5-callback-redirect-loc", loc)
    _ok(f"t5-callback success redirect 302 -> {loc}")

    # Open-redirect defense: external RelayState becomes /.
    req = rf.post("/sso/saml/slo/callback/",
                  data={"SAMLResponse": _b64.b64encode(success_xml).decode(),
                        "RelayState": "https://evil.example/take-over"})
    req._dont_enforce_csrf_checks = True
    req.session = _NullSession()
    resp = slo_callback(req)
    if resp.get("Location") != "/":
        _fail("t5-callback-open-redirect", resp.get("Location"))
    _ok("t5-callback open-redirect defense: external target -> /")

    # Protocol-relative RelayState (//evil.example/...) defense.
    req = rf.post("/sso/saml/slo/callback/",
                  data={"SAMLResponse": _b64.b64encode(success_xml).decode(),
                        "RelayState": "//evil.example/take-over"})
    req._dont_enforce_csrf_checks = True
    req.session = _NullSession()
    resp = slo_callback(req)
    if resp.get("Location") != "/":
        _fail("t5-callback-proto-relative", resp.get("Location"))
    _ok("t5-callback open-redirect defense: protocol-relative -> /")

    # URL reverses.
    from django.urls import reverse
    p1 = reverse("sso_saml_slo_start")
    p2 = reverse("sso_saml_slo_callback")
    if not p1.endswith("/sso/saml/slo/start/"):
        _fail("t5-url-start", p1)
    if not p2.endswith("/sso/saml/slo/callback/"):
        _fail("t5-url-callback", p2)
    _ok(f"t5-url-start {p1}")
    _ok(f"t5-url-callback {p2}")


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
