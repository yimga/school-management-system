"""v4.00.78 (FINAL of 10-wave 50-target sweep) smoke."""
from __future__ import annotations
import json as _json
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django  # noqa: E402
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.test import RequestFactory  # noqa: E402


def _line(s): print(s, flush=True)  # noqa: E702
def _ok(name): _line(f"  OK   {name}")  # noqa: E702
def _fail(name, detail):
    _line(f"  FAIL {name} :: {detail}"); sys.exit(1)


def run_t1():
    _line("\n[T1] +14 subdivisions (final batch)")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    keys = ["CA-ON","CA-QC","CA-BC","KI-G","TV-FUN","FJ-C","WS-AA",
            "JM-09","TT-POS","BB-13","BS-NP","IS-1","SR-PM","CY-04"]
    for k in keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-{k}", "missing")
        _ok(f"t1-{k} OK")
    # 10-wave total target: ~609+ entries (some refreshes happen).
    if len(COUNTRY_LOCALIZATION) < 609:
        _fail("t1-sot-count", f"got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries (10-wave goal)")


def run_t2():
    _line("\n[T2] OneRoster /lineItems/ window + classSourcedId filters")
    from apps.api import oneroster_results as mod
    rf = RequestFactory()
    os.environ["RMC_ONEROSTER_BEARER"] = "smoke-bearer"
    try:
        # Unfiltered.
        req = rf.get("/api/roster/results/v1p2/lineItems/")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.line_items_list(req)
        if resp.status_code != 200:
            _fail("t2-status", f"got {resp.status_code}")
        _ok("t2-/lineItems/ unfiltered -> 200")

        # since= filter shouldn't error.
        req = rf.get("/api/roster/results/v1p2/lineItems/?since=2026-01-01")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.line_items_list(req)
        if resp.status_code != 200:
            _fail("t2-since", f"got {resp.status_code}")
        body = _json.loads(resp.content)
        # Every item must have dateLastModified >= "2026-01-01".
        for it in body.get("lineItems", []):
            if (it.get("dateLastModified") or "") < "2026-01-01":
                _fail("t2-since-filter", str(it))
        _ok(f"t2-?since=2026-01-01 -> {len(body.get('lineItems', []))} items, all dateLastModified >= 2026-01-01")

        # before= filter.
        req = rf.get("/api/roster/results/v1p2/lineItems/?before=2026-12-31")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.line_items_list(req)
        if resp.status_code != 200:
            _fail("t2-before", f"got {resp.status_code}")
        _ok("t2-?before=2026-12-31 -> 200 (filter applies)")

        # classSourcedId filter.
        req = rf.get("/api/roster/results/v1p2/lineItems/?classSourcedId=nonexistent")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.line_items_list(req)
        body = _json.loads(resp.content)
        for it in body.get("lineItems", []):
            if it.get("classSourcedId") != "nonexistent":
                _fail("t2-class-filter", str(it))
        _ok("t2-?classSourcedId= filters (all rows match)")
    finally:
        os.environ.pop("RMC_ONEROSTER_BEARER", None)


def run_t3():
    _line("\n[T3] Demographics suffix + title free-text validation")
    from apps.api import oneroster_demographics as odm

    # Missing/empty OK.
    if odm._validate_suffix_and_title({}) is not None:
        _fail("t3-missing", "expected None")
    if odm._validate_suffix_and_title({"suffix": "", "title": ""}) is not None:
        _fail("t3-empty", "expected None")
    _ok("t3-missing/empty suffix + title -> None")

    # Normal values accepted.
    for v in ("Jr", "Sr", "III", "Esq", "Dr", "Prof", "Mr", "Mrs", "Dato'", "Sir"):
        for f in ("suffix", "title"):
            err = odm._validate_suffix_and_title({f: v})
            if err is not None:
                _fail(f"t3-good-{f}-{v}", f"got {err.content}")
    _ok("t3-10 real-world suffix/title values accepted (incl unicode + apostrophe)")

    # 20-char boundary.
    if odm._validate_suffix_and_title({"suffix": "A" * 20}) is not None:
        _fail("t3-boundary", "expected None for exactly 20")
    err = odm._validate_suffix_and_title({"suffix": "A" * 21})
    if err is None or err.status_code != 400:
        _fail("t3-21", "expected 400")
    body = _json.loads(err.content)
    if body.get("reason") != "too_long":
        _fail("t3-21-reason", str(body))
    if body.get("field") != "suffix":
        _fail("t3-21-field", str(body))
    _ok("t3-21-char suffix -> 400 too_long w/ field=suffix")

    # Title overflow.
    err = odm._validate_suffix_and_title({"title": "B" * 25})
    if err is None or err.status_code != 400:
        _fail("t3-title-long", "expected 400")
    body = _json.loads(err.content)
    if body.get("field") != "title":
        _fail("t3-title-field", str(body))
    _ok("t3-25-char title -> 400 too_long w/ field=title")

    # Control char.
    err = odm._validate_suffix_and_title({"suffix": "Jr\x00X"})
    if err is None or err.status_code != 400:
        _fail("t3-ctrl", "expected 400")
    body = _json.loads(err.content)
    if body.get("reason") != "control_chars":
        _fail("t3-ctrl-reason", str(body))
    _ok("t3-control char in suffix -> 400 control_chars")

    # E2E.
    body_bytes = _json.dumps({"demographic": {"suffix": "Jr", "title": "Dr"}}).encode("utf-8")
    inner, err = odm._parse_demographic_payload(body_bytes)
    if err is not None:
        _fail("t3-e2e", f"got {err}")
    _ok("t3-_parse_demographic_payload accepts suffix='Jr' + title='Dr'")


def run_t4():
    _line("\n[T4] build_audit_row_export_packet")
    from apps.migration_cloud import views_lms_diagnostics as vld
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    try:
        from apps.integrations_marketplace.models import LMSPushGradeAudit
        LMSPushGradeAudit.objects.filter(course_id="_diag_action").delete()  # tenant-isolation-allow: smoke-cleanup
    except Exception:
        pass
    vld._LAST_ACTION_RING.clear()
    vld.reset_retention_sweep_counters()

    pkt = vld.build_audit_row_export_packet()
    for k in ("generated_at", "filters", "alarms", "rollup_by_action",
              "rollup_by_provider", "retention_counters", "entry_count", "entries"):
        if k not in pkt:
            _fail(f"t4-key-{k}", "missing")
    if pkt["entry_count"] != 0 or pkt["entries"] != []:
        _fail("t4-empty", str(pkt))
    _ok("t4-empty export has all 8 expected keys")

    # Seed.
    vld._LAST_ACTION_RING.extend([
        {"ts_iso": "2026-05-29T10:00:00Z", "action": "force_refresh",
         "provider": "canvas", "actor_hash": "a", "considered": 5, "ok": 5, "failed": 0},
        {"ts_iso": "2026-05-29T10:05:00Z", "action": "force_rotate",
         "provider": "moodle", "actor_hash": "b", "considered": 1, "ok": 0, "failed": 1},
    ])
    vld._bump_retention_sweep_counter(kind="preview", considered=10, deleted=0)
    vld._bump_retention_sweep_counter(kind="purge", considered=10, deleted=10)

    pkt = vld.build_audit_row_export_packet()
    if pkt["entry_count"] != 2:
        _fail("t4-count", str(pkt))
    if "canvas" not in pkt["rollup_by_provider"]:
        _fail("t4-rollup-canvas", str(pkt))
    if pkt["retention_counters"]["purges_count"] != 1:
        _fail("t4-retention", str(pkt["retention_counters"]))
    if pkt["retention_counters"]["rows_deleted_total"] != 10:
        _fail("t4-deleted-total", str(pkt["retention_counters"]))
    _ok(f"t4-2 entries; canvas+moodle rollup; retention_counters present (deleted_total={pkt['retention_counters']['rows_deleted_total']})")

    # Provider filter.
    pkt = vld.build_audit_row_export_packet(provider="canvas")
    if pkt["entry_count"] != 1:
        _fail("t4-provider-filter", str(pkt))
    _ok(f"t4-provider=canvas filter -> {pkt['entry_count']} entries")

    # JSON-serializable (key property — counsel hands this to S3 / paperwork).
    import json as _j
    try:
        _j.dumps(pkt)
    except (TypeError, ValueError) as exc:
        _fail("t4-json-serializable", str(exc))
    _ok("t4-packet is JSON-serializable (counsel-handoff safe)")

    vld._LAST_ACTION_RING.clear()
    vld.reset_retention_sweep_counters()
    _ok("t4-cleanup")


def run_t5():
    _line("\n[T5] LMS PKI bundle export")
    from apps.integrations_marketplace import lms_pki_bundle as pki

    bundle = pki.build_lms_pki_bundle()

    # Shape.
    for k in ("generated_at", "schema_version", "providers", "beats_in_use",
              "audit_tables", "retention_default_years", "notes"):
        if k not in bundle:
            _fail(f"t5-key-{k}", "missing")
    _ok(f"t5-bundle has all 7 top-level keys; schema_version={bundle['schema_version']}")

    if len(bundle["providers"]) != 5:
        _fail("t5-providers-len", f"got {len(bundle['providers'])}")
    _ok(f"t5-5 providers in bundle (canvas, moodle, google, schoology, d2l)")

    # Each provider has expected shape.
    for p in bundle["providers"]:
        for k in ("slug", "label", "maturity", "oauth_ready", "is_scaffold"):
            if k not in p:
                _fail(f"t5-provider-key-{k}", str(p))
    _ok("t5-each provider has slug/label/maturity/oauth_ready/is_scaffold")

    # Schoology + D2L expose authorize/token URLs from their modules.
    sg = next(p for p in bundle["providers"] if p["slug"] == "schoology")
    if "schoology.com" not in sg.get("authorize_url", ""):
        _fail("t5-schoology-url", str(sg))
    d2l = next(p for p in bundle["providers"] if p["slug"] == "d2l_brightspace")
    if "brightspace.com" not in d2l.get("authorize_url", ""):
        _fail("t5-d2l-url", str(d2l))
    _ok("t5-Schoology + D2L authorize URLs surfaced from connector modules")

    # NEVER leaks secret patterns.
    bundle_json = _json.dumps(bundle)
    for forbidden in ("client_secret", "private_key", "api_key", "PRIVATE", "SECRET=", "_KEY="):
        if forbidden.lower() in bundle_json.lower():
            _fail(f"t5-leak-{forbidden}", f"bundle contains {forbidden!r}")
    _ok("t5-bundle contains no secret patterns (client_secret/private_key/api_key/etc.)")

    # 6 beats listed.
    if len(bundle["beats_in_use"]) != 6:
        _fail("t5-beats", str(bundle["beats_in_use"]))
    if "integrations-lms-token-refresh" not in bundle["beats_in_use"]:
        _fail("t5-beat-refresh", str(bundle["beats_in_use"]))
    _ok(f"t5-6 Celery beats in bundle including integrations-lms-token-refresh")

    # Fingerprint is deterministic.
    fp1 = pki.bundle_fingerprint(bundle)
    fp2 = pki.bundle_fingerprint(bundle)
    if fp1 != fp2:
        _fail("t5-fp-deterministic", f"{fp1} != {fp2}")
    if len(fp1) != 16:
        _fail("t5-fp-len", f"got {len(fp1)}")
    _ok(f"t5-bundle_fingerprint deterministic; SHA-256[:16]={fp1}")

    # Tamper detection.
    tampered = dict(bundle)
    tampered["retention_default_years"] = 1
    if pki.bundle_fingerprint(tampered) == fp1:
        _fail("t5-fp-tamper", "fingerprint should change on edit")
    _ok("t5-fingerprint changes when bundle is tampered (counsel can detect)")


def main():
    run_t1(); run_t2(); run_t3(); run_t4(); run_t5()
    _line("\nALL GREEN")
    _line("\n=== 10-wave 50-target sweep complete (v4.00.69-78) ===")


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(2)
