"""Semantic-runtime verifier for the ExperienceTemplate marketplace.

Runs the dedicated runtime test module
(``apps.brand_experience.tests.test_template_marketplace_semantic_runtime``)
end-to-end via Django's test runner and emits a JSON status artifact
under ``docs/generated/template_marketplace_semantic_runtime.json``.

This is the gate that lifts the program from "structural completeness"
(every file/route/registry-entry exists with the right shape) to
"semantic correctness" (the Studio OS Experience-mode view actually
injects ``experience_template_overlays`` into the fold partial; all
9 tenant marketplace views render under the real request cycle; the
Setup Studio ``select_experience_template`` step actually surfaces in
the live payload; the append-only TemplateAuditEvent contract holds
under the ORM).

Honest scope: this verifier does not exercise the 6 operator
``/configuration/experience-templates/*`` routes. Those routes reuse the
existing ``pack_marketplace`` / ``pack_detail`` / ``pack_preview`` /
``pack_simulation`` / ``pack_impact`` / ``pack_apply`` route stack, which
is covered by platform_runtime tests. Wave E+ live blockers (LiteLLM live
mode, partner publish flip, monetization billing) remain counsel-pending
per the 6-gate docket.

Exit codes:
  0 — TEMPLATE_MARKETPLACE_SEMANTIC_RUNTIME_PASS
  1 — TEMPLATE_MARKETPLACE_SEMANTIC_RUNTIME_FAIL (full subprocess output captured)
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
GENERATED_DIR = REPO_ROOT / "docs" / "generated"
OUT_JSON = GENERATED_DIR / "template_marketplace_semantic_runtime.json"

TEST_LABEL = "apps.brand_experience.tests.test_template_marketplace_semantic_runtime"
TEST_SETTINGS = os.getenv("RMC_SEMANTIC_TEST_SETTINGS") or "config.settings"

HONEST_SCOPE = {
    "proves": [
        "Studio OS Experience-mode view injects experience_template_overlays into the live fold partial",
        "9 tenant marketplace views render through the Django request cycle",
        "Setup Studio select_experience_template step surfaces in the live payload",
        "TemplateAuditEvent append-only ORM contract holds",
    ],
    "does_not_exercise": [
        "6 operator /configuration/experience-templates/* routes",
        "Live LiteLLM recommendation mode",
        "Partner-publish production flip",
        "Monetization billing or Stripe settlement",
    ],
    "operator_route_coverage_source": (
        "Operator routes reuse pack_marketplace, pack_detail, pack_preview_view, "
        "pack_simulation_view, pack_impact_view, and pack_apply_view; those are "
        "covered by the platform_runtime pack route/lifecycle tests."
    ),
    "wave_e_external_blockers": (
        "Live LiteLLM, partner-publish flip, and monetization billing remain "
        "explicitly counsel-pending per docs/TEMPLATE_MARKETPLACE_WAVE_E_COUNSEL_PENDING.md."
    ),
}

# Test-class expectations (count + ordering kept independently from the test
# file so the verifier catches accidental deletions in a single read).
EXPECTED_TEST_CLASSES = [
    "ExperienceFoldPartialContractTests",
    "StudioOSExperienceModeViewRuntimeTests",
    "SetupStudioExperienceTemplateStepRuntimeTests",
    "TenantTemplateMarketplaceViewsRuntimeTests",
    "TemplateAuditEventAppendOnlyRuntimeTests",
]


def _resolve_python() -> str:
    """Pick the same Python interpreter that's running this verifier."""
    return sys.executable or "python"


def _structural_preflight() -> tuple[bool, list[str]]:
    """Confirm the test module is on disk + the fold is wired before running tests.

    Catches a deletion/rename that would silently make the test run a no-op.
    """
    notes: list[str] = []
    ok = True

    test_path = (
        REPO_ROOT
        / "apps"
        / "brand_experience"
        / "tests"
        / "test_template_marketplace_semantic_runtime.py"
    )
    if not test_path.exists():
        ok = False
        notes.append(f"missing: {test_path.relative_to(REPO_ROOT)}")
    else:
        body = test_path.read_text(encoding="utf-8")
        for cls in EXPECTED_TEST_CLASSES:
            if f"class {cls}" not in body:
                ok = False
                notes.append(f"missing test class: {cls}")

    fold_path = (
        REPO_ROOT
        / "templates"
        / "studio_os"
        / "partials"
        / "experience_templates_fold.html"
    )
    if not fold_path.exists():
        ok = False
        notes.append("missing: studio_os fold partial")

    mode_path = (
        REPO_ROOT
        / "templates"
        / "studio_os"
        / "modes"
        / "experience.html"
    )
    if not mode_path.exists():
        ok = False
        notes.append("missing: studio Experience mode template")
    else:
        body = mode_path.read_text(encoding="utf-8")
        if 'data-rmc-fold-stage="templates"' not in body:
            ok = False
            notes.append("studio Experience mode does not declare the Templates fold stage")
        if "experience_templates_fold.html" not in body:
            ok = False
            notes.append(
                "studio Experience mode does not include experience_templates_fold.html"
            )

    views_path = REPO_ROOT / "apps" / "studio_os" / "views.py"
    if not views_path.exists():
        ok = False
        notes.append("missing: apps/studio_os/views.py")
    else:
        body = views_path.read_text(encoding="utf-8")
        if "experience_template_overlays" not in body:
            ok = False
            notes.append(
                "apps/studio_os/views.py does not inject experience_template_overlays context"
            )

    return ok, notes


def _parse_test_summary(stderr_text: str) -> dict:
    """Pull ran/ok/failed counts out of Django test runner stderr.

    Django prints e.g.:
        Ran 18 tests in 12.345s

        OK
    or
        Ran 18 tests in 12.345s

        FAILED (failures=1, errors=2, skipped=3)
    """
    summary: dict = {"ran": None, "ok": False, "failures": 0, "errors": 0, "skipped": 0}
    m = re.search(r"Ran\s+(\d+)\s+tests?", stderr_text or "")
    if m:
        try:
            summary["ran"] = int(m.group(1))
        except ValueError:
            pass
    text = stderr_text or ""
    if re.search(r"^OK(\s*\(.*\))?\s*$", text, flags=re.MULTILINE):
        summary["ok"] = True
    fm = re.search(r"failures=(\d+)", text)
    em = re.search(r"errors=(\d+)", text)
    sm = re.search(r"skipped=(\d+)", text)
    if fm:
        summary["failures"] = int(fm.group(1))
    if em:
        summary["errors"] = int(em.group(1))
    if sm:
        summary["skipped"] = int(sm.group(1))
    return summary


def _run_test_label() -> tuple[int, str, str]:
    """Invoke the Django test runner for the semantic-runtime label."""
    python = _resolve_python()
    if os.name == "nt":
        cmd = [
            python,
            str(REPO_ROOT / "scripts" / "run_sqlite_memory_tests.py"),
            TEST_LABEL,
            "--verbosity=2",
        ]
    else:
        cmd = [
            python,
            "manage.py",
            "test",
            TEST_LABEL,
            f"--settings={TEST_SETTINGS}",
            "--noinput",
            "--keepdb",
            "-v",
            "2",
        ]
    env = os.environ.copy()
    env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    env.setdefault("DEBUG", "1")
    env.setdefault("SECRET_KEY", "semantic-runtime-verifier-local-only")
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _write_artifact(payload: dict) -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def main() -> int:
    pre_ok, pre_notes = _structural_preflight()
    if not pre_ok:
        payload = {
            "status": "TEMPLATE_MARKETPLACE_SEMANTIC_RUNTIME_FAIL",
            "reason": "structural-preflight-failed",
            "preflight_notes": pre_notes,
            "honest_scope": HONEST_SCOPE,
            "generated_at": _dt.datetime.now(_dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        _write_artifact(payload)
        print("FAIL: structural preflight — " + " | ".join(pre_notes))
        return 1

    print(
        "Running semantic-runtime test label: "
        + TEST_LABEL
        + " (this exercises view + partial + setup-studio + audit append-only)"
    )
    rc, stdout_text, stderr_text = _run_test_label()
    summary = _parse_test_summary(stderr_text)

    passed = rc == 0 and summary["ok"]
    payload = {
        "status": (
            "TEMPLATE_MARKETPLACE_SEMANTIC_RUNTIME_PASS"
            if passed
            else "TEMPLATE_MARKETPLACE_SEMANTIC_RUNTIME_FAIL"
        ),
        "test_label": TEST_LABEL,
        "subprocess_returncode": rc,
        "summary": summary,
        "honest_scope": HONEST_SCOPE,
        "preflight_notes": pre_notes,
        "expected_test_classes": EXPECTED_TEST_CLASSES,
        "stdout_tail": (stdout_text or "")[-4000:],
        "stderr_tail": (stderr_text or "")[-4000:],
        "generated_at": _dt.datetime.now(_dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    _write_artifact(payload)

    if passed:
        ran = summary.get("ran") or 0
        print(
            f"PASS: TEMPLATE_MARKETPLACE_SEMANTIC_RUNTIME_PASS "
            f"({ran} tests across {len(EXPECTED_TEST_CLASSES)} classes)"
        )
        print(
            "SCOPE: tenant/Studio OS/Setup Studio/audit semantic coverage; "
            "operator /configuration routes reuse platform_runtime pack coverage; "
            "Wave E+ live blockers remain counsel-pending."
        )
        return 0
    print("FAIL: TEMPLATE_MARKETPLACE_SEMANTIC_RUNTIME_FAIL")
    print(f"  subprocess returncode = {rc}")
    print(f"  summary = {summary}")
    # Surface the tail of stderr to make CI logs immediately useful.
    print("--- stderr tail ---")
    print((stderr_text or "")[-2000:])
    return 1


if __name__ == "__main__":
    sys.exit(main())
