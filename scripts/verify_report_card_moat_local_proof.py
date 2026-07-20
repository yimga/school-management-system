#!/usr/bin/env python3
"""Report-card moat local-proof scaffold (#4).

PASS when:
  - Django e2e flow + seed tests exist
  - Playwright parent hash spec exists
  - npm tenant-moat / report-card scripts are wired
  - optional local proof artifact documents a real local armed run

Reports ``EXTERNAL_ACTIONS_GREEN_REQUIRED`` when GitHub ``tenant-moat-e2e`` is
not proven green. Never invents Actions success.

Run: python scripts/verify_report_card_moat_local_proof.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROOF_ARTIFACT = "docs/generated/report_card_moat_local_proof.json"
PACKAGE_JSON = "package.json"

DJANGO_FLOW = "apps/reports/tests/test_report_card_e2e_flow.py"
DJANGO_SEED = "apps/reports/tests/test_report_card_e2e_seed.py"
PLAYWRIGHT_PARENT = "tests/e2e/report-card-hash-parent.spec.js"
ARMED_RUNNER = "scripts/run_tenant_moat_e2e.mjs"


def _file_exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def _file_contains(rel: str, needle: str) -> bool:
    return needle in _read(rel)


def _npm_has_script(name: str) -> bool:
    raw = _read(PACKAGE_JSON)
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    scripts = data.get("scripts") or {}
    return name in scripts


def _local_proof_status() -> tuple[bool, str]:
    rel = PROOF_ARTIFACT
    if not _file_exists(rel):
        return False, f"{rel} absent (optional until a local armed run is recorded)"
    try:
        data = json.loads(_read(rel))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"{rel} unreadable: {exc}"
    status = str(data.get("status") or "").upper()
    if status not in {"LOCAL_MOAT_PASS", "PASS"}:
        return False, f"{rel} status={status!r} (want LOCAL_MOAT_PASS)"
    if not data.get("django_e2e_ok"):
        return False, f"{rel} missing django_e2e_ok=true"
    # Django staff→parent e2e is sufficient for local moat PASS.
    # Playwright parent / armed runner are optional upgrades.
    extras = []
    if data.get("playwright_parent_ok"):
        extras.append("playwright_parent")
    if data.get("armed_runner_ok"):
        extras.append("armed_runner")
    extra_note = f" +{','.join(extras)}" if extras else " (Django e2e only)"
    return True, f"{rel} status={status}{extra_note}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    checks: list[dict] = []
    external: list[str] = []

    checks.append(
        {
            "check": "django_e2e_flow",
            "pass": _file_exists(DJANGO_FLOW),
            "detail": DJANGO_FLOW if _file_exists(DJANGO_FLOW) else "MISSING",
        }
    )
    checks.append(
        {
            "check": "django_e2e_seed",
            "pass": _file_exists(DJANGO_SEED),
            "detail": DJANGO_SEED if _file_exists(DJANGO_SEED) else "MISSING",
        }
    )
    checks.append(
        {
            "check": "playwright_parent_spec",
            "pass": _file_exists(PLAYWRIGHT_PARENT)
            and _file_contains(PLAYWRIGHT_PARENT, "parent"),
            "detail": (
                PLAYWRIGHT_PARENT
                if _file_exists(PLAYWRIGHT_PARENT)
                else "MISSING parent Playwright spec"
            ),
        }
    )
    npm_hash = _npm_has_script("test:e2e:report-card-hash")
    npm_moat = _npm_has_script("test:e2e:tenant-moat")
    npm_armed = _npm_has_script("test:e2e:tenant-moat:armed")
    checks.append(
        {
            "check": "npm_moat_scripts",
            "pass": npm_hash and npm_moat and npm_armed,
            "detail": (
                "report-card-hash + tenant-moat + tenant-moat:armed"
                if npm_hash and npm_moat and npm_armed
                else "MISSING one or more npm moat scripts"
            ),
        }
    )
    checks.append(
        {
            "check": "armed_runner_script",
            "pass": _file_exists(ARMED_RUNNER),
            "detail": ARMED_RUNNER if _file_exists(ARMED_RUNNER) else "MISSING",
        }
    )

    local_ok, local_detail = _local_proof_status()
    checks.append(
        {
            "check": "local_proof_artifact",
            "pass": True,  # optional — absence is EXTERNAL-classified, not FAIL
            "detail": local_detail,
            "optional_recorded": local_ok,
        }
    )
    if not local_ok:
        external.append(
            "EXTERNAL_LOCAL_MOAT_PROOF_OPTIONAL: No committed "
            f"{PROOF_ARTIFACT} with LOCAL_MOAT_PASS yet. Record after a real "
            "`npm run test:e2e:tenant-moat:armed` (or Django+Playwright subset) "
            "— never invent a green run."
        )

    external.append(
        "EXTERNAL_ACTIONS_GREEN_REQUIRED: GitHub Actions tenant-moat-e2e / "
        "postgres green remains operator-gated (runner billing). Do not invent "
        "Actions success from this scaffold."
    )

    repo_required = [c for c in checks if c["check"] != "local_proof_artifact"]
    all_pass = all(c["pass"] for c in repo_required)
    report = {
        "gate": "verify_report_card_moat_local_proof",
        "status": "PASS" if all_pass else "FAIL",
        "checks": checks,
        "external_remaining": external,
        "local_proof_recorded": local_ok,
        "summary": (
            "Report-card moat scaffolding is present. "
            + (
                "Local proof artifact recorded."
                if local_ok
                else "Local proof artifact optional until armed run is recorded."
            )
            + " Actions green remains EXTERNAL."
            if all_pass
            else "Some repo-contained moat wiring checks failed — see checks[]."
        ),
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"verify_report_card_moat_local_proof: {report['status']}")
        for c in checks:
            mark = "OK" if c["pass"] else "FAIL"
            print(f"  [{mark}] {c['check']}: {c['detail']}")
        if external:
            print("\n  EXTERNAL (honest classification, not a gate failure):")
            for e in external:
                print(f"    - {e}")
        if all_pass:
            print("REPORT_CARD_MOAT_SCAFFOLD_PASS")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
