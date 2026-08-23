"""Every app must have exactly ONE migration leaf.

WHY THIS EXISTS. Two agents work this repo concurrently. On 2026-08-23 main landed
``schools/0085_advancement_grant_child_school_column`` while a branch added
``schools/0085_alter_school_subdomain``. Different FILENAMES, so git merged both without a
conflict and reported a clean tree -- and both declared ``0084`` as their dependency, so
the schools app came out of the merge with TWO leaf nodes. Django then refuses to migrate
the app at all: *"Conflicting migrations detected; multiple leaf nodes in the migration
graph."*

Nothing in the merge says so. Not the merge output, not ``git diff``, not a file-level
review -- the failure lives in a graph that neither side's diff shows, and each side's
migration is perfectly correct on its own. That is what makes it worth a gate rather than
a habit: it is invisible precisely at the moment somebody is deciding the merge went fine.

It is also cheap to be sure about. ``MigrationLoader`` builds the same graph Django builds
at ``migrate`` time, so this asks the authority rather than pattern-matching filenames --
a numeric-prefix check would miss a collision between ``0085_a`` and ``0085b_a``, and
would false-positive on the many legitimate merge migrations in this tree.

FIXING ONE. Renumber the LATER migration to sit after the other's chain and repoint its
``dependencies``, so the history stays linear -- see
``schools/0087_alter_school_subdomain``. Django's own ``makemigrations --merge`` writes a
merge migration instead, which is also valid; either way the app ends with one leaf.
Renumbering is usually kinder to read later, and it is what this repo has done before.

Whatever you choose, update any comment that names the migration by number. A comment
pointing at a migration that no longer exists is how the next person loses an hour.

No baseline: an app with two leaves cannot be deployed, so there is nothing to ratchet.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def leaves_by_app() -> dict[str, list[str]]:
    """Every app's leaf migrations, from the graph Django itself will build."""
    from django.db.migrations.loader import MigrationLoader

    loader = MigrationLoader(None, ignore_no_migrations=True)
    grouped: dict[str, list[str]] = {}
    for app_label, name in loader.graph.leaf_nodes():
        grouped.setdefault(app_label, []).append(name)
    return {app: sorted(names) for app, names in grouped.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = parser.parse_args()

    import django

    django.setup()

    grouped = leaves_by_app()
    conflicted = {app: names for app, names in grouped.items() if len(names) > 1}

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "finding_count": len(conflicted),
                    "apps_checked": len(grouped),
                    "conflicts": conflicted,
                },
                indent=2,
            )
        )
        return 1 if conflicted else 0

    for app, names in sorted(conflicted.items()):
        print(f"  {app}: {len(names)} leaves -- Django will refuse to migrate this app")
        for name in names:
            print(f"      {name}")

    if conflicted:
        print(
            f"\nmigration leaves: {len(conflicted)} app(s) with more than one.\n"
            "Fix: renumber the later migration after the other's chain and repoint its\n"
            "     dependencies (see schools/0087_alter_school_subdomain), or run\n"
            "     `manage.py makemigrations --merge`. Update any comment naming it."
        )
        return 1

    print(f"migration leaves: {len(grouped)} app(s) checked, all single-leaf.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
