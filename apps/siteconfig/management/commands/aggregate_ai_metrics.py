"""
Aggregate AI Gateway cache metrics into AIGatewayMetric for observability dashboards.
Run daily (e.g. via cron or Celery Beat). Reads cache keys ai:metrics:YYYY-MM-DD:* and
upserts into siteconfig_aigatewaymetric; optionally deletes consumed keys.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.db import DatabaseError, IntegrityError

from apps.platform_runtime.structured_logging import log_exception_with_context

# §2.4 Typed exceptions for allowlist shrink (broad_exception_audit)
_AGGREGATE_AI_METRICS_CACHE_ITER_ERRORS = (
    ConnectionError,
    OSError,
    TypeError,
    ValueError,
    AttributeError,
    RuntimeError,
)
_AGGREGATE_AI_METRICS_KEY_ERRORS = (
    DatabaseError,
    IntegrityError,
    ValueError,
    TypeError,
    AttributeError,
    KeyError,
)


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
        from services.ai_gateway import _cost_class_for_tier

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
        except _AGGREGATE_AI_METRICS_CACHE_ITER_ERRORS as e:
            log_exception_with_context(
                "aggregate_ai_metrics: cache key iteration failed",
                school_id=None,
                extra={"command": "aggregate_ai_metrics", "prefix": prefix, "error": str(e)},
            )
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
            tenant_id, task_type, tier = parts[0], parts[1], parts[2]
            cost_class = parts[3] if len(parts) > 3 else _cost_class_for_tier(tier)
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
                review_count = int(bucket.get("review_count", 0) or 0)
                accepted_count = int(bucket.get("accepted_count", 0) or 0)
                manual_correction_count = int(bucket.get("manual_correction_count", 0) or 0)
                if count <= 0 and review_count <= 0:
                    continue
                latency_sum = float(bucket.get("latency_sum", 0) or 0)
                failures = int(bucket.get("failures", 0) or 0)
                schema_fail = int(bucket.get("schema_fail", 0) or 0)
                _, created_flag = AIGatewayMetric.objects.update_or_create(
                    date=agg_date,
                    tenant_id=tid,
                    task_type=task_type,
                    tier=tier,
                    cost_class=cost_class,
                    defaults={
                        "request_count": count,
                        "total_latency_ms": latency_sum,
                        "failure_count": failures,
                        "schema_validation_failures": schema_fail,
                        "review_count": review_count,
                        "accepted_count": accepted_count,
                        "manual_correction_count": manual_correction_count,
                    },
                )
                if created_flag:
                    created += 1
                else:
                    updated += 1
                if not options.get("no_delete"):
                    cache.delete(key)
            except _AGGREGATE_AI_METRICS_KEY_ERRORS as e:
                log_exception_with_context(
                    "aggregate_ai_metrics: skip key",
                    school_id=None,
                    extra={"command": "aggregate_ai_metrics", "key": key, "error": str(e)},
                )
                self.stdout.write(self.style.WARNING(f"Skip key {key}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Aggregated {agg_date}: created={created}, updated={updated}"))
