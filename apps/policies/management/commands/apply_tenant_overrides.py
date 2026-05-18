"""Management command: apply a declarative tenant-overrides file.

Usage::
    python manage.py apply_tenant_overrides path/to/overrides.json
    python manage.py apply_tenant_overrides path/to/overrides.yaml --prune
    python manage.py apply_tenant_overrides --stdin   # read from stdin
"""

from __future__ import annotations

import json
import sys

from django.core.management.base import BaseCommand, CommandError

from apps.policies.declarative_overrides import (
    apply_overrides_dict,
    apply_overrides_file,
)


class Command(BaseCommand):
    help = "Apply declarative tenant policy overrides from a JSON/YAML file."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=None)
        parser.add_argument(
            "--stdin", action="store_true", help="Read the JSON payload from stdin."
        )
        parser.add_argument(
            "--prune",
            action="store_true",
            help="Delete TenantPolicyOverride rows for the schools in the payload "
            "that are NOT mentioned in the file.",
        )
        parser.add_argument("--json", action="store_true", help="Emit JSON result.")

    def handle(self, *args, **options):
        if options["stdin"]:
            payload = json.loads(sys.stdin.read())
            result = apply_overrides_dict(payload, prune=options["prune"])
        elif options.get("path"):
            result = apply_overrides_file(options["path"], prune=options["prune"])
        else:
            raise CommandError("Provide a file path or --stdin.")
        out = result.asdict()
        if options["json"]:
            self.stdout.write(json.dumps(out, indent=2))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"created={out['created']} updated={out['updated']} "
                f"unchanged={out['unchanged']} pruned={out['pruned']}"
            )
        )
        for err in out["errors"]:
            self.stdout.write(self.style.WARNING(f"  warn: {err}"))
