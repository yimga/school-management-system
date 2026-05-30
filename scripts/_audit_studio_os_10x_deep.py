#!/usr/bin/env python3
"""Studio OS 10X deep audit — 20 gates beyond the standard smoke surface.

Each gate fails LOUDLY with a precise reason. Exit 0 only when every gate passes.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

PASS: int = 0
FAIL: list[str] = []


def gate(label: str):
    def decorator(fn):
        def wrapper(*a, **kw):
            global PASS
            try:
                fn(*a, **kw)
                PASS += 1
                print(f"  OK   [{label}] {fn.__doc__ or fn.__name__}")
            except AssertionError as exc:
                msg = str(exc) or "assertion failed"
                FAIL.append(f"[{label}] {fn.__name__}: {msg}")
                print(f"  FAIL [{label}] {fn.__name__}: {msg}")
            except Exception as exc:  # noqa: BLE001
                FAIL.append(f"[{label}] {fn.__name__}: {type(exc).__name__}: {exc}")
                print(f"  FAIL [{label}] {fn.__name__}: {type(exc).__name__}: {exc}")
        return wrapper
    return decorator


# ============================================================================
# Gate 1 — py_compile every new file (no syntax errors anywhere)
# ============================================================================
NEW_FILES = (
    "apps/integrations_marketplace/views_studio_os_10x_w1.py",
    "apps/integrations_marketplace/lms_connector_dispatcher.py",
    "apps/integrations_marketplace/lms_oauth_ready_helpers.py",
    "apps/integrations_marketplace/lms_connector_ms_teams_edu.py",
    "apps/integrations_marketplace/lms_connector_clever.py",
    "apps/integrations_marketplace/lms_connector_classlink.py",
    "apps/integrations_marketplace/lti_1_3_launch_verifier.py",
    "apps/integrations_marketplace/xapi_caliper_emitter.py",
    "apps/integrations_marketplace/oneroster_outbound_csv.py",
    "apps/integrations_marketplace/studio_os_10x_w2_w5_operator_ui.py",
    "apps/integrations_marketplace/studio_os_10x_w2_w5_marketplace.py",
    "apps/api/oneroster_w1_extensions.py",
    "apps/api/studio_os_10x_w2_w5_oneroster.py",
    "apps/governance/turbo/studio_os_10x_w2_w5_governance.py",
    "scripts/_emit_studio_os_10x_waves_2_5.py",
    "scripts/smoke_studio_os_10x_w1.py",
    "scripts/smoke_studio_os_10x_all_waves.py",
    "scripts/verify_studio_os_10x_completion.py",
)


@gate("G1")
def g1_py_compile():
    """every new module compiles without SyntaxError"""
    import py_compile
    for rel in NEW_FILES:
        path = REPO / rel
        assert path.is_file(), f"missing file {rel}"
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            raise AssertionError(f"py_compile failed for {rel}: {exc.msg}")


# ============================================================================
# Gate 2 — every Studio-OS-10X module importable
# ============================================================================
ALL_NEW_MODULES = (
    "apps.integrations_marketplace.views_studio_os_10x_w1",
    "apps.integrations_marketplace.lms_connector_dispatcher",
    "apps.integrations_marketplace.lms_oauth_ready_helpers",
    "apps.integrations_marketplace.lms_connector_ms_teams_edu",
    "apps.integrations_marketplace.lms_connector_clever",
    "apps.integrations_marketplace.lms_connector_classlink",
    "apps.integrations_marketplace.lti_1_3_launch_verifier",
    "apps.integrations_marketplace.xapi_caliper_emitter",
    "apps.integrations_marketplace.oneroster_outbound_csv",
    "apps.integrations_marketplace.studio_os_10x_w2_w5_operator_ui",
    "apps.integrations_marketplace.studio_os_10x_w2_w5_marketplace",
    "apps.api.oneroster_w1_extensions",
    "apps.api.studio_os_10x_w2_w5_oneroster",
    "apps.governance.turbo.studio_os_10x_w2_w5_governance",
)


@gate("G2")
def g2_imports():
    """all 14 new Studio-OS-10X modules import cleanly"""
    for m in ALL_NEW_MODULES:
        importlib.import_module(m)


# ============================================================================
# Gate 3 — pre-existing Phase 6 turbo modules still importable (no regressions)
# ============================================================================
PHASE6_MODULES = (
    "apps.governance.turbo.realtime_compliance_engine",
    "apps.governance.turbo.sovereignty_trust_score",
    "apps.governance.turbo.time_traveling_matrix",
    "apps.governance.turbo.cross_vertical_kernel",
    "apps.governance.turbo.zero_form_bootstrap",
    "apps.governance.turbo.w3c_verifiable_credentials",
    "apps.governance.turbo.federated_emis_aggregator",
    "apps.governance.turbo.multimodal_terminology",
    "apps.governance.turbo.adversarial_redteam",
    "apps.governance.turbo.agentic_self_healing_matrix",
    "apps.governance.turbo.cross_org_marketplace",
    "apps.governance.turbo.living_competitor_tracker",
    "apps.governance.turbo.formal_verification_tla",
    "apps.governance.turbo.ai_policy_copilot",
    "apps.governance.turbo.regulator_api_federation",
)


@gate("G3")
def g3_phase6_no_regression():
    """all 15 Phase 6 turbo modules still importable + runtime_health() callable"""
    for m in PHASE6_MODULES:
        mod = importlib.import_module(m)
        assert hasattr(mod, "runtime_health"), f"{m} missing runtime_health"
        h = mod.runtime_health()
        assert isinstance(h, dict), f"{m}.runtime_health() returned non-dict"
        assert "healthy" in h, f"{m}.runtime_health() missing 'healthy' key"


# ============================================================================
# Gate 4 — compliance engine: all 10 actions evaluable
# ============================================================================
@gate("G4")
def g4_compliance_engine_actions():
    """all 10 compliance actions return a structured decision dict"""
    from apps.governance.turbo import realtime_compliance_engine as ce
    assert len(ce.SUPPORTED_ACTIONS) == 10, f"got {len(ce.SUPPORTED_ACTIONS)} actions, expected 10"
    shard = next((REPO / "docs" / "generated" / "country_governance_matrix").glob("*.json"), None)
    assert shard is not None, "no matrix shards"
    iso = shard.stem
    for action in ce.SUPPORTED_ACTIONS:
        d = ce.evaluate(action, country_iso=iso, payload={
            "subject_age": 12, "parental_consent": True,
            "target_country_iso": iso, "vendor_dpa_signed": True,
            "vendor_subprocessor_listed": True, "retention_years_requested": 7,
            "express_opt_in": True,
        })
        assert d.get("decision") in ("allow", "deny", "warn"), f"{action}: bad decision {d.get('decision')}"
        assert d.get("action") == action, f"{action}: action label mismatch"
        assert "evaluated_at" in d, f"{action}: missing evaluated_at"


# ============================================================================
# Gate 5 — sovereignty trust score: 10 signals + WEIGHTS sum=100 invariant
# ============================================================================
@gate("G5")
def g5_sovereignty_score():
    """sovereignty WEIGHTS sum to 100 + compute_score surfaces all 10 signals"""
    from apps.governance.turbo import sovereignty_trust_score as sts
    assert sum(sts.WEIGHTS.values()) == 100, f"WEIGHTS sum = {sum(sts.WEIGHTS.values())}"
    expected_signals = (
        "infra_residency", "key_custody", "regulator_api_uptime_90d",
        "counsel_signoff_fresh", "incident_history_90d_clean",
        "regulatory_matrix_complete", "statute_citation_fresh",
        "data_residency_attestation_present", "subprocessor_list_published",
        "breach_notification_window_hours_le_72",
    )
    for s in expected_signals:
        assert s in sts.WEIGHTS, f"missing signal {s}"
    shard = next((REPO / "docs" / "generated" / "country_governance_matrix").glob("*.json"), None)
    r = sts.compute_score(shard.stem)
    for s in expected_signals:
        assert s in r["signals"], f"compute_score missing signal {s}"
    assert 0 <= r["score"] <= 100, f"score out of range: {r['score']}"


# ============================================================================
# Gate 6 — demographics: 25 override fields + 5 new validators wired
# ============================================================================
@gate("G6")
def g6_demographics_validators():
    """5 new demographic validators return 400 on bad vocab + accept explicit-clear"""
    from apps.api import oneroster_demographics as od
    assert len(od._DEMOGRAPHIC_OVERRIDE_FIELDS) == 25, f"override fields = {len(od._DEMOGRAPHIC_OVERRIDE_FIELDS)}"
    new_fields = (
        "militaryConnectedStatus", "parentInArmedForcesStatus",
        "householdGuardianRelationship", "stateAttributeWaiver",
        "accommodationsStatus",
    )
    for f in new_fields:
        assert f in od._DEMOGRAPHIC_OVERRIDE_FIELDS, f"{f} missing"

    def parse(d):
        return od._parse_demographic_payload(json.dumps({"demographic": d}).encode())

    # Sad paths
    for field, bad in [
        ("militaryConnectedStatus", "civilian"),
        ("parentInArmedForcesStatus", "navy"),
        ("householdGuardianRelationship", "cousin"),
        ("accommodationsStatus", "gifted"),
        ("stateAttributeWaiver", "maybe"),
    ]:
        _, err = parse({field: bad})
        assert err is not None and err.status_code == 400, f"{field}={bad!r} should 400"
    # Happy paths
    for field, good in [
        ("militaryConnectedStatus", "active_duty"),
        ("parentInArmedForcesStatus", "reserve"),
        ("householdGuardianRelationship", "legal_guardian"),
        ("accommodationsStatus", "iep"),
        ("stateAttributeWaiver", True),
    ]:
        _, err = parse({field: good})
        assert err is None, f"{field}={good!r} should pass but got {err}"
    # Explicit-clear (empty string) all 5
    for field in new_fields:
        _, err = parse({field: ""})
        assert err is None, f"{field}='' explicit-clear should pass"


# ============================================================================
# Gate 7 — filter grammar: all 15 operators + back-compat
# ============================================================================
@gate("G7")
def g7_filter_grammar_coverage():
    """all operators (=, !=, >, >=, <, <=, ~, IN, IS NULL, LIKE, NOT, AND, OR, parens, BETWEEN, =NULL) green"""
    from apps.api import oneroster_filter as orf

    cases = [
        # Basic comparison
        ("a='1'", {"a": "1"}, True),
        ("a!='1'", {"a": "2"}, True),
        # Numeric ordering (string fallback when non-numeric)
        ("score>'50'", {"score": 75}, True),
        ("score>='75'", {"score": 75}, True),
        ("score<'80'", {"score": 75}, True),
        ("score<='75'", {"score": 75}, True),
        # Substring contains
        ("name~'ohn'", {"name": "John"}, True),
        # IN list
        ("a IN('x','y')", {"a": "y"}, True),
        ("a IN('x','y')", {"a": "z"}, False),
        ("a IN()", {"a": "anything"}, False),
        # IS NULL family
        ("a IS NULL", {"a": None}, True),
        ("a IS NULL", {"a": ""}, True),
        ("a IS NOT NULL", {"a": "v"}, True),
        # LIKE
        ("a LIKE '50%'", {"a": "50abc"}, True),
        ("a LIKE 'foo_bar'", {"a": "fooXbar"}, True),
        # Boolean ops
        ("a='1' AND b='2'", {"a": "1", "b": "2"}, True),
        ("a='1' OR b='2'", {"a": "x", "b": "2"}, True),
        ("NOT a='1'", {"a": "2"}, True),
        ("(a='1' OR a='2') AND b='3'", {"a": "1", "b": "3"}, True),
        # v4.00.91 W1 additions
        ("score BETWEEN '70' AND '90'", {"score": 80}, True),
        ("score BETWEEN '70' AND '90'", {"score": 95}, False),
        ("score BETWEEN '70' AND '90'", {"score": None}, False),
        ("a=NULL", {"a": None}, True),
        ("a=NULL", {"a": ""}, True),
        ("a=NULL", {"a": "v"}, False),
        ("a!=NULL", {"a": "v"}, True),
        ("a!=NULL", {"a": None}, False),
        ("a='NULL'", {"a": "NULL"}, True),
        ("a='NULL'", {"a": None}, False),
    ]
    for expr, row, want in cases:
        got = orf.parse_filter(expr)(row)
        assert got == want, f"{expr!r} on {row!r}: expected {want}, got {got}"


# ============================================================================
# Gate 8 — W1 OneRoster extension endpoints return correct status codes
# ============================================================================
@gate("G8")
def g8_oneroster_w1_extensions():
    """D1-D14 endpoints return expected status codes + ETag round-trip"""
    import django; django.setup()
    from apps.api import oneroster_w1_extensions as x
    from django.test import RequestFactory
    rf = RequestFactory()

    # D14 helpers
    etag = x.compute_etag({"k": "v"})
    assert len(etag) == 12

    # D1 lineItems detail (no Evaluation table → 404)
    resp = x.lineitem_detail(rf.get("/"), "li-bogus")
    assert resp.status_code in (200, 404)

    # D2/D3 bulk POST
    body_ok = json.dumps({"rows": [{"sourcedId": "c1", "classSourcedId": "c1", "userSourcedId": "u1"}]}).encode()
    body_over = json.dumps({"rows": [{}] * 501}).encode()
    body_bad_json = b"not json"
    body_empty = b""
    for view in (x.classes_bulk_post, x.enrollments_bulk_post):
        r = view(rf.post("/", data=body_ok, content_type="application/json"))
        assert r.status_code == 202, f"{view.__name__} happy path got {r.status_code}"
        r = view(rf.post("/", data=body_over, content_type="application/json"))
        assert r.status_code == 400, f"{view.__name__} over-cap got {r.status_code}"
        r = view(rf.post("/", data=body_bad_json, content_type="application/json"))
        assert r.status_code == 400, f"{view.__name__} bad-json got {r.status_code}"
        r = view(rf.post("/", data=body_empty, content_type="application/json"))
        assert r.status_code == 400, f"{view.__name__} empty got {r.status_code}"

    # D11/D12 delta + If-None-Match round-trip
    for view in (x.staff_delta, x.demographics_delta):
        r = view(rf.get("/?modifiedSince=2026-01-01T00:00:00Z"))
        assert r.status_code == 200
        assert "ETag" in r
        etag_val = r["ETag"].strip('"')
        r2 = view(rf.get("/?modifiedSince=2026-01-01T00:00:00Z", HTTP_IF_NONE_MATCH=etag_val))
        assert r2.status_code == 304, f"{view.__name__} expected 304 got {r2.status_code}"

    # D13 fields=
    r = x.classes_with_fields_mask(rf.get("/?fields=title,classCode"))
    data = json.loads(r.content)
    assert data["fields_mask"][0] == "sourcedId", "sourcedId not pinned in mask"
    r = x.enrollments_with_fields_mask(rf.get("/?fields=role,primary"))
    data = json.loads(r.content)
    assert data["fields_mask"][0] == "sourcedId"


# ============================================================================
# Gate 9 — Pillar A: all 14 operator UI views return 200 + structured payload
# ============================================================================
@gate("G9")
def g9_pillar_a_views():
    """all 14 W1 operator UI views render 200 + emit surface envelope"""
    from apps.integrations_marketplace import views_studio_os_10x_w1 as s10x
    from django.test import RequestFactory
    assert len(s10x.STUDIO_OS_10X_W1_VIEWS) == 14
    class FakeStaff:
        is_authenticated = True
        is_staff = True
        is_active = True
        is_superuser = False
    rf = RequestFactory()
    req = rf.get("/operator/studio-os-10x/")
    req.user = FakeStaff()
    for v in s10x.STUDIO_OS_10X_W1_VIEWS:
        r = v(req)
        assert r.status_code == 200, f"{v.__name__} -> {r.status_code}"
        body = json.loads(r.content)
        assert "surface" in body, f"{v.__name__} missing surface key"
        assert "generated_at" in body, f"{v.__name__} missing generated_at"


# ============================================================================
# Gate 10 — Pillar B: OAUTH_READY contract on all 4 promoted scaffolds
# ============================================================================
@gate("G10")
def g10_oauth_ready_promotions():
    """B1-B4 each expose exchange + refresh + push_grade_live and return dry_run_scaffold"""
    for name in ("blackboard", "powerschool", "sakai", "itslearning"):
        mod = importlib.import_module(f"apps.integrations_marketplace.lms_connector_{name}")
        assert hasattr(mod, "exchange_authorization_code_for_token"), f"{name}: missing exchange"
        assert hasattr(mod, "refresh_access_token"), f"{name}: missing refresh"
        assert hasattr(mod, "push_grade_live"), f"{name}: missing push_grade_live"
        # Dry-run envelopes (no env flags set)
        r = mod.exchange_authorization_code_for_token(state="s1", code="c1", client_id="cid")
        assert r["status"] == "dry_run_scaffold", f"{name} exchange: {r}"
        r = mod.refresh_access_token(refresh_token="rt1", client_id="cid")
        assert r["status"] == "dry_run_scaffold", f"{name} refresh: {r}"
        r = mod.push_grade_live(
            student_external_id="s1", course_external_id="c1",
            assignment_external_id="a1", score=85, max_score=100,
        )
        assert r["status"] == "dry_run_scaffold", f"{name} push_grade_live: {r}"
        # Bad-request taxonomy
        r = mod.exchange_authorization_code_for_token(state="", code="")
        assert r["status"] == "bad_request", f"{name} empty-code should bad_request"


# ============================================================================
# Gate 11 — Pillar B: 3 new scaffold connectors symmetric mint/read
# ============================================================================
@gate("G11")
def g11_b8_b10_new_scaffolds():
    """MS Teams Edu / Clever / ClassLink: mint->read roundtrip + push_grade contract"""
    from apps.integrations_marketplace import lms_supported_providers as sot
    for slug in ("ms_teams_edu", "clever", "classlink"):
        assert slug in sot.SCAFFOLD_LMS_PROVIDERS, f"{slug} not in SCAFFOLD set"
        mod = importlib.import_module(f"apps.integrations_marketplace.lms_connector_{slug}")
        tok = mod.mint_oauth_state(client_id="cid", return_to="/return/")
        payload, reason = mod.read_oauth_state(tok)
        assert reason == "ok", f"{slug}: roundtrip reason={reason}"
        assert payload["client_id"] == "cid"
        _, bad = mod.read_oauth_state("garbage")
        assert bad == "bad_token", f"{slug}: bad_token sentinel"
        _, missing = mod.read_oauth_state("")
        assert missing == "missing_token", f"{slug}: missing_token sentinel"


# ============================================================================
# Gate 12 — universal dispatcher: tier resolution + error taxonomy
# ============================================================================
@gate("G12")
def g12_dispatcher_contract():
    """dispatcher resolves all 11 registered providers + raises taxonomy correctly"""
    from apps.integrations_marketplace import lms_connector_dispatcher as disp
    expected = {
        "canvas": "production", "moodle": "production", "google_classroom": "production",
        "google": "production", "schoology": "production", "d2l_brightspace": "production",
        "blackboard": "oauth_ready", "powerschool": "oauth_ready",
        "sakai": "oauth_ready", "itslearning": "oauth_ready",
        "ms_teams_edu": "scaffold", "clever": "scaffold", "classlink": "scaffold",
    }
    for slug, want in expected.items():
        got = disp.maturity_tier(slug)
        assert got == want, f"tier({slug}): expected {want} got {got}"
    try:
        disp.call("nonexistent", "push_grade_live")
        raise AssertionError("bad provider didn't raise")
    except disp.UnknownLMSProviderError:
        pass
    try:
        disp.call("canvas", "totally_bogus_op")
        raise AssertionError("bad op didn't raise")
    except disp.UnsupportedLMSOperationError:
        pass


# ============================================================================
# Gate 13 — LTI 1.3 verifier verdict taxonomy
# ============================================================================
@gate("G13")
def g13_lti_verifier_verdicts():
    """LTI verifier returns ok/replay/iss_mismatch/expired/aud_mismatch"""
    import jwt, time
    from apps.integrations_marketplace import lti_1_3_launch_verifier as lti
    base = {
        "iss": "https://platform.example", "aud": "rmc-001",
        "exp": int(time.time()) + 3600, "iat": int(time.time()),
        "sub": "u-1",
        "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiResourceLinkRequest",
        "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
        "https://purl.imsglobal.org/spec/lti/claim/deployment_id": "d-1",
        "https://purl.imsglobal.org/spec/lti/claim/resource_link": {"id": "rl-1"},
    }
    # OK
    t = jwt.encode({**base, "nonce": "n1"}, "k", algorithm="HS256")
    r = lti.verify_launch(id_token=t, expected_iss=base["iss"], expected_aud=base["aud"])
    assert r["verdict"] == "ok", f"ok path: {r}"
    # Replay
    r2 = lti.verify_launch(id_token=t, expected_iss=base["iss"], expected_aud=base["aud"])
    assert r2["verdict"] == "replay", f"replay path: {r2}"
    # iss mismatch
    t = jwt.encode({**base, "iss": "https://attacker", "nonce": "n2"}, "k", algorithm="HS256")
    r = lti.verify_launch(id_token=t, expected_iss=base["iss"], expected_aud=base["aud"])
    assert r["verdict"] == "iss_mismatch"
    # aud mismatch
    t = jwt.encode({**base, "aud": "different-aud", "nonce": "n3"}, "k", algorithm="HS256")
    r = lti.verify_launch(id_token=t, expected_iss=base["iss"], expected_aud=base["aud"])
    assert r["verdict"] == "aud_mismatch"
    # Expired
    t = jwt.encode({**base, "exp": int(time.time()) - 100, "nonce": "n4"}, "k", algorithm="HS256")
    r = lti.verify_launch(id_token=t, expected_iss=base["iss"], expected_aud=base["aud"])
    assert r["verdict"] == "expired"
    # Empty token
    r = lti.verify_launch(id_token="", expected_iss=base["iss"], expected_aud=base["aud"])
    assert r["verdict"] == "bad_jwt"


# ============================================================================
# Gate 14 — xAPI + Caliper emitter contract
# ============================================================================
@gate("G14")
def g14_xapi_caliper():
    """xAPI + Caliper emitters return dry_run_scaffold + reject bad inputs"""
    from apps.integrations_marketplace import xapi_caliper_emitter as xc
    # xAPI happy
    r = xc.emit_xapi_statement(actor_mbox="mailto:s@e.com", verb_id="http://x", verb_display_en="experienced", object_id="http://y")
    assert r["status"] == "dry_run_scaffold" and r["format"] == "xapi"
    assert r["would_send"]["actor"]["mbox"] == "mailto:s@e.com"
    # xAPI sad — bad mbox
    r = xc.emit_xapi_statement(actor_mbox="s@e.com", verb_id="v", verb_display_en="d", object_id="o")
    assert r["status"] == "bad_request"
    # Caliper happy
    r = xc.emit_caliper_event(actor_id="https://x/u/1", action="Viewed", object_id="https://x/a/1")
    assert r["status"] == "dry_run_scaffold" and r["format"] == "caliper"
    # Caliper sad
    r = xc.emit_caliper_event(actor_id="", action="Viewed", object_id="oid")
    assert r["status"] == "bad_request"


# ============================================================================
# Gate 15 — OneRoster CSV bundle: 5 files + manifest version
# ============================================================================
@gate("G15")
def g15_oneroster_csv_bundle():
    """OneRoster v1.2 CSV Schema 4 bundle has manifest + 4 resource files + version"""
    import io, zipfile
    from apps.integrations_marketplace import oneroster_outbound_csv as orc
    blob = orc.build_oneroster_csv_zip(
        orgs=[{"sourcedId": "o1", "name": "Acme"}],
        users=[{"sourcedId": "u1", "givenName": "Jane"}],
        classes=[{"sourcedId": "c1", "title": "Math"}],
        enrollments=[{"sourcedId": "e1", "classSourcedId": "c1", "userSourcedId": "u1"}],
    )
    zf = zipfile.ZipFile(io.BytesIO(blob))
    names = sorted(zf.namelist())
    assert names == ["classes.csv", "enrollments.csv", "manifest.csv", "orgs.csv", "users.csv"], f"names={names}"
    manifest = zf.read("manifest.csv").decode()
    assert "oneroster.version,1.2" in manifest
    assert "manifest.version,1.0" in manifest
    # Push helper returns dry-run
    r = orc.push_oneroster_csv_bundle()
    assert r["status"] == "dry_run_scaffold"
    assert r["summary"]["file_count"] == 5


# ============================================================================
# Gate 16 — W2-5 surface contracts: all 224 callable
# ============================================================================
@gate("G16")
def g16_w2_w5_surfaces_all_callable():
    """every W2-W5 surface callable returns a valid envelope"""
    from apps.integrations_marketplace import studio_os_10x_w2_w5_operator_ui as op
    from apps.integrations_marketplace import studio_os_10x_w2_w5_marketplace as mp
    from apps.api import studio_os_10x_w2_w5_oneroster as orx
    from apps.governance.turbo import studio_os_10x_w2_w5_governance as govx
    total = 0
    for mod, name in ((op, "op"), (mp, "mp"), (orx, "or"), (govx, "gov")):
        rows = mod.list_surfaces()
        assert len(rows) == 56, f"{name}: {len(rows)} surfaces"
        # call EVERY surface
        for row in rows:
            env = mod.call_surface(row["slug"])
            assert env["surface"] == row["slug"], f"{name}/{row['slug']}: surface mismatch"
            assert env["status"] == "scaffold_registered", f"{name}/{row['slug']}: status mismatch"
            assert env["wave"] == row["wave"], f"{name}/{row['slug']}: wave mismatch"
            assert env["pillar"] == mod.PILLAR, f"{name}/{row['slug']}: pillar mismatch"
            assert "generated_at" in env
            total += 1
    assert total == 224, f"total surfaces called: {total}"


# ============================================================================
# Gate 17 — Subdivisions: all 60 new ISO-3166-2 keys present
# ============================================================================
@gate("G17")
def g17_subdivisions_present():
    """all 60 new subdivisions (W1 12 + W2-5 48) present in COUNTRY_LOCALIZATION"""
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION as CL
    all_new = [
        # W1 (12)
        "MX-CMX","MX-GUA","MX-PUE","MX-CHP","MX-OAX",
        "BR-AM","BR-GO","BR-SC",
        "ZA-FS","ZA-NC","NG-FC","VE-D",
        # W2 (12)
        "MX-CHH","MX-TAB","MX-VER","MX-MOR","MX-QUE","MX-COA",
        "MX-DGO","MX-AGU","MX-NAY","MX-COL","MX-CAM","MX-YUC",
        # W3 (12)
        "MX-BCS","MX-ZAC","MX-TLA",
        "BR-MA","BR-PI","BR-AL","BR-SE","BR-PB","BR-RN","BR-AP","BR-RR","BR-RO",
        # W4 (12)
        "BR-AC","BR-TO","BR-MT","BR-MS",
        "ZA-LP","ZA-NW",
        "NG-BY","NG-RV","NG-KW","NG-OS","NG-EK","NG-PL",
        # W5 (12)
        "KR-32","KR-33","KR-34","KR-35","KR-36","KR-37","KR-38","KR-39","KR-40",
        "JP-36","JP-41","JP-42",
    ]
    missing = [k for k in all_new if k not in CL]
    assert not missing, f"missing: {missing}"
    for k in all_new:
        row = CL[k]
        assert "calendar_system" in row, f"{k}: missing calendar_system"
        assert "school_types" in row, f"{k}: missing school_types"
        assert "education_levels" in row, f"{k}: missing education_levels"
        assert "terminology" in row, f"{k}: missing terminology"


# ============================================================================
# Gate 18 — Register schema integrity
# ============================================================================
@gate("G18")
def g18_register_schema_integrity():
    """register schema valid + all items have required fields"""
    path = REPO / "docs" / "generated" / "studio_os_10x_completion_register.json"
    register = json.loads(path.read_text(encoding="utf-8"))
    assert register["schema_version"] == "studio_os_10x.v1"
    assert register["status_counts"]["DONE"] == 23
    assert register["status_counts"]["NOT_DONE"] == 0
    assert register["status_counts"]["IN_PROGRESS"] == 0
    items = register["items"]
    assert len(items) == 23
    seen_ids = set()
    for item in items:
        for k in ("id", "wave", "pillar", "title", "status"):
            assert k in item, f"item missing key {k}: {item}"
        assert item["id"] not in seen_ids, f"duplicate id {item['id']}"
        seen_ids.add(item["id"])
        assert item["status"] in ("DONE", "EXTERNAL_BLOCKED"), f"{item['id']}: status {item['status']}"
    # Required batch IDs present
    required = {"studio-10x-umbrella", "w5-cross-register", "w5-cross-ci-gate"}
    for w in (1, 2, 3, 4, 5):
        for p in ("A-operator-ui", "B-integrations-marketplace", "C-governance-kernel", "D-oneroster-demographics"):
            required.add(f"w{w}-{p}")
    assert required == seen_ids, f"register IDs mismatch: missing={required - seen_ids} extra={seen_ids - required}"


# ============================================================================
# Gate 19 — Secret hygiene: no leaked tokens in any new module
# ============================================================================
@gate("G19")
def g19_secret_hygiene():
    """no actual secrets (access_token=<value>, etc.) literal-logged in new code"""
    forbidden_patterns = (
        re.compile(r"logger\.\w+\([^)]*access_token=[^)]*\b[A-Za-z0-9]{20,}", re.IGNORECASE),
        re.compile(r"print\([^)]*refresh_token=[^)]*\b[A-Za-z0-9]{20,}", re.IGNORECASE),
        re.compile(r"logger\.\w+\([^)]*client_secret=[^)]*\b[A-Za-z0-9]{20,}", re.IGNORECASE),
    )
    for rel in NEW_FILES:
        text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        for pat in forbidden_patterns:
            assert not pat.search(text), f"{rel} contains secret-leaking log statement"


# ============================================================================
# Gate 20 — CI workflow YAML well-formed + references correct scripts
# ============================================================================
@gate("G20")
def g20_ci_workflow_gate():
    """CI yaml has studio-os-10x-completion job with --strict gate"""
    import yaml
    path = REPO / ".github" / "workflows" / "architectural-boundaries.yml"
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    jobs = parsed.get("jobs", {})
    job = jobs.get("studio-os-10x-completion")
    assert job is not None, "studio-os-10x-completion job missing"
    assert job.get("runs-on") == "ubuntu-latest"
    steps = job.get("steps", [])
    run_text = "\n".join(s.get("run", "") for s in steps if s.get("run"))
    assert "smoke_studio_os_10x_w1.py" in run_text, "W1 smoke not in CI steps"
    assert "smoke_studio_os_10x_all_waves.py" in run_text, "all-waves smoke not in CI steps"
    assert "verify_studio_os_10x_completion.py --strict" in run_text, "--strict flag missing"


# ============================================================================
# Gate runner
# ============================================================================
def main() -> int:
    print("STUDIO_OS_10X DEEP AUDIT — 20 gates beyond standard smoke surface\n")
    g1_py_compile()
    g2_imports()
    g3_phase6_no_regression()
    g4_compliance_engine_actions()
    g5_sovereignty_score()
    g6_demographics_validators()
    g7_filter_grammar_coverage()
    g8_oneroster_w1_extensions()
    g9_pillar_a_views()
    g10_oauth_ready_promotions()
    g11_b8_b10_new_scaffolds()
    g12_dispatcher_contract()
    g13_lti_verifier_verdicts()
    g14_xapi_caliper()
    g15_oneroster_csv_bundle()
    g16_w2_w5_surfaces_all_callable()
    g17_subdivisions_present()
    g18_register_schema_integrity()
    g19_secret_hygiene()
    g20_ci_workflow_gate()
    total = PASS + len(FAIL)
    print(f"\nSUMMARY: {PASS}/{total} gates pass, {len(FAIL)} fail")
    if FAIL:
        for line in FAIL[:20]:
            print(f"  - {line}")
        return 1
    print("STUDIO_OS_10X_DEEP_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
