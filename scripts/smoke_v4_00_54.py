"""v4.00.54 — RequestFactory smoke across the 5 wave targets.

Runs:
  T1: 14 ISO 3166-2 subdivision packs registered + fields complete
  T2: OneRoster Result Service attachment + rubric writes
  T3: lms_token_rotation sweep classification + Celery task registered
  T4: lms_audit_retention sweep counts + cutoff math + Celery task registered
  T5: PKCE auth-URL builder API endpoint

Exits 0 on full pass; non-zero on first failure.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


def _line(s):  # noqa: ANN001
    print(s, flush=True)


def _ok(name):  # noqa: ANN001
    _line(f"  OK   {name}")


def _fail(name, detail):  # noqa: ANN001
    _line(f"  FAIL {name}: {detail}")
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# T1 — 14 ISO 3166-2 subdivision packs
# ---------------------------------------------------------------------------
def run_t1():
    _line("\nT1 — 14 ISO 3166-2 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    expected = [
        "US-IL", "US-PA", "US-GA",
        "IN-WB", "IN-UP",
        "DE-BW",
        "CN-GD", "CN-SH",
        "AU-QLD",
        "BR-RJ",
        "MX-CDMX", "MX-JAL",
        "FR-IDF", "FR-PACA",
    ]
    for code in expected:
        if code not in COUNTRY_LOCALIZATION:
            _fail("T1.subdivision_registered", f"missing {code}")
        row = COUNTRY_LOCALIZATION[code]
        for field in ("calendar_system", "school_types", "education_levels", "terminology"):
            if field not in row:
                _fail("T1.row_completeness", f"{code} missing {field}")
        if not isinstance(row["school_types"], list) or len(row["school_types"]) < 4:
            _fail("T1.school_types_min", f"{code} has {len(row.get('school_types', []))}")
        if not isinstance(row["education_levels"], list) or len(row["education_levels"]) < 3:
            _fail("T1.education_levels_min", f"{code} has {len(row.get('education_levels', []))}")
    _ok(f"all 14 subdivisions registered with required fields (sot len={len(COUNTRY_LOCALIZATION)})")


# ---------------------------------------------------------------------------
# T2 — OneRoster Result Service Attachment + Rubric writes
# ---------------------------------------------------------------------------
def run_t2():
    _line("\nT2 — OneRoster Result Service attachment + rubric writes")
    import json
    from django.test import RequestFactory
    from apps.api import oneroster_results as orr

    # Reset module-level state for deterministic smoke.
    orr._ATTACHMENT_OVERRIDES.clear()
    orr._ATTACHMENT_TOMBSTONES.clear()
    orr._RUBRIC_OVERRIDES.clear()
    orr._RUBRIC_TOMBSTONES.clear()

    rf = RequestFactory()

    def _post(path, body, headers=None):
        req = rf.post(path, data=json.dumps(body), content_type="application/json",
                      **(headers or {}))
        req._dont_enforce_csrf_checks = True
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        return req

    def _put(path, body, headers=None):
        req = rf.put(path, data=json.dumps(body), content_type="application/json",
                     **(headers or {}))
        req._dont_enforce_csrf_checks = True
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        return req

    def _delete(path):
        req = rf.delete(path)
        req._dont_enforce_csrf_checks = True
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        return req

    def _get(path):
        req = rf.get(path)
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        return req

    # --- Attachment POST: missing idempotency-key -> 428 ---
    r = orr.post_attachment(_post("/api/roster/results/v1p2/attachments/post/", {}))
    if r.status_code != 428:
        _fail("T2.attachment.missing_idem", f"got {r.status_code}")
    _ok("attachment POST 428 on missing Idempotency-Key")

    # --- Attachment POST: success 201 ---
    req = _post(
        "/api/roster/results/v1p2/attachments/post/",
        {"attachment": {"lineItemSourcedId": "li-1", "url": "https://example.org/q3.pdf",
                        "title": "Quiz 3 reading", "type": "document"}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-att-1"},
    )
    r = orr.post_attachment(req)
    if r.status_code != 201:
        _fail("T2.attachment.first_post", f"got {r.status_code} body={r.content[:200]!r}")
    body = json.loads(r.content)
    sid = body["attachment"]["sourcedId"]
    if not sid.startswith("att-"):
        _fail("T2.attachment.sid_prefix", sid)
    _ok(f"attachment POST 201 creates {sid}")

    # --- Attachment POST: replay returns cached body + Idempotency-Replay ---
    req2 = _post(
        "/api/roster/results/v1p2/attachments/post/",
        {"attachment": {"lineItemSourcedId": "li-1", "url": "https://example.org/q3.pdf",
                        "title": "Quiz 3 reading", "type": "document"}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-att-1"},
    )
    r = orr.post_attachment(req2)
    if r.status_code != 201:
        _fail("T2.attachment.replay_status", f"got {r.status_code}")
    if r.get("Idempotency-Replay") != "true":
        _fail("T2.attachment.replay_header", r.get("Idempotency-Replay"))
    _ok("attachment POST replay returns Idempotency-Replay: true")

    # --- Attachment POST: payload mismatch -> 409 ---
    req3 = _post(
        "/api/roster/results/v1p2/attachments/post/",
        {"attachment": {"lineItemSourcedId": "li-2", "url": "https://example.org/different.pdf"}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-att-1"},
    )
    r = orr.post_attachment(req3)
    if r.status_code != 409:
        _fail("T2.attachment.mismatch_409", f"got {r.status_code}")
    _ok("attachment POST 409 on payload mismatch (same idem, different body)")

    # --- Attachment POST: bad URL -> 400 ---
    req_bad = _post(
        "/api/roster/results/v1p2/attachments/post/",
        {"attachment": {"lineItemSourcedId": "li-1", "url": "javascript:alert(1)"}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-att-bad-url"},
    )
    r = orr.post_attachment(req_bad)
    if r.status_code != 400:
        _fail("T2.attachment.bad_url_400", f"got {r.status_code}")
    _ok("attachment POST 400 on non-http URL")

    # --- Attachment POST: bad lineItemSourcedId -> 400 ---
    req_bad_li = _post(
        "/api/roster/results/v1p2/attachments/post/",
        {"attachment": {"lineItemSourcedId": "not-a-li", "url": "https://example.org/a"}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-att-bad-li"},
    )
    r = orr.post_attachment(req_bad_li)
    if r.status_code != 400:
        _fail("T2.attachment.bad_li_400", f"got {r.status_code}")
    _ok("attachment POST 400 on non-li lineItemSourcedId")

    # --- Attachment PUT: rename ---
    req_put = _put(
        f"/api/roster/results/v1p2/attachments/{sid}/put/",
        {"attachment": {"title": "Quiz 3 reading (revised)"}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-att-put-1"},
    )
    r = orr.put_attachment(req_put, sid)
    if r.status_code != 200:
        _fail("T2.attachment.put_status", f"got {r.status_code} body={r.content[:200]!r}")
    body = json.loads(r.content)
    if body["attachment"]["title"] != "Quiz 3 reading (revised)":
        _fail("T2.attachment.put_renamed", body["attachment"]["title"])
    _ok("attachment PUT 200 renames")

    # --- Attachment PUT: bad sourced_id -> 400 ---
    req_put_bad = _put(
        "/api/roster/results/v1p2/attachments/cat-foo/put/",
        {"attachment": {"title": "x"}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-att-put-bad"},
    )
    r = orr.put_attachment(req_put_bad, "cat-foo")
    if r.status_code != 400:
        _fail("T2.attachment.put_bad_sid", f"got {r.status_code}")
    _ok("attachment PUT 400 on non-att sourcedId")

    # --- Attachment DELETE: first delete 200 alreadyDeleted=false ---
    r = orr.delete_attachment(_delete(f"/api/roster/results/v1p2/attachments/{sid}/delete/"), sid)
    body = json.loads(r.content)
    if r.status_code != 200 or body.get("alreadyDeleted") is not False:
        _fail("T2.attachment.first_delete", f"status={r.status_code} body={body}")
    _ok("attachment DELETE 200 alreadyDeleted=false")

    # --- Attachment DELETE: second delete 200 alreadyDeleted=true ---
    r = orr.delete_attachment(_delete(f"/api/roster/results/v1p2/attachments/{sid}/delete/"), sid)
    body = json.loads(r.content)
    if r.status_code != 200 or body.get("alreadyDeleted") is not True:
        _fail("T2.attachment.second_delete", f"status={r.status_code} body={body}")
    _ok("attachment DELETE 200 alreadyDeleted=true (idempotent)")

    # --- Attachment list hides tombstoned ---
    r = orr.attachments_list(_get("/api/roster/results/v1p2/attachments/"))
    body = json.loads(r.content)
    if any(a["sourcedId"] == sid for a in body.get("attachments", [])):
        _fail("T2.attachment.list_hides_tombstoned", str(body))
    _ok("attachment list hides tombstoned row")

    # --- Rubric POST: success ---
    req_rub = _post(
        "/api/roster/results/v1p2/rubrics/post/",
        {"rubric": {"lineItemSourcedId": "li-1", "title": "Essay rubric",
                    "criteria": [
                        {"title": "Thesis clarity", "points": 5},
                        {"title": "Evidence", "points": 5},
                        {"title": "Organization", "points": 3},
                    ]}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-rub-1"},
    )
    r = orr.post_rubric(req_rub)
    if r.status_code != 201:
        _fail("T2.rubric.first_post", f"got {r.status_code} body={r.content[:200]!r}")
    body = json.loads(r.content)
    rsid = body["rubric"]["sourcedId"]
    if not rsid.startswith("rub-"):
        _fail("T2.rubric.sid_prefix", rsid)
    if len(body["rubric"]["criteria"]) != 3:
        _fail("T2.rubric.criteria_count", str(body["rubric"]["criteria"]))
    _ok(f"rubric POST 201 creates {rsid} with 3 criteria")

    # --- Rubric POST: missing criteria -> 400 ---
    req_no_crit = _post(
        "/api/roster/results/v1p2/rubrics/post/",
        {"rubric": {"lineItemSourcedId": "li-1", "title": "Bad rubric"}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-rub-no-crit"},
    )
    r = orr.post_rubric(req_no_crit)
    if r.status_code != 400:
        _fail("T2.rubric.no_criteria_400", f"got {r.status_code}")
    _ok("rubric POST 400 on missing criteria")

    # --- Rubric POST: bad criterion (no title) -> 400 ---
    req_bad_crit = _post(
        "/api/roster/results/v1p2/rubrics/post/",
        {"rubric": {"lineItemSourcedId": "li-1", "criteria": [{"points": 5}]}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-rub-bad-crit"},
    )
    r = orr.post_rubric(req_bad_crit)
    if r.status_code != 400:
        _fail("T2.rubric.bad_criterion_400", f"got {r.status_code}")
    _ok("rubric POST 400 on criterion missing title")

    # --- Rubric POST: bad lineItem -> 400 ---
    req_bad_li2 = _post(
        "/api/roster/results/v1p2/rubrics/post/",
        {"rubric": {"lineItemSourcedId": "foo", "criteria": [{"title": "x", "points": 1}]}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-rub-bad-li"},
    )
    r = orr.post_rubric(req_bad_li2)
    if r.status_code != 400:
        _fail("T2.rubric.bad_li_400", f"got {r.status_code}")
    _ok("rubric POST 400 on non-li lineItemSourcedId")

    # --- Rubric PUT: update criteria ---
    req_rub_put = _put(
        f"/api/roster/results/v1p2/rubrics/{rsid}/put/",
        {"rubric": {"criteria": [{"title": "Single criterion", "points": 10}]}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-rub-put-1"},
    )
    r = orr.put_rubric(req_rub_put, rsid)
    if r.status_code != 200:
        _fail("T2.rubric.put_status", f"got {r.status_code}")
    body = json.loads(r.content)
    if len(body["rubric"]["criteria"]) != 1:
        _fail("T2.rubric.put_criteria_replaced", str(body["rubric"]["criteria"]))
    _ok("rubric PUT 200 replaces criteria list")

    # --- Rubric DELETE idempotent ---
    r = orr.delete_rubric(_delete(f"/api/roster/results/v1p2/rubrics/{rsid}/delete/"), rsid)
    body = json.loads(r.content)
    if body.get("alreadyDeleted") is not False:
        _fail("T2.rubric.first_delete", str(body))
    r = orr.delete_rubric(_delete(f"/api/roster/results/v1p2/rubrics/{rsid}/delete/"), rsid)
    body = json.loads(r.content)
    if body.get("alreadyDeleted") is not True:
        _fail("T2.rubric.second_delete", str(body))
    _ok("rubric DELETE idempotent (alreadyDeleted false then true)")


# ---------------------------------------------------------------------------
# T3 — LMS token rotation sweep
# ---------------------------------------------------------------------------
def run_t3():
    _line("\nT3 — LMS token rotation sweep")
    from apps.integrations_marketplace import lms_token_rotation as ltr

    # Module imports + task wrapper registered ---
    if not callable(ltr.sweep_lms_tokens_due_rotation):
        _fail("T3.sweep_callable", "not callable")
    if ltr.DEFAULT_GRACE_SECONDS != 7 * 24 * 60 * 60:
        _fail("T3.default_grace", str(ltr.DEFAULT_GRACE_SECONDS))
    _ok("module imports + DEFAULT_GRACE_SECONDS=604800 (7d)")

    if ltr.rotate_due_lms_tokens is None:
        _fail("T3.celery_task_missing", "rotate_due_lms_tokens is None")
    if getattr(ltr.rotate_due_lms_tokens, "name", "") != "integrations_marketplace.rotate_due_lms_tokens":
        _fail("T3.celery_task_name", str(getattr(ltr.rotate_due_lms_tokens, "name", "")))
    _ok("@shared_task integrations_marketplace.rotate_due_lms_tokens registered")

    # Failure classifier ---
    if ltr._classify_failure({"detail": "invalid_grant: revoked"}) != "refresh_revoked":
        _fail("T3.classify_invalid_grant", "expected refresh_revoked")
    if ltr._classify_failure({"detail": "", "status_code": 401}) != "refresh_revoked":
        _fail("T3.classify_401", "expected refresh_revoked")
    if ltr._classify_failure({"detail": "server error", "status_code": 500}) != "refresh_failed":
        _fail("T3.classify_500", "expected refresh_failed")
    _ok("failure classifier maps invalid_grant + 401 -> refresh_revoked; 500 -> refresh_failed")

    # Sweep with no rows is graceful ---
    out = ltr.sweep_lms_tokens_due_rotation()
    if "considered" not in out or "rotated" not in out:
        _fail("T3.sweep_shape", str(out))
    _ok(f"sweep returns audit dict {sorted(out)[:6]}...")

    # Disabled mode ---
    os.environ["RMC_LMS_TOKEN_ROTATION_DISABLED"] = "1"
    try:
        out = ltr.sweep_lms_tokens_due_rotation()
        if not out.get("disabled") or out["considered"] != 0:
            _fail("T3.disabled", str(out))
    finally:
        del os.environ["RMC_LMS_TOKEN_ROTATION_DISABLED"]
    _ok("RMC_LMS_TOKEN_ROTATION_DISABLED=1 no-ops the sweep")


# ---------------------------------------------------------------------------
# T4 — LMS audit retention sweep
# ---------------------------------------------------------------------------
def run_t4():
    _line("\nT4 — LMS audit retention sweep (7y FERPA)")
    from apps.integrations_marketplace import lms_audit_retention as lar

    if not callable(lar.sweep_lms_audit_retention):
        _fail("T4.sweep_callable", "not callable")
    if lar.DEFAULT_RETENTION_YEARS != 7:
        _fail("T4.default_years", str(lar.DEFAULT_RETENTION_YEARS))
    _ok("module imports + DEFAULT_RETENTION_YEARS=7")

    if lar.purge_due_lms_audit_rows is None:
        _fail("T4.celery_task_missing", "purge_due_lms_audit_rows is None")
    if getattr(lar.purge_due_lms_audit_rows, "name", "") != "integrations_marketplace.purge_due_lms_audit_rows":
        _fail("T4.celery_task_name", str(getattr(lar.purge_due_lms_audit_rows, "name", "")))
    _ok("@shared_task integrations_marketplace.purge_due_lms_audit_rows registered")

    # Sweep with retention=0 -> retention_disabled
    out = lar.sweep_lms_audit_retention(years=0)
    if out.get("skipped_reason") != "retention_disabled":
        _fail("T4.retention_zero", str(out))
    _ok("years=0 skips with retention_disabled")

    # Sweep dry-run -> never deletes, still computes cutoff
    out = lar.sweep_lms_audit_retention(years=7, dry_run=True)
    if not out.get("dry_run"):
        _fail("T4.dry_run_flag", str(out))
    if out.get("purged") != 0:
        _fail("T4.dry_run_purged", str(out))
    if not out.get("cutoff_iso"):
        _fail("T4.cutoff_iso", str(out))
    _ok(f"dry_run=True computes cutoff {out['cutoff_iso'][:10]} and never deletes")

    # Cutoff math: 7 years back from a fixed point should land on the day
    from django.utils import timezone as _tz
    from datetime import timedelta
    pinned_now = _tz.now()
    out = lar.sweep_lms_audit_retention(years=7, now=pinned_now, dry_run=True)
    expected_cutoff = pinned_now - timedelta(days=7 * 365)
    # ISO compare to day precision so timezone offsets don't break us
    if out["cutoff_iso"][:10] != expected_cutoff.isoformat()[:10]:
        _fail("T4.cutoff_math", f"expected {expected_cutoff.isoformat()[:10]} got {out['cutoff_iso'][:10]}")
    _ok("cutoff math = now - (7 * 365 days)")

    # Live sweep (no rows present) returns considered=0, purged=0
    out = lar.sweep_lms_audit_retention()
    if out.get("considered", -1) < 0:
        _fail("T4.live_sweep", str(out))
    _ok(f"live sweep runs cleanly considered={out['considered']} purged={out['purged']}")


# ---------------------------------------------------------------------------
# T5 — PKCE auth-URL builder API endpoint
# ---------------------------------------------------------------------------
def run_t5():
    _line("\nT5 — PKCE auth-URL builder API endpoint")
    import json as _json
    import hashlib as _h
    import urllib.parse as _up
    from django.test import RequestFactory
    from django.contrib.auth import get_user_model
    from apps.portal.views_lms_pkce import lms_pkce_build

    User = get_user_model()
    staff = User(pk=999991, username="smoke-staff-pkce-builder", is_staff=True, is_active=True)
    staff.set_unusable_password()
    rf = RequestFactory()

    def _req(provider, qs=""):
        req = rf.get(f"/portal/super/integrations/lms/{provider}/pkce/build/{qs}")
        req.user = staff
        return req

    # --- Moodle: unsupported -> 400 ---
    os.environ["RMC_LMS_CANVAS_CLIENT_ID"] = "smoke-canvas-cid"
    os.environ["RMC_LMS_GOOGLE_CLIENT_ID"] = "smoke-google-cid"
    try:
        r = lms_pkce_build(_req("moodle", "?school=1"), "moodle")
        if r.status_code != 400:
            _fail("T5.moodle_400", f"got {r.status_code}")
        _ok("moodle returns 400 unsupported_provider")

        # --- Unknown provider -> 404 ---
        r = lms_pkce_build(_req("nope", "?school=1"), "nope")
        if r.status_code != 404:
            _fail("T5.unknown_404", f"got {r.status_code}")
        _ok("unknown provider returns 404")

        # --- Missing school -> 400 ---
        r = lms_pkce_build(_req("google"), "google")
        if r.status_code != 400:
            _fail("T5.missing_school", f"got {r.status_code}")
        _ok("missing school returns 400")

        # --- Google: success (no base_url needed) ---
        r = lms_pkce_build(_req("google", "?school=42"), "google")
        if r.status_code != 200:
            _fail("T5.google_200", f"got {r.status_code} body={r.content[:200]!r}")
        body = _json.loads(r.content)
        if body["provider"] != "google":
            _fail("T5.google_provider", str(body))
        if "accounts.google.com/o/oauth2/v2/auth" not in body["authorize_url"]:
            _fail("T5.google_authz_host", body["authorize_url"])
        qs = dict(_up.parse_qsl(body["authorize_url"].split("?", 1)[1]))
        if qs.get("code_challenge_method") != "S256":
            _fail("T5.google_pkce_method", str(qs))
        if qs.get("access_type") != "offline":
            _fail("T5.google_access_type", str(qs))
        if qs.get("prompt") != "consent":
            _fail("T5.google_prompt", str(qs))
        if "code_verifier" in body["pkce"]:
            _fail("T5.verifier_default_hidden", "verifier leaked without include_verifier")
        if len(body["pkce"]["verifier_sha256_16"]) != 16:
            _fail("T5.verifier_hash_len", str(body["pkce"]))
        _ok("google builder returns authorize_url + S256 challenge + offline/consent params, verifier hidden")

        # --- include_verifier=1 returns raw verifier and matches challenge ---
        r = lms_pkce_build(_req("google", "?school=42&include_verifier=1"), "google")
        body = _json.loads(r.content)
        verifier = body["pkce"]["code_verifier"]
        challenge = body["pkce"]["code_challenge"]
        import base64 as _b64
        recomputed = _b64.urlsafe_b64encode(
            _h.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        if recomputed != challenge:
            _fail("T5.verifier_to_challenge", "recompute != stored challenge")
        _ok("include_verifier=1 returns raw verifier whose SHA-256 base64url matches challenge")

        # --- Canvas without base_url -> 400 missing_base_url ---
        # School is UUID-typed in this codebase, so use a valid UUID.
        school_uuid = "00000000-0000-0000-0000-000000000099"
        r = lms_pkce_build(_req("canvas", f"?school={school_uuid}"), "canvas")
        if r.status_code != 400:
            _fail("T5.canvas_missing_base_url", f"got {r.status_code} body={r.content[:200]!r}")
        body = _json.loads(r.content)
        if body.get("error") != "missing_base_url":
            _fail("T5.canvas_missing_base_url_error", str(body))
        _ok("canvas without base_url returns 400 missing_base_url")

        # --- Canvas WITH base_url -> 200 ---
        r = lms_pkce_build(_req("canvas", f"?school={school_uuid}&base_url=https://canvas.smoke.edu"), "canvas")
        if r.status_code != 200:
            _fail("T5.canvas_200", f"got {r.status_code}")
        body = _json.loads(r.content)
        if "canvas.smoke.edu/login/oauth2/auth" not in body["authorize_url"]:
            _fail("T5.canvas_authz_host", body["authorize_url"])
        _ok("canvas builder returns tenant-scoped authorize_url")

        # --- Missing client_id -> 412 ---
        del os.environ["RMC_LMS_GOOGLE_CLIENT_ID"]
        r = lms_pkce_build(_req("google", "?school=42"), "google")
        if r.status_code != 412:
            _fail("T5.missing_client_id", f"got {r.status_code} body={r.content[:200]!r}")
        _ok("missing CLIENT_ID returns 412")
    finally:
        os.environ.pop("RMC_LMS_CANVAS_CLIENT_ID", None)
        os.environ.pop("RMC_LMS_GOOGLE_CLIENT_ID", None)


# ---------------------------------------------------------------------------

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
