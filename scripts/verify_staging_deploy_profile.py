#!/usr/bin/env python3
"""
Document staging/production deploy readiness from manage.py check --deploy.

Writes docs/generated/staging_deploy_readiness.json with expected env overrides.
Does not claim STAGING READY unless STAGING_PROFILE=1 and warnings are cleared.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = REPO_ROOT / "docs" / "generated" / "staging_deploy_readiness.json"
OUT_MD = REPO_ROOT / "docs" / "generated" / "staging_deploy_readiness.md"

STAGING_ENV = {
    "DEBUG": "0",
    "SECRET_KEY": "staging-profile-not-for-production-use-change-me-32chars",
    "SECURE_SSL_REDIRECT": "1",
    "SESSION_COOKIE_SECURE": "1",
    "CSRF_COOKIE_SECURE": "1",
    "SECURE_HSTS_SECONDS": "31536000",
}


def main() -> int:
    env = os.environ.copy()
    use_staging = env.get("STAGING_PROFILE", "").strip() in ("1", "true", "yes")
    if use_staging:
        env.update(STAGING_ENV)

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "manage.py"), "check", "--deploy", "--settings=config.settings"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    warnings = [line.strip() for line in combined.splitlines() if "security.W" in line or "SecurityWarning" in line]

    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    ready = use_staging and proc.returncode == 0 and not warnings

    report = {
        "generated_at": generated,
        "staging_profile_applied": use_staging,
        "check_deploy_exit_code": proc.returncode,
        "security_warnings": warnings,
        "required_staging_env": STAGING_ENV,
        "verdict": "STAGING PROFILE READY (local simulation)" if ready else "STAGING UNKNOWN — apply STAGING_PROFILE=1 on deploy host",
        "honesty": "Real staging/prod still requires operator secrets, TLS termination, and DATABASE_URL; this script only documents Django deploy checks.",
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(
        f"# Staging deploy readiness\n\n"
        f"- Generated: {generated}\n"
        f"- STAGING_PROFILE applied: {use_staging}\n"
        f"- Verdict: **{report['verdict']}**\n\n"
        f"Warnings ({len(warnings)}):\n"
        + "\n".join(f"- `{w}`" for w in warnings[:20])
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_JSON}")
    print(report["verdict"])
    if not use_staging:
        print("Hint: STAGING_PROFILE=1 python scripts/verify_staging_deploy_profile.py")
        return 0
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
