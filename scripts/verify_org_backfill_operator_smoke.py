#!/usr/bin/env python3
"""Operator smoke for Organization backfill from hierarchy (Phase 6B).

Validates:
  1. ``manage.py backfill_organizations_from_hierarchy`` dry-run exits 0 with JSON shape.
  2. In-process apply on a synthetic parent_school tree (rolled back — no persistent writes).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated" / "org_backfill_operator_smoke_audit.json"

JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


def _mgmt_command_dry_run() -> tuple[bool, str, dict | None]:
    cmd = [
        sys.executable,
        str(REPO / "manage.py"),
        "backfill_organizations_from_hierarchy",
    ]
    env = os.environ.copy()
    env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc), None

    combined = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        return False, combined[-400:], None

    match = JSON_BLOCK_RE.search(combined)
    if not match:
        return False, "dry-run stdout missing JSON payload", None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc}", None

    for key in ("organizations_created", "schools_linked", "schools_skipped", "notes"):
        if key not in payload:
            return False, f"JSON missing key {key!r}", None
    if not isinstance(payload["notes"], list):
        return False, "notes must be a list", None

    return True, "dry-run JSON contract OK", payload


def _in_process_apply_smoke() -> tuple[bool, str]:
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django
    from django.db import transaction

    django.setup()

    from apps.governance.backfill_organizations import backfill_from_parent_school_trees
    from apps.governance.models import Organization
    from apps.schools.models import School

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    root_slug = f"org-backfill-smoke-root-{suffix}"
    child_slug = f"org-backfill-smoke-child-{suffix}"

    try:
        with transaction.atomic():
            root = School.objects.create(
                name="Org Backfill Smoke Root",
                slug=root_slug,
                subdomain=root_slug,
            )
            School.objects.create(
                name="Org Backfill Smoke Child",
                slug=child_slug,
                subdomain=child_slug,
                parent_school=root,
            )

            dry = backfill_from_parent_school_trees(apply=False)
            if dry.organizations_created < 1 or dry.schools_linked < 2:
                return (
                    False,
                    f"dry-run counts unexpected: orgs={dry.organizations_created} "
                    f"linked={dry.schools_linked}",
                )

            applied = backfill_from_parent_school_trees(apply=True)
            if applied.organizations_created < 1 or applied.schools_linked < 2:
                return (
                    False,
                    f"apply counts unexpected: orgs={applied.organizations_created} "
                    f"linked={applied.schools_linked}",
                )

            org = Organization.objects.filter(slug=root_slug).first()
            if org is None:
                return False, "Organization row not created after apply"

            root.refresh_from_db()
            if root.organization_id != org.pk:
                return False, "root school not linked to Organization"

            second = backfill_from_parent_school_trees(apply=True)
            if second.organizations_created != 0:
                return False, "idempotent second apply created extra organizations"

            transaction.set_rollback(True)
    except Exception as exc:
        return False, str(exc)

    return True, "in-process apply + idempotence OK (rolled back)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Org backfill operator smoke gate")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    checks: list[dict[str, str]] = []

    ok, proof, payload = _mgmt_command_dry_run()
    checks.append(
        {
            "id": "mgmt_command_dry_run",
            "status": "PASS" if ok else "FAIL",
            "proof": proof,
        }
    )
    if not ok:
        failures.append(f"mgmt command dry-run: {proof}")
    elif payload is not None:
        checks[-1]["organizations_created"] = str(payload.get("organizations_created"))

    ok, proof = _in_process_apply_smoke()
    checks.append({"id": "in_process_apply_smoke", "status": "PASS" if ok else "FAIL", "proof": proof})
    if not ok:
        failures.append(f"in-process smoke: {proof}")

    verdict = (
        "ORG_BACKFILL_OPERATOR_SMOKE_PASS"
        if not failures
        else "ORG_BACKFILL_OPERATOR_SMOKE_FAIL"
    )
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "finding_count": len(failures),
        "checks": checks,
        "failures": failures,
    }
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(f"verify_org_backfill_operator_smoke: {verdict}", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_org_backfill_operator_smoke: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
