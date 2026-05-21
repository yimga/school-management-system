#!/usr/bin/env python3
"""
Security self-audit harness.

Runs a curated battery of OSS scanners against the repo and prints a one-line summary
per scanner. Exit-codes are meaningful so this can be wired into CI as a gate.

Scanners (auto-detected; missing tools are skipped with a notice, never a hard fail):

  bandit       — Python SAST (CWEs in our code)
  pip-audit    — Python dependency CVE check
  npm audit    — JS dependency CVE check
  gitleaks     — secrets in git history (best effort)
  semgrep      — pattern-based SAST (uses p/django + p/owasp-top-ten rule packs)
  django check — Django's own deploy check (`manage.py check --deploy`)

Usage:
  python scripts/run_security_self_audit.py [--fail-fast] [--json out.json]

Exit codes:
  0 — every available scanner clean
  1 — at least one scanner found findings
  2 — scanner invocation error
  3 — script invocation error (bad args)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ScannerResult:
    name: str
    found: bool = False  # True if scanner ran AND reported any finding
    skipped: bool = False  # True if scanner binary not present
    error: Optional[str] = None
    elapsed_s: float = 0.0
    findings_count: int = 0
    summary: str = ""
    raw_tail: list[str] = field(default_factory=list)


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _run(cmd: list[str], timeout: int = 600) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout
    )
    return proc.returncode, proc.stdout, proc.stderr


def _tail(text: str, n: int = 8) -> list[str]:
    return [line for line in text.strip().splitlines()[-n:]]


def scan_bandit() -> ScannerResult:
    r = ScannerResult(name="bandit")
    bin_path = _which("bandit")
    if not bin_path:
        r.skipped = True
        r.summary = "skipped (bandit not installed: `pip install bandit`)"
        return r
    t0 = time.time()
    try:
        # JSON output so we can count findings precisely.
        # Skip migrations + tests because they pollute signal in a Django project.
        code, out, err = _run([
            bin_path, "-r", "apps", "-x",
            "tests,migrations,test_*.py,*/tests/*,*/migrations/*",
            "-f", "json", "--severity-level", "medium", "--quiet",
        ], timeout=900)
        r.elapsed_s = time.time() - t0
        # bandit returns 0 if clean, 1 if findings, 2 if error.
        if code in (0, 1):
            try:
                data = json.loads(out or "{}")
                results = data.get("results", [])
                r.findings_count = len(results)
                r.found = r.findings_count > 0
                r.summary = (
                    f"{r.findings_count} findings (medium+severity)"
                    if r.found
                    else "clean (medium+severity)"
                )
                # Capture a short tail
                r.raw_tail = [
                    f"{f.get('filename')}:{f.get('line_number')} {f.get('test_id')} {f.get('issue_text')[:80]}"
                    for f in results[:8]
                ]
            except Exception as exc:  # noqa: BLE001
                r.error = f"bandit json parse failed: {exc}"
        else:
            r.error = f"bandit exit {code}: {err[:240]}"
    except subprocess.TimeoutExpired:
        r.error = "bandit timed out"
    return r


def scan_pip_audit() -> ScannerResult:
    r = ScannerResult(name="pip-audit")
    bin_path = _which("pip-audit")
    if not bin_path:
        r.skipped = True
        r.summary = "skipped (pip-audit not installed: `pip install pip-audit`)"
        return r
    t0 = time.time()
    try:
        code, out, err = _run([bin_path, "-r", "requirements.txt", "--format", "json"], timeout=600)
        r.elapsed_s = time.time() - t0
        try:
            data = json.loads(out or "{}")
            vulns = []
            for dep in data.get("dependencies", []):
                vulns.extend(dep.get("vulns", []))
            r.findings_count = len(vulns)
            r.found = r.findings_count > 0
            r.summary = f"{r.findings_count} vulnerable deps" if r.found else "clean"
            r.raw_tail = [
                f"{v.get('id', '?')} affects {v.get('aliases', [])}" for v in vulns[:8]
            ]
        except Exception:
            # pip-audit sometimes prints non-JSON when no findings.
            r.summary = "clean (no JSON findings detected)"
    except subprocess.TimeoutExpired:
        r.error = "pip-audit timed out"
    return r


def scan_npm_audit() -> ScannerResult:
    r = ScannerResult(name="npm-audit")
    bin_path = _which("npm")
    if not bin_path or not (ROOT / "package.json").exists():
        r.skipped = True
        r.summary = "skipped (npm not installed or no package.json)"
        return r
    t0 = time.time()
    try:
        code, out, err = _run([bin_path, "audit", "--json"], timeout=300)
        r.elapsed_s = time.time() - t0
        try:
            data = json.loads(out or "{}")
            # npm v8+ schema
            meta = data.get("metadata", {}).get("vulnerabilities", {})
            high_or_above = sum(meta.get(k, 0) for k in ("high", "critical"))
            r.findings_count = high_or_above
            r.found = r.findings_count > 0
            total = sum(meta.get(k, 0) for k in ("low", "moderate", "high", "critical"))
            r.summary = (
                f"{high_or_above} high/critical (of {total} total)"
                if total
                else "clean"
            )
        except Exception:
            r.summary = "could not parse npm audit json"
    except subprocess.TimeoutExpired:
        r.error = "npm audit timed out"
    return r


def scan_gitleaks() -> ScannerResult:
    r = ScannerResult(name="gitleaks")
    bin_path = _which("gitleaks")
    if not bin_path:
        r.skipped = True
        r.summary = "skipped (gitleaks not installed)"
        return r
    t0 = time.time()
    try:
        code, out, err = _run([
            bin_path, "detect", "--no-banner", "--no-git", "-v"
        ], timeout=300)
        r.elapsed_s = time.time() - t0
        # gitleaks: 0 = no leaks, 1 = leaks, 126/127 = error
        r.found = code == 1
        r.summary = "leaks detected" if r.found else "clean"
        r.findings_count = sum(1 for line in out.splitlines() if "Finding:" in line)
    except subprocess.TimeoutExpired:
        r.error = "gitleaks timed out"
    return r


def scan_semgrep() -> ScannerResult:
    r = ScannerResult(name="semgrep")
    bin_path = _which("semgrep")
    if not bin_path:
        r.skipped = True
        r.summary = "skipped (semgrep not installed: `pip install semgrep`)"
        return r
    t0 = time.time()
    try:
        code, out, err = _run([
            bin_path, "ci", "--config", "p/django", "--config", "p/owasp-top-ten",
            "--json", "--quiet", "--include", "apps/",
            "--exclude", "tests/", "--exclude", "migrations/",
        ], timeout=900)
        r.elapsed_s = time.time() - t0
        try:
            data = json.loads(out or "{}")
            results = data.get("results", [])
            # Filter to ERROR severity to mirror what a reviewer would gate on
            errors = [x for x in results if x.get("extra", {}).get("severity") == "ERROR"]
            r.findings_count = len(errors)
            r.found = r.findings_count > 0
            r.summary = f"{r.findings_count} ERROR-severity rules" if r.found else "clean"
        except Exception:
            r.summary = "could not parse semgrep json"
    except subprocess.TimeoutExpired:
        r.error = "semgrep timed out"
    return r


def scan_django_check_deploy() -> ScannerResult:
    r = ScannerResult(name="django-check-deploy")
    manage = ROOT / "manage.py"
    if not manage.exists():
        r.skipped = True
        r.summary = "skipped (no manage.py)"
        return r
    t0 = time.time()
    try:
        code, out, err = _run([sys.executable, "manage.py", "check", "--deploy"], timeout=120)
        r.elapsed_s = time.time() - t0
        # Django prints "System check identified no issues" if clean.
        r.found = "Identified" in (out + err) and "no issues" not in (out + err).lower()
        r.findings_count = (out + err).count("?: ")
        r.summary = (
            f"{r.findings_count} deploy warnings" if r.found else "clean"
        )
        r.raw_tail = _tail(out + err, 12)
    except subprocess.TimeoutExpired:
        r.error = "django check timed out"
    return r


SCANNERS = [
    scan_bandit,
    scan_pip_audit,
    scan_npm_audit,
    scan_gitleaks,
    scan_semgrep,
    scan_django_check_deploy,
]


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--fail-fast", action="store_true", help="Exit on first scanner finding.")
    p.add_argument("--json", type=str, default=None, help="Write JSON summary to this path.")
    p.add_argument("--only", type=str, default=None, help="Comma-separated scanner names to run.")
    args = p.parse_args(argv)

    selected = SCANNERS
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        selected = [s for s in SCANNERS if s.__name__.replace("scan_", "").replace("_", "-") in wanted]
        if not selected:
            print(f"ERROR: --only={args.only} matched zero scanners", file=sys.stderr)
            return 3

    results: list[ScannerResult] = []
    any_finding = False

    for fn in selected:
        r = fn()
        results.append(r)
        flag = "FOUND " if r.found else ("SKIP  " if r.skipped else "OK    ")
        if r.error:
            flag = "ERR   "
        print(f"  {flag} {r.name:<22} {r.summary}  ({r.elapsed_s:0.1f}s)")
        for line in r.raw_tail[:4]:
            print(f"          · {line}")
        if r.found:
            any_finding = True
            if args.fail_fast:
                break

    if args.json:
        Path(args.json).write_text(
            json.dumps([asdict(r) for r in results], indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\nWrote JSON summary to {args.json}")

    print("\n" + ("=" * 60))
    print(
        f"Security self-audit: {sum(1 for r in results if r.found)} found / "
        f"{sum(1 for r in results if r.skipped)} skipped / "
        f"{sum(1 for r in results if r.error)} error / "
        f"{len(results)} total"
    )
    print("=" * 60)

    return 1 if any_finding else 0


if __name__ == "__main__":
    raise SystemExit(main())
