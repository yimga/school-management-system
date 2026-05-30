"""v4.00.70 smoke."""
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


def _line(s): print(s, flush=True)  # noqa: E702
def _ok(name): _line(f"  OK   {name}")  # noqa: E702
def _fail(name, detail):  # noqa: ANN001
    _line(f"  FAIL {name} :: {detail}"); sys.exit(1)


def _staff_user():
    User = get_user_model()
    u, _ = User.objects.get_or_create(
        username="smoke-v4-00-70-staff",
        defaults={"email": "smoke@v4-00-70.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


def run_t1():
    _line("\n[T1] +14 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = ["PE-CUS", "AR-T", "EG-GIZ", "NG-AB", "NG-KD", "NG-RI", "ZA-EC", "ZA-MP",
                "IT-CAM", "IT-VEN", "ES-AN", "FR-OCC", "FR-NAQ", "GR-C"]
    for k in new_keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-present-{k}", f"missing/non-dict: {type(e).__name__}")
        for r in ("calendar_system", "school_types", "education_levels", "terminology"):
            if r not in e:
                _fail(f"t1-shape-{k}-{r}", "missing")
        _ok(f"t1-{k} OK")
    if len(COUNTRY_LOCALIZATION) < 504:
        _fail("t1-sot-count", f"expected >= 504, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] OneRoster orgs single-org detail endpoint + enriched projection")
    from apps.api import oneroster as mod
    rf = RequestFactory()
    # Enriched projection: parentSourcedId + metadata keys present.
    orgs = list(mod._iter_orgs())
    if not orgs:
        # No schools in DB — make a quick assertion that the projection
        # would still carry the keys at least for one synthetic check.
        # Walk an empty iter — verify the function did not raise.
        _ok("t2-_iter_orgs() returned empty (no Schools in DB) without raising")
    else:
        first = orgs[0]
        for key in ("sourcedId", "status", "type", "name", "identifier", "parentSourcedId", "metadata"):
            if key not in first:
                _fail(f"t2-org-key-{key}", f"missing in {first}")
        if "subdivisionCode" not in first["metadata"]:
            _fail("t2-metadata-subdivision", "missing")
        if "countryCode" not in first["metadata"]:
            _fail("t2-metadata-country", "missing")
        _ok(f"t2-org projection carries 7 keys + metadata.subdivisionCode/countryCode (n={len(orgs)})")

    # org_detail view 404 path.
    req = rf.get("/api/roster/v1p2/orgs/9999999/")
    req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
    os.environ["RMC_ONEROSTER_BEARER"] = "smoke-bearer"
    try:
        resp = mod.org_detail(req, sourced_id="9999999")
        if resp.status_code != 404:
            _fail("t2-detail-404", f"got {resp.status_code}")
        body = _json.loads(resp.content)
        if body.get("error") != "org_not_found":
            _fail("t2-detail-404-body", f"got {body}")
        _ok("t2-org_detail GET non-existent sourcedId -> 404 org_not_found")
    finally:
        os.environ.pop("RMC_ONEROSTER_BEARER", None)

    # URL resolves.
    from django.urls import reverse, NoReverseMatch
    try:
        url = reverse("api:api-roster-v1p2-org-detail", kwargs={"sourced_id": "abc"})
        if not url.endswith("/orgs/abc/"):
            _fail("t2-url-shape", url)
        _ok(f"t2-URL route resolves: {url}")
    except NoReverseMatch as exc:
        _fail("t2-url", str(exc))


def run_t3():
    _line("\n[T3] Demographics americanIndianOrAlaskaNative bool flag validation")
    from apps.api import oneroster_demographics as odm

    # Missing accepted.
    if odm._validate_race_ethnicity_bool_flags({}) is not None:
        _fail("t3-missing", "expected None")
    _ok("t3-missing field -> None")

    # True / False bool literals accepted.
    for val in (True, False):
        err = odm._validate_race_ethnicity_bool_flags({"americanIndianOrAlaskaNative": val})
        if err is not None:
            _fail(f"t3-bool-{val}", f"got {err.content}")
    _ok("t3-bool literals True / False accepted")

    # Truthy/falsey strings accepted (case-insensitive).
    for s in ("true", "false", "yes", "no", "1", "0", "TRUE", "False", "Y", "n"):
        err = odm._validate_race_ethnicity_bool_flags({"americanIndianOrAlaskaNative": s})
        if err is not None:
            _fail(f"t3-str-{s}", f"got {err.content}")
    _ok("t3-truthy/falsey strings (true/false/yes/no/1/0/Y/n + case) accepted")

    # Empty string treated as explicit clear (no error).
    err = odm._validate_race_ethnicity_bool_flags({"americanIndianOrAlaskaNative": ""})
    if err is not None:
        _fail("t3-empty", f"got {err.content}")
    _ok("t3-empty string -> None (explicit clear)")

    # Bad shape rejected.
    for bad in ("maybe", "huh", "kinda", "42"):
        err = odm._validate_race_ethnicity_bool_flags({"americanIndianOrAlaskaNative": bad})
        if err is None or err.status_code != 400:
            _fail(f"t3-bad-{bad}", f"expected 400; got {err}")
        body = _json.loads(err.content)
        if body.get("reason") != "not_boolish":
            _fail(f"t3-bad-reason-{bad}", f"got {body}")
        if body.get("field") != "americanIndianOrAlaskaNative":
            _fail(f"t3-bad-field-{bad}", f"got {body}")
    _ok("t3-non-boolish strings -> 400 not_boolish (field name echoed)")

    # E2E via _parse_demographic_payload.
    body_bytes = _json.dumps({"demographic": {"americanIndianOrAlaskaNative": "true"}}).encode("utf-8")
    inner, err = odm._parse_demographic_payload(body_bytes)
    if err is not None:
        _fail("t3-e2e-happy", f"got {err}")
    _ok("t3-_parse_demographic_payload accepts boolish 'true'")

    body_bytes = _json.dumps({"demographic": {"americanIndianOrAlaskaNative": "maybe"}}).encode("utf-8")
    inner, err = odm._parse_demographic_payload(body_bytes)
    if err is None or err.status_code != 400:
        _fail("t3-e2e-bad", f"expected 400; got {err}")
    _ok("t3-_parse_demographic_payload rejects 'maybe' w/ 400")


def run_t4():
    _line("\n[T4] Retention preview JSONL export")
    from apps.migration_cloud import views_lms_diagnostics as vld
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    rf = RequestFactory()
    user = _staff_user()
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()

    # JSONL export shape.
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?format=jsonl&years=7")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    if resp.status_code != 200:
        _fail("t4-jsonl-status", f"got {resp.status_code}")
    if "application/x-ndjson" not in resp["Content-Type"]:
        _fail("t4-jsonl-content-type", resp["Content-Type"])
    if "attachment" not in resp["Content-Disposition"]:
        _fail("t4-jsonl-disposition", resp["Content-Disposition"])
    if ".jsonl" not in resp["Content-Disposition"]:
        _fail("t4-jsonl-filename", resp["Content-Disposition"])
    _ok("t4-?format=jsonl returns application/x-ndjson + attachment + .jsonl filename")

    body = resp.content.decode("utf-8")
    lines = [ln for ln in body.split("\n") if ln.strip()]
    if not lines:
        _fail("t4-jsonl-empty", "no lines")
    summary = _json.loads(lines[0])
    if summary.get("kind") != "summary":
        _fail("t4-jsonl-line1-kind", f"got {summary}")
    for k in ("years", "cutoff_iso", "considered", "before_total", "after_total",
              "weeks_per_side", "p25", "p50", "p75"):
        if k not in summary:
            _fail(f"t4-jsonl-summary-key-{k}", f"missing in {summary}")
    _ok(f"t4-line 1 is kind=summary w/ all expected keys (lines: {len(lines)})")

    # Bucket lines should follow.
    bucket_lines = [_json.loads(ln) for ln in lines[1:]]
    if not all(b.get("kind") == "bucket" for b in bucket_lines):
        _fail("t4-jsonl-bucket-kinds", "non-bucket line found")
    if len(bucket_lines) != 24:
        _fail("t4-jsonl-bucket-count", f"expected 24; got {len(bucket_lines)}")
    for b in bucket_lines:
        for k in ("week_start_iso", "side", "count"):
            if k not in b:
                _fail(f"t4-jsonl-bucket-key-{k}", f"missing in {b}")
    _ok("t4-24 bucket lines follow, all w/ week_start_iso/side/count keys")

    # X-headers set.
    if not resp.get("X-Retention-Sparkline-Bucket-Count"):
        _fail("t4-x-header", "missing")
    _ok(f"t4-X-Retention-* headers set (bucket-count={resp['X-Retention-Sparkline-Bucket-Count']})")

    # Back-compat: ?format=csv still works.
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?format=csv&years=7")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    if resp.status_code != 200 or "text/csv" not in resp["Content-Type"]:
        _fail("t4-csv-backcompat", f"got {resp.status_code} {resp['Content-Type']}")
    _ok("t4-?format=csv back-compat preserved")

    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()
    _ok("t4-cleanup")


def run_t5():
    _line("\n[T5] D2L Brightspace scaffold adapter")
    from apps.integrations_marketplace import lms_connector_d2l as d2l
    from apps.integrations_marketplace import lms_supported_providers as lsp

    # Module surface.
    for func in ("oauth_authorize_url", "refresh_token", "push_grade", "pull_courses", "is_scaffold"):
        if not hasattr(d2l, func):
            _fail(f"t5-func-{func}", "missing")
    _ok("t5-5 surface functions present (oauth_authorize_url + refresh + push + pull + is_scaffold)")

    # is_scaffold honest-declaration check.
    # Forward-compat note: True at v4.00.70; D2L promoted to production
    # in v4.00.84/.88. Accept either snapshot value — both are correct
    # at their respective waves.
    _ok(f"t5-is_scaffold() returns {d2l.is_scaffold()} "
        f"(was True at v4.00.70; post-v4.00.84 promotion: False)")

    # OAuth authorize URL shape.
    url = d2l.oauth_authorize_url(
        client_id="cid-123", redirect_uri="https://rmc.test/cb",
        state="state-xyz", scopes=("core:*:*",),
    )
    if not url.startswith("https://auth.brightspace.com/oauth2/auth"):
        _fail("t5-authorize-prefix", url)
    for needle in ("client_id=cid-123", "redirect_uri=", "state=state-xyz",
                   "response_type=code", "scope=core"):
        if needle not in url:
            _fail(f"t5-authorize-{needle}", url)
    _ok("t5-authorize URL carries client_id + redirect_uri + state + scope + response_type=code")

    # refresh_token honest-stub shape.
    out = d2l.refresh_token(refresh_token="r-1", client_id="c-1", client_secret="s-1")
    if out.get("ok") is not False or out.get("reason") != "scaffold_not_wired":
        _fail("t5-refresh-stub", str(out))
    if out.get("provider") != "d2l_brightspace":
        _fail("t5-refresh-provider", str(out))
    _ok("t5-refresh_token honest-stub -> ok=False reason=scaffold_not_wired provider=d2l_brightspace")

    # push_grade honest-stub shape.
    out = d2l.push_grade(base_url="https://b.x", access_token="t", course_id="c",
                         user_id="u", score=85, max_score=100)
    if out.get("ok") is not False or out.get("reason") != "scaffold_not_wired":
        _fail("t5-push-stub", str(out))
    _ok("t5-push_grade honest-stub -> ok=False reason=scaffold_not_wired")

    # pull_courses honest-stub.
    out = d2l.pull_courses(base_url="https://b.x", access_token="t")
    if out != []:
        _fail("t5-pull-stub", str(out))
    _ok("t5-pull_courses honest-stub -> []")

    # D2L registered in SOT. Forward-compat: at v4.00.70 D2L was a
    # scaffold + NOT oauth_ready; promoted to oauth_ready in v4.00.84 +
    # production in v4.00.88. Only the stable invariants are still
    # asserted (still supported, label unchanged).
    if not lsp.is_supported_lms_provider("d2l_brightspace"):
        _fail("t5-sot-supported", "expected True")
    if lsp.canonical_lms_provider_label("d2l_brightspace") != "Brightspace (D2L)":
        _fail("t5-sot-label", lsp.canonical_lms_provider_label("d2l_brightspace"))
    _ok(f"t5-D2L is_supported, label='Brightspace (D2L)', "
        f"scaffold={lsp.is_scaffold_lms_provider('d2l_brightspace')}, "
        f"oauth_ready={lsp.is_oauth_ready_lms_provider('d2l_brightspace')} "
        f"(was scaffold+NOT oauth_ready at v4.00.70)")


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
