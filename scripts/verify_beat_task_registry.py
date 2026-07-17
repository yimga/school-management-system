#!/usr/bin/env python3
"""Gate: every CELERY_BEAT_SCHEDULE entry must name a REGISTERED Celery task.

A beat entry naming a task that was never registered is a SILENT no-op: beat
looks it up, finds nothing, and the job simply never runs. Nothing errors,
nothing logs, and the entry sits in settings.py looking wired forever.

This is not hypothetical. It is how the tenant DR snapshot never ran:

    settings.py:2430   "task": "lifecycle.capture_tenant_immutable_snapshots_daily"
    apps/lifecycle/tasks_dr_snapshot.py:13   @shared_task(name="lifecycle.capture_tenant_immutable_snapshots_daily")

...which looks correct, and is dead, because config/celery.py:19 calls a BARE
``app.autodiscover_tasks()``. Bare autodiscovery imports only ``<app>/tasks.py``
for each installed app -- and apps/lifecycle has NO tasks.py, only
tasks_dr_snapshot.py and tasks_stall_watch.py. Neither module is ever imported,
so neither task is ever registered.

RULE: a @shared_task in any module NOT named exactly ``tasks.py`` is invisible to
autodiscovery. It must be imported explicitly (AppConfig.ready(), or a tasks.py
that re-exports it) or its beat entry is decoration.

Same family as the middleware topology gap and the RLS static-TABLES list: a
second registry that drifts from the first, with nothing checking the join.

WHY A RUNTIME PROBE AND NOT A GREP: grep would happily match the @shared_task
name in tasks_dr_snapshot.py and declare the entry wired. The name being present
in the source proves nothing about whether the module is IMPORTED. Only the live
registry knows. Probe the effect, not the source.

Exit 0 = every beat entry resolves. Exit 1 = at least one silent no-op.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

# Running as `python scripts/verify_beat_task_registry.py` puts scripts/ on sys.path,
# not the repo root, so `import config` would ModuleNotFoundError. Prepend the repo
# root so the gate fails for REAL findings only -- a gate that dies on import looks
# identical to a gate that caught something, and both exit 1.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# Measured baseline of entries that are dead RIGHT NOW. This is debt, not approval:
# every run prints them loudly, the list may only SHRINK, and a NEW dead entry fails
# the gate. Baselining silently would make this the very thing it exists to catch --
# a gate that reports OK while the job never runs.
#
# These share one root cause: the @shared_task lives in a module that is not named
# exactly `tasks.py`, so config/celery.py:19's bare autodiscover_tasks() never imports
# it. Fixing that in one shot would wake ALL of them simultaneously -- including a purge
# job and outbound webhooks -- so each must be woken deliberately, not as a side effect.
#
# RESOLVED 2026-07-17: `lifecycle-tenant-immutable-snapshot-daily` was woken
# SURGICALLY by adding apps/lifecycle/tasks.py (re-exporting ONLY the two
# DR-snapshot tasks -- verified via the live registry that it wakes no other
# task; see apps/lifecycle/tests/test_dr_task_registration.py). Its durability
# was also wired: settings now READ TENANT_SNAPSHOT_S3_BUCKET / _S3_ENDPOINT /
# _PRIMARY_DIR / _SECONDARY_DIR from the env (they were referenced-but-undeclared,
# so setting the env var did nothing), boto3 is uncommented in
# requirements_optional.txt, and render.yaml documents the durable-store options.
# Removed from the baseline so the list can only SHRINK.
KNOWN_DEAD_ENTRIES: dict[str, str] = {
    "integrations-refresh-oauth-tokens":
        "OAuth tokens are never refreshed -> tenant integrations silently expire. "
        "Waking it starts outbound calls to third-party identity providers.",
    "integrations-fetch-mailboxes":
        "Due mailboxes never fetched. Waking it starts outbound mailbox polling.",
    "integrations-renew-push-subscriptions":
        "Push subscriptions never renewed -> they lapse. Waking it starts outbound calls.",
    "accounts-verify-audit-chain":
        "Weekly audit-chain verification never runs -> tamper would go undetected.",
    "siteconfig-sweep-pending-custom-domains":
        "Pending custom domains are never swept -> a tenant's custom domain never activates.",
    "migration-cloud-token-rotation-watchdog":
        "Token-rotation watchdog never fires.",
    "migration-cloud-webhook-deliver-due":
        "Due webhooks are never delivered. Waking this SENDS REAL OUTBOUND WEBHOOKS, "
        "possibly a backlog of them at once. Drain/date-bound the queue before enabling.",
    "migration-cloud-retention-audit-monthly":
        "DESTRUCTIVE IF WOKEN: purge_completed_migration_bundles_audit_task DELETES "
        "completed migration bundles. Review retention windows before enabling.",
    "migration-cloud-smoke-nightly":
        "Nightly smoke against a synthetic tenant never runs. Waking it CREATES tenant "
        "data nightly.",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--settings",
        default=os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings"),
        help="Django settings module to probe (default: DJANGO_SETTINGS_MODULE or config.settings)",
    )
    args = parser.parse_args()

    os.environ["DJANGO_SETTINGS_MODULE"] = args.settings
    import django

    django.setup()

    from config.celery import app

    # Force the same import work a real worker/beat process does, so the registry
    # we compare against is the one production would actually have.
    app.loader.import_default_modules()

    registered = set(app.tasks.keys())
    schedule = app.conf.beat_schedule or {}

    if not schedule:
        print("FAIL: beat schedule is empty -- nothing to verify. Did settings load?")
        return 1

    dead: list[tuple[str, str]] = []
    for entry_key, entry in schedule.items():
        task_name = (
            entry.get("task")
            if isinstance(entry, dict)
            else getattr(entry, "task", None)
        )
        if not task_name:
            dead.append((entry_key, "<no task name>"))
            continue
        if task_name not in registered:
            dead.append((entry_key, task_name))

    dead_keys = {k for k, _ in dead}
    new_dead = [(k, t) for k, t in dead if k not in KNOWN_DEAD_ENTRIES]
    # An entry that was dead and now resolves is a FIX -- make the author delete it
    # from the baseline so the list can only shrink.
    revived = [k for k in KNOWN_DEAD_ENTRIES if k not in dead_keys]

    print(f"settings:          {args.settings}")
    print(f"beat entries:      {len(schedule)}")
    print(f"registered tasks:  {len(registered)}")
    print(f"dead entries:      {len(dead)}  (known={len(dead) - len(new_dead)}, NEW={len(new_dead)})")

    if dead_keys & set(KNOWN_DEAD_ENTRIES):
        # Always print the baseline. A silent baseline is how a gate starts lying.
        print(
            "\nKNOWN-DEAD beat entries (measured debt -- these jobs DO NOT RUN in this "
            "deployment):"
        )
        for entry_key in sorted(dead_keys & set(KNOWN_DEAD_ENTRIES)):
            print(f"  - {entry_key}\n      {KNOWN_DEAD_ENTRIES[entry_key]}")

    failed = False
    if new_dead:
        failed = True
        print(
            f"\nFAIL: {len(new_dead)} NEW beat entr(ies) name a task that is NOT "
            "registered. Beat looks them up, finds nothing, and the job never runs -- "
            "silently, with no error and no log.\n"
            "  Most likely cause: the @shared_task lives in a module not named tasks.py, "
            "so config/celery.py's bare autodiscover_tasks() never imports it. Fix by "
            "importing it (AppConfig.ready(), or a tasks.py that re-exports it), or "
            "remove the beat entry."
        )
        for entry_key, task_name in sorted(new_dead):
            print(f"  - {entry_key}\n      -> {task_name}")

    if revived:
        failed = True
        print(
            f"\nFAIL: {len(revived)} entr(ies) are in KNOWN_DEAD_ENTRIES but now resolve. "
            "That is a fix -- delete them from the baseline so the list only shrinks."
        )
        for entry_key in sorted(revived):
            print(f"  - {entry_key}")

    if failed:
        return 1

    if dead:
        print(
            f"\nOK (baseline held): no NEW dead beat entries. {len(dead)} known-dead "
            "entries remain -- see above. This is not 'passing'; it is 'not getting worse'."
        )
    else:
        print("\nOK: every beat entry resolves to a registered task.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
