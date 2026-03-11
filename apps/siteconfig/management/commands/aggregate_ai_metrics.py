"""
Aggregate AI Gateway cache metrics into AIGatewayMetric for observability dashboards.
Run daily (e.g. via cron or Celery Beat). Reads cache keys ai:metrics:YYYY-MM-DD:* and
upserts into siteconfig_aigatewaymetric; optionally deletes consumed keys.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.core.cache import cache


class Command(BaseCommand):
    help = "Aggregate AI gateway cache metrics into AIGatewayMetric table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Date to aggregate (YYYY-MM-DD); default: yesterday.",
        )
        parser.add_argument(
            "--no-delete",
            action="store_true",
            help="Do not delete cache keys after aggregating.",
        )

    def handle(self, *args, **options):
        from apps.siteconfig.models import AIGatewayMetric

        date_str = options.get("date")
        if date_str:
            try:
                agg_date = date.fromisoformat(date_str)
            except ValueError:
                self.stdout.write(self.style.ERROR(f"Invalid --date: {date_str} (use YYYY-MM-DD)"))
                return
        else:
            agg_date = date.today() - timedelta(days=1)

        prefix = f"ai:metrics:{agg_date.isoformat()}:"
        keys = []
        try:
            if hasattr(cache, "iter_keys"):
                keys = list(cache.iter_keys(prefix))
            elif hasattr(cache, "keys"):
                keys = cache.keys(prefix) or []
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Cache key iteration: {e}"))

        if not keys:
            self.stdout.write(self.style.WARNING("No cache keys found for this date. Ensure AI_GATEWAY_METRICS_ENABLED and cache backend support key iteration."))
            return

        created = 0
        updated = 0
        for key in keys:
            if not key.startswith(prefix):
                continue
            suffix = key[len(prefix):]
            parts = suffix.split(":")
            if len(parts) < 3:
                continue
            tenant_id, task_type, tier = parts[0], parts[1], ":".join(parts[2:]) if len(parts) > 3 else parts[2]
            try:
                bucket = cache.get(key)
                if not bucket or not isinstance(bucket, dict):
                    continue
                from uuid import UUID
                try:
                    tid = UUID(tenant_id) if tenant_id != "global" else None
                except (ValueError, TypeError):
                    tid = None
                count = bucket.get("count", 0) or 0
                if count <= 0:
                    continue
                latency_sum = float(bucket.get("latency_sum", 0) or 0)
                failures = int(bucket.get("failures", 0) or 0)
                schema_fail = int(bucket.get("schema_fail", 0) or 0)
                obj, created_flag = AIGatewayMetric.objects.update_or_create(
                    date=agg_date,
                    tenant_id=tid,
                    task_type=task_type,
                    tier=tier,
                    defaults={
                        "request_count": count,
                        "total_latency_ms": latency_sum,
                        "failure_count": failures,
                        "schema_validation_failures": schema_fail,
                    },
                )
                if created_flag:
                    created += 1
                else:
                    updated += 1
                if not options.get("no_delete"):
                    cache.delete(key)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Skip key {key}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Aggregated {agg_date}: created={created}, updated={updated}"))
