"""Wave K4 — preflight before flipping ``DATA_RESIDENCY_ENFORCE=True``.

Wraps :func:`apps.schools.residency_readiness.assess_readiness` with
operator-friendly output and the right exit semantics for CI / cron.

Usage:

    # Quick dry check (exit 0/1 based on readiness):
    python manage.py verify_residency_readiness

    # Narrow to one tenant during investigation:
    python manage.py verify_residency_readiness --school tenant-slug

    # Suppress per-row output, just exit code:
    python manage.py verify_residency_readiness --quiet
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Preflight check before flipping DATA_RESIDENCY_ENFORCE=True. "
        "Reports missing region replicas, misaligned tenants, and "
        "tenants whose data_region needs backfill."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school", default="",
            help="Optional school slug filter (narrows the audit to one tenant).",
        )
        parser.add_argument(
            "--quiet", action="store_true",
            help="Suppress per-row output; rely on exit code (0=ready, 1=not).",
        )

    def handle(self, *args, **opts):
        from apps.schools.residency_readiness import assess_readiness

        slug = (opts.get("school") or "").strip()
        quiet = bool(opts.get("quiet"))
        report = assess_readiness(slug_filter=slug)

        if not quiet:
            self._render(report)

        if not report.ready:
            raise SystemExit(1)

    def _render(self, report) -> None:  # noqa: ANN001 — ReadinessReport from helper
        self.stdout.write("=== Data residency readiness preflight ===")
        self.stdout.write(f"Active schools examined: {report.schools_total}")
        if report.schools_active_regions:
            self.stdout.write(
                "Active regions in use: "
                + ", ".join(sorted(report.schools_active_regions))
            )
        else:
            self.stdout.write("Active regions in use: (none — only 'global')")

        # Registered replica aliases
        if report.registered_replica_aliases:
            pairs = ", ".join(
                f"{r}→{a}" for r, a in sorted(report.registered_replica_aliases.items())
            )
            self.stdout.write(f"Registered replica aliases: {pairs}")
        else:
            self.stdout.write(
                "Registered replica aliases: (none — set "
                "DATA_RESIDENCY_REPLICA_<REGION> env vars to register)"
            )

        self.stdout.write("")
        self._render_issue(
            report.missing_replicas,
            "Missing region replicas",
            fmt=lambda r: f"  - {r}  (set env DATA_RESIDENCY_REPLICA_{r.upper()}=<url>)",
        )
        self._render_issue(
            report.misaligned_schools,
            "Misaligned tenants (operational ≠ regulatory)",
            fmt=lambda row: f"  - {row[0]}  regulatory={row[1]}  operational={row[2]}",
        )
        self._render_issue(
            report.unbackfilled_schools,
            "Tenants needing data_region backfill",
            fmt=lambda row: (
                f"  - {row[0]}  country={row[1]}  derived={row[2]}  "
                f"(run: manage.py verify_data_residency --fix-derive)"
            ),
        )

        self.stdout.write("")
        if report.ready:
            self.stdout.write(self.style.SUCCESS(
                "READY — safe to flip DATA_RESIDENCY_ENFORCE=True."
            ))
        else:
            n = report.issue_count()
            self.stdout.write(self.style.WARNING(
                f"NOT READY — {n} issue(s) above must be resolved first."
            ))

    def _render_issue(self, items, heading: str, *, fmt) -> None:
        if not items:
            self.stdout.write(self.style.SUCCESS(f"OK  {heading}: none"))
            return
        self.stdout.write(self.style.WARNING(f"!!  {heading}: {len(items)}"))
        for item in items:
            self.stdout.write(fmt(item))
