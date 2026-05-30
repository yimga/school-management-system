"""v4.00.71 smoke."""
from __future__ import annotations
import json as _json
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django  # noqa: E402
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.test import RequestFactory  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402


def _line(s): print(s, flush=True)  # noqa: E702
def _ok(name): _line(f"  OK   {name}")  # noqa: E702
def _fail(name, detail):  # noqa: ANN001
    _line(f"  FAIL {name} :: {detail}"); sys.exit(1)


def _staff_user():
    User = get_user_model()
    u, _ = User.objects.get_or_create(
        username="smoke-v4-00-71-staff",
        defaults={"email": "smoke@v4-00-71.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


def run_t1():
    _line("\n[T1] +14 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = ["AE-DU", "AE-AZ", "IL-TA", "JO-AM", "EG-MN", "MA-CAS", "DZ-16",
                "NG-OG", "NG-AN", "BR-DF", "KE-30", "GH-AA", "UG-101", "TZ-02"]
    for k in new_keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-{k}", f"missing: {type(e).__name__}")
        for r in ("calendar_system", "school_types", "education_levels", "terminology"):
            if r not in e:
                _fail(f"t1-shape-{k}-{r}", "missing")
        _ok(f"t1-{k} OK")
    if len(COUNTRY_LOCALIZATION) < 518:
        _fail("t1-sot-count", f"expected >= 518, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] OneRoster academic_sessions enriched + detail endpoint")
    from apps.api import oneroster as mod
    sessions = list(mod._iter_academic_sessions())
    if sessions:
        for k in ("sourcedId", "status", "title", "type", "startDate", "endDate", "schoolYear", "parentSourcedId"):
            if k not in sessions[0]:
                _fail(f"t2-key-{k}", "missing")
        _ok(f"t2-academic_session projection carries 8 keys incl startDate/endDate/schoolYear/parentSourcedId (n={len(sessions)})")
    else:
        _ok("t2-_iter_academic_sessions empty (no AcademicYear rows in DB) — projection function callable")

    rf = RequestFactory()
    os.environ["RMC_ONEROSTER_BEARER"] = "smoke-bearer"
    try:
        req = rf.get("/api/roster/v1p2/academic-sessions/9999/")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.academic_session_detail(req, sourced_id="9999")
        if resp.status_code != 404:
            _fail("t2-detail-404", f"got {resp.status_code}")
        body = _json.loads(resp.content)
        if body.get("error") != "academic_session_not_found":
            _fail("t2-detail-404-body", str(body))
        _ok("t2-academic_session_detail 404 path returns academic_session_not_found")
    finally:
        os.environ.pop("RMC_ONEROSTER_BEARER", None)

    from django.urls import reverse, NoReverseMatch
    try:
        url = reverse("api:api-roster-v1p2-academic-session-detail", kwargs={"sourced_id": "X"})
        if not url.endswith("/academic-sessions/X/"):
            _fail("t2-url-shape", url)
        _ok(f"t2-URL route resolves: {url}")
    except NoReverseMatch as exc:
        _fail("t2-url", str(exc))


def run_t3():
    _line("\n[T3] Race flag expansion: asian + blackOrAfricanAmerican")
    from apps.api import oneroster_demographics as odm
    if "asian" not in odm.RACE_ETHNICITY_BOOL_FIELDS:
        _fail("t3-asian-registered", "missing from RACE_ETHNICITY_BOOL_FIELDS")
    if "blackOrAfricanAmerican" not in odm.RACE_ETHNICITY_BOOL_FIELDS:
        _fail("t3-black-registered", "missing from RACE_ETHNICITY_BOOL_FIELDS")
    _ok("t3-RACE_ETHNICITY_BOOL_FIELDS now includes americanIndianOrAlaskaNative + asian + blackOrAfricanAmerican")

    # asian boolish accepted.
    for v in (True, False, "true", "yes", "1", "0", "no", ""):
        err = odm._validate_race_ethnicity_bool_flags({"asian": v})
        if err is not None:
            _fail(f"t3-asian-{v!r}", f"got {err.content}")
    _ok("t3-asian field accepts bool literals + boolish strings + empty (clear)")

    # blackOrAfricanAmerican boolish accepted.
    err = odm._validate_race_ethnicity_bool_flags({"blackOrAfricanAmerican": "true"})
    if err is not None:
        _fail("t3-black-true", f"got {err.content}")
    _ok("t3-blackOrAfricanAmerican accepts boolish")

    # Bad value rejected w/ field=asian in body.
    err = odm._validate_race_ethnicity_bool_flags({"asian": "maybe"})
    if err is None or err.status_code != 400:
        _fail("t3-asian-bad", f"got {err}")
    body = _json.loads(err.content)
    if body.get("field") != "asian":
        _fail("t3-asian-bad-field", str(body))
    _ok("t3-asian='maybe' -> 400 not_boolish w/ field=asian")

    # E2E.
    body_bytes = _json.dumps({"demographic": {"asian": "true", "blackOrAfricanAmerican": "no"}}).encode("utf-8")
    inner, err = odm._parse_demographic_payload(body_bytes)
    if err is not None:
        _fail("t3-e2e", f"got {err}")
    _ok("t3-_parse_demographic_payload accepts payload w/ asian=true + black=no")


def run_t4():
    _line("\n[T4] Retention sweep cumulative counters")
    from apps.migration_cloud import views_lms_diagnostics as vld
    rf = RequestFactory()
    user = _staff_user()

    vld.reset_retention_sweep_counters()
    base = vld.get_retention_sweep_counters()
    for k in ("previews_count", "purges_count", "rows_considered_total", "rows_deleted_total"):
        if base.get(k) != 0:
            _fail(f"t4-reset-{k}", f"got {base}")
    _ok("t4-reset_retention_sweep_counters -> all 4 counters at 0")

    # Hit preview view; previews_count should go up.
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?format=json&years=7")
    req.user = user
    vld.lms_diagnostics_retention_preview(req)
    snap = vld.get_retention_sweep_counters()
    if snap["previews_count"] != 1:
        _fail("t4-preview-bump", f"got {snap}")
    _ok(f"t4-preview view bumps previews_count -> {snap['previews_count']}")

    # Multiple previews accumulate.
    for _ in range(3):
        vld.lms_diagnostics_retention_preview(req)
    snap = vld.get_retention_sweep_counters()
    if snap["previews_count"] != 4:
        _fail("t4-preview-accum", f"got {snap}")
    _ok(f"t4-4 previews cumulative previews_count={snap['previews_count']}")

    # Manual bump w/ deleted=>0 simulates purge.
    vld._bump_retention_sweep_counter(kind="purge", considered=10, deleted=7)
    snap = vld.get_retention_sweep_counters()
    if snap["purges_count"] != 1:
        _fail("t4-purge-bump", f"got {snap}")
    if snap["rows_deleted_total"] != 7:
        _fail("t4-deleted-bump", f"got {snap}")
    if snap["rows_considered_total"] < 10:
        _fail("t4-considered-bump", f"got {snap}")
    _ok(f"t4-purge bump: purges_count={snap['purges_count']} rows_deleted_total={snap['rows_deleted_total']}")

    # Defensive: bump w/ None values.
    vld._bump_retention_sweep_counter(kind="purge", considered=None, deleted=None)
    snap2 = vld.get_retention_sweep_counters()
    if snap2["purges_count"] != 2:
        _fail("t4-bump-none", f"got {snap2}")
    _ok("t4-bump handles None inputs defensively")

    vld.reset_retention_sweep_counters()
    _ok("t4-cleanup")


def run_t5():
    _line("\n[T5] Schoology scaffold adapter + OAuth state mint")
    from apps.integrations_marketplace import lms_connector_schoology as sg
    from apps.integrations_marketplace import lms_supported_providers as lsp

    # Surface functions.
    for f in ("oauth_authorize_url", "mint_oauth_state", "read_oauth_state",
              "refresh_token", "push_grade", "pull_courses", "is_scaffold"):
        if not hasattr(sg, f):
            _fail(f"t5-func-{f}", "missing")
    _ok("t5-7 surface functions present (5 adapter + mint + read OAuth state)")

    # Authorize URL shape.
    url = sg.oauth_authorize_url(client_id="cid", redirect_uri="https://rmc.test/cb", state="s")
    if "www.schoology.com/oauth/authorize" not in url:
        _fail("t5-authorize-url", url)
    if "client_id=cid" not in url or "state=s" not in url:
        _fail("t5-authorize-qs", url)
    _ok("t5-authorize URL targets schoology.com w/ client_id + state")

    # State mint + read round-trip.
    token = sg.mint_oauth_state(tenant_slug="acme", user_pk=42, redirect_path="/portal/dashboard/")
    if not token or ":" not in token:
        _fail("t5-mint-shape", token)
    parsed, reason = sg.read_oauth_state(token)
    if reason != "ok":
        _fail("t5-read-ok", f"got reason={reason} parsed={parsed}")
    if parsed["tenant_slug"] != "acme" or str(parsed["user_pk"]) != "42":
        _fail("t5-read-payload", str(parsed))
    if parsed["redirect_path"] != "/portal/dashboard/":
        _fail("t5-read-redirect", str(parsed))
    _ok("t5-mint + read OAuth state round-trip preserves tenant_slug/user_pk/redirect_path")

    # Bad token -> bad_token reason.
    _, reason = sg.read_oauth_state("garbage-not-a-signed-token")
    if reason != "bad_token":
        _fail("t5-bad-token", f"got {reason}")
    _ok("t5-bad token -> reason=bad_token")

    # Missing token.
    _, reason = sg.read_oauth_state("")
    if reason != "missing_token":
        _fail("t5-missing", f"got {reason}")
    _ok("t5-empty token -> reason=missing_token")

    # Open-redirect defense on mint: //external -> "/" fallback.
    token = sg.mint_oauth_state(tenant_slug="acme", user_pk=1, redirect_path="//evil.example/")
    parsed, _ = sg.read_oauth_state(token)
    if parsed["redirect_path"] != "/":
        _fail("t5-open-redirect", str(parsed))
    _ok("t5-//external redirect_path collapsed to / on mint (open-redirect defense)")

    # is_scaffold True.
    if sg.is_scaffold() is not True:
        _fail("t5-is-scaffold", "expected True")
    if not lsp.is_scaffold_lms_provider("schoology"):
        _fail("t5-sot-scaffold", "expected True")
    _ok("t5-Schoology is_scaffold + registered in SOT scaffold set")


def main():
    run_t1(); run_t2(); run_t3(); run_t4(); run_t5()
    _line("\nALL GREEN")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(2)
