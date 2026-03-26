"""
Generate an AI quality scorecard by task type from AIGatewayMetric.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Sum


class Command(BaseCommand):
    help = "Print AI quality scorecard (acceptance/manual correction/schema fail) by task_type."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Lookback window in days (default: 7).",
        )
        parser.add_argument(
            "--task-type",
            type=str,
            default=None,
            help="Optional task_type filter (e.g. general_chat).",
        )

    def handle(self, *args, **options):
        from apps.siteconfig.models import AIGatewayMetric

        days = max(1, min(30, int(options.get("days") or 7)))
        since = date.today() - timedelta(days=days - 1)
        qs = AIGatewayMetric.objects.filter(date__gte=since)
        task_type = (options.get("task_type") or "").strip().lower()
        if task_type:
            qs = qs.filter(task_type=task_type)

        grouped = (
            qs.values("task_type")
            .annotate(
                request_count=Sum("request_count"),
                failure_count=Sum("failure_count"),
                schema_fail=Sum("schema_validation_failures"),
                review_count=Sum("review_count"),
                accepted_count=Sum("accepted_count"),
                manual_correction_count=Sum("manual_correction_count"),
            )
            .order_by("task_type")
        )
        rows = list(grouped)
        if not rows:
            self.stdout.write(self.style.WARNING("No AI metrics found for this window."))
            return

        self.stdout.write(f"AI quality scorecard since {since.isoformat()} (days={days})")
        for row in rows:
            req = int(row.get("request_count") or 0)
            fail = int(row.get("failure_count") or 0)
            schema = int(row.get("schema_fail") or 0)
            review = int(row.get("review_count") or 0)
            accepted = int(row.get("accepted_count") or 0)
            corrected = int(row.get("manual_correction_count") or 0)
            acceptance_rate = (accepted / review * 100.0) if review else 0.0
            correction_rate = (corrected / review * 100.0) if review else 0.0
            schema_fail_rate = (schema / req * 100.0) if req else 0.0
            failure_rate = (fail / req * 100.0) if req else 0.0
            self.stdout.write(
                f"- {row['task_type']}: requests={req}, review={review}, "
                f"acceptance_rate={acceptance_rate:.1f}%, manual_correction_rate={correction_rate:.1f}%, "
                f"schema_fail_rate={schema_fail_rate:.1f}%, failure_rate={failure_rate:.1f}%"
            )
