"""Wave O2 — RLS runtime readiness preflight CLI."""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Preflight: verify the RLS tenant-isolation chain is intact "
        "(middleware wired, rls_context importable, USE_DJANGO_TENANTS=False, "
        "GUC settable on Postgres, at least one policy registered)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet", action="store_true",
            help="Suppress per-row output; rely on exit code (0=ready, 1=not).",
        )

    def handle(self, *args, **opts):
        from apps.schools.rls_readiness import assess_rls_readiness

        quiet = bool(opts.get("quiet"))
        report = assess_rls_readiness()

        if not quiet:
            self._render(report)

        if not report.ready:
            raise SystemExit(1)

    def _render(self, report) -> None:  # noqa: ANN001
        self.stdout.write("=== RLS runtime readiness preflight ===")
        self.stdout.write(f"DB vendor:              {report.backend_vendor}")
        self.stdout.write(
            f"Middleware wired:       {'YES' if report.middleware_wired else 'NO'}"
        )
        self.stdout.write(
            f"rls_context importable: {'YES' if report.rls_context_importable else 'NO'}"
        )
        self.stdout.write(
            f"USE_DJANGO_TENANTS=False: "
            f"{'YES' if report.use_django_tenants_disabled else 'NO (RLS bypassed!)'}"
        )
        if report.guc_settable is None:
            self.stdout.write("GUC settable:           SKIPPED (non-Postgres)")
        else:
            self.stdout.write(
                f"GUC settable:           {'YES' if report.guc_settable else 'NO'}"
            )
        if report.policy_count is None:
            self.stdout.write("RLS policy count:       SKIPPED (non-Postgres)")
        else:
            self.stdout.write(f"RLS policy count:       {report.policy_count}")
        if report.skipped_checks:
            self.stdout.write("")
            self.stdout.write("Skipped checks:")
            for reason in report.skipped_checks:
                self.stdout.write(f"  - {reason}")
        if report.error_detail:
            self.stdout.write(self.style.WARNING(f"!!  detail: {report.error_detail}"))

        self.stdout.write("")
        if report.ready:
            if report.backend_vendor != "postgresql":
                self.stdout.write(self.style.SUCCESS(
                    "READY (dev/test mode) — middleware + helpers wired; "
                    "Postgres-only checks skipped. Run on production DB "
                    "to verify GUC + policy count."
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    "READY — RLS chain intact end-to-end."
                ))
        else:
            n = report.issue_count()
            self.stdout.write(self.style.WARNING(
                f"NOT READY — {n} issue(s). Tenant isolation may be at risk."
            ))
