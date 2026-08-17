"""Rewind the edge sync cursors so the next cycle replays EVERYTHING.

The box-side twin of the cloud's "Queue full resync" button, for an operator who is
already on the box (or driving it over SSH) and does not want to wait for the directive
to be collected. This is the supported answer to "the box has missed a lot of changes":
rewind the position and let the ordinary, idempotent apply path replay the corpus, rather
than hand-patching rows.

Safe to run repeatedly. It writes no tenant data itself — it only clears cursors — and
with ``--run`` it then drives normal cycles until the backlog is drained.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Rewind edge sync cursors (full resync). Optionally drive cycles until drained."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="", help="School slug (default: the box's own school).")
        parser.add_argument(
            "--direction",
            default="",
            choices=["", "push", "pull"],
            help="Rewind only one direction (default: both).",
        )
        parser.add_argument(
            "--run",
            action="store_true",
            help="After rewinding, run sync cycles until nothing is left to push.",
        )
        parser.add_argument(
            "--max-cycles",
            dest="max_cycles",
            type=int,
            default=50,
            help="Ceiling on cycles driven by --run, so the command always terminates.",
        )

    def handle(self, *args, **options):
        from apps.schools.models import School
        from apps.sync_engine.edge_scheduler import resolve_edge_school
        from apps.sync_engine.models import reset_sync_cursors

        slug = (options.get("slug") or "").strip().lower()
        if slug:
            school = School.objects.filter(slug=slug).first()
            if school is None:
                raise CommandError(f"No school with slug {slug!r}.")
        else:
            school = resolve_edge_school()
            if school is None:
                raise CommandError(
                    "Could not resolve this box's school — pass --slug or set "
                    "RMC_EDGE_SCHOOL_SLUG."
                )

        direction = (options.get("direction") or "").strip()
        rewound = reset_sync_cursors(school, direction=direction)
        scope = direction or "push+pull"
        self.stdout.write(
            f"edge-resync: rewound {rewound} cursor row(s) for {school.slug} ({scope})."
        )

        if not options.get("run"):
            self.stdout.write(
                "edge-resync: the next scheduled cycle will replay everything. "
                "Pass --run to drain it now."
            )
            return

        from apps.sync_engine import sync_runner

        max_cycles = max(1, int(options.get("max_cycles") or 50))
        total_pushed = total_pulled = 0
        for cycle in range(1, max_cycles + 1):
            result = sync_runner.run_sync_cycle(school, mode="live")
            if not result.get("enabled", True):
                self.stdout.write(self.style.WARNING(f"edge-resync: {result.get('message')}"))
                return
            total_pushed += int(result.get("pushed") or 0)
            total_pulled += int(result.get("pulled") or 0)
            self.stdout.write(
                f"  cycle {cycle}: pushed {result.get('pushed')} pulled "
                f"{result.get('pulled')} ok={result.get('ok')}"
            )
            if not result.get("ok"):
                # A cursor never advances past unconfirmed work, so stopping here loses
                # nothing — the next run resumes from the same position.
                self.stderr.write(
                    self.style.WARNING(
                        f"edge-resync: stopping on error: {result.get('error')}. "
                        "Cursors are unmoved past the failure; re-run when it clears."
                    )
                )
                break
            if not result.get("pushed") and not result.get("pulled"):
                self.stdout.write(self.style.SUCCESS("edge-resync: drained."))
                break
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"edge-resync: hit the {max_cycles}-cycle ceiling with work remaining; "
                    "re-run to continue (progress is durable)."
                )
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"edge-resync: total pushed {total_pushed}, pulled {total_pulled}."
            )
        )
