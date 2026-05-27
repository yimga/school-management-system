#!/usr/bin/env python3
"""
Repo-side post-deploy smoke for tenant lifecycle + back-to-top (Lane 1).

Does not HTTP-call production — runs mechanical gates and prints operator URLs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GATES = (
    ("verify_platform_back_to_top.py", "PLATFORM_BACK_TO_TOP_PASS"),
    ("audit_shell_scroll_contract.py", "SHELL_SCROLL_CONTRACT_AUDIT_PASS"),
    ("verify_tenant_lifecycle_completion.py", "TENANT_LIFECYCLE_COMPLETION_PASS"),
    ("audit_tenant_lifecycle_full.py", "TENANT_LIFECYCLE_FULL_AUDIT_PASS"),
    ("audit_tenant_lifecycle_aggressive.py", "TENANT_LIFECYCLE_AGGRESSIVE_AUDIT_PASS"),
    ("verify_lifecycle_lane2_render_env.py", "LIFECYCLE_LANE2_RENDER_ENV_PASS"),
)

SMOKE_URLS = """
Post-deploy operator smoke (hard-refresh after deploy / SW bump):

Manager
  Offboarding queue     https://manager.runmycampus.com/super/offboarding/
  Rapid create          https://manager.runmycampus.com/super/schools/rapid/
  Provisioning jobs     https://manager.runmycampus.com/provisioning/jobs/
  Email health          https://manager.runmycampus.com/super/email/health/

Tenant (replace <slug>)
  Lifecycle hub         https://<slug>.runmycampus.com/school/studio/lifecycle/
  Offboarding           https://<slug>.runmycampus.com/school/studio/offboarding/
  School Studio         https://<slug>.runmycampus.com/school/studio/

Back-to-top: floating control visible bottom-right on every authenticated page (dim at top).
"""


def _run(script: str) -> tuple[bool, str]:
    path = ROOT / "scripts" / script
    proc = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out.strip()


def main() -> int:
    failures: list[str] = []
    for script, token in GATES:
        ok, out = _run(script)
        if not ok or token not in out:
            failures.append(f"{script} failed (expected {token})")
            if out:
                failures.append(f"  output: {out.splitlines()[-1][:200]}")

    print(SMOKE_URLS.strip())
    print()

    if failures:
        print("verify_lifecycle_post_deploy_smoke: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print("verify_lifecycle_post_deploy_smoke: LIFECYCLE_POST_DEPLOY_SMOKE_PASS")
    print(f"  gates: {len(GATES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
