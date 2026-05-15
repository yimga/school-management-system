"""Wave D — G3: safe wrapper around ``manage.py migrate``.

Usage::

    python manage.py apply_platform_migration --plan
    python manage.py apply_platform_migration --target schools
    python manage.py apply_platform_migration --dangerous --notes "TKT-1234"

Refuses to apply destructive operations (RemoveField, RenameField,
RenameModel, DeleteModel, AlterField, RunSQL) without ``--dangerous``.
Records the apply in ``SchemaRollout`` + per-alias ``SchemaRolloutAlias``.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.platform_runtime.schema_rollout import run_rollout


class Command(BaseCommand):
    help = "Apply Django migrations across all known DB aliases with an audit trail."

    def add_arguments(self, parser):
        parser.add_argument("--target", default="",
                            help="App label or 'app.0001' migration target (passes through to migrate).")
        parser.add_argument("--dangerous", action="store_true",
                            help="Acknowledge that destructive operations will run.")
        parser.add_argument("--plan", action="store_true", dest="dry_run",
                            help="Show what would run; no schema changes.")
        parser.add_argument("--notes", default="",
                            help="Free-form audit text (ticket ref, deploy ID).")

    def handle(self, *args, **opts):
        result = run_rollout(
            target=opts.get("target") or "",
            dangerous=bool(opts.get("dangerous")),
            dry_run=bool(opts.get("dry_run")),
            notes=opts.get("notes") or "",
        )
        if not result.get("ok") and result.get("reason") == "dangerous_migrations_present":
            self.stderr.write(self.style.ERROR(result["message"]))
            for app_label, name, op in result.get("dangerous_ops") or []:
                self.stderr.write(f"  · {app_label}.{name}: {op}")
            return

        status = result.get("status", "unknown")
        rid = result.get("rollout_id")
        self.stdout.write(self.style.SUCCESS(
            f"rollout #{rid} → {status}  ({len(result.get('aliases') or [])} alias(es))"
        ))
        for alias, info in (result.get("summary") or {}).items():
            mark = "ok" if info.get("ok") else "FAIL"
            self.stdout.write(f"  · {alias}: {mark}")
            if info.get("stderr"):
                for line in info["stderr"].splitlines():
                    self.stdout.write(f"      {line}")
