"""v4.00.57 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +13 Tier-1 subdivisions (US-AZ/CO/MN/MD/TN, IN-RJ/MP/OD, JP-14, KR-31,
    CL-RM, PE-LIM, AR-C) shape-asserted in COUNTRY_LOCALIZATION SOT (>= 322).
T2: SAML signature c14n verify (lxml+signxml lazy import, cert_unset,
    deps_missing, strict-default).
T3: GradeBookEntry CSV export per class (text/csv stream + Content-Disposition).
T4: ClassGroup bulk delete-by-class (idem-keyed; tombstones matching groups,
    leaves non-matching alone, replay returns Idempotency-Replay header).
T5: Idempotency-Key audit ring (fresh/replayed events, snapshot, totals,
    operator URL).

Exits 0 on full pass; non-zero on first failure.
"""
from __future__ import annotations

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
        username="smoke-v4-00-57-staff",
        defaults={"email": "smoke@v4-00-57.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


def _bearer_request(rf, method, path, body=None, idem=None):
    kwargs = {"content_type": "application/json", "HTTP_AUTHORIZATION": "Bearer smoke-bearer"}
    if idem:
        kwargs["HTTP_IDEMPOTENCY_KEY"] = idem
    if body is not None:
        kwargs["data"] = _json.dumps(body) if not isinstance(body, (bytes, str)) else body
    req = getattr(rf, method.lower())(path, **kwargs)
    req._dont_enforce_csrf_checks = True
    return req


# ---------------------------------------------------------------------------
# T1
# ---------------------------------------------------------------------------

def run_t1():
    _line("\n[T1] +13 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = [
        "US-AZ", "US-CO", "US-MN", "US-MD", "US-TN",
        "IN-RJ", "IN-MP", "IN-OD",
        "JP-14", "KR-31",
        "CL-RM", "PE-LIM", "AR-C",
    ]
    for k in new_keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-present-{k}", f"missing or non-dict: {type(e).__name__}")
        for required in ("calendar_system", "school_types", "education_levels", "terminology"):
            if required not in e:
                _fail(f"t1-shape-{k}-{required}", f"missing {required}")
        if not isinstance(e["school_types"], list) or len(e["school_types"]) < 3:
            _fail(f"t1-school-types-{k}", "need >= 3 school_types")
        if not isinstance(e["education_levels"], list) or len(e["education_levels"]) < 3:
            _fail(f"t1-education-levels-{k}", "need >= 3 education_levels")
        _ok(f"t1-{k} shape OK ({len(e['school_types'])} types, {len(e['education_levels'])} levels)")
    if len(COUNTRY_LOCALIZATION) < 322:
        _fail("t1-sot-count", f"expected >= 322 entries, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


# ---------------------------------------------------------------------------
# T2
# ---------------------------------------------------------------------------

def run_t2():
    _line("\n[T2] SAML signature c14n verify")
    from apps.api.saml import _verify_saml_signature_c14n, _require_signature_strict

    # cert_unset path
    v, r = _verify_saml_signature_c14n("SGVsbG8=", "")
    if v is not False or r != "cert_unset":
        _fail("t2-cert-unset", f"got ({v}, {r})")
    _ok("t2-cert-unset -> (False, 'cert_unset')")

    # deps_missing path (lxml/signxml not installed in dev; this is the
    # contract that activates the install when deps land)
    v, r = _verify_saml_signature_c14n("Tk9UWE1M", "AAAA")
    if r not in ("deps_missing", "bad_xml", "signature_missing"):
        _fail("t2-deps-missing", f"expected deps_missing/bad_xml/signature_missing, got ({v}, {r})")
    _ok(f"t2-no-deps -> (False, '{r}')")

    # strict default
    if not _require_signature_strict():
        _fail("t2-strict-default", "expected True (strict by default)")
    _ok("t2-strict-default True")

    # strict off
    os.environ["RMC_SAML_SIGNATURE_STRICT"] = "0"
    try:
        if _require_signature_strict():
            _fail("t2-strict-off", "expected False when env=0")
        _ok("t2-strict-off -> False")
    finally:
        del os.environ["RMC_SAML_SIGNATURE_STRICT"]


# ---------------------------------------------------------------------------
# T3
# ---------------------------------------------------------------------------

def run_t3():
    _line("\n[T3] GradeBookEntry CSV export per class")
    from apps.api import oneroster_results as ors
    rf = RequestFactory()

    # Missing class_sourced_id
    req = _bearer_request(rf, "GET", "/api/roster/results/v1p2/classes//gradeBookEntries.csv")
    resp = ors.gradebook_entries_csv(req, "")
    if resp.status_code != 400:
        _fail("t3-missing-class", f"expected 400, got {resp.status_code}")
    _ok("t3-missing class_sourced_id -> 400")

    # Happy path — non-existent class still returns 200 w/ header-only CSV
    req = _bearer_request(rf, "GET", "/api/roster/results/v1p2/classes/c-nonexistent-xyz/gradeBookEntries.csv")
    resp = ors.gradebook_entries_csv(req, "c-nonexistent-xyz")
    if resp.status_code != 200:
        _fail("t3-empty-status", f"got {resp.status_code}")
    if resp["Content-Type"] != "text/csv; charset=utf-8":
        _fail("t3-content-type", resp["Content-Type"])
    cd = resp.get("Content-Disposition", "")
    if "attachment" not in cd or "gradebook-" not in cd:
        _fail("t3-content-disposition", cd)
    body = b"".join(resp.streaming_content).decode("utf-8")
    lines = [ln for ln in body.split("\r\n") if ln]
    if not lines:
        _fail("t3-empty-body", "no lines in body")
    if not lines[0].startswith("sourcedId,lineItemSourcedId,lineItemTitle,classSourcedId,categorySourcedId"):
        _fail("t3-header", f"unexpected header: {lines[0]}")
    _ok(f"t3-empty-class 200 + header-only CSV ({len(lines)} line)")

    # Happy path — real class. Build a lineItem on the fly is not viable
    # without DB seeds, so we just verify the stream rendered properly for
    # whatever live data exists (entries == 0 is acceptable for the smoke).
    req = _bearer_request(rf, "GET", "/api/roster/results/v1p2/classes/1/gradeBookEntries.csv")
    resp = ors.gradebook_entries_csv(req, "1")
    if resp.status_code != 200:
        _fail("t3-real-status", f"got {resp.status_code}")
    body = b"".join(resp.streaming_content).decode("utf-8")
    lines = [ln for ln in body.split("\r\n") if ln]
    _ok(f"t3-real-class 200 ({len(lines)} lines incl header)")

    # URL reverse
    from django.urls import reverse
    p = reverse("api:api-roster-results-gradebook-entries-csv", args=["1"])
    if not p.endswith("/classes/1/gradeBookEntries.csv"):
        _fail("t3-url", p)
    _ok(f"t3-url {p}")


# ---------------------------------------------------------------------------
# T4
# ---------------------------------------------------------------------------

def run_t4():
    _line("\n[T4] ClassGroup bulk delete-by-class")
    from apps.api import oneroster_results as ors
    rf = RequestFactory()

    ors._CLASSGROUP_OVERRIDES.clear()
    ors._CLASSGROUP_TOMBSTONES.clear()
    ors._CLASSGROUP_OVERRIDES["cg-A1"] = {"sourcedId": "cg-A1", "title": "Cohort A1", "type": "cohort", "classSourcedIds": ["c-100", "c-200"]}
    ors._CLASSGROUP_OVERRIDES["cg-A2"] = {"sourcedId": "cg-A2", "title": "Cohort A2", "type": "cohort", "classSourcedIds": ["c-100"]}
    ors._CLASSGROUP_OVERRIDES["cg-B1"] = {"sourcedId": "cg-B1", "title": "Cohort B1", "type": "cohort", "classSourcedIds": ["c-999"]}

    # Missing Idempotency-Key -> 428
    req = _bearer_request(rf, "POST", "/api/roster/results/v1p2/classGroups/bulk-delete-by-class/", body={"classSourcedId": "c-100"})
    resp = ors.classgroups_bulk_delete_by_class(req)
    if resp.status_code != 428:
        _fail("t4-missing-idem", f"expected 428, got {resp.status_code}")
    _ok("t4-missing-idem -> 428")

    # Missing classSourcedId -> 400
    req = _bearer_request(rf, "POST", "/api/roster/results/v1p2/classGroups/bulk-delete-by-class/", body={}, idem="smoke-t4-missing-class")
    resp = ors.classgroups_bulk_delete_by_class(req)
    if resp.status_code != 400:
        _fail("t4-missing-classsid", f"expected 400, got {resp.status_code}")
    _ok("t4-missing-classSourcedId -> 400")

    # Happy path
    req = _bearer_request(rf, "POST", "/api/roster/results/v1p2/classGroups/bulk-delete-by-class/", body={"classSourcedId": "c-100"}, idem="smoke-t4-happy")
    resp = ors.classgroups_bulk_delete_by_class(req)
    if resp.status_code != 200:
        _fail("t4-happy-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("tombstoned") != 2:
        _fail("t4-tombstoned-count", f"expected 2, got {body.get('tombstoned')}")
    if sorted(body.get("sourcedIds") or []) != ["cg-A1", "cg-A2"]:
        _fail("t4-sourcedIds", f"expected [cg-A1, cg-A2], got {body.get('sourcedIds')}")
    if "cg-A1" not in ors._CLASSGROUP_TOMBSTONES or "cg-A2" not in ors._CLASSGROUP_TOMBSTONES:
        _fail("t4-tombstone-set", f"missing tombstones; got {sorted(ors._CLASSGROUP_TOMBSTONES)}")
    if "cg-B1" in ors._CLASSGROUP_TOMBSTONES:
        _fail("t4-nontarget-untouched", "cg-B1 should NOT have been tombstoned")
    _ok(f"t4-happy 200 tombstoned=2 (cg-A1+cg-A2), cg-B1 untouched")

    # Replay -> Idempotency-Replay: true
    req = _bearer_request(rf, "POST", "/api/roster/results/v1p2/classGroups/bulk-delete-by-class/", body={"classSourcedId": "c-100"}, idem="smoke-t4-happy")
    resp = ors.classgroups_bulk_delete_by_class(req)
    if resp.status_code != 200:
        _fail("t4-replay-status", f"got {resp.status_code}")
    if resp.get("Idempotency-Replay") != "true":
        _fail("t4-replay-header", f"got {resp.get('Idempotency-Replay')}")
    _ok("t4-replay Idempotency-Replay: true")

    # URL reverse
    from django.urls import reverse
    p = reverse("api:api-roster-results-class-groups-bulk-delete")
    if not p.endswith("/classGroups/bulk-delete-by-class/"):
        _fail("t4-url", p)
    _ok(f"t4-url {p}")


# ---------------------------------------------------------------------------
# T5
# ---------------------------------------------------------------------------

def run_t5():
    _line("\n[T5] Idempotency-Key audit ring + operator surface")
    from apps.api.oneroster_results import (
        _IDEM_AUDIT_RING, _log_idem_event,
        get_idem_audit_snapshot, get_idem_audit_totals,
    )
    from apps.portal import views_idempotency_audit as via
    rf = RequestFactory()

    _IDEM_AUDIT_RING.clear()
    _log_idem_event("results-bulk-import", "idem-A", "POST",
                    "/api/roster/results/v1p2/results/import/", 201, False)
    _log_idem_event("results-bulk-import", "idem-A", "POST",
                    "/api/roster/results/v1p2/results/import/", 201, True)
    _log_idem_event("classgroups-bulk-delete-by-class", "idem-B", "POST",
                    "/api/roster/results/v1p2/classGroups/bulk-delete-by-class/", 200, False)

    # snapshot newest-first
    snap = get_idem_audit_snapshot(limit=10)
    if len(snap) != 3:
        _fail("t5-snap-count", f"expected 3, got {len(snap)}")
    if snap[0]["idempotency_key"] != "idem-B":
        _fail("t5-snap-newest-first", f"got {snap[0]}")
    _ok("t5-snapshot 3 events newest-first")

    # totals
    totals = get_idem_audit_totals()
    if totals["total"] != 3 or totals["fresh"] != 2 or totals["replayed"] != 1:
        _fail("t5-totals", f"got {totals}")
    if totals["by_entity"].get("results-bulk-import") != 2:
        _fail("t5-by-entity", f"got {totals['by_entity']}")
    _ok(f"t5-totals total=3 fresh=2 replayed=1 by_entity OK")

    # Operator UI JSON endpoint — un-filtered
    user = _staff_user()
    req = _bearer_request(rf, "GET", "/portal/super/integrations/oneroster/idempotency-audit/?format=json")
    req.user = user
    resp = via.idempotency_audit_index(req)
    if resp.status_code != 200:
        _fail("t5-json-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if not body.get("success"):
        _fail("t5-json-success", f"got {body}")
    if len(body["events"]) != 3:
        _fail("t5-json-events", f"expected 3 events, got {len(body['events'])}")
    _ok(f"t5-json 200 events=3 totals={body['totals']}")

    # Filter: entity=results-bulk-import
    req = _bearer_request(rf, "GET", "/portal/super/integrations/oneroster/idempotency-audit/?format=json&entity=results-bulk-import")
    req.user = user
    resp = via.idempotency_audit_index(req)
    body = _json.loads(resp.content)
    if len(body["events"]) != 2:
        _fail("t5-filter-entity", f"expected 2 events, got {len(body['events'])}")
    _ok(f"t5-filter entity=results-bulk-import -> 2 events")

    # Filter: replayed=only
    req = _bearer_request(rf, "GET", "/portal/super/integrations/oneroster/idempotency-audit/?format=json&replayed=only")
    req.user = user
    resp = via.idempotency_audit_index(req)
    body = _json.loads(resp.content)
    if len(body["events"]) != 1:
        _fail("t5-filter-replayed", f"expected 1 event, got {len(body['events'])}")
    _ok("t5-filter replayed=only -> 1 event")

    # URL reverse
    from django.urls import reverse
    p = reverse("portal:idempotency_audit_index")
    if not p.endswith("/oneroster/idempotency-audit/"):
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
