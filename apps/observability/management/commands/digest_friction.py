"""Wave B — G5: nightly friction digest.

Aggregates ``FrictionEvent`` rows from the last 24h per tenant and prints
a humanised summary intended to be wrapped by the
``CommunicationTemplate`` system (Wave NS-5) when a success owner is
configured.

Usage::

    python manage.py digest_friction --dry-run
    python manage.py digest_friction --threshold 5
    python manage.py digest_friction --school <slug>

Exit code is always 0 — telemetry summaries never fail a cron.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.observability.models_friction import FRICTION_KINDS, FrictionEvent

logger = logging.getLogger(__name__)

KIND_LABEL = dict(FRICTION_KINDS)


class Command(BaseCommand):
    help = "Summarise FrictionEvent rows from the last 24h per tenant."

    def add_arguments(self, parser):
        parser.add_argument("--threshold", type=int, default=3,
                            help="Minimum count per row to include (default: 3).")
        parser.add_argument("--hours", type=int, default=24,
                            help="Window in hours (default: 24).")
        parser.add_argument("--school", default="",
                            help="Optional school slug filter.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Print to stdout instead of dispatching templates.")
        # Wave J (2026-05-15): empathy-aware AI narrative.
        parser.add_argument("--no-ai", action="store_true",
                            help="Skip the AI gateway enrichment even when it's available.")

    def handle(self, *args, **opts):
        threshold = max(1, int(opts.get("threshold") or 3))
        hours = max(1, int(opts.get("hours") or 24))
        school_slug = (opts.get("school") or "").strip()
        dry_run = bool(opts.get("dry_run"))
        no_ai = bool(opts.get("no_ai"))

        since = timezone.now() - timedelta(hours=hours)
        # tenant-isolation-allow: friction digest aggregates across all tenants by design
        qs = FrictionEvent.objects.filter(
            last_seen__gte=since,
            resolved_at__isnull=True,
            count__gte=threshold,
        ).select_related("school", "user").order_by("school_id", "-count")
        if school_slug:
            qs = qs.filter(school__slug=school_slug)

        buckets: dict[object, list[FrictionEvent]] = {}
        for event in qs:
            buckets.setdefault(event.school_id, []).append(event)

        if not buckets:
            self.stdout.write(self.style.SUCCESS("No friction events above threshold."))
            return

        for school_id, events in buckets.items():
            tenant_name = (events[0].school.name if events[0].school else "<no tenant>")
            top = events[:5]
            lines = [self._format_event(e) for e in top]
            body = self._humanise(tenant_name, lines, total_rows=len(events))
            # Wave J: empathy AI narrative — optionally prepend an executive summary
            # produced by the gateway. Falls back silently when the gateway is off
            # or the tenant has AI disabled; the template body always ships.
            if not no_ai:
                narrative = self._invoke_empathy_narrative(events[0].school, lines, tenant_name)
                if narrative:
                    body = narrative + "\n\n" + body
            if dry_run:
                self.stdout.write("─" * 60)
                self.stdout.write(body)
            else:
                self._dispatch(school_id, body)

    def _format_event(self, event: FrictionEvent) -> str:
        actor = getattr(event.user, "username", None) or "anonymous"
        kind = KIND_LABEL.get(event.kind, event.kind)
        return f"• {actor} on {event.view_name} — {kind} (×{event.count})"

    def _humanise(self, tenant_name: str, lines: list[str], *, total_rows: int) -> str:
        suffix = "" if total_rows <= 5 else f"\n…and {total_rows - 5} more rows."
        return (
            f"Friction digest for {tenant_name}\n"
            f"We noticed a few people getting stuck in the last day:\n\n"
            + "\n".join(lines)
            + suffix
            + "\n\nNothing requires immediate action — this is a nudge to "
              "review the highlighted flows when convenient."
        )

    def _invoke_empathy_narrative(self, school, lines: list[str], tenant_name: str) -> str | None:
        """Wave J: AI-enriched summary via the gateway, or None on fallback.

        Always routes through ``services.ai_helpers.invoke_with_request`` so the
        AI gateway boundary CI gate stays clean. Returns None when:
          * the helper is unavailable (import path missing)
          * AI is policy-disabled for the tenant
          * the gateway returns an empty / errored payload
        The caller treats None as "ship the template-only body".
        """
        if school is None or not lines:
            return None
        try:
            from services.ai_gateway import TaskType  # noqa: PLC0415
            from services.ai_helpers import invoke_with_request  # noqa: PLC0415
        except ImportError:
            return None
        prompt = (
            "You are a tenant-success teammate writing a one-paragraph empathy summary "
            "of UI friction events for the school's success owner. Tone: warm, premium, "
            "supportive — never alarmist, never robotic. Reference the specific events "
            "below. Output the paragraph only (no preamble, no headers, 80 words max).\n\n"
            f"School: {tenant_name}\n"
            "Top friction events (last day):\n"
            + "\n".join(lines)
        )
        try:
            result = invoke_with_request(
                task_type=TaskType.OBSERVABILITY_ASSISTANT,
                prompt=prompt,
                school=school,
                user_query="Friction digest empathy summary",
                metadata={"surface": "digest_friction", "event_count": len(lines)},
            )
        except Exception as exc:  # noqa: BLE001 — telemetry, not load-bearing
            logger.debug("digest_friction AI narrative failed: %s", exc)
            return None
        if not result:
            return None
        text, _metadata = result if isinstance(result, tuple) else (result, {})
        if not text or not str(text).strip():
            return None
        return str(text).strip()

    def _dispatch(self, school_id, body: str) -> None:
        """Hand off to CommunicationTemplate when available.

        We deliberately fall back to logging if the tenant has no
        ``friction_digest`` template configured — a missing template should
        not block the digest run.
        """
        try:
            from apps.communication.models import CommunicationTemplate  # noqa: PLC0415

            tpl = CommunicationTemplate.objects.filter(
                school_id=school_id, slug="friction_digest", is_active=True
            ).first()
            if tpl is None:
                logger.info("friction_digest no template for school_id=%s", school_id)
                return
            # Real send is handled by the Communication app's worker; here we
            # just record the digest body in the template's last_render
            # field so the worker picks it up.
            tpl.queue_render({"body": body})
        except (AttributeError, ImportError, RuntimeError, ValueError):
            logger.info("friction_digest fallback school_id=%s body_chars=%s", school_id, len(body))
