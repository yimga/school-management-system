#!/usr/bin/env python3
"""Synthetic chain verifier — daily ops next-best actions resolve for every role."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from apps.academics.year_close import academic_year_close_in_progress
    from apps.platform_runtime.tenant_daily_ops import (
        WORKFLOW_ACTIONS,
        next_best_actions_for_role,
        resolve_action_urls,
    )
    from apps.platform_runtime.tenant_operational_lifecycle import (
        ALL_OPERATIONAL_STATES,
        resolve_operational_lifecycle_state,
    )
    from apps.schools.models import School

    failures: list[str] = []

    school = School(
        name="Synthetic Ops School",
        slug="synthetic-ops-school",
        subdomain="synthetic-ops-school",
        is_active=True,
    )
    school.pk = 1

    if not WORKFLOW_ACTIONS:
        failures.append("WORKFLOW_ACTIONS empty")

    roles_checked = 0
    for role in WORKFLOW_ACTIONS:
        user = type("U", (), {"role": role})()
        raw = next_best_actions_for_role(school, user)
        if not raw:
            failures.append(f"{role}: no next-best actions")
            continue
        if any(a.get("school_id") != "1" for a in raw):
            failures.append(f"{role}: school_id not stamped on all actions")
        resolved = resolve_action_urls(raw)
        if not all("url" in a for a in resolved):
            failures.append(f"{role}: resolve_action_urls missing url field")
        roles_checked += 1

    if roles_checked < 4:
        failures.append(f"expected >=4 roles in WORKFLOW_ACTIONS, got {roles_checked}")

    try:
        academic_year_close_in_progress(school=None)
    except TypeError:
        pass
    except Exception as exc:
        failures.append(f"academic_year_close_in_progress raised: {exc}")

    if not ALL_OPERATIONAL_STATES:
        failures.append("ALL_OPERATIONAL_STATES empty")
    else:
        ops = resolve_operational_lifecycle_state(school)
        if ops.get("state") not in ALL_OPERATIONAL_STATES:
            failures.append("resolve_operational_lifecycle_state returned unknown state")

    if failures:
        print("verify_tenant_daily_ops_synthetic_chain: FAIL")
        for item in failures:
            print(f"- {item}")
        return 1

    print(
        "verify_tenant_daily_ops_synthetic_chain: "
        f"TENANT_DAILY_OPS_SYNTHETIC_CHAIN_PASS ({roles_checked} roles)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
