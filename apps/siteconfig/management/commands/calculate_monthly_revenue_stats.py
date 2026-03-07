"""
Phase E: Run calculate_monthly_stats to fill RevenueSnapshot.
Use for manual run or cron; Celery Beat also runs this daily.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Compute monthly revenue and waiver metrics (RevenueSnapshot)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Snapshot month (YYYY-MM); default: current month.",
        )

    def handle(self, *args, **options):
        from apps.siteconfig.billing_services import calculate_monthly_stats

        date_str = options.get("date")
        snapshot_date = None
        if date_str:
            try:
                snapshot_date = timezone.datetime.strptime(date_str + "-01", "%Y-%m-%d").date()
            except ValueError:
                self.stdout.write(self.style.ERROR(f"Invalid --date: {date_str} (use YYYY-MM)"))
                return
        result = calculate_monthly_stats(snapshot_date=snapshot_date)
        self.stdout.write(
            self.style.SUCCESS(
                f"Snapshot {result['snapshot_date']}: "
                f"MRR={result['total_actual']:.2f}, waived={result['total_waived']:.2f}, "
                f"schools={result['schools_processed']}"
            )
        )
