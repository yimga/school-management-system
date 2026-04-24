#!/usr/bin/env python3
"""
Repair canonical RunMyCampus markdown when accidental mega-lines break the ledger.

Default: docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md (strip long lines,
re-insert §11.4 forward-queue rows when missing, normalize queue headers).

Use --execution-log for docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md (strip only;
drops lines over the length threshold — typically mojibake paste corruption).

Does not modify application code. Intended for agent/operator recovery only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "docs" / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
DEFAULT_EXECUTION_LOG = ROOT / "docs" / "RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md"

# Inserted after "At a glance" / release buckets, before existing newest batch rows (804…).
# Wording condensed from RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md batches 805–812 plus 813 (this repair).
_INSERT_AFTER_SUBSTR = "- **C (Non-migration beats)**: operator visibility + database connectivity + automation failure trend beats"

_INSERT_BLOCKS = r"""
**§11.4 forward queue - batch 846 (Phase II.3 / Phase B SiteSettings — evals grade approval workflow tests use `apply_feature_control_state`, 2026-04-08):** **DONE** - **`apps/evals/tests/test_grade_approval_workflow.py`**: **`GradeApprovalWorkflowTestCase`**. **`DJANGO_TEST_DB_FILE=.django_test_dbs/evals_grade_approval_846.sqlite3 python manage.py test apps.evals.tests.test_grade_approval_workflow --noinput --keepdb -v 2`** — **4 OK**. **`python scripts/lint_tenant_settings.py --check-get-solo-only --check-school-settings-features --check-sitesettings-orm-in-tenant-apps`** — **PASS**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-845** slice — evals tests only (**no** Raw SQL / WOPI). **Next window:** **`847+`** — coordinate.

**§11.4 forward queue - batch 844 (Phase II.3 / Phase B SiteSettings — accounts `GuardianFinanceOptInTests` use `apply_feature_control_state`, 2026-04-08):** **DONE** - **`apps/accounts/tests/test_permissions_hierarchy.py`**: **`GuardianFinanceOptInTests`**. **`DJANGO_TEST_DB_FILE=.django_test_dbs/permissions_hierarchy_832.sqlite3 python manage.py test apps.accounts.tests.test_permissions_hierarchy.GuardianFinanceOptInTests --noinput --keepdb -v 2`** — **2 OK**. **`python scripts/lint_tenant_settings.py --check-get-solo-only --check-school-settings-features --check-sitesettings-orm-in-tenant-apps`** — **PASS**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-843** slice — accounts tests only (**no** Raw SQL / WOPI). **Next window:** **`845+`** — coordinate.

**§11.4 forward queue - batch 831 (Phase II.2 Raw SQL — allowlist manifest repo-bar lock, 2026-04-08):** **DONE** - **`apps/platform_runtime/tests/test_raw_sql_allowlist_manifest.py`**: **`RawSqlAllowlistManifestTests.test_allowlist_json_files_match_repo_bar`**. **`python manage.py test apps.platform_runtime.tests.test_raw_sql_allowlist_manifest --noinput -v 2`** — **1 OK**. **`python scripts/lint_raw_sql_usage.py`** — **PASS**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-830** slice — manifest parity only (**no** SiteSettings / WOPI). **Next window:** **`832+`** — coordinate.

**§11.4 forward queue - batch 827 (Release readiness bucket A — `ai_quality_scorecard` `--days` clamp + falsy-zero fix, 2026-04-08):** **DONE** - **`apps/siteconfig/management/commands/ai_quality_scorecard.py`**: **`int(options.get("days", 7))`** replaces **`int(options.get("days") or 7)`** so **`--days 0`** clamps to **1**. **`apps/siteconfig/tests/test_ai_quality_scorecard.py`**: **`test_ai_quality_scorecard_days_clamped_to_1_to_30`**. **`DJANGO_TEST_DB_FILE=.django_test_dbs/ai_quality_scorecard_819.sqlite3 python manage.py test apps.siteconfig.tests.test_ai_quality_scorecard.AIQualityScorecardTests.test_ai_quality_scorecard_days_clamped_to_1_to_30 --noinput --keepdb -v 2`** — **1 OK**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-826** slice — siteconfig scorecard command + tests (**no** WOPI). **Next window:** **`828+`** — coordinate.

**§11.4 forward queue - batch 817 (Release readiness bucket C — `check_db_liveness` unhealthy error payload capped at 200 chars, 2026-04-08):** **DONE** - **`apps/observability/tests/test_db_liveness.py`**: **`DbLivenessErrorShapeTests.test_unhealthy_truncates_error_at_200_chars`** — **`SimpleTestCase`** (no DB). **`python manage.py test apps.observability.tests.test_db_liveness.DbLivenessErrorShapeTests --noinput -v 2`** — **1 OK**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-816** slice — observability tests only (**no** Raw SQL / SiteSettings / WOPI). **Next window:** **`818+`** — coordinate.

**§11.4 forward queue - batch 816 (Release readiness bucket B — migration playbook preflight override strips invisible characters, 2026-04-08):** **DONE** - **`apps/automation/playbook_override_reason.py`**: **`normalize_playbook_override_reason()`** removes zero-width / BOM characters so invisible-only strings cannot bypass the low-confidence preflight gate; **`apps/automation/playbook_executor.py`** uses it. **`apps/automation/tests/test_playbook_override_reason.py`**: unit tests (**no DB**). **`python manage.py test apps.automation.tests.test_playbook_override_reason --noinput -v 2`** — **5 OK**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-815** slice — automation preflight only (**no** Raw SQL / SiteSettings / WOPI). **Next window:** **`817 closed (db_liveness error truncation contract)`**, then **`818+`** — coordinate.

**§11.4 forward queue - batch 815 (Release readiness bucket A — `/api/ai/feedback` tier guard + invalid JSON + JSONDecodeError handler order, 2026-04-08):** **DONE** - **`apps/portal/views_ai_gateway.py`**: **`api_ai_feedback`** — **`except json.JSONDecodeError` before `except ValueError`**. **`apps/portal/tests/test_ai_feedback.py`**: **`test_feedback_400_when_tier_missing`**, **`test_feedback_400_when_invalid_json`**. **`python manage.py test apps.portal.tests.test_ai_feedback --noinput -v 2`** — **7 OK**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-814** slice — portal gateway + tests only (**no** Raw SQL / SiteSettings / WOPI). **Next window:** **`816 closed (playbook override invisible-char strip)`**, then **`817+`** — coordinate.

**§11.4 forward queue - batch 814 (Autonomous execution log — strip mega-line mojibake corruption + canonical line-length gate, 2026-04-08):** **DONE** - **`docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md`**: removed **10** lines **>50000** characters (pathological repeated `## Slice` mojibake). **`scripts/verify_doc_plan_density_discipline.py`**: **`_MAX_CANONICAL_LINE_CHARS` (50000)** on SOT and autonomous log. **`scripts/repair_runmycampus_sot.py`**: **`--execution-log`** strips mega-lines only. **`python scripts/repair_runmycampus_sot.py --execution-log`**; **`python scripts/verify_doc_plan_density_discipline.py` PASS**. **Post-813** slice — docs + verifier only (**no** application code). **Next window:** **`815 closed (AI feedback tier + invalid JSON contracts)`**, then **`816+`** — coordinate.

**§11.4 forward queue - batch 813 (SOT integrity — strip mega-lines + §11.4 prefix normalization, 2026-04-08):** **DONE** - **`docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`**: removed **6** corrupted lines **>50000** characters (**~18 MB** pathological expansion); normalized legacy rows where the Markdown bold prefix was missing the section sign before `11.4 forward queue`; header repair for mojibake-prefixed queue rows. **`python scripts/repair_runmycampus_sot.py`**; **`python scripts/verify_doc_plan_density_discipline.py` PASS**. **Post-812** slice — documentation file only (**no** application code). **Next window:** **`814 closed (autonomous log mega-line strip + line-length gate)`**, then **`815+`** — coordinate.

**§11.4 forward queue - batch 812 (Release readiness bucket C — `automation_failure_trend_signal` tolerates non-numeric `AUTOMATION_FAILURE_TREND_*` env, 2026-04-08):** **DONE** - **`apps/platform_runtime/tasks.py`**: **`_parse_bounded_int_env()`** for **`AUTOMATION_FAILURE_TREND_LOOKBACK_HOURS`** (default **24**, bounds **1–168**) and **`AUTOMATION_FAILURE_TREND_MAX_FAILURES`** (default **10**, bounds **0–1000**); non-numeric operator values fall back to defaults (no Celery **`ValueError`**). **`apps/platform_runtime/tests/test_health_heartbeat_tasks.py`**: **`test_failure_trend_invalid_env_integers_use_defaults`**. **`python manage.py test apps.platform_runtime.tests.test_health_heartbeat_tasks --noinput -v 2`** — **9 OK**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-811** slice — bucket C operator beat robustness only (**no** Raw SQL / SiteSettings / WOPI). **Next window:** **`813 closed (SOT mega-line repair)`**, then **`814+`** — coordinate.

**§11.4 forward queue - batch 811 (Release readiness bucket A — `ai_quality_scorecard` CLI window/filter contract tests, 2026-04-08):** **DONE** - **`apps/siteconfig/tests/test_ai_quality_scorecard.py`**: relative metric date for the base scorecard assertion; **`test_ai_quality_scorecard_task_type_filter_is_case_normalized`**; **`test_ai_quality_scorecard_warns_when_window_has_no_metrics`**. **`DJANGO_TEST_DB_FILE=.django_test_dbs/ai_quality_scorecard_811.sqlite3 python manage.py test apps.siteconfig.tests.test_ai_quality_scorecard --noinput --keepdb -v 2`** — **4 OK**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-810** slice — release-readiness bucket A CLI tests only (**no** portal feedback / SCIM / Raw SQL overlap). **Next window:** **`812 closed (automation failure trend env parsing)`**, then **`813+`** — coordinate.

**§11.4 forward queue - batch 810 (Release readiness bucket C — automation failure trend beat under-threshold success path, 2026-04-08):** **DONE** - **`apps/platform_runtime/tests/test_health_heartbeat_tasks.py`**: **`test_failure_trend_under_threshold_succeeds`**. **`python manage.py test apps.platform_runtime.tests.test_health_heartbeat_tasks.HealthHeartbeatTaskTests.test_failure_trend_under_threshold_succeeds --noinput -v 2`** (named target). **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-809** slice — **`platform_runtime`** tests only (**no** Raw SQL / **`apps/schools`** overlap). **Next window:** **`811 closed (AI quality scorecard CLI contract tests)`**, then **`812+`** — coordinate.

**§11.4 forward queue - batch 809 (PATH Phase II.1 — SCIM optional `X-SCIM-Signature` HMAC body integrity, 2026-04-08):** **DONE** - **`apps/api/scim_views.py`**: **`_scim_signature_check()`** — when **`X-SCIM-Signature`** is **`sha256=<hex>`**, **`hex`** must equal **HMAC-SHA256**(shared bearer secret, **`request.body`**); absent header unchanged. **`apps/api/tests/test_scim_views.py`**: four HMAC tests. **`python manage.py test apps.api.tests.test_scim_views --noinput -v 2`** — **25 OK** (isolated DB via **`DJANGO_TEST_DB_FILE`** when default test DB is busy). **`docs/public_endpoint_audit.md`**; **`docs/PATH_TO_100_PERCENT_EXECUTION_PLAN.md`** Phase **II.1**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-808** slice — SCIM HMAC only (**no** Raw SQL / SiteSettings / WOPI). **Next window:** **`810 closed (automation failure trend under-threshold success test)`**, then **`811+`** — coordinate.

**§11.4 forward queue - batch 808 (PATH Phase II.1 — SCIM optional `X-SCIM-Nonce` replay deduplication + `X-SCIM-Timestamp` tests, 2026-04-08):** **DONE** - **`apps/api/scim_views.py`**: **`_scim_nonce_replay_check()`**; **`apps/api/tests/test_scim_views.py`**: timestamp and nonce tests. **`python manage.py test apps.api.tests.test_scim_views --noinput -v 2`** — **21 OK**. **`docs/public_endpoint_audit.md`**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-807** public-endpoint replay slice (**no** Raw SQL / SiteSettings / WOPI). **Next window:** **`809 closed (SCIM HMAC signature)`**, then **`810+`** — coordinate.

**§11.4 forward queue - batch 807 (Release readiness bucket B — migration playbook preflight override reason must be non-empty after strip, 2026-04-08):** **DONE** - **`apps/automation/tests/test_playbook_quarantine_and_logs.py`**: **`test_preflight_whitespace_only_override_reason_still_blocks`**. **`python manage.py test apps.automation.tests.test_playbook_quarantine_and_logs.PlaybookExecutionLogTests.test_preflight_whitespace_only_override_reason_still_blocks --noinput -v 2`**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-806** slice — **`apps/automation`** tests only (**no** Raw SQL / **`apps/schools`** hot-path overlap). **Next window:** **`808 closed (SCIM nonce + timestamp tests)`**, then **`809+`** — coordinate.

**§11.4 forward queue - batch 806 (Release readiness bucket A — `/api/ai/feedback` validation + rate-limit tests, 2026-04-08):** **DONE** - **`apps/portal/tests/test_ai_feedback.py`**: **`test_feedback_400_when_task_type_missing`**, **`test_feedback_400_when_neither_accepted_nor_manual_correction`**, **`test_feedback_429_when_rate_limited`**. **`python manage.py test apps.portal.tests.test_ai_feedback --noinput -v 2`** — **5 OK**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-805** slice — portal tests only (**no** Raw SQL / **`apps/schools`** overlap). **Next window:** **`807 closed (migration playbook preflight whitespace override guard)`**, then **`808+`** — coordinate.

**§11.4 forward queue - batch 805 (Phase II.3 — runtime sync first-class owner scope regression tests, 2026-04-08):** **DONE** - **`apps/platform_runtime/tests/test_runtime_sync_first_class_scope.py`**: **`first_class_field_names_for_runtime_sync`** asserts **`enable_offline_mode`** and **`backend_feature_flags`** fall under **`policies_rules`** scope, **`site_name`** under **`brand_experience`**, so owner-filtered **`RuntimeDefaults.sync_from_site_settings`** cannot silently drop Phase B payload-owned offline flags when branding owners are excluded. **`python manage.py test apps.platform_runtime.tests.test_runtime_sync_first_class_scope --noinput -v 2`** — **3 OK**. **`python scripts/lint_tenant_settings.py`** **`--check-get-solo-only`** / **`--check-school-settings-features`** / **`--check-sitesettings-orm-in-tenant-apps`** — **PASS**. **`python scripts/verify_doc_plan_density_discipline.py` PASS** (after SOT/log). **Post-804** slice — **`domain_ownership` + `runtime_defaults_first_class`** contract tests only (**no** production path change). **Next window:** **`806 closed (AI feedback endpoint tests)`**, then **`807 closed (migration playbook preflight whitespace override guard)`**, then **`808+`** — coordinate.

""".strip()


def strip_oversized_lines(text: str, *, max_line_len: int = 50_000) -> str:
    """Drop lines longer than max_line_len; preserve splitlines(keepends=True) structure."""
    lines = text.splitlines(keepends=True)
    kept = [ln for ln in lines if len(ln) <= max_line_len]
    return "".join(kept)


def _fix_forward_prefix(line: str) -> str:
    return re.sub(
        r"\*\*[^§\n]*?§(?=11\.4\s+forward\s+queue)",
        "**§",
        line,
    )


def repair_text(text: str, *, max_line_len: int = 50_000) -> str:
    lines = text.splitlines(keepends=True)
    kept = [ln for ln in lines if len(ln) <= max_line_len]
    body = "".join(kept)

    if _INSERT_AFTER_SUBSTR not in body:
        raise SystemExit(
            f"repair_runmycampus_sot: anchor not found: {_INSERT_AFTER_SUBSTR!r}"
        )

    # Avoid duplicate insert if re-run.
    if (
        "forward queue - batch 846 " in body
        and "test_grade_approval_workflow" in body
    ):
        insert = ""
    else:
        blocks = [b.strip() for b in _INSERT_BLOCKS.split("\n\n") if b.strip()]
        insert = "\n\n".join(blocks) + "\n\n"

    parts = body.split(_INSERT_AFTER_SUBSTR, 1)
    body = parts[0] + _INSERT_AFTER_SUBSTR + "\n\n" + insert + parts[1]

    out_lines = []
    for ln in body.splitlines(keepends=True):
        if "11.4 forward queue" in ln and ln.lstrip().startswith("**"):
            ln = _fix_forward_prefix(ln)
        out_lines.append(ln)
    body = "".join(out_lines)

    # Only fix lines where the **forward queue** row itself starts with `**11.4 forward queue`
    # (missing §). A global substring replace corrupts batch descriptions that mention
    # `11.4 forward queue` in prose (e.g. batch 813 ledger text).
    fixed_lines = []
    for ln in body.splitlines(keepends=True):
        if re.match(r"^\s*\*\*11\.4 forward queue", ln) and not re.match(
            r"^\s*\*\*§11\.4 forward queue", ln
        ):
            ln = ln.replace("**11.4 forward queue", "**§11.4 forward queue", 1)
        fixed_lines.append(ln)
    body = "".join(fixed_lines)
    return body


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to target markdown (default: SOT, or execution log with --execution-log)",
    )
    p.add_argument(
        "--execution-log",
        action="store_true",
        help=f"Repair {DEFAULT_EXECUTION_LOG.name} (strip mega-lines only; no SOT insert).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print byte size before/after only",
    )
    args = p.parse_args(argv)

    if args.execution_log:
        path = Path(args.path) if args.path else DEFAULT_EXECUTION_LOG
    else:
        path = Path(args.path) if args.path else DEFAULT_PATH

    raw = path.read_text(encoding="utf-8")
    if args.execution_log:
        fixed = strip_oversized_lines(raw)
    else:
        fixed = repair_text(raw)
    if args.dry_run:
        print("before bytes", len(raw.encode("utf-8")))
        print("after bytes", len(fixed.encode("utf-8")))
        return 0
    path.write_text(fixed, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
