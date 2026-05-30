#!/usr/bin/env python3
"""Studio OS 10X Wave 1 smoke — consolidates per-pillar assertions.

Run: ``python scripts/smoke_studio_os_10x_w1.py``

Asserts the 25 sub-targets shipped so far:
  Pillar C (14): 12 subdivisions + 5 compliance actions + 3 sovereignty signals
  Pillar D ( 7): D4 BETWEEN filter, D5 NULL mixed-context, D6-D10 demographic fields
  Pillar B ( 4): B8 MS-Teams, B9 Clever, B10 ClassLink scaffolds + B11 dispatcher

Exits 0 on green; non-zero with a summary on first failure.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

PASS = 0
FAIL: list[str] = []


def _ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  OK   {label}")


def _bad(label: str, detail: str = "") -> None:
    FAIL.append(f"{label}: {detail}" if detail else label)
    print(f"  FAIL {label}: {detail}")


def pillar_c_subdivisions() -> None:
    print("\n[Pillar C] 12 net-new ISO 3166-2 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION as CL
    expected = (
        "MX-CMX", "MX-GUA", "MX-PUE", "MX-CHP", "MX-OAX",
        "BR-AM", "BR-GO", "BR-SC",
        "ZA-FS", "ZA-NC", "NG-FC", "VE-D",
    )
    for k in expected:
        if k in CL and CL[k].get("calendar_system", {}).get("label"):
            _ok(f"subdivision {k} seeded ({CL[k]['calendar_system']['label']})")
        else:
            _bad(f"subdivision {k}", "missing or unlabeled")
    print(f"  total COUNTRY_LOCALIZATION keys: {len(CL)}")


def pillar_c13_compliance_engine_actions() -> None:
    print("\n[Pillar C13] 5 new realtime compliance engine actions")
    from apps.governance.turbo import realtime_compliance_engine as ce
    new_actions = (
        "export_transcript_to_country", "enroll_minor",
        "share_iep_with_vendor", "proctor_with_camera_only",
        "archive_finance_records",
    )
    for a in new_actions:
        if a in ce.SUPPORTED_ACTIONS:
            _ok(f"compliance action registered: {a}")
        else:
            _bad(f"compliance action {a}", "not in SUPPORTED_ACTIONS")
    # Functional smoke: evaluate against AD shard with a realistic payload
    shard_dir = REPO / "docs" / "generated" / "country_governance_matrix"
    sample = next(shard_dir.glob("*.json"), None)
    if sample is None:
        _bad("compliance functional", "no shards")
        return
    iso = sample.stem
    cases = (
        ("enroll_minor", {"subject_age": 12, "parental_consent": False}, "deny"),
        ("share_iep_with_vendor", {"vendor_dpa_signed": False}, "deny"),
        ("archive_finance_records", {"retention_years_requested": 3}, "deny"),
        ("export_transcript_to_country", {"target_country_iso": iso}, "allow"),
    )
    for action, payload, want in cases:
        d = ce.evaluate(action, country_iso=iso, payload=payload)
        if d.get("decision") == want:
            _ok(f"evaluate({action}) -> {want}")
        else:
            _bad(f"evaluate({action})", f"expected {want}, got {d.get('decision')}")


def pillar_c14_sovereignty_signals() -> None:
    print("\n[Pillar C14] 3 new sovereignty trust score signals")
    from apps.governance.turbo import sovereignty_trust_score as sts
    new_signals = (
        "data_residency_attestation_present",
        "subprocessor_list_published",
        "breach_notification_window_hours_le_72",
    )
    for s in new_signals:
        if s in sts.WEIGHTS:
            _ok(f"signal weight registered: {s} = {sts.WEIGHTS[s]}")
        else:
            _bad(f"signal {s}", "not in WEIGHTS")
    if sum(sts.WEIGHTS.values()) == 100:
        _ok("WEIGHTS sum to 100")
    else:
        _bad("WEIGHTS sum", f"expected 100, got {sum(sts.WEIGHTS.values())}")
    shard_dir = REPO / "docs" / "generated" / "country_governance_matrix"
    sample = next(shard_dir.glob("*.json"), None)
    if sample is not None:
        result = sts.compute_score(sample.stem)
        if all(s in result["signals"] for s in new_signals):
            _ok(f"compute_score surfaces 3 new signals (sample {sample.stem}: score={result['score']})")
        else:
            _bad("compute_score signals", "missing new signals in output")


def pillar_d_demographics_fields() -> None:
    print("\n[Pillar D6-D10] 5 new demographics fields with validators")
    from apps.api import oneroster_demographics as od
    new_fields = (
        "militaryConnectedStatus", "parentInArmedForcesStatus",
        "householdGuardianRelationship", "stateAttributeWaiver",
        "accommodationsStatus",
    )
    for f in new_fields:
        if f in od._DEMOGRAPHIC_OVERRIDE_FIELDS:
            _ok(f"override field registered: {f}")
        else:
            _bad(f"override field {f}", "not in _DEMOGRAPHIC_OVERRIDE_FIELDS")

    def parse(d: dict):
        return od._parse_demographic_payload(json.dumps({"demographic": d}).encode())

    happy = (
        ("militaryConnectedStatus", "active_duty"),
        ("militaryConnectedStatus", "prefer_not_to_say"),
        ("parentInArmedForcesStatus", "reserve"),
        ("householdGuardianRelationship", "foster_parent"),
        ("householdGuardianRelationship", "legal_guardian"),
        ("accommodationsStatus", "iep"),
        ("accommodationsStatus", "504_plan"),
        ("stateAttributeWaiver", True),
        ("stateAttributeWaiver", "true"),
        ("stateAttributeWaiver", "false"),
    )
    for field, val in happy:
        _, err = parse({field: val})
        if err is None:
            _ok(f"happy {field}={val!r}")
        else:
            _bad(f"happy {field}={val!r}", "rejected")

    sad = (
        ("militaryConnectedStatus", "civilian"),
        ("parentInArmedForcesStatus", "navy"),
        ("householdGuardianRelationship", "cousin"),
        ("accommodationsStatus", "gifted"),
        ("stateAttributeWaiver", "maybe"),
    )
    for field, val in sad:
        _, err = parse({field: val})
        if err is not None and err.status_code == 400:
            _ok(f"sad {field}={val!r} -> 400")
        else:
            _bad(f"sad {field}={val!r}", "accepted (should 400)")

    for field in new_fields:
        _, err = parse({field: ""})
        if err is None:
            _ok(f"explicit-clear {field}")
        else:
            _bad(f"explicit-clear {field}", "rejected")


def pillar_b11_dispatcher() -> None:
    print("\n[Pillar B11] universal connector dispatcher")
    from apps.integrations_marketplace import lms_connector_dispatcher as disp

    expected = {
        "canvas": "production",
        "moodle": "production",
        "google_classroom": "production",
        "schoology": "production",
        "d2l_brightspace": "production",
        # v4.00.91 W1 Pillar B1-B4: promoted from scaffold to oauth_ready.
        "blackboard": "oauth_ready",
        "powerschool": "oauth_ready",
        "sakai": "oauth_ready",
        "itslearning": "oauth_ready",
        # v4.00.91 W1 Pillar B8-B10: new scaffold-tier connectors.
        "ms_teams_edu": "scaffold",
        "clever": "scaffold",
        "classlink": "scaffold",
    }
    for slug, want in expected.items():
        got = disp.maturity_tier(slug)
        if got == want:
            _ok(f"tier({slug}) = {want}")
        else:
            _bad(f"tier({slug})", f"expected {want}, got {got}")

    try:
        disp.call("canvas", "bad_op_name")
        _bad("call(canvas, bad_op)", "did not raise")
    except disp.UnsupportedLMSOperationError:
        _ok("bad op raises UnsupportedLMSOperationError")

    try:
        disp.call("nonexistent_provider", "push_grade_live")
        _bad("call(bogus, push_grade_live)", "did not raise")
    except disp.UnknownLMSProviderError:
        _ok("bad provider raises UnknownLMSProviderError")

    # B8-B10 are still SCAFFOLD tier — dispatcher short-circuits with scaffold_only.
    result = disp.call("ms_teams_edu", "push_grade_live", target_class="c1", target_user="u1", value=85)
    if isinstance(result, dict) and result.get("status") == "scaffold_only":
        _ok("scaffold-tier call returns scaffold_only deferral (ms_teams_edu)")
    else:
        _bad("scaffold deferral", f"got {result}")
    # B1-B4 are OAUTH_READY — dispatcher calls through to dry_run_scaffold envelope.
    result = disp.call(
        "blackboard", "push_grade_live",
        student_external_id="s1", course_external_id="c1",
        assignment_external_id="a1", score=85, max_score=100,
    )
    if isinstance(result, dict) and result.get("status") == "dry_run_scaffold":
        _ok("oauth_ready-tier call returns dry_run_scaffold envelope (blackboard)")
    else:
        _bad("oauth_ready dry-run", f"got {result}")


def pillar_b8_b10_new_scaffolds() -> None:
    print("\n[Pillar B8-B10] 3 new scaffold connectors: MS Teams Edu / Clever / ClassLink")
    from apps.integrations_marketplace import (
        lms_connector_ms_teams_edu as t,
        lms_connector_clever as c,
        lms_connector_classlink as cl,
    )
    from apps.integrations_marketplace import lms_supported_providers as sot

    for slug, mod in (("ms_teams_edu", t), ("clever", c), ("classlink", cl)):
        if slug in sot.SCAFFOLD_LMS_PROVIDERS:
            _ok(f"{slug} registered in SCAFFOLD_LMS_PROVIDERS")
        else:
            _bad(f"{slug} SOT", "missing from SCAFFOLD_LMS_PROVIDERS")
        # OAuth state roundtrip
        token = mod.mint_oauth_state(client_id="cid-test", return_to="/post-oauth/")
        payload, reason = mod.read_oauth_state(token)
        if reason == "ok" and payload and payload["client_id"] == "cid-test":
            _ok(f"{slug} OAuth state mint/read roundtrip")
        else:
            _bad(f"{slug} OAuth state", f"reason={reason}")
        # bad_token taxonomy
        _, bad_reason = mod.read_oauth_state("garbage-token")
        if bad_reason == "bad_token":
            _ok(f"{slug} bad_token sentinel")
        else:
            _bad(f"{slug} bad_token", f"got reason={bad_reason}")

    # ms_teams_edu IS an LMS — push_grade returns PATCH shape
    r = t.push_grade(student_external_id="s1", course_external_id="c1",
                     assignment_external_id="a1", score=85, max_score=100)
    if r.get("would_send") and r.get("target_method") == "PATCH":
        _ok("ms_teams_edu push_grade returns PATCH would_send envelope")
    else:
        _bad("ms_teams_edu push_grade", str(r))
    # Clever + ClassLink are roster IdPs — push_grade refuses
    if c.push_grade().get("reason") == "provider_does_not_accept_grades":
        _ok("clever push_grade refuses (roster IdP)")
    else:
        _bad("clever push_grade", "should refuse grades")
    if cl.push_grade().get("reason") == "provider_does_not_accept_grades":
        _ok("classlink push_grade refuses (roster IdP)")
    else:
        _bad("classlink push_grade", "should refuse grades")


def pillar_d4_d5_filter_grammar() -> None:
    print("\n[Pillar D4/D5] filter grammar — BETWEEN + NULL mixed-context shorthand")
    from apps.api import oneroster_filter as orf

    # D4 BETWEEN
    pred = orf.parse_filter("score BETWEEN '70' AND '90'")
    cases = [
        ({"score": 80}, True, "mid"),
        ({"score": 70}, True, "lo_incl"),
        ({"score": 90}, True, "hi_incl"),
        ({"score": 69}, False, "below"),
        ({"score": 91}, False, "above"),
        ({"score": "85"}, True, "str_numeric"),
        ({"score": None}, False, "null_excluded"),
        ({"score": ""}, False, "empty_excluded"),
    ]
    for row, want, name in cases:
        got = pred(row)
        if got == want:
            _ok(f"BETWEEN {name}")
        else:
            _bad(f"BETWEEN {name}", f"row={row} expected {want} got {got}")

    # D4 NOT BETWEEN
    pred = orf.parse_filter("NOT score BETWEEN '70' AND '90'")
    for row, want in [({"score": 50}, True), ({"score": 80}, False), ({"score": 100}, True)]:
        if pred(row) == want:
            _ok(f"NOT BETWEEN row={row}")
        else:
            _bad(f"NOT BETWEEN row={row}", f"expected {want}")

    # D5 NULL mixed-context (bareword NULL after = or !=)
    pred = orf.parse_filter("middleName=NULL")
    for row, want in [({"middleName": None}, True), ({"middleName": ""}, True), ({"middleName": "Jane"}, False)]:
        if pred(row) == want:
            _ok(f"=NULL row={row}")
        else:
            _bad(f"=NULL row={row}", f"expected {want}")

    pred = orf.parse_filter("middleName!=NULL")
    for row, want in [({"middleName": None}, False), ({"middleName": ""}, False), ({"middleName": "Jane"}, True)]:
        if pred(row) == want:
            _ok(f"!=NULL row={row}")
        else:
            _bad(f"!=NULL row={row}", f"expected {want}")

    # D5 case-insensitive NULL bareword
    pred = orf.parse_filter("middleName=null")
    if pred({"middleName": None}) and not pred({"middleName": "Jane"}):
        _ok("=null case-insensitive")
    else:
        _bad("=null", "case-insensitivity broken")

    # D5 quoted 'NULL' still treated as literal string (back-compat)
    pred = orf.parse_filter("middleName='NULL'")
    if pred({"middleName": "NULL"}) and not pred({"middleName": None}) and not pred({"middleName": ""}):
        _ok("='NULL' literal string match preserved")
    else:
        _bad("='NULL'", "literal string semantics broken")

    # Backward compat: all existing operators still work
    if orf.parse_filter("a='1'")({"a": "1"}):
        _ok("backward-compat = operator")
    if orf.parse_filter("a IS NULL")({"a": None}):
        _ok("backward-compat IS NULL")
    if orf.parse_filter("a LIKE 'foo%'")({"a": "foobar"}):
        _ok("backward-compat LIKE")
    if orf.parse_filter("a IN('x','y')")({"a": "x"}):
        _ok("backward-compat IN")


def main() -> int:
    print("STUDIO_OS_10X Wave 1 smoke — 25 sub-targets across 4 pillars")
    pillar_c_subdivisions()
    pillar_c13_compliance_engine_actions()
    pillar_c14_sovereignty_signals()
    pillar_d_demographics_fields()
    pillar_d4_d5_filter_grammar()
    pillar_b11_dispatcher()
    pillar_b8_b10_new_scaffolds()
    total = PASS + len(FAIL)
    print(f"\nSUMMARY: {PASS}/{total} pass, {len(FAIL)} fail")
    if FAIL:
        for line in FAIL[:20]:
            print(f"  - {line}")
        return 1
    print("STUDIO_OS_10X_W1_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
