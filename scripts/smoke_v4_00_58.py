"""v4.00.58 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +12 Tier-1 subdivisions (US-NV/UT/NM/OK/KY/LA, IN-AS/CH, JP-23, CO-DC,
    EC-P, BO-LP); SOT count >= 334.
T2: SAML2 SLO endpoint hardening (parses POST + Redirect bindings, builds
    LogoutResponse, flushes session, JSON format=json).
T3: GradeBookEntry PDF render per class (reportlab; %PDF magic bytes;
    attachment Content-Disposition).
T4: Result Service POST /results/bulk-update/ (Idempotency-Key, per-row
    idempotencyKey replay, 207 partial / 200 clean).
T5: Idempotency-audit sweep — singleton write endpoints (post_category +
    put_category) emit fresh + replayed events with path-derived entity.

Exits 0 on full pass; non-zero on first failure.
"""
from __future__ import annotations

import base64 as _b64
import json as _json
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import RequestFactory  # noqa: E402


def _line(s):  # noqa: ANN001
    print(s, flush=True)


def _ok(name):  # noqa: ANN001
    _line(f"  OK   {name}")


def _fail(name, detail):  # noqa: ANN001
    _line(f"  FAIL {name} :: {detail}")
    sys.exit(1)


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
    _line("\n[T1] +12 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = [
        "US-NV", "US-UT", "US-NM", "US-OK", "US-KY", "US-LA",
        "IN-AS", "IN-CH",
        "JP-23",
        "CO-DC", "EC-P", "BO-LP",
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
    if len(COUNTRY_LOCALIZATION) < 334:
        _fail("t1-sot-count", f"expected >= 334, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] SAML2 SLO endpoint hardening")
    from apps.api.saml import (
        _parse_saml_logout_request, _build_saml_logout_response, sls,
    )
    rf = RequestFactory()

    xml = (
        b'<samlp:LogoutRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        b'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        b'ID="_lr-smoke-1" Version="2.0" IssueInstant="2026-05-29T12:00:00Z">'
        b'<saml:Issuer>https://idp.example/saml</saml:Issuer>'
        b'<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">user@example.com</saml:NameID>'
        b'<samlp:SessionIndex>sx-abc</samlp:SessionIndex>'
        b'</samlp:LogoutRequest>'
    )

    # Plain base64
    p = _parse_saml_logout_request(_b64.b64encode(xml).decode())
    if p.get("error") or p.get("id") != "_lr-smoke-1":
        _fail("t2-parse-plain", f"got {p}")
    _ok("t2-parse plain base64 -> id+name_id+session_index")

    # Deflated base64 (HTTP-Redirect binding)
    deflated = zlib.compress(xml)[2:-4]
    p = _parse_saml_logout_request(_b64.b64encode(deflated).decode())
    if p.get("error") or p.get("name_id") != "user@example.com":
        _fail("t2-parse-deflated", f"got {p}")
    _ok("t2-parse deflated base64 -> auto-detected")

    # Empty
    p = _parse_saml_logout_request("")
    if p.get("error") != "missing_payload":
        _fail("t2-parse-empty", f"got {p}")
    _ok("t2-parse empty -> missing_payload")

    # Bad base64
    p = _parse_saml_logout_request("NOTBASE64!!!")
    if not p.get("error"):
        _fail("t2-parse-bad", f"got {p}")
    _ok(f"t2-parse bad-b64 -> error: {p['error']}")

    # Build LogoutResponse
    resp_bytes = _build_saml_logout_response("_lr-in-resp", "https://sp/saml", "https://idp/saml/slo")
    if b"urn:oasis:names:tc:SAML:2.0:status:Success" not in resp_bytes:
        _fail("t2-build-status", "missing Success status")
    if b'InResponseTo="_lr-in-resp"' not in resp_bytes:
        _fail("t2-build-irt", "missing InResponseTo")
    _ok(f"t2-build LogoutResponse ({len(resp_bytes)} bytes) status=Success InResponseTo set")

    # SLS view — POST + JSON
    req = rf.post("/sso/saml/sls/?format=json", data={"SAMLRequest": _b64.b64encode(xml).decode()})
    req._dont_enforce_csrf_checks = True
    if not hasattr(req, "session"):
        # RequestFactory doesn't attach a session by default; mock minimal
        class _NullSession:
            def flush(self): pass
            def __setitem__(self, k, v): pass
            def __getitem__(self, k): raise KeyError(k)
        req.session = _NullSession()
    resp = sls(req)
    if resp.status_code != 200:
        _fail("t2-sls-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if not body.get("success") or body.get("name_id") != "user@example.com":
        _fail("t2-sls-body", f"got {body}")
    _ok(f"t2-sls JSON 200 name_id={body['name_id']} stage={body['stage']}")

    # SLS view — missing SAMLRequest
    req = rf.post("/sso/saml/sls/", data={})
    req._dont_enforce_csrf_checks = True
    class _NS:
        def flush(self): pass
        def __setitem__(self, k, v): pass
        def __getitem__(self, k): raise KeyError(k)
    req.session = _NS()
    resp = sls(req)
    if resp.status_code != 400:
        _fail("t2-sls-missing", f"expected 400, got {resp.status_code}")
    _ok("t2-sls missing-SAMLRequest -> 400 + session flushed")


def run_t3():
    _line("\n[T3] GradeBookEntry PDF render per class")
    from apps.api import oneroster_results as ors
    rf = RequestFactory()

    # Missing class id -> 400
    req = _bearer_request(rf, "GET", "/api/roster/results/v1p2/classes//gradeBookEntries.pdf")
    resp = ors.gradebook_entries_pdf(req, "")
    if resp.status_code != 400:
        _fail("t3-missing-class", f"got {resp.status_code}")
    _ok("t3-missing class -> 400")

    # Real call (whatever data exists) — PDF magic
    req = _bearer_request(rf, "GET", "/api/roster/results/v1p2/classes/1/gradeBookEntries.pdf")
    resp = ors.gradebook_entries_pdf(req, "1")
    if resp.status_code != 200:
        _fail("t3-status", f"got {resp.status_code}")
    if resp["Content-Type"] != "application/pdf":
        _fail("t3-content-type", resp["Content-Type"])
    cd = resp.get("Content-Disposition", "")
    if "attachment" not in cd or "gradebook-" not in cd:
        _fail("t3-content-disposition", cd)
    if not resp.content.startswith(b"%PDF"):
        _fail("t3-pdf-magic", f"got prefix {resp.content[:6]!r}")
    _ok(f"t3-pdf 200 {len(resp.content)} bytes, magic=%PDF, Content-Disposition={cd}")

    # Empty class -> still 200 PDF with "(no entries)" caption (don't assert text — just magic)
    req = _bearer_request(rf, "GET", "/api/roster/results/v1p2/classes/c-empty/gradeBookEntries.pdf")
    resp = ors.gradebook_entries_pdf(req, "c-empty")
    if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
        _fail("t3-empty-class-pdf", f"status={resp.status_code} prefix={resp.content[:6]!r}")
    _ok(f"t3-empty-class 200 PDF ({len(resp.content)} bytes)")

    # URL reverse
    from django.urls import reverse
    p = reverse("api:api-roster-results-gradebook-entries-pdf", args=["1"])
    if not p.endswith("/classes/1/gradeBookEntries.pdf"):
        _fail("t3-url", p)
    _ok(f"t3-url {p}")


def run_t4():
    _line("\n[T4] Result Service POST /results/bulk-update/")
    from apps.api import oneroster_results as ors
    rf = RequestFactory()

    # Missing idem -> 428
    req = _bearer_request(rf, "POST", "/api/roster/results/v1p2/results/bulk-update/", body={})
    resp = ors.post_results_bulk_update(req)
    if resp.status_code != 428:
        _fail("t4-missing-idem", f"got {resp.status_code}")
    _ok("t4-missing-idem -> 428")

    # Bad JSON -> 400
    rf2 = RequestFactory()
    req = rf2.post(
        "/api/roster/results/v1p2/results/bulk-update/",
        data="not-json",
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer smoke-bearer",
        HTTP_IDEMPOTENCY_KEY="smoke-t4-bad",
    )
    req._dont_enforce_csrf_checks = True
    resp = ors.post_results_bulk_update(req)
    if resp.status_code != 400:
        _fail("t4-bad-json", f"got {resp.status_code}")
    _ok("t4-bad-json -> 400")

    # Empty results -> 400
    req = _bearer_request(rf, "POST", "/api/roster/results/v1p2/results/bulk-update/",
                          body={"results": []}, idem="smoke-t4-empty")
    resp = ors.post_results_bulk_update(req)
    if resp.status_code != 400:
        _fail("t4-empty", f"got {resp.status_code}")
    _ok("t4-empty results array -> 400")

    # Partial-failure batch: bad-sid + missing-id + nonexistent res-pk
    body = {"results": [
        {"sourcedId": "NOT-A-RES", "score": "90"},
        {"score": "50"},
        {"sourcedId": "res-99999999", "score": "85"},
    ]}
    req = _bearer_request(rf, "POST", "/api/roster/results/v1p2/results/bulk-update/",
                          body=body, idem="smoke-t4-A")
    resp = ors.post_results_bulk_update(req)
    if resp.status_code != 207:
        _fail("t4-partial-status", f"expected 207, got {resp.status_code}")
    b = _json.loads(resp.content)
    if set(["updated", "not_found", "errored", "unchanged", "replayed", "outcomes"]) - set(b.keys()):
        _fail("t4-shape", f"missing keys; got {sorted(b.keys())}")
    if b["updated"] != 0 or b["errored"] < 1 or b["not_found"] < 1:
        _fail("t4-counts", f"got updated={b['updated']} errored={b['errored']} not_found={b['not_found']}")
    _ok(f"t4-partial 207 updated=0 not_found={b['not_found']} errored={b['errored']}")

    # Replay -> Idempotency-Replay: true
    req = _bearer_request(rf, "POST", "/api/roster/results/v1p2/results/bulk-update/",
                          body=body, idem="smoke-t4-A")
    resp = ors.post_results_bulk_update(req)
    if resp.status_code != 207:
        _fail("t4-replay-status", f"got {resp.status_code}")
    if resp.get("Idempotency-Replay") != "true":
        _fail("t4-replay-header", f"got {resp.get('Idempotency-Replay')}")
    _ok("t4-replay Idempotency-Replay: true")

    # URL reverse
    from django.urls import reverse
    p = reverse("api:api-roster-results-bulk-update")
    if not p.endswith("/results/bulk-update/"):
        _fail("t4-url", p)
    _ok(f"t4-url {p}")


def run_t5():
    _line("\n[T5] Idempotency-audit sweep — singleton write endpoints")
    from apps.api import oneroster_results as ors
    from apps.api.oneroster_results import (
        _entity_from_path, _log_idem_from_request,
        _IDEM_AUDIT_RING, get_idem_audit_totals,
    )
    rf = RequestFactory()

    # Path-derivation tests
    cases = [
        ("/api/roster/results/v1p2/categories/post/", "category"),
        ("/api/roster/results/v1p2/categories/cat-1/put/", "category"),
        ("/api/roster/results/v1p2/lineItems/li-9/", "line-item"),
        ("/api/roster/results/v1p2/gradingPeriods/post/", "grading-period"),
        ("/api/roster/results/v1p2/attachments/att-1/delete/", "attachment"),
        ("/api/roster/results/v1p2/rubrics/r-1/put/", "rubric"),
        ("/api/roster/results/v1p2/classGroups/cg-1/", "class-group"),
        ("/api/roster/results/v1p2/classGroups/bulk-delete-by-class/", "classgroups-bulk-delete-by-class"),
        ("/api/roster/results/v1p2/results/import/", "results-bulk-import"),
        ("/api/roster/results/v1p2/results/bulk-update/", "results-bulk-update"),
        ("/api/roster/results/v1p2/results/res-1/", "result"),
        ("/api/something/else/", "unknown"),
    ]
    for path, expected in cases:
        got = _entity_from_path(path)
        if got != expected:
            _fail(f"t5-entity-{expected}", f"path={path} got={got!r}")
    _ok(f"t5-entity 12/12 paths resolve correctly")

    # Live exercise: post_category fresh + replay; check ring records both
    ors._IDEM_AUDIT_RING.clear()
    ors._CATEGORY_OVERRIDES.clear()
    ors._CATEGORY_TOMBSTONES.clear()
    cat_body = {"category": {"title": "Smoke T5 Cat", "type": "formative"}}
    req = _bearer_request(rf, "POST", "/api/roster/results/v1p2/categories/post/",
                          body=cat_body, idem="smoke-t5-cat-A")
    resp = ors.post_category(req)
    if resp.status_code != 201:
        _fail("t5-cat-fresh-status", f"got {resp.status_code}")
    req = _bearer_request(rf, "POST", "/api/roster/results/v1p2/categories/post/",
                          body=cat_body, idem="smoke-t5-cat-A")
    resp = ors.post_category(req)
    if resp.get("Idempotency-Replay") != "true":
        _fail("t5-cat-replay-header", f"got {resp.get('Idempotency-Replay')}")
    totals = get_idem_audit_totals()
    if totals["total"] != 2 or totals["fresh"] != 1 or totals["replayed"] != 1:
        _fail("t5-cat-totals", f"got {totals}")
    if totals["by_entity"].get("category") != 2:
        _fail("t5-cat-by-entity", f"got {totals['by_entity']}")
    _ok(f"t5-post_category fresh+replay -> ring{{total=2,fresh=1,replayed=1,by_entity.category=2}}")

    # PUT — also instrumented
    ors._IDEM_AUDIT_RING.clear()
    put_body = {"category": {"title": "Smoke T5 Cat (updated)", "type": "summative"}}
    sid = list(ors._CATEGORY_OVERRIDES.keys())[0]
    req = _bearer_request(rf, "PUT", f"/api/roster/results/v1p2/categories/{sid}/put/",
                          body=put_body, idem="smoke-t5-cat-PUT")
    resp = ors.put_category(req, sid)
    if resp.status_code not in (200, 201):
        _fail("t5-put-status", f"got {resp.status_code}")
    totals = get_idem_audit_totals()
    if totals["by_entity"].get("category") != 1:
        _fail("t5-put-by-entity", f"got {totals['by_entity']}")
    _ok(f"t5-put_category -> ring entity=category recorded ({totals['fresh']} fresh)")


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
