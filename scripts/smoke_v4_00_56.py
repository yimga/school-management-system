"""v4.00.56 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +13 ISO 3166-2 subdivisions (US-VA/WA/NJ, IN-PB/HR/KL, JP-27, KR-26, AR-BA,
    NG-LA, NG-KN, ZA-GT, BR-MG) shape-asserted in COUNTRY_LOCALIZATION SOT.
T2: OneRoster GradeBookEntry projections (lineItem+category+classGroup+resultsRollup).
T3: LMS audit retention export download UI (list + serve + traversal refusal).
T4: Bulk-import per-row idempotency-key replay.
T5: /super/migration/lms/diagnostics/ operator dashboard (incl. ?format=json).

Exits 0 on full pass; non-zero on first failure.
"""
from __future__ import annotations

import json as _json
import os
import sys
import tempfile

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
        username="smoke-v4-00-56-staff",
        defaults={"email": "smoke@v4-00-56.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


def _bearer_request(rf, method, path, body=None, idem=None, row_idem=False):
    kwargs = {"content_type": "application/json", "HTTP_AUTHORIZATION": "Bearer smoke-bearer"}
    if idem:
        kwargs["HTTP_IDEMPOTENCY_KEY"] = idem
    if body is not None:
        kwargs["data"] = _json.dumps(body) if not isinstance(body, (bytes, str)) else body
    req = getattr(rf, method.lower())(path, **kwargs)
    req._dont_enforce_csrf_checks = True
    return req


# ---------------------------------------------------------------------------
# T1 — 13 ISO 3166-2 subdivisions in SOT.
# ---------------------------------------------------------------------------

def run_t1():
    _line("\n[T1] +13 ISO 3166-2 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = [
        "US-VA", "US-WA", "US-NJ",
        "IN-PB", "IN-HR", "IN-KL",
        "JP-27", "KR-26",
        "AR-BA",
        "NG-LA", "NG-KN",
        "ZA-GT",
        "BR-MG",
    ]
    for k in new_keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-present-{k}", f"missing or non-dict: {type(e).__name__}")
        for required in ("calendar_system", "school_types", "education_levels", "terminology"):
            if required not in e:
                _fail(f"t1-shape-{k}-{required}", f"missing {required}")
        if not isinstance(e["school_types"], list) or len(e["school_types"]) < 4:
            _fail(f"t1-school-types-{k}", "need >= 4 school_types")
        if not isinstance(e["education_levels"], list) or len(e["education_levels"]) < 3:
            _fail(f"t1-education-levels-{k}", "need >= 3 education_levels")
        _ok(f"t1-{k} shape OK ({len(e['school_types'])} types, {len(e['education_levels'])} levels)")
    if len(COUNTRY_LOCALIZATION) < 309:
        _fail("t1-sot-count", f"expected >= 309 entries, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


# ---------------------------------------------------------------------------
# T2 — GradeBookEntry projections.
# ---------------------------------------------------------------------------

def run_t2():
    _line("\n[T2] OneRoster GradeBookEntry projections")
    from apps.api import oneroster_results as ors
    rf = RequestFactory()

    # List endpoint
    req = _bearer_request(rf, "GET", "/api/roster/results/v1p2/gradeBookEntries/")
    resp = ors.gradebook_entries_collection(req)
    if resp.status_code != 200:
        _fail("t2-list-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if "gradeBookEntries" not in body:
        _fail("t2-list-envelope", f"missing gradeBookEntries key, got {sorted(body)}")
    _ok(f"t2-list 200 envelope=gradeBookEntries (entries={len(body['gradeBookEntries'])})")

    # Each projected entry has the 5 required keys
    if body["gradeBookEntries"]:
        e0 = body["gradeBookEntries"][0]
        for k in ("sourcedId", "lineItem", "category", "classGroups", "resultsRollup"):
            if k not in e0:
                _fail(f"t2-shape-{k}", f"missing {k} in projection")
        _ok("t2-shape sourcedId+lineItem+category+classGroups+resultsRollup all present")
        for k in ("count", "scored", "pending", "average", "min", "max"):
            if k not in e0["resultsRollup"]:
                _fail(f"t2-rollup-{k}", f"rollup missing {k}")
        _ok("t2-rollup shape count/scored/pending/avg/min/max all present")
    else:
        _ok("t2-list (empty list — no classrooms; shape unverifiable but route lives)")

    # Detail endpoint — bad sourcedId
    req = _bearer_request(rf, "GET", "/api/roster/results/v1p2/gradeBookEntries/bad-id/")
    resp = ors.gradebook_entry_detail(req, "bad-id")
    if resp.status_code != 400:
        _fail("t2-detail-bad-id", f"expected 400, got {resp.status_code}")
    _ok("t2-detail bad sourcedId -> 400")

    # Detail endpoint — not found
    req = _bearer_request(rf, "GET", "/api/roster/results/v1p2/gradeBookEntries/gbe-99999999/")
    resp = ors.gradebook_entry_detail(req, "gbe-99999999")
    if resp.status_code != 404:
        _fail("t2-detail-not-found", f"expected 404, got {resp.status_code}")
    _ok("t2-detail not-found -> 404")

    # Filter sanity — classSourcedId=<bogus> returns 0 entries (still 200)
    req = _bearer_request(rf, "GET", "/api/roster/results/v1p2/gradeBookEntries/?classSourcedId=__bogus__")
    resp = ors.gradebook_entries_collection(req)
    if resp.status_code != 200:
        _fail("t2-filter-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("gradeBookEntries"):
        _fail("t2-filter", f"expected empty list for bogus classSourcedId, got {len(body['gradeBookEntries'])}")
    _ok("t2-filter classSourcedId=__bogus__ -> 0 entries")

    # Verify URL resolves under api: namespace
    from django.urls import reverse
    p1 = reverse("api:api-roster-results-gradebook-entries")
    p2 = reverse("api:api-roster-results-gradebook-entry-detail", args=["gbe-1"])
    if not p1.endswith("/gradeBookEntries/"):
        _fail("t2-url-list", p1)
    if not p2.endswith("/gradeBookEntries/gbe-1/"):
        _fail("t2-url-detail", p2)
    _ok(f"t2-url-list {p1}")
    _ok(f"t2-url-detail {p2}")


# ---------------------------------------------------------------------------
# T3 — Audit retention export download UI.
# ---------------------------------------------------------------------------

def run_t3():
    _line("\n[T3] Audit retention export download UI")
    from apps.portal import views_lms_audit as vla
    rf = RequestFactory()

    # Filename validator — accepts well-formed sweep output
    good = "lms_audit_purge_2026-05-29T12-00-00p00-00.jsonl"
    if not vla._validate_export_filename(good):
        _fail("t3-validate-good", f"rejected legit name {good}")
    _ok(f"t3-validate accepts {good}")

    # Filename validator — rejects traversal + bad pattern
    for bad in ("../etc/passwd", "lms_audit_purge_x.jsonl/../boom", "evil.jsonl", "purge.jsonl", "lms_audit_purge_x.txt"):
        if vla._validate_export_filename(bad):
            _fail(f"t3-validate-bad-{bad}", "should have rejected")
    _ok("t3-validate rejects 5 traversal/wrong-pattern names")

    # Index endpoint without env var -> error_reason
    os.environ.pop("RMC_LMS_AUDIT_RETENTION_EXPORT_DIR", None)
    user = _staff_user()
    req = _bearer_request(rf, "GET", "/portal/super/integrations/lms/audit/exports/?format=json")
    req.user = user
    resp = vla.lms_audit_export_index(req)
    if resp.status_code != 200:
        _fail("t3-index-no-env-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("error") != "export_dir_not_configured":
        _fail("t3-index-no-env-err", f"expected export_dir_not_configured, got {body.get('error')}")
    _ok("t3-index no-env -> error=export_dir_not_configured")

    # Index endpoint WITH env var pointing at tempdir -> success + files listed
    with tempfile.TemporaryDirectory() as td:
        os.environ["RMC_LMS_AUDIT_RETENTION_EXPORT_DIR"] = td
        f1 = os.path.join(td, "lms_audit_purge_2026-05-29T03-30-00p00-00.jsonl")
        with open(f1, "w", encoding="utf-8") as fh:
            fh.write('{"id": 1, "ok": true}\n')
        # Decoy file that should NOT appear in list
        with open(os.path.join(td, "unrelated.txt"), "w") as fh:
            fh.write("noise")

        req = _bearer_request(rf, "GET", "/portal/super/integrations/lms/audit/exports/?format=json")
        req.user = user
        resp = vla.lms_audit_export_index(req)
        if resp.status_code != 200:
            _fail("t3-index-status", f"got {resp.status_code}")
        body = _json.loads(resp.content)
        if not body.get("success"):
            _fail("t3-index-success", f"expected success=True; got {body}")
        names = [f["name"] for f in body["files"]]
        if "lms_audit_purge_2026-05-29T03-30-00p00-00.jsonl" not in names:
            _fail("t3-index-listing", f"missing legit file; got {names}")
        if "unrelated.txt" in names:
            _fail("t3-index-decoy", f"decoy file leaked into listing: {names}")
        _ok(f"t3-index listing 1 legit, decoy excluded ({len(body['files'])} entries)")

        # Download endpoint — happy path
        req = _bearer_request(rf, "GET", "/portal/super/integrations/lms/audit/exports/lms_audit_purge_2026-05-29T03-30-00p00-00.jsonl/")
        req.user = user
        resp = vla.lms_audit_export_download(req, "lms_audit_purge_2026-05-29T03-30-00p00-00.jsonl")
        if resp.status_code != 200:
            _fail("t3-download-status", f"got {resp.status_code}")
        cd = resp.get("Content-Disposition", "")
        if "attachment" not in cd or "lms_audit_purge_" not in cd:
            _fail("t3-download-cd", f"expected attachment Content-Disposition, got {cd!r}")
        _ok(f"t3-download 200 Content-Disposition={cd}")
        # Release the file handle so Windows tempdir cleanup can delete the file.
        resp.close()

        # Download endpoint — traversal-style filename refused (400)
        req = _bearer_request(rf, "GET", "/portal/super/integrations/lms/audit/exports/..%2Fetc%2Fpasswd/")
        req.user = user
        resp = vla.lms_audit_export_download(req, "../etc/passwd")
        if resp.status_code != 400:
            _fail("t3-download-traversal", f"expected 400, got {resp.status_code}")
        _ok("t3-download traversal filename -> 400")

        # Download endpoint — well-formed-but-missing -> 404
        req = _bearer_request(rf, "GET", "/portal/super/integrations/lms/audit/exports/lms_audit_purge_x-not-here.jsonl/")
        req.user = user
        resp = vla.lms_audit_export_download(req, "lms_audit_purge_x-not-here.jsonl")
        if resp.status_code != 404:
            _fail("t3-download-missing", f"expected 404, got {resp.status_code}")
        _ok("t3-download missing file -> 404")
    os.environ.pop("RMC_LMS_AUDIT_RETENTION_EXPORT_DIR", None)


# ---------------------------------------------------------------------------
# T4 — Bulk-import per-row idempotency replay.
# ---------------------------------------------------------------------------

def run_t4():
    _line("\n[T4] Bulk-import per-row Idempotency-Key replay")
    from apps.api import oneroster_results as ors
    from django.core.cache import cache
    rf = RequestFactory()

    # Smoke the per-row idem cache helper directly so we don't need a real
    # Evaluation create to validate replay semantics.
    test_idem = "smoke-v4-00-56-row-idem-A"
    ck = ors._bulk_row_idem_cache_key(test_idem)
    cache.set(ck, {"outcome": "created", "sourcedId": "res-9001"}, ors._BULK_IMPORT_ROW_IDEM_TTL)
    cached = cache.get(ck)
    if not isinstance(cached, dict) or cached.get("outcome") != "created" or cached.get("sourcedId") != "res-9001":
        _fail("t4-cache-roundtrip", f"got {cached}")
    _ok("t4-cache-roundtrip outcome=created sourcedId=res-9001")

    # Build a batch with one row carrying the cached idempotencyKey. The
    # post handler must short-circuit to a replayed=True outcome WITHOUT
    # touching the ORM. We send another row WITHOUT idem, which should
    # error gracefully (no such student/classroom).
    body = {
        "results": [
            {"idempotencyKey": test_idem, "studentSourcedId": "stu-1",
             "lineItemSourcedId": "li-9999", "score": "85", "textScore": "B"},
            {"studentSourcedId": "stu-X-no-such", "lineItemSourcedId": "li-also-no-such",
             "score": "50", "textScore": "F"},
        ]
    }
    req = _bearer_request(rf, "POST", "/api/roster/results/v1p2/results/import/", body=body,
                          idem="smoke-v4-00-56-batch-A")
    resp = ors.post_results_bulk_import(req)
    if resp.status_code != 207:
        _fail("t4-status", f"expected 207 (partial — at least 1 errored row), got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("replayed") != 1:
        _fail("t4-replayed-count", f"expected replayed=1, got {body.get('replayed')}; outcomes={body.get('outcomes')}")
    if body.get("created") != 1:
        _fail("t4-created-count", f"expected created=1, got {body.get('created')}")
    if body.get("errored") < 1:
        _fail("t4-errored-count", f"expected errored>=1, got {body.get('errored')}")
    # The replayed row should carry replayed=True
    row0 = body["outcomes"][0]
    if not row0.get("replayed"):
        _fail("t4-row-replayed-flag", f"first row missing replayed=True; got {row0}")
    if row0.get("sourcedId") != "res-9001":
        _fail("t4-row-replayed-sid", f"replayed sourcedId mismatch; got {row0.get('sourcedId')}")
    _ok(f"t4-row1 replayed=True sourcedId=res-9001 (no ORM hit)")
    _ok(f"t4-row2 errored gracefully (no abort)")

    # Cleanup
    cache.delete(ck)


# ---------------------------------------------------------------------------
# T5 — LMS diagnostics operator dashboard.
# ---------------------------------------------------------------------------

def run_t5():
    _line("\n[T5] /super/migration/lms/diagnostics/")
    from apps.migration_cloud import views_lms_diagnostics as vld
    rf = RequestFactory()

    # Pure-function aggregator
    diag = vld._compute_lms_diagnostics()
    for k in ("generated_at", "lookback_hours", "rotation_grace_seconds", "providers", "totals", "errors"):
        if k not in diag:
            _fail(f"t5-shape-{k}", f"missing {k} in diag")
    for tk in ("configured", "unconfigured", "expired", "past_grace", "missing_refresh"):
        if tk not in diag["totals"]:
            _fail(f"t5-totals-{tk}", f"missing totals.{tk}")
    if diag["lookback_hours"] != 24:
        _fail("t5-lookback", f"expected 24, got {diag['lookback_hours']}")
    if diag["rotation_grace_seconds"] != 7 * 24 * 3600:
        _fail("t5-grace", f"expected 604800, got {diag['rotation_grace_seconds']}")
    _ok(f"t5-aggregator shape OK (errors={len(diag['errors'])})")

    # JSON endpoint
    user = _staff_user()
    req = _bearer_request(rf, "GET", "/super/migration/lms/diagnostics/?format=json")
    req.user = user
    resp = vld.lms_diagnostics(req)
    if resp.status_code != 200:
        _fail("t5-json-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if "providers" not in body or "totals" not in body:
        _fail("t5-json-shape", f"missing providers/totals; got {sorted(body)}")
    _ok(f"t5-json 200 providers={len(body['providers'])} totals.configured={body['totals']['configured']}")

    # URL resolves under migration_cloud_super namespace
    from django.urls import reverse
    p = reverse("migration_cloud_super:migration_cloud_lms_diagnostics")
    if not p.endswith("/lms/diagnostics/"):
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
