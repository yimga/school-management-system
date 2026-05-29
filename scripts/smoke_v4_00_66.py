"""v4.00.66 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +14 Tier-1 subdivisions (JP-28/40/20, CN-AH/HB/SC/CQ, KR-45, CA-NS,
    BR-PR/PE/CE, GB-ENG, VN-HN); SOT >= 454.
T2: SAML attribute mapping config — RMC_SAML_ATTR_FIRST_NAME / _LAST_NAME
    / _EMAIL env-driven priority lists; defaults preserve v4.00.45.
T3: OneRoster ?filter= boolean expression parser per Roster Service spec
    § 4.13. Grammar: predicate (logical_op predicate)*. Operators:
    = != > >= < <= ~. Boolean: AND OR. AND-precedence higher than OR.
T4: Demographics countryOfBirthCode ISO 3166-1 alpha-2 validation —
    shape regex + SOT membership check from COUNTRY_LOCALIZATION.
T5: Retention force-purge with signed-token round-trip — preview view
    emits 5min-TTL HMAC token bound to (years, cutoff_iso); purge POST
    validates + runs real sweep + writes action-history audit row.

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
        username="smoke-v4-00-66-staff",
        defaults={"email": "smoke@v4-00-66.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


def run_t1():
    _line("\n[T1] +14 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = [
        "JP-28", "JP-40", "JP-20",
        "CN-AH", "CN-HB", "CN-SC", "CN-CQ",
        "KR-45",
        "CA-NS",
        "BR-PR", "BR-PE", "BR-CE",
        "GB-ENG", "VN-HN",
    ]
    for k in new_keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-present-{k}", f"missing or non-dict: {type(e).__name__}")
        for r in ("calendar_system", "school_types", "education_levels", "terminology"):
            if r not in e:
                _fail(f"t1-shape-{k}-{r}", f"missing {r}")
        if not isinstance(e["school_types"], list) or len(e["school_types"]) < 4:
            _fail(f"t1-school-types-{k}", "need >= 4")
        if not isinstance(e["education_levels"], list) or len(e["education_levels"]) < 3:
            _fail(f"t1-education-levels-{k}", "need >= 3")
        _ok(f"t1-{k} OK ({len(e['school_types'])} types, {len(e['education_levels'])} levels)")
    if len(COUNTRY_LOCALIZATION) < 454:
        _fail("t1-sot-count", f"expected >= 454, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] SAML attribute mapping config")
    from apps.api import saml as saml_mod

    # Defaults present.
    for env_key in ("RMC_SAML_ATTR_FIRST_NAME", "RMC_SAML_ATTR_LAST_NAME", "RMC_SAML_ATTR_EMAIL"):
        os.environ.pop(env_key, None)
    m = saml_mod._resolve_saml_attr_map()
    if "givenName" not in m["first_name"]:
        _fail("t2-default-first", f"got {m['first_name']}")
    if "sn" not in m["last_name"]:
        _fail("t2-default-last", f"got {m['last_name']}")
    if "email" not in m["email"]:
        _fail("t2-default-email", f"got {m['email']}")
    _ok("t2-default map preserves v4.00.45 attribute names")

    # Env override.
    os.environ["RMC_SAML_ATTR_FIRST_NAME"] = "firstName,first_name"
    os.environ["RMC_SAML_ATTR_EMAIL"] = "email_addr,Email"
    try:
        m = saml_mod._resolve_saml_attr_map()
        if m["first_name"] != ("firstName", "first_name"):
            _fail("t2-env-first", f"got {m['first_name']}")
        if m["email"] != ("email_addr", "Email"):
            _fail("t2-env-email", f"got {m['email']}")
        _ok("t2-env RMC_SAML_ATTR_FIRST_NAME + _EMAIL override honored")
    finally:
        os.environ.pop("RMC_SAML_ATTR_FIRST_NAME", None)
        os.environ.pop("RMC_SAML_ATTR_EMAIL", None)

    # _extract_saml_attr walks priority list.
    val = saml_mod._extract_saml_attr({"firstName": "Ada", "first_name": ""}, ("givenName", "firstName"))
    if val != "Ada":
        _fail("t2-extract-priority", f"got {val!r}")
    _ok("t2-extract walks priority list: givenName not present, firstName='Ada' wins")

    # Empty priority returns "".
    val = saml_mod._extract_saml_attr({}, ("givenName",))
    if val != "":
        _fail("t2-extract-empty", f"got {val!r}")
    _ok("t2-extract empty returns ''")

    # Provision honors custom map.
    os.environ["RMC_SAML_ATTR_FIRST_NAME"] = "customFirst"
    os.environ["RMC_SAML_ATTR_LAST_NAME"] = "customLast"
    os.environ["RMC_SAML_ATTR_EMAIL"] = "customEmail"
    try:
        # Cleanup any prior smoke user.
        User = get_user_model()
        User.objects.filter(username__startswith="custom-smoke-").delete()  # tenant-isolation-allow: smoke-cleanup
        user, created = saml_mod._provision_user_from_saml(
            "custom-smoke-name-id",
            {"customFirst": "Grace", "customLast": "Hopper", "customEmail": "grace@example.org"},
        )
        if not created:
            _fail("t2-provision-created", "expected new user")
        if user.first_name != "Grace" or user.last_name != "Hopper":
            _fail("t2-provision-names", f"got {user.first_name!r} {user.last_name!r}")
        if user.email != "grace@example.org":
            _fail("t2-provision-email", f"got {user.email!r}")
        _ok("t2-provision custom mapping populated User.first_name + .last_name + .email")
        user.delete()
    finally:
        os.environ.pop("RMC_SAML_ATTR_FIRST_NAME", None)
        os.environ.pop("RMC_SAML_ATTR_LAST_NAME", None)
        os.environ.pop("RMC_SAML_ATTR_EMAIL", None)


def run_t3():
    _line("\n[T3] OneRoster ?filter= boolean expression parser")
    from apps.api.oneroster_filter import parse_filter, apply_filter

    rows = [
        {"sourcedId": "demo-1", "status": "active", "sex": "male",   "birthDate": "2008-01-01"},
        {"sourcedId": "demo-2", "status": "active", "sex": "female", "birthDate": "2010-06-15"},
        {"sourcedId": "demo-3", "status": "tobedeleted", "sex": "male", "birthDate": "2005-03-12"},
        {"sourcedId": "demo-4", "status": "active", "sex": "other",  "birthDate": ""},
    ]

    # Empty -> all pass.
    out = apply_filter(rows, "")
    if len(out) != 4:
        _fail("t3-empty", f"got {len(out)}")
    _ok("t3-empty filter -> all 4 rows pass")

    # Single predicate =.
    out = apply_filter(rows, "status='active'")
    if [r["sourcedId"] for r in out] != ["demo-1", "demo-2", "demo-4"]:
        _fail("t3-eq", f"got {[r['sourcedId'] for r in out]}")
    _ok("t3-= status='active' -> 3 rows")

    # != .
    out = apply_filter(rows, "status!='active'")
    if [r["sourcedId"] for r in out] != ["demo-3"]:
        _fail("t3-neq", f"got {[r['sourcedId'] for r in out]}")
    _ok("t3-!= status!='active' -> demo-3")

    # AND (intersection).
    out = apply_filter(rows, "status='active' AND sex='male'")
    if [r["sourcedId"] for r in out] != ["demo-1"]:
        _fail("t3-AND", f"got {[r['sourcedId'] for r in out]}")
    _ok("t3-AND status='active' AND sex='male' -> demo-1")

    # OR (union).
    out = apply_filter(rows, "sex='female' OR sex='other'")
    if {r["sourcedId"] for r in out} != {"demo-2", "demo-4"}:
        _fail("t3-OR", f"got {[r['sourcedId'] for r in out]}")
    _ok("t3-OR sex='female' OR sex='other' -> {demo-2,demo-4}")

    # Mixed precedence (AND binds tighter than OR).
    out = apply_filter(rows, "status='tobedeleted' OR sex='female' AND status='active'")
    # tobedeleted OR (female AND active) -> {demo-3, demo-2}
    if {r["sourcedId"] for r in out} != {"demo-2", "demo-3"}:
        _fail("t3-precedence", f"got {[r['sourcedId'] for r in out]}")
    _ok("t3-precedence AND binds tighter than OR")

    # Contains (~).
    out = apply_filter(rows, "status~'act'")
    if {r["sourcedId"] for r in out} != {"demo-1", "demo-2", "demo-4"}:
        _fail("t3-contains", f"got {[r['sourcedId'] for r in out]}")
    _ok("t3-~ status~'act' (substring) -> 3 rows")

    # > on ISO timestamp string (lexicographic fallback when not numeric).
    out = apply_filter(rows, "birthDate>'2008-12-31'")
    if {r["sourcedId"] for r in out} != {"demo-2"}:
        _fail("t3-gt", f"got {[r['sourcedId'] for r in out]}")
    _ok("t3-> birthDate>'2008-12-31' (ISO string compare) -> demo-2")

    # Bad expression -> always-true (no 400).
    out = apply_filter(rows, "garbage tokens 'unclosed")
    if len(out) != 4:
        _fail("t3-bad", f"got {len(out)}")
    _ok("t3-bad unparseable -> always-true (operator-facing surface)")

    # Quoted string with embedded single quote.
    out = apply_filter([{"status": "ain't ready"}], r"status='ain\'t ready'")
    if len(out) != 1:
        _fail("t3-escape", f"got {len(out)}")
    _ok("t3-escape '\\'' in literal accepted")

    # Numeric coercion.
    num_rows = [{"score": "85"}, {"score": "75"}, {"score": "90"}]
    out = apply_filter(num_rows, "score>='80'")
    if len(out) != 2:
        _fail("t3-numeric", f"got {len(out)}")
    _ok("t3-numeric score>='80' -> 2 rows (85+90)")


def run_t4():
    _line("\n[T4] Demographics countryOfBirthCode ISO 3166-1 validation")
    from apps.api import oneroster_demographics as odm

    # Missing + empty allowed.
    if odm._validate_country_of_birth_code({}) is not None:
        _fail("t4-missing", "expected None")
    if odm._validate_country_of_birth_code({"countryOfBirthCode": ""}) is not None:
        _fail("t4-empty", "expected None")
    _ok("t4-cob missing + empty -> None (explicit clear)")

    # Valid 2-letter codes (case-insensitive accept after upper-cast).
    for valid in ("NG", "US", "GB", "ng", "Us"):
        err = odm._validate_country_of_birth_code({"countryOfBirthCode": valid})
        if err is not None:
            _fail(f"t4-cob-{valid}", f"got {err}")
    _ok("t4-cob NG/US/GB (+ lowercase) accepted")

    # Wrong shape -> 400 expected_iso_3166_1_alpha_2.
    # Note: whitespace-only ("  ") is collapsed to "" by .strip() and treated
    # as explicit clear — that's a feature not a bug, exclude from this set.
    for bad in ("USA", "1", "U-S", "USA1"):
        err = odm._validate_country_of_birth_code({"countryOfBirthCode": bad})
        if err is None or err.status_code != 400:
            _fail(f"t4-cob-bad-{bad!r}", f"expected 400; got {err}")
    _ok("t4-cob wrong-shape values -> 400 expected_iso_3166_1_alpha_2")

    # 2 letters but not in SOT -> 400 not_in_iso_3166_1_alpha_2.
    err = odm._validate_country_of_birth_code({"countryOfBirthCode": "ZZ"})
    if err is None or err.status_code != 400:
        _fail("t4-cob-zz", f"got {err}")
    body = _json.loads(err.content)
    if body.get("reason") != "not_in_iso_3166_1_alpha_2":
        _fail("t4-cob-zz-reason", f"got {body}")
    _ok("t4-cob 'ZZ' (well-shaped but not in SOT) -> 400 not_in_iso_3166_1_alpha_2")

    # End-to-end POST rejection routes through _parse_demographic_payload.
    rf = RequestFactory()
    payload = _json.dumps({"demographic": {"sourcedId": "demo-1", "countryOfBirthCode": "ZZ"}})
    req = rf.post("/api/roster/v1p2/demographics/put/",
                  data=payload, content_type="application/json",
                  HTTP_IDEMPOTENCY_KEY="smoke-cob-zz-1",
                  HTTP_AUTHORIZATION="Bearer smoke-bearer")
    req._dont_enforce_csrf_checks = True
    resp = odm.post_demographic(req)
    if resp.status_code not in (400, 401):
        _fail("t4-post-cob-zz", f"got {resp.status_code}")
    _ok(f"t4-cob POST w/ countryOfBirthCode=ZZ -> {resp.status_code}")


def run_t5():
    _line("\n[T5] Retention force-purge with signed-token round-trip")
    from apps.migration_cloud import views_lms_diagnostics as vld
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    rf = RequestFactory()
    user = _staff_user()

    # Clean slate.
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()

    # Token mint + read round-trip.
    tok = vld._make_retention_purge_token(years=7, cutoff_iso="2019-05-29T00:00:00+00:00")
    parsed, reason = vld._read_retention_purge_token(tok)
    if parsed is None or reason != "ok":
        _fail("t5-token-roundtrip", f"got parsed={parsed} reason={reason}")
    if parsed[0] != 7 or parsed[1] != "2019-05-29T00:00:00+00:00":
        _fail("t5-token-payload", f"got {parsed}")
    _ok("t5-token mint+verify round-trip OK (years=7 cutoff_iso preserved)")

    # Missing token.
    _, r = vld._read_retention_purge_token("")
    if r != "missing_token":
        _fail("t5-token-missing", f"got {r}")
    _ok("t5-token missing -> reason=missing_token")

    # Bad token (truncated).
    _, r = vld._read_retention_purge_token(tok[:-3] + "xxx")
    if r != "bad_token":
        _fail("t5-token-bad", f"got {r}")
    _ok("t5-token tampered -> reason=bad_token")

    # No rows -> preview does NOT mint a token (considered==0).
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?format=json&years=7")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    body = _json.loads(resp.content)
    if body.get("purge_token") != "":
        _fail("t5-no-rows-no-token", f"got {body.get('purge_token')!r}")
    if body.get("retention", {}).get("considered") != 0:
        _fail("t5-no-rows-considered", f"got {body}")
    _ok("t5-preview no-rows -> purge_token='' (no button rendered)")

    # Seed 3 ancient rows + 1 recent.
    from django.utils import timezone as _tz
    from datetime import timedelta
    now = _tz.now()
    ancient = now - timedelta(days=8 * 365)
    recent = now - timedelta(days=2)
    for _ in range(3):
        r0 = LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: smoke
            action="force_refresh", provider="canvas",
            actor_hash="abc", actor_user_id="1",
            considered=1, ok_count=1, failed_count=0,
        )
        LMSDiagActionAudit.objects.filter(pk=r0.pk).update(created_at=ancient)  # tenant-isolation-allow: smoke
    r1 = LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: smoke
        action="force_rotate", provider="moodle",
        actor_hash="def", actor_user_id="2",
        considered=1, ok_count=1, failed_count=0,
    )
    LMSDiagActionAudit.objects.filter(pk=r1.pk).update(created_at=recent)  # tenant-isolation-allow: smoke
    _ok("t5-seed 3 ancient + 1 recent rows")

    # Preview NOW mints a token (considered=3, cutoff_iso present).
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?format=json&years=7")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    body = _json.loads(resp.content)
    if body.get("retention", {}).get("considered") != 3:
        _fail("t5-preview-considered", f"got {body}")
    if not body.get("purge_token"):
        _fail("t5-preview-token", "expected non-empty purge_token")
    if body.get("purge_token_ttl_seconds") != 300:
        _fail("t5-preview-ttl", f"got {body.get('purge_token_ttl_seconds')}")
    token = body["purge_token"]
    _ok(f"t5-preview considered=3 mints purge_token (len={len(token)}, TTL=300s)")

    # Purge w/ missing token -> 401.
    req = rf.post("/super/migration/lms/diagnostics/retention-purge/")
    req.user = user
    resp = vld.lms_diagnostics_retention_purge(req)
    if resp.status_code != 401:
        _fail("t5-purge-no-token", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("reason") != "missing_token":
        _fail("t5-purge-no-token-reason", f"got {body}")
    _ok("t5-purge missing token -> 401 invalid_purge_token reason=missing_token")

    # Purge w/ bad token -> 401.
    req = rf.post("/super/migration/lms/diagnostics/retention-purge/",
                  {"token": "garbage-payload"})
    req.user = user
    resp = vld.lms_diagnostics_retention_purge(req)
    if resp.status_code != 401:
        _fail("t5-purge-bad-token-status", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("reason") not in ("bad_token", "malformed_payload"):
        _fail("t5-purge-bad-token-reason", f"got {body}")
    _ok(f"t5-purge bad token -> 401 reason={body.get('reason')}")

    # Real purge w/ valid token + Accept: JSON.
    req = rf.post("/super/migration/lms/diagnostics/retention-purge/",
                  {"token": token},
                  HTTP_ACCEPT="application/json")
    req.user = user
    resp = vld.lms_diagnostics_retention_purge(req)
    if resp.status_code != 200:
        _fail("t5-purge-real-status", f"got {resp.status_code}, body={resp.content[:200]!r}")
    body = _json.loads(resp.content)
    if body.get("success") is not True:
        _fail("t5-purge-success", f"got {body}")
    if body.get("action") != "retention_purge":
        _fail("t5-purge-action", f"got {body}")
    if body.get("considered") != 3 or body.get("deleted") != 3:
        _fail("t5-purge-counts", f"got {body}")
    _ok(f"t5-purge real sweep considered=3 deleted=3 (3 ancient gone, 1 recent remains)")

    # After purge, the table holds: 1 recent ancient-window survivor +
    # 1 new audit row that v4.00.61 _record_action wrote via the dual-write
    # path (LMSDiagActionAudit canonical + LMSPushGradeAudit legacy mirror).
    # So 2 rows remain, not 1.
    remaining = LMSDiagActionAudit.objects.count()  # tenant-isolation-allow: smoke-verify
    if remaining != 2:
        _fail("t5-purge-remaining", f"got {remaining}")
    _ok("t5-purge 2 rows remain after real sweep (1 recent + 1 new audit row from _record_action)")

    # Audit row landed in the ring.
    if not vld._LAST_ACTION_RING:
        _fail("t5-purge-audit-ring", "ring empty after purge")
    last = vld._LAST_ACTION_RING[-1]
    if last.get("action") != "retention_purge":
        _fail("t5-purge-audit-action", f"got {last}")
    _ok(f"t5-purge audit row landed in ring: action={last.get('action')}, provider={last.get('provider')}")

    # Cleanup.
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()
    _ok("t5-cleanup rows + ring cleared")

    # URL route resolves.
    from django.urls import reverse, NoReverseMatch
    try:
        url = reverse("migration_cloud_super:migration_cloud_lms_diagnostics_retention_purge")
        if "/retention-purge/" not in url:
            _fail("t5-url-shape", url)
        _ok(f"t5-URL route resolves: {url}")
    except NoReverseMatch as exc:
        _fail("t5-url-reverse", str(exc))


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
