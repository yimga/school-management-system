#!/usr/bin/env python3
"""
GEOS-99 matrix verifier — authoritative repo/live/composite scoring per pillar.

Writes docs/generated/greatest_education_os_matrix.{json,md} on --write.
Exits 0 with GEOS_99_MATRIX_PASS when every pillar repo_pct >= 99 (live reported honestly).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED_JSON = ROOT / "docs" / "generated" / "greatest_education_os_matrix.json"
GENERATED_MD = ROOT / "docs" / "generated" / "greatest_education_os_matrix.md"
REGISTER = ROOT / "docs" / "external_dependencies_register.json"
PILOT = ROOT / "docs" / "generated" / "pilot_readiness_scorecard.json"
REPO_TARGET = 99.0
COMPOSITE_TARGET = 99.0
COMPOSITE_REPO_WEIGHT = 0.6
COMPOSITE_LIVE_WEIGHT = 0.4

# Shared Lane 2 live-axis helpers (entry-id gates + pilot slot 1).
sys.path.insert(0, str(ROOT))
from apps.platform_runtime.geos_lane2_evidence import (  # noqa: E402
    PILLAR_LIVE_ENTRY_IDS,
    live_pct_from_entry_ids,
    pilot_slot_pct,
)


@dataclass
class Check:
    check_id: str
    description: str
    passed: bool
    proof: str = ""


@dataclass
class PillarResult:
    pillar_id: str
    title: str
    checks: list[Check] = field(default_factory=list)

    @property
    def repo_pct(self) -> float:
        if not self.checks:
            return 0.0
        return round(100.0 * sum(1 for c in self.checks if c.passed) / len(self.checks), 1)

    def composite_pct(self, live_pct: float) -> float:
        return round(
            COMPOSITE_REPO_WEIGHT * self.repo_pct + COMPOSITE_LIVE_WEIGHT * live_pct,
            1,
        )


def _run(cmd: list[str], timeout: int = 300) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        tail = out[-500:] if out else ""
        return proc.returncode == 0, tail
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


def _file_ok(rel: str, needle: str = "") -> bool:
    path = ROOT / rel
    if not path.is_file():
        return False
    if not needle:
        return True
    return needle in path.read_text(encoding="utf-8", errors="replace")




def build_pillars() -> list[PillarResult]:
    script = sys.executable
    pillars: list[PillarResult] = []

    def add(pillar_id: str, title: str, checks: list[tuple[str, str, bool, str]]) -> None:
        pr = PillarResult(pillar_id=pillar_id, title=title)
        for cid, desc, ok, proof in checks:
            pr.checks.append(Check(cid, desc, ok, proof))
        pillars.append(pr)

    ok_help, tail_help = _run([script, "scripts/verify_help_center_tiers.py"])
    ok_ai_posture, tail_ai = _run([script, "scripts/verify_render_online_ai_posture.py"])
    ok_ai_engine, tail_engine = _run([script, "scripts/verify_ai_engine_room.py"])
    ok_support, tail_support = _run([script, "scripts/verify_support_pipeline_integrity.py"])
    ok_offboard, tail_off = _run([script, "scripts/verify_tenant_offboarding_surface.py"])
    ok_five, tail_five = _run([script, "scripts/verify_five_pillar_platform_completion.py"])
    ok_mw, tail_mw = _run([script, "scripts/verify_middleware_stack_order.py"])

    add(
        "google",
        "Google — AI / search / help",
        [
            ("help_tiers", "verify_help_center_tiers.py", ok_help, tail_help),
            ("ai_posture", "verify_render_online_ai_posture.py", ok_ai_posture, tail_ai),
            ("ai_engine", "verify_ai_engine_room.py", ok_ai_engine, tail_engine),
            ("support_pipe", "verify_support_pipeline_integrity.py", ok_support, tail_support),
            (
                "workflow_ai_keys",
                "workflow_registry AI context keys",
                _file_ok("apps/platform_runtime/workflow_registry.py", "academics.marks_entry.assist")
                and _file_ok(
                    "apps/platform_runtime/workflow_registry.py",
                    "portal.support_help.assist",
                ),
                "teacher-enter-marks + support-help-hub",
            ),
            (
                "help_governance",
                "help_governance parent/student policy",
                _file_ok("apps/portal/help_governance.py", "ai_assistant_panel_enabled_for_request"),
                "apps/portal/help_governance.py",
            ),
            (
                "ai_governance_doc",
                "docs/AI_GOVERNANCE_CLASSROOM.md",
                _file_ok("docs/AI_GOVERNANCE_CLASSROOM.md"),
                "docs/AI_GOVERNANCE_CLASSROOM.md",
            ),
            (
                "risk_regen",
                "risk explanation regenerate endpoint",
                _file_ok("apps/portal/views_ai_surfaces.py", "student_risk_explanation_regenerate"),
                "portal/views_ai_surfaces.py",
            ),
            (
                "tenant_copilot",
                "tenant AI copilot wired to assist dock",
                _file_ok("templates/portal_base.html", "components/ai_copilot.html"),
                "portal_base.html",
            ),
        ],
    )

    add(
        "linux",
        "Linux — extensions / companion / ecosystem",
        [
            ("five_pillar", "verify_five_pillar_platform_completion.py", ok_five, tail_five),
            (
                "companion_preflight",
                "companion signed-release preflight",
                _file_ok("scripts/preflight_signed_release.py"),
                "scripts/preflight_signed_release.py",
            ),
            (
                "forums_kb",
                "community forums + marketing KB",
                _file_ok("apps/portal/models_forums.py", "CommunityForumTopic")
                and _file_ok("apps/portal/marketing_kb.py", "marketing_kb_search"),
                "batch 1357",
            ),
        ],
    )

    add(
        "aws",
        "AWS — tenancy / middleware / isolation",
        [
            ("middleware", "verify_middleware_stack_order.py", ok_mw, tail_mw),
            (
                "tenant_offboarding",
                "verify_tenant_offboarding_surface.py",
                ok_offboard,
                tail_off,
            ),
            (
                "workflow_bridge",
                "ai_workflow_bridge bind_workflow_context_for_ai",
                _file_ok("apps/platform_runtime/ai_workflow_bridge.py", "bind_workflow_context_for_ai"),
                "ai_workflow_bridge.py",
            ),
        ],
    )

    add(
        "shopify",
        "Shopify — marketplace / payments readiness",
        [
            ("five_pillar_shopify", "five_pillar Shopify rows", ok_five, tail_five),
            (
                "psp_health",
                "payment_gateway_health module",
                _file_ok("apps/finance/payment_gateway_health.py"),
                "apps/finance/payment_gateway_health.py",
            ),
        ],
    )

    add(
        "salesforce",
        "Salesforce — CS / pilots / orchestration",
        [
            ("five_pillar_sf", "five_pillar Salesforce rows", ok_five, tail_five),
            (
                "pilot_scorecard",
                "pilot_readiness_scorecard.json exists",
                PILOT.is_file(),
                str(PILOT),
            ),
            (
                "customersuccess",
                "customersuccess app present",
                (ROOT / "apps/customersuccess").is_dir(),
                "apps/customersuccess",
            ),
        ],
    )

    add(
        "localglobal",
        "LocalGlobal — i18n / RTL / corridor",
        [
            (
                "locale_dir",
                "locale catalogs present",
                (ROOT / "locale/fr").is_dir() and (ROOT / "locale/ar").is_dir(),
                "locale/",
            ),
            (
                "corridor",
                "global_registries app",
                (ROOT / "apps/global_registries").is_dir(),
                "apps/global_registries",
            ),
            (
                "help_locale",
                "KB locale fallback",
                _file_ok("apps/portal/kb_embeddings.py", "filter_kb_queryset_by_locale_with_fallback"),
                "kb_embeddings.py",
            ),
        ],
    )

    add(
        "amazon",
        "Amazon — ops excellence / DR / observability",
        [
            (
                "dr_schedule",
                "verify_dr_drill_schedule.py",
                _file_ok("scripts/verify_dr_drill_schedule.py"),
                "scripts/verify_dr_drill_schedule.py",
            ),
            (
                "sentry_drift",
                "verify_sentry_alert_rule_drift.py",
                _file_ok("scripts/verify_sentry_alert_rule_drift.py"),
                "scripts/verify_sentry_alert_rule_drift.py",
            ),
            (
                "observability",
                "apps/observability metrics bridge",
                _file_ok("apps/observability/metrics.py", "emit_counter"),
                "observability/metrics.py",
            ),
        ],
    )

    add(
        "dailyops",
        "DailyOps — provision / academic loop / email",
        [
            (
                "welcome_email",
                "welcome email on provision",
                _file_ok("apps/schools/welcome_email.py"),
                "apps/schools/welcome_email.py",
            ),
            (
                "teacher_drafts",
                "AI teacher draft endpoints",
                _file_ok("apps/portal/views_ai_draft.py", "_resolve_student"),
                "views_ai_draft.py",
            ),
            (
                "command_bar_ai",
                "command bar help center action",
                _file_ok("apps/siteconfig/command_bar_registry.py", "Help center (AI)"),
                "command_bar_registry.py",
            ),
        ],
    )

    return pillars


def _live_pct_for_pillar(pillar_id: str) -> float:
    if pillar_id in ("salesforce", "amazon", "dailyops"):
        return pilot_slot_pct()
    entry_ids = PILLAR_LIVE_ENTRY_IDS.get(pillar_id)
    if entry_ids:
        live = live_pct_from_entry_ids(entry_ids)
        if pillar_id == "google":
            return min(live, 100.0 if _file_ok("docs/AI_DEPLOYMENT_POSTURE.md") else 50.0)
        return live
    return 0.0


def render_markdown(payload: dict) -> str:
    lines = [
        "# Greatest Education OS matrix",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        f"**Verdict:** {payload['verdict']}",
        "",
        "| Pillar | Repo % | Live % | Composite % |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in payload["pillars"]:
        lines.append(
            f"| {row['title']} | {row['repo_pct']} | {row['live_pct']} | {row['composite_pct']} |"
        )
    lines.extend(
        [
            "",
            "Repo target ≥ 99% per pillar. Composite = 0.6×repo + 0.4×live.",
            "Live axis uses curated register entry ids per pillar + pilot slot 1 gate.",
            "Statuses: `verified_live`, `not_required`, or `repo_complete`/`approved_*` with evidence file.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write generated artifacts.")
    parser.add_argument("--pillar", help="Filter output to one pillar id.")
    parser.add_argument(
        "--require-composite-99",
        action="store_true",
        help="Exit 1 when overall composite_pct < 99 (repo pass still required).",
    )
    args = parser.parse_args()

    pillars = build_pillars()
    if args.pillar:
        pillars = [p for p in pillars if p.pillar_id == args.pillar]
        if not pillars:
            print(f"Unknown pillar: {args.pillar}", file=sys.stderr)
            return 1

    rows = []
    all_repo_pass = True
    for pr in pillars:
        live_pct = _live_pct_for_pillar(pr.pillar_id)
        composite = pr.composite_pct(live_pct)
        if pr.repo_pct < REPO_TARGET:
            all_repo_pass = False
        rows.append(
            {
                "pillar_id": pr.pillar_id,
                "title": pr.title,
                "repo_pct": pr.repo_pct,
                "live_pct": live_pct,
                "composite_pct": composite,
                "checks": [
                    {
                        "check_id": c.check_id,
                        "description": c.description,
                        "passed": c.passed,
                        "proof": c.proof,
                    }
                    for c in pr.checks
                ],
            }
        )

    overall_repo = round(
        sum(r["repo_pct"] for r in rows) / len(rows) if rows else 0.0, 1
    )
    overall_live = round(
        sum(r["live_pct"] for r in rows) / len(rows) if rows else 0.0, 1
    )
    overall_composite = round(
        COMPOSITE_REPO_WEIGHT * overall_repo + COMPOSITE_LIVE_WEIGHT * overall_live,
        1,
    )

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_target_pct": REPO_TARGET,
        "verdict": "GEOS_99_MATRIX_PASS" if all_repo_pass else "GEOS_99_MATRIX_FAIL",
        "overall": {
            "repo_pct": overall_repo,
            "live_pct": overall_live,
            "composite_pct": overall_composite,
        },
        "pillars": rows,
    }

    if args.write:
        GENERATED_JSON.parent.mkdir(parents=True, exist_ok=True)
        GENERATED_JSON.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        GENERATED_MD.write_text(render_markdown(payload), encoding="utf-8")

    for row in rows:
        status = "PASS" if row["repo_pct"] >= REPO_TARGET else "FAIL"
        print(
            f"{row['pillar_id']}: repo={row['repo_pct']}% live={row['live_pct']}% "
            f"composite={row['composite_pct']}% [{status}]"
        )
    print(
        f"overall: repo={overall_repo}% live={overall_live}% composite={overall_composite}% "
        f"-> {payload['verdict']}"
    )

    if not all_repo_pass:
        failed = [r for r in rows if r["repo_pct"] < REPO_TARGET]
        print(f"GEOS matrix: {len(failed)} pillar(s) below repo {REPO_TARGET}%", file=sys.stderr)
        return 1
    if args.require_composite_99 and overall_composite < COMPOSITE_TARGET:
        print(
            f"GEOS matrix: composite {overall_composite}% < {COMPOSITE_TARGET}% "
            f"(live {overall_live}%)",
            file=sys.stderr,
        )
        return 1
    print("verify_greatest_education_os_matrix: GEOS_99_MATRIX_PASS")
    if args.require_composite_99:
        print(
            "verify_greatest_education_os_matrix: GEOS_99_COMPOSITE_PASS "
            f"(composite {overall_composite}%)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
