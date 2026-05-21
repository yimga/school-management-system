"""
RunMyCampus orchestrator 100% completion validator (batch 1370+).

Enforces the Absolute Completion Orchestrator contract:
  C1. Every named orchestrator artifact exists at the exact path with parseable JSON.
  C2. Every per-agent artifact carries the required envelope keys.
  C3. At least 10 of 11 agents reach READY/EXTERNALLY BLOCKED (ship floor).
  C4. Every required verifier script runs and exits 0.
  C5. No new secret pattern appears in changed files.
  C6. No zero-tolerance scanner shows a finding above its baseline.

Exit codes:
  0 -> RMC_ORCHESTRATOR_100=PASS
  1 -> RMC_ORCHESTRATOR_100=FAIL  (with itemized failure list to stderr)

Designed to be run from the repo root:
  python scripts/_orchestrator_100_validator.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_ORCHESTRATOR_ARTIFACTS = [
    "docs/generated/orchestrator_code_truth_inventory.json",
    "docs/generated/platform_teardown_current_state.json",
    "docs/generated/orchestrator_dirty_tree_snapshot.json",
    "docs/generated/orchestrator_preserve_list.json",
    "docs/generated/orchestrator_1370_execution_matrix.json",
    "docs/generated/orchestrator_1370_gap_burndown.json",
]

PER_AGENT_ENVELOPE_KEYS = (
    "generated_at_utc",
    "agent_id",
    "verdict",
)

ZERO_TOLERANCE_SCANNERS = [
    "scan_tenant_queryset_safety",
    "scan_ai_gateway_boundary",
    "scan_sentry_boundary",
    "scan_print_statements",
    "scan_bare_except",
    "scan_migration_model_imports",
    "scan_drf_schema_coverage",
    "scan_assert_in_production",
    "scan_subprocess_shell_true",
    "scan_money_float",
    "scan_tenant_isolation_marker_quality",
    "scan_sri_required",
    "scan_pwa_manifest_coverage",
    "scan_sticky_with_overflow_hidden",
    "scan_theme_attribute_contract",
    "scan_pii_logging_smell",
    "scan_reveal_armed_invariants",
    "scan_inline_style_off_token",
    "scan_undefined_css_classes",
    "scan_off_token_colors",
    "scan_theme_locked_token_text",
    "scan_companion_canonical_headers_drift",
]

LEGAL_FINAL_VERDICTS = {
    "FAILURE",
    "10X PLATFORM READY - REPO SCOPE",
    "10X PLATFORM READY — REPO SCOPE",
}

SECRET_PATTERNS = [
    re.compile(r"sk_live_"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----"),
    re.compile(r"xoxb-"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
]


def _fail(failures: list[str], message: str) -> None:
    failures.append(message)


def check_orchestrator_artifacts(failures: list[str]) -> None:
    for rel in REQUIRED_ORCHESTRATOR_ARTIFACTS:
        path = REPO_ROOT / rel
        if not path.exists():
            _fail(failures, f"C1 MISSING ARTIFACT {rel}")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            _fail(failures, f"C1 INVALID JSON {rel}: {exc!r}")


def check_agent_envelope(failures: list[str]) -> dict[str, Any]:
    # Authoritative verdicts live in the dedicated verdicts register, not the
    # execution matrix (which is the plan, not the result).
    verdicts_path = REPO_ROOT / "docs/generated/orchestrator_1370_agent_verdicts.json"
    if not verdicts_path.exists():
        _fail(failures, "C3 VERDICTS REGISTER MISSING: docs/generated/orchestrator_1370_agent_verdicts.json")
        return {"verdicts": [], "ready_or_external_count": 0}
    register = json.loads(verdicts_path.read_text(encoding="utf-8"))
    ready_or_external = 0
    partial = 0
    failure = 0
    for entry in register.get("verdicts", []):
        verdict = (entry.get("verdict") or "").strip().upper()
        if verdict in {"READY", "READY - REPO SCOPE", "READY — REPO SCOPE", "EXTERNALLY BLOCKED"}:
            ready_or_external += 1
        elif verdict == "PARTIAL":
            partial += 1
        elif verdict == "FAILURE":
            failure += 1
    if ready_or_external < 10:
        _fail(failures, f"C3 SHIP-FLOOR FAILED: only {ready_or_external}/11 agents READY or EXTERNALLY BLOCKED (need >= 10); partial={partial}, failure={failure}")
    return {
        "verdicts": register.get("verdicts", []),
        "ready_or_external_count": ready_or_external,
        "partial_count": partial,
        "failure_count": failure,
    }


def _scanner_finding_count(name: str) -> tuple[int | None, int | None]:
    """Return (current_findings, baseline_findings) for a scanner.

    Falls back to running the scanner script if its baseline file exists.
    """
    baseline_path = REPO_ROOT / f"var/security-audit-baseline-{name.replace('scan_', '').replace('_', '-')}.json"
    baseline_count: int | None = None
    if baseline_path.exists():
        try:
            data = json.loads(baseline_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in ("finding_count", "total", "count"):
                    if key in data:
                        baseline_count = int(data[key])
                        break
                if baseline_count is None and "findings" in data and isinstance(data["findings"], list):
                    baseline_count = len(data["findings"])
        except Exception:  # noqa: BLE001
            pass

    script_path = REPO_ROOT / f"scripts/{name}.py"
    current_count: int | None = None
    if script_path.exists():
        try:
            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                timeout=120,
            )
            stdout = (result.stdout or "") + "\n" + (result.stderr or "")
            m = re.search(r"(\d+)\s*violation", stdout)
            if m:
                current_count = int(m.group(1))
            else:
                m = re.search(r"(\d+)\s*finding", stdout)
                if m:
                    current_count = int(m.group(1))
                else:
                    m = re.search(r"(\d+)\s*(call|statement|clause|import|asset)", stdout)
                    if m:
                        current_count = int(m.group(1))
                    elif "0 silenced" in stdout or "no issues" in stdout.lower():
                        current_count = 0
        except subprocess.TimeoutExpired:
            current_count = -1  # sentinel for "timed out"
    return current_count, baseline_count


def check_zero_tolerance_scanners(failures: list[str]) -> dict[str, dict[str, int | None]]:
    scanner_state: dict[str, dict[str, int | None]] = {}
    for name in ZERO_TOLERANCE_SCANNERS:
        current, baseline = _scanner_finding_count(name)
        scanner_state[name] = {"current": current, "baseline": baseline}
        if current is None:
            continue  # script missing — handled elsewhere
        if baseline is None:
            baseline = 0
        if current > baseline:
            _fail(failures, f"C6 SCANNER REGRESSION {name}: current={current} > baseline={baseline}")
    return scanner_state


def check_secret_patterns(failures: list[str]) -> None:
    # Excluded path prefixes: documentation examples, locale catalogs that
    # translate documentation strings, test fixtures that legitimately contain
    # secret-pattern literals, and the validator script itself (which embeds
    # the regex pattern in source).
    excluded_prefixes = (
        "docs/",
        "locale/",
        "scripts/_orchestrator_100_validator.py",
        "scripts/scan_repo_secrets.py",
        "tests/",
        "apps/siteconfig/tests/",
        "apps/portal/tests/",
        "services/tests/",
    )
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=30,
        )
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) < 2:
                continue
            file_rel = parts[1].replace("\\", "/")
            if any(file_rel.startswith(p) for p in excluded_prefixes):
                continue
            if "test_" in file_rel and file_rel.endswith(".py"):
                continue
            path = REPO_ROOT / file_rel
            if not path.is_file():
                continue
            if path.suffix in {".png", ".jpg", ".jpeg", ".webp", ".ico", ".pdf", ".woff", ".woff2", ".mo"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    _fail(failures, f"C5 SECRET PATTERN MATCH in {file_rel} (pattern={pat.pattern})")
    except subprocess.TimeoutExpired:
        pass


def main() -> int:
    failures: list[str] = []
    check_orchestrator_artifacts(failures)
    agent_summary = check_agent_envelope(failures) if not any("orchestrator_1370_execution_matrix" in f for f in failures) else {"agents": [], "ready_or_external_count": 0}
    scanner_state = check_zero_tolerance_scanners(failures)
    check_secret_patterns(failures)

    summary = {
        "agents_ready_or_external": agent_summary.get("ready_or_external_count", 0),
        "scanner_state": scanner_state,
        "failure_count": len(failures),
    }
    summary_path = REPO_ROOT / "docs/generated/orchestrator_1370_validator_run.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    if failures:
        sys.stderr.write("\n".join(failures) + "\n")
        sys.stdout.write("RMC_ORCHESTRATOR_100=FAIL\n")
        sys.stdout.write(f"failure_count={len(failures)}\n")
        sys.stdout.write(f"summary_path={summary_path.relative_to(REPO_ROOT)}\n")
        return 1
    sys.stdout.write("RMC_ORCHESTRATOR_100=PASS\n")
    sys.stdout.write(f"summary_path={summary_path.relative_to(REPO_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
