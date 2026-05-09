"""Daily incremental analytics export to an external warehouse.

Usage::

    python manage.py export_to_warehouse [--since YYYY-MM-DD] [--dry-run]

Reads ``settings.ANALYTICS_WAREHOUSE_URL``; if unset the command emits a
clear "warehouse not configured" message and exits 0 (so cron does not page).
Uses stdlib ``urllib`` — no extra dependency.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date


class Command(BaseCommand):
    help = "Daily incremental export of analytics rollups to the configured warehouse."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since",
            type=str,
            default="",
            help="ISO date YYYY-MM-DD; default = yesterday.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print payload counts; do not POST.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10000,
            help="Max rows per slice (safety cap).",
        )

    def handle(self, *args, **opts):
        url = (getattr(settings, "ANALYTICS_WAREHOUSE_URL", "") or "").strip()
        api_key = (getattr(settings, "ANALYTICS_WAREHOUSE_API_KEY", "") or "").strip()

        since_raw = (opts.get("since") or "").strip()
        if since_raw:
            since = parse_date(since_raw)
            if since is None:
                self.stderr.write(self.style.ERROR(f"Invalid --since {since_raw!r}"))
                return
            since_dt = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
        else:
            yesterday = datetime.now(tz=timezone.utc) - timedelta(days=1)
            since_dt = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)

        limit = max(int(opts.get("limit") or 1) or 1, 1)
        slices = self._collect_slices(since_dt, limit)
        total = sum(len(rows) for _, rows in slices)

        payload = {
            "since": since_dt.isoformat(),
            "slice_count": len(slices),
            "row_count": total,
            "slices": [
                {"name": name, "rows": rows} for name, rows in slices
            ],
        }

        if not url:
            self.stdout.write(self.style.WARNING(
                "ANALYTICS_WAREHOUSE_URL not configured — export skipped (no-op)."
            ))
            self.stdout.write(self.style.SUCCESS(
                f"slices={len(slices)} total_rows={total} since={since_dt.isoformat()}"
            ))
            return

        if opts.get("dry_run"):
            self.stdout.write(self.style.SUCCESS(
                f"DRY-RUN slices={len(slices)} total_rows={total} -> {url}"
            ))
            return

        status = self._post(url, payload, api_key)
        if 200 <= status < 300:
            self.stdout.write(self.style.SUCCESS(
                f"Exported {total} rows across {len(slices)} slices (HTTP {status})"
            ))
        else:
            self.stderr.write(self.style.ERROR(
                f"Warehouse rejected payload (HTTP {status})"
            ))

    @staticmethod
    def _collect_slices(since_dt: datetime, limit: int) -> list[tuple[str, list[dict]]]:
        """Collect rollup slices since ``since_dt``. Tolerant to missing models.

        Each slice is ``(name, [row_dict, ...])``. We keep payloads small —
        warehouse-side schemas can normalise.
        """
        out: list[tuple[str, list[dict]]] = []

        # Event analytics rollups (when present)
        try:
            from apps.analytics.models import (  # type: ignore
                EventAnalyticsRollupDaily,
            )
            rows = list(
                EventAnalyticsRollupDaily.objects.filter(
                    rollup_date__gte=since_dt.date()
                ).values()[:limit]
            )
            if rows:
                out.append(("event_analytics_daily", _normalize_for_json(rows)))
        except Exception:
            pass

        # Student risk signals (when present)
        try:
            from apps.analytics.models import StudentAtRiskSignal  # type: ignore
            rows = list(
                StudentAtRiskSignal.objects.filter(
                    created_at__gte=since_dt
                ).values()[:limit]
            )
            if rows:
                out.append(("student_at_risk_signal", _normalize_for_json(rows)))
        except Exception:
            pass

        # Audit log (when present)
        try:
            from apps.compliance.models import AuditLog  # type: ignore
            rows = list(
                AuditLog.objects.filter(timestamp__gte=since_dt).values()[:limit]
            )
            if rows:
                out.append(("audit_log", _normalize_for_json(rows)))
        except Exception:
            pass

        return out

    @staticmethod
    def _post(url: str, payload: dict, api_key: str) -> int:
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen

        body = json.dumps(payload, default=str).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            req = Request(url, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=30) as resp:
                return int(resp.getcode() or 0)
        except HTTPError as exc:
            return int(getattr(exc, "code", 0) or 0)
        except URLError:
            return 0


def _normalize_for_json(rows: list[dict]) -> list[dict]:
    """Stringify datetimes / UUIDs so json.dumps doesn't trip up."""
    out = []
    for r in rows:
        norm = {}
        for k, v in r.items():
            if isinstance(v, (datetime,)):
                norm[k] = v.isoformat()
            else:
                try:
                    json.dumps(v)
                    norm[k] = v
                except (TypeError, ValueError):
                    norm[k] = str(v)
        out.append(norm)
    return out
