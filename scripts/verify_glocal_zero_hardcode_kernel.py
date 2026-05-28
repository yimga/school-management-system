#!/usr/bin/env python3
"""Glocal Zero-Hardcode kernel gate (batch 1529) — four audit checkpoints + delegates."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "generated" / "glocal_zero_hardcode_kernel_audit.json"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

CHECKS: list[tuple[str, str, callable]] = []


def check(name: str, desc: str):
    def deco(fn):
        CHECKS.append((name, desc, fn))
        return fn

    return deco


def _run_script(script: str, extra: list[str] | None = None, *, timeout: int = 600) -> tuple[bool, str]:
    argv = [sys.executable, str(REPO / "scripts" / script), *(extra or [])]
    gate_env = os.environ.copy()
    gate_env.setdefault("USE_FILE_LOGGING", "0")
    proc = subprocess.run(
        argv,
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=gate_env,
    )
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-600:]
    return proc.returncode == 0, tail


@check("CP1-data-residency-module", "data_residency kernel present")
def _cp1_module():
    path = REPO / "apps/schools/data_residency.py"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "derive_default_region" in text
    assert "CANONICAL_REGIONS" in text


@check("CP1-school-data-region-field", "School.data_region on model")
def _cp1_field():
    from apps.schools.models import School

    field = School._meta.get_field("data_region")
    assert field.max_length >= 8


@check("CP1-sovereignty-wizard", "setup_studio sovereignty writers")
def _cp1_wizard():
    src = (REPO / "apps/setup_studio/wizard_resolvers.py").read_text(encoding="utf-8")
    assert "write_sovereignty_jurisdiction" in src
    assert "list_data_residency_regions" in src


@check("CP1-verify-data-residency-cmd", "verify_data_residency management command")
def _cp1_cmd():
    path = REPO / "apps/schools/management/commands/verify_data_residency.py"
    assert path.is_file()


@check("CP1-residency-readiness", "residency_readiness assess_readiness")
def _cp1_readiness():
    from apps.schools.residency_readiness import assess_readiness

    report = assess_readiness()
    assert hasattr(report, "ready")


@check("CP1-onboarding-verifier", "data residency onboarding script")
def _cp1_onboarding_script():
    ok, tail = _run_script("verify_data_residency_onboarding.py", timeout=30)
    assert ok, tail


@check("CP2-permission-manifest", "colon token manifest + CRDT rejected")
def _cp2_manifest():
    from apps.accounts.permission_manifest import manifest_snapshot

    snap = manifest_snapshot()
    assert snap.get("format") == "colon_token"
    crdt = snap.get("advanced_capabilities", {}).get("crdt_edge_iam_admin", {})
    assert crdt.get("status") == "REJECTED"


@check("CP2-rebac-token-check", "rebac.check_permission_token export")
def _cp2_rebac():
    from apps.accounts.rebac import check_permission_token

    assert callable(check_permission_token)


@check("CP2-iam-localization", "iam_localization localized_role_label")
def _cp2_iam():
    from apps.accounts.iam_localization import localized_role_label

    assert localized_role_label("ADMIN", None) == "Admin"


@check("CP3-conflict-resolver", "sync_engine conflict_resolver")
def _cp3_conflict():
    from apps.sync_engine.conflict_resolver import ResolutionStrategy, resolve_one

    out = resolve_one({"entity": "grade_entry"}, strategy=ResolutionStrategy.MANUAL_REVIEW)
    assert out.get("action") == "manual_review"


@check("CP3-offline-queue", "platform_runtime offline_queue facade")
def _cp3_queue():
    from apps.platform_runtime import offline_queue

    assert hasattr(offline_queue, "enqueue_offline_action")
    assert hasattr(offline_queue, "get_pending_actions")


@check("CP3-service-worker", "service worker offline queue registration")
def _cp3_sw():
    sw = (REPO / "static/js/service-worker.js").read_text(encoding="utf-8")
    assert "offline" in sw.lower()
    assert "CACHE_VERSION" in sw


@check("CP4-isomorphic-css", "rmc-isomorphic-grid-sweep on platform chrome")
def _cp4_css():
    chrome = (REPO / "templates/partials/rmc_platform_chrome_styles.html").read_text(
        encoding="utf-8"
    )
    assert "rmc-isomorphic-grid-sweep.css" in chrome


@check("CP4-shells-lexicon", "portal + CP shells load regional UI")
def _cp4_shells():
    portal = (REPO / "templates/portal_base.html").read_text(encoding="utf-8")
    cp = (REPO / "templates/control_plane_skeleton.html").read_text(encoding="utf-8")
    assert "data-rmc-regional-ui" in portal
    assert "rmc-lexicon.js" in portal
    assert "data-rmc-regional-ui" in cp or "rmc-lexicon.js" in cp


PROGRAM_DELEGATES: tuple[tuple[str, str, list[str]], ...] = (
    ("delegate-onboarding", "verify_data_residency_onboarding.py", []),
    ("delegate-offline-envelope", "verify_offline_event_envelope.py", []),
    ("delegate-iam-vocab", "verify_isomorphic_iam_vocabulary.py", []),
    ("delegate-viewport", "verify_isomorphic_workspace_viewport.py", []),
    ("delegate-qr-attendance", "verify_zero_input_attendance_pilot.py", []),
    ("delegate-multi-region", "verify_multi_region_router_scaffold.py", []),
    ("delegate-grid-sweep", "audit_isomorphic_grid_channel_sweep.py", []),
    ("delegate-out-of-scope-honesty", "verify_glocal_out_of_scope_honesty.py", []),
    ("delegate-adoption-tranche", "verify_glocal_adoption_tranche.py", []),
)

REGRESSION_DELEGATES: tuple[tuple[str, str, list[str]], ...] = (
    ("delegate-glocal-closeout", "verify_glocal_closeout_completion.py", []),
    ("delegate-local-first", "verify_local_first_completion.py", []),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--skip-delegates",
        action="store_true",
        help="Skip slow delegate verifiers (inline CP checks only).",
    )
    args = parser.parse_args()

    import django

    django.setup()

    failures: list[str] = []
    rows: list[dict] = []

    for name, desc, fn in CHECKS:
        try:
            fn()
            rows.append({"id": name, "status": "PASS", "detail": desc})
            print(f"OK  {name} {desc}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            rows.append({"id": name, "status": "FAIL", "detail": str(exc)})
            print(f"FAIL {name} {desc}: {exc}")

    delegate_steps = () if args.skip_delegates else PROGRAM_DELEGATES
    for step_id, label, extra in delegate_steps:
        ok, tail = _run_script(label, extra)
        rows.append(
            {
                "id": step_id,
                "status": "PASS" if ok else "FAIL",
                "detail": label,
                "proof_tail": tail,
            }
        )
        if ok:
            print(f"OK  {step_id} {label}")
        else:
            failures.append(f"{label}: {tail}")
            print(f"FAIL {step_id} {label}")

    if not args.skip_delegates:
        for step_id, label, extra in REGRESSION_DELEGATES:
            ok, tail = _run_script(label, extra, timeout=900)
            rows.append(
                {
                    "id": step_id,
                    "status": "PASS" if ok else "FAIL",
                    "detail": label,
                    "proof_tail": tail,
                }
            )
            if ok:
                print(f"OK  {step_id} {label}")
            else:
                failures.append(f"{label}: {tail}")
                print(f"FAIL {step_id} {label}")

    verdict = "GLOCAL_ZERO_HARDCODE_KERNEL_PASS" if not failures else "GLOCAL_ZERO_HARDCODE_KERNEL_FAIL"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "finding_count": len(failures),
        "checks": rows,
        "failures": failures,
    }
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(f"\nverify_glocal_zero_hardcode_kernel: {verdict}", file=sys.stderr)
        for item in failures[:20]:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"\nverify_glocal_zero_hardcode_kernel: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
