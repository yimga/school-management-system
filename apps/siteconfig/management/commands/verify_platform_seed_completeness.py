"""Fail when any canonical seed manifest or active-tenant baseline is incomplete."""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Fail-closed verification of platform catalogs and active tenant baselines."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only-tenant",
            default="",
            help="Limit tenant checks to one active school slug; platform catalogs remain checked.",
        )

    def handle(self, *args, **options):
        from apps.siteconfig.platform_seed_audit import audit_platform_seed

        report = audit_platform_seed(only_tenant=str(options.get("only_tenant") or ""))
        for check in report.checks:
            marker = "OK" if check.ok else "FAIL"
            writer = self.stdout.write if check.ok else self.stderr.write
            writer(f"[{marker}] {check.key}: {check.detail}")
        if not report.ok:
            raise CommandError(
                "Platform seed completeness failed: "
                + ", ".join(check.key for check in report.failures)
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Platform seed completeness OK: {len(report.checks)} checks."
            )
        )
