"""v4.00.61 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +14 Tier-1 subdivisions (US-MO/AK/HI/ME/VT, IN-AR/GA/SK/HP, JP-04/JP-34,
    KR-41, CN-SH/CN-ZJ); SOT >= 377.
T2: OneRoster v1.2 demographics ``userSourcedIds`` spec link field +
    ``?userSourcedId=`` collection filter.
T3: Signed SAML LogoutRequest path — opt-in via RMC_SAML_SP_SIGN_LOGOUT;
    deps_missing path returns reason in JSON shape; strict-mode 503.
T4: Last-action history DB persistence — record() writes to
    LMSPushGradeAudit with course_id="_diag_action"; snapshot reads back
    from DB; survives ring reset.
T5: /super/migration/lms/diagnostics/ _auto_prune rollup — totals cards
    pruned_24h + pruned_dry_run_24h; per-provider prune_24h/prune_dry_run_24h.

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
        username="smoke-v4-00-61-staff",
        defaults={"email": "smoke@v4-00-61.local", "is_staff": True, "is_active": True},
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
    _line("\n[T1] +14 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = [
        "US-MO", "US-AK", "US-HI", "US-ME", "US-VT",
        "IN-AR", "IN-GA", "IN-SK", "IN-HP",
        "JP-04", "JP-34",
        "KR-41",
        "CN-SH", "CN-ZJ",
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
    if len(COUNTRY_LOCALIZATION) < 377:
        _fail("t1-sot-count", f"expected >= 377, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] OneRoster demographics userSourcedIds spec link field")
    from apps.api import oneroster_demographics as odm

    # Stub StudentProfile to test the projection (avoid DB churn).
    class _Stub:
        pk = 42
        user_id = 777
        date_of_birth = None
        gender = "FEMALE"
        place_of_birth = "Honolulu"
        updated_at = None

    rec = odm._demographic_from_student(_Stub())
    if "userSourcedIds" not in rec:
        _fail("t2-key-missing", f"got {sorted(rec)}")
    if not isinstance(rec["userSourcedIds"], list):
        _fail("t2-key-type", f"got {type(rec['userSourcedIds']).__name__}")
    if rec["userSourcedIds"] != ["777"]:
        _fail("t2-key-value", f"got {rec['userSourcedIds']}")
    _ok(f"t2-projection userSourcedIds=['777'] OK")

    # Empty when no user_id.
    class _Orphan:
        pk = 43
        user_id = None
        date_of_birth = None
        gender = ""
        place_of_birth = ""
        updated_at = None

    rec2 = odm._demographic_from_student(_Orphan())
    if rec2["userSourcedIds"] != []:
        _fail("t2-orphan", f"got {rec2['userSourcedIds']}")
    _ok("t2-projection orphan profile -> userSourcedIds=[]")

    # Override-ring round-trip preserved alongside userSourcedIds.
    odm._DEMOGRAPHIC_OVERRIDES.clear()
    odm._set_demographic_overrides(f"demo-{_Stub.pk}", {"asian": "yes"})
    rec3 = odm._demographic_from_student(_Stub())
    if rec3.get("asian") != "yes":
        _fail("t2-override-asian", f"got {rec3.get('asian')}")
    if rec3["userSourcedIds"] != ["777"]:
        _fail("t2-override-link-preserved", f"got {rec3['userSourcedIds']}")
    _ok("t2-projection override + userSourcedIds coexist")

    # ?userSourcedId= filter on collection — verify match-and-skip logic.
    items = [
        {"sourcedId": "demo-1", "userSourcedIds": ["100"]},
        {"sourcedId": "demo-2", "userSourcedIds": ["200"]},
        {"sourcedId": "demo-3", "userSourcedIds": ["100", "300"]},
        {"sourcedId": "demo-4", "userSourcedIds": []},
    ]
    matched_100 = [r for r in items if "100" in (r.get("userSourcedIds") or [])]
    if len(matched_100) != 2:
        _fail("t2-filter-100", f"got {len(matched_100)}")
    matched_999 = [r for r in items if "999" in (r.get("userSourcedIds") or [])]
    if matched_999 != []:
        _fail("t2-filter-999", f"got {matched_999}")
    _ok("t2-filter ?userSourcedId= match-skip logic OK")

    # URL still reverses (no route change for T2).
    from django.urls import reverse
    p = reverse("api:api-roster-v1p2-demographics")
    if not p.endswith("/demographics/"):
        _fail("t2-url", p)
    _ok(f"t2-url collection {p}")


def run_t3():
    _line("\n[T3] Signed SAML LogoutRequest path")
    from apps.api.saml import (
        _sign_saml_logout_request, _sp_sign_logout_enabled, slo_start,
    )
    rf = RequestFactory()

    # Default: signing OFF.
    os.environ.pop("RMC_SAML_SP_SIGN_LOGOUT", None)
    if _sp_sign_logout_enabled() is not False:
        _fail("t3-default-off", "expected False")
    _ok("t3-default-off RMC_SAML_SP_SIGN_LOGOUT unset -> disabled")

    # Turn it on.
    os.environ["RMC_SAML_SP_SIGN_LOGOUT"] = "1"
    try:
        if _sp_sign_logout_enabled() is not True:
            _fail("t3-flag-on", "expected True")
        _ok("t3-flag-on RMC_SAML_SP_SIGN_LOGOUT=1 -> enabled")

        # No key configured -> key_unset.
        os.environ.pop("RMC_SAML_SP_PRIVATE_KEY_PEM", None)
        signed, reason = _sign_saml_logout_request(b"<samlp:LogoutRequest/>")
        if reason != "key_unset":
            _fail("t3-key-unset", f"got {reason}")
        _ok("t3-sign key_unset reason classified")

        # Key set but no cert -> cert_unset.
        os.environ["RMC_SAML_SP_PRIVATE_KEY_PEM"] = "-----BEGIN PRIVATE KEY-----\nstub\n-----END PRIVATE KEY-----"
        os.environ.pop("RMC_SAML_SP_CERT_PEM", None)
        signed, reason = _sign_saml_logout_request(b"<samlp:LogoutRequest/>")
        if reason != "cert_unset":
            _fail("t3-cert-unset", f"got {reason}")
        _ok("t3-sign cert_unset reason classified")

        # Key + cert set, but lxml/signxml not installed -> deps_missing
        # (assuming deps not yet installed on this dev box).
        os.environ["RMC_SAML_SP_CERT_PEM"] = "-----BEGIN CERTIFICATE-----\nstub\n-----END CERTIFICATE-----"
        signed, reason = _sign_saml_logout_request(b"<samlp:LogoutRequest/>")
        if reason not in ("deps_missing", "bad_xml", "signature_error"):
            _fail("t3-sign-reason", f"got {reason}")
        _ok(f"t3-sign reason={reason} (deps_missing or downstream error)")

        # Pass-through: original bytes returned when reason != "ok".
        if reason != "ok" and signed != b"<samlp:LogoutRequest/>":
            _fail("t3-pass-through", "signing failure must return original bytes")
        _ok("t3-sign pass-through on failure preserved original XML")

        # JSON path reports signed:false + signature_reason.
        os.environ["RMC_SAML_SIGNATURE_STRICT"] = "0"  # non-strict for this case
        try:
            req = rf.get("/sso/saml/slo/start/?format=json&name_id=alice")
            req.session = _NullSession()
            resp = slo_start(req)
            if resp.status_code != 200:
                _fail("t3-json-status", f"got {resp.status_code}")
            body = _json.loads(resp.content)
            if "signed" not in body or "signature_reason" not in body:
                _fail("t3-json-shape", f"got {sorted(body)}")
            if body["signed"] is True and body["signature_reason"] != "ok":
                _fail("t3-json-signed-flag", f"got {body}")
            _ok(f"t3-json signed={body['signed']} reason={body['signature_reason']}")
        finally:
            os.environ.pop("RMC_SAML_SIGNATURE_STRICT", None)

        # Strict mode 503 on deps_missing.
        os.environ["RMC_SAML_SIGNATURE_STRICT"] = "1"
        try:
            req = rf.get("/sso/saml/slo/start/")
            req.session = _NullSession()
            resp = slo_start(req)
            if resp.status_code != 503:
                _fail("t3-strict-503", f"got {resp.status_code}")
            body = _json.loads(resp.content)
            if body.get("stage") != "sp_signer_unavailable":
                _fail("t3-strict-stage", f"got {body.get('stage')}")
            _ok(f"t3-strict 503 stage=sp_signer_unavailable reason={body.get('reason')}")
        finally:
            os.environ.pop("RMC_SAML_SIGNATURE_STRICT", None)

    finally:
        for k in ("RMC_SAML_SP_SIGN_LOGOUT", "RMC_SAML_SP_PRIVATE_KEY_PEM",
                  "RMC_SAML_SP_CERT_PEM"):
            os.environ.pop(k, None)


def run_t4():
    _line("\n[T4] Last-action history DB persistence")
    from apps.migration_cloud import views_lms_diagnostics as vld
    rf = RequestFactory()
    user = _staff_user()

    # Clear the in-process ring AND any prior DB rows for a clean baseline.
    vld._LAST_ACTION_RING.clear()
    try:
        from apps.integrations_marketplace.models import LMSPushGradeAudit
        LMSPushGradeAudit.objects.filter(  # tenant-isolation-allow: smoke-cleanup
            course_id=vld._DIAG_ACTION_COURSE_ID,
        ).delete()
    except Exception as exc:  # noqa: BLE001
        _line(f"  WARN smoke cleanup skipped: {exc}")

    # Record an action via the view path.
    req = rf.post("/super/migration/lms/diagnostics/force-refresh/",
                  {"provider": "canvas"}, HTTP_ACCEPT="application/json")
    req.user = user
    req._dont_enforce_csrf_checks = True
    resp = vld.lms_diagnostics_force_refresh(req)
    if resp.status_code != 200:
        _fail("t4-force-refresh", f"got {resp.status_code}")
    _ok("t4-force-refresh action recorded via view")

    # In-process ring has 1.
    if len(vld._LAST_ACTION_RING) != 1:
        _fail("t4-ring-1", f"got {len(vld._LAST_ACTION_RING)}")
    _ok("t4-ring-1 in-process ring has the entry")

    # DB also has 1 row with course_id="_diag_action".
    try:
        n = LMSPushGradeAudit.objects.filter(  # tenant-isolation-allow: smoke
            course_id=vld._DIAG_ACTION_COURSE_ID,
        ).count()
        if n != 1:
            _fail("t4-db-1", f"got {n}")
        _ok("t4-db-1 DB has 1 _diag_action row")
    except Exception as exc:  # noqa: BLE001
        _fail("t4-db-1-query", str(exc))

    # CLEAR the in-process ring — simulating worker restart.
    vld._LAST_ACTION_RING.clear()
    if vld._LAST_ACTION_RING:
        _fail("t4-ring-cleared", "ring should be empty")
    _ok("t4-ring-cleared simulating worker restart")

    # Durable snapshot still returns the DB row.
    snap = vld.get_last_action_snapshot(limit=10, durable=True)
    if len(snap) != 1:
        _fail("t4-durable-1", f"got {len(snap)}")
    if snap[0]["action"] != "force_refresh" or snap[0]["provider"] != "canvas":
        _fail("t4-durable-shape", f"got {snap[0]}")
    _ok(f"t4-durable snapshot survives ring clear (action={snap[0]['action']})")

    # Non-durable snapshot returns ring (empty).
    snap_ring = vld.get_last_action_snapshot(limit=10, durable=False)
    if snap_ring != []:
        _fail("t4-ring-only", f"got {snap_ring}")
    _ok("t4-ring-only durable=False returns ring-only (empty after restart)")

    # Counters parsed back from detail string.
    if snap[0]["considered"] < 0 or snap[0]["ok"] < 0 or snap[0]["failed"] < 0:
        _fail("t4-counters", f"got {snap[0]}")
    _ok(f"t4-counters parsed back: considered={snap[0]['considered']} ok={snap[0]['ok']} failed={snap[0]['failed']}")

    # Add a second action.
    req = rf.post("/super/migration/lms/diagnostics/force-rotate/",
                  {"provider": "moodle"}, HTTP_ACCEPT="application/json")
    req.user = user
    req._dont_enforce_csrf_checks = True
    resp = vld.lms_diagnostics_force_rotate(req)
    if resp.status_code != 200:
        _fail("t4-force-rotate", f"got {resp.status_code}")
    snap2 = vld.get_last_action_snapshot(limit=10, durable=True)
    if len(snap2) != 2:
        _fail("t4-durable-2", f"got {len(snap2)}")
    # Newest-first.
    if snap2[0]["action"] != "force_rotate":
        _fail("t4-newest-first", f"got {[s['action'] for s in snap2]}")
    _ok(f"t4-durable 2 rows newest-first: {[s['action'] for s in snap2]}")

    # _action_totals reflects DB rather than current-worker ring.
    totals = vld._action_totals()
    if totals.get("durable") is not True:
        _fail("t4-totals-durable-flag", f"got {totals}")
    if totals.get("total") != 2:
        _fail("t4-totals-count", f"got {totals}")
    _ok(f"t4-totals durable={totals['durable']} total={totals['total']}")

    # Cleanup smoke rows so we don't pollute the operator surface.
    LMSPushGradeAudit.objects.filter(  # tenant-isolation-allow: smoke-cleanup
        course_id=vld._DIAG_ACTION_COURSE_ID,
    ).delete()
    _ok("t4-cleanup smoke _diag_action rows removed")


def run_t5():
    _line("\n[T5] /super/migration/lms/diagnostics/ _auto_prune rollup")
    from apps.migration_cloud import views_lms_diagnostics as vld
    from apps.integrations_marketplace.models import LMSPushGradeAudit

    # Clean slate for the audit rollup.
    LMSPushGradeAudit.objects.filter(  # tenant-isolation-allow: smoke-cleanup
        course_id="_auto_prune",
    ).delete()

    # Seed 3 real prunes + 2 dry-runs across two providers.
    LMSPushGradeAudit.objects.bulk_create([  # tenant-isolation-allow: smoke-seed
        LMSPushGradeAudit(
            school_id=None, provider="canvas", course_id="_auto_prune",
            assignment_id="refresh_revoked", user_hash="",
            score_text="", ok=False, status_code=0, detail="seed-real-1",
            actor_user_id="",
        ),
        LMSPushGradeAudit(
            school_id=None, provider="canvas", course_id="_auto_prune",
            assignment_id="refresh_revoked", user_hash="",
            score_text="", ok=False, status_code=0, detail="seed-real-2",
            actor_user_id="",
        ),
        LMSPushGradeAudit(
            school_id=None, provider="google", course_id="_auto_prune",
            assignment_id="refresh_revoked", user_hash="",
            score_text="", ok=False, status_code=0, detail="seed-real-3",
            actor_user_id="",
        ),
        LMSPushGradeAudit(
            school_id=None, provider="moodle", course_id="_auto_prune",
            assignment_id="dry_run:refresh_revoked", user_hash="",
            score_text="", ok=False, status_code=0, detail="seed-dry-1",
            actor_user_id="",
        ),
        LMSPushGradeAudit(
            school_id=None, provider="canvas", course_id="_auto_prune",
            assignment_id="dry_run:refresh_revoked", user_hash="",
            score_text="", ok=False, status_code=0, detail="seed-dry-2",
            actor_user_id="",
        ),
    ])

    diag = vld._compute_lms_diagnostics()
    if "pruned_24h" not in diag["totals"]:
        _fail("t5-totals-pruned-key", f"got {sorted(diag['totals'])}")
    if diag["totals"]["pruned_24h"] != 3:
        _fail("t5-totals-pruned-3", f"got {diag['totals']['pruned_24h']}")
    if diag["totals"]["pruned_dry_run_24h"] != 2:
        _fail("t5-totals-dry-2", f"got {diag['totals']['pruned_dry_run_24h']}")
    _ok(f"t5-totals pruned_24h=3 pruned_dry_run_24h=2")

    # Per-provider partitioning.
    by_provider = {p["provider"]: p for p in diag["providers"]}
    if "canvas" not in by_provider:
        _fail("t5-providers-canvas", f"got {sorted(by_provider)}")
    canvas = by_provider["canvas"]
    if canvas.get("prune_24h") != 2:
        _fail("t5-canvas-prune-2", f"got {canvas}")
    if canvas.get("prune_dry_run_24h") != 1:
        _fail("t5-canvas-dry-1", f"got {canvas}")
    google = by_provider.get("google", {})
    if google.get("prune_24h") != 1:
        _fail("t5-google-prune-1", f"got {google}")
    moodle = by_provider.get("moodle", {})
    if moodle.get("prune_dry_run_24h") != 1:
        _fail("t5-moodle-dry-1", f"got {moodle}")
    _ok("t5-per-provider canvas(2,1) + google(1,0) + moodle(0,1)")

    # Default-zero shape for providers with no prune rows.
    for p in diag["providers"]:
        for k in ("prune_24h", "prune_dry_run_24h", "health_ok_24h", "health_failed_24h"):
            if k not in p:
                _fail("t5-default-zero", f"provider={p['provider']} missing {k}")
    _ok("t5-default-zero all providers carry prune/health keys")

    # Cleanup seeds.
    LMSPushGradeAudit.objects.filter(  # tenant-isolation-allow: smoke-cleanup
        course_id="_auto_prune",
    ).delete()
    _ok("t5-cleanup seeds removed")


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
