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

_TEMPLATE_KEY = "friction_digest"

# Typed dispatch failures (§2.4 broad-except policy). AttributeError stays in
# the tuple — a wrong method name must not crash a cron — but it is now logged
# at ERROR with a traceback instead of an INFO "fallback".
_DISPATCH_ERRORS = (
    AttributeError,
    ImportError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


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
                self._dispatch(events[0].school, body)

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
            from services.ai_helpers import TaskType, invoke_with_request  # noqa: PLC0415
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

    def _recipients(self, school) -> list[str]:
        """Tenant admins are the digest's success owners."""
        from apps.schools.models import SchoolMembership  # noqa: PLC0415

        emails: list[str] = []
        memberships = (
            SchoolMembership.objects.filter(school=school, role="ADMIN")
            .select_related("user")
            .order_by("-is_primary", "id")[:20]
        )
        for membership in memberships:
            email = (getattr(membership.user, "email", "") or "").strip()
            if email and email not in emails:
                emails.append(email)
        return emails

    def _subject(self, school) -> str:
        """Subject from the tenant's (or the platform's) ``friction_digest``
        override when configured.

        Only the subject: the body is composed above from live FrictionEvent
        rows, so re-rendering it through the override's body_template would
        throw the digest away.
        """
        try:
            from apps.communication.models import CommunicationTemplate  # noqa: PLC0415

            tpl = (
                CommunicationTemplate.objects.filter(
                    school=school, key=_TEMPLATE_KEY, is_active=True
                ).first()
                or CommunicationTemplate.objects.filter(
                    school__isnull=True, key=_TEMPLATE_KEY, is_active=True
                ).first()
            )
            if tpl is not None and tpl.subject_template:
                return tpl.subject_template
        except _DISPATCH_ERRORS:
            logger.exception("friction_digest subject lookup failed school=%s", school.pk)
        return f"Friction digest — {school.name}"

    def _dispatch(self, school, body: str) -> None:
        """Email the digest to the tenant's success owners.

        A missing recipient is benign (nobody asked for this tenant's digest)
        and stays at INFO. A failing send is NOT benign — it used to be
        downgraded to an INFO "fallback" line indistinguishable from the
        no-recipient case, which is how a dispatch call to a method that never
        existed survived unnoticed.
        """
        if school is None:
            logger.info("friction_digest skipped: friction rows carry no tenant")
            return
        recipients = self._recipients(school)
        if not recipients:
            logger.info("friction_digest no recipients for school_id=%s", school.pk)
            return
        try:
            from apps.communication.notification_service import send_email  # noqa: PLC0415

            send_email(
                recipients,
                self._subject(school),
                body,
                school=school,
                fail_silently=True,
            )
        except _DISPATCH_ERRORS:
            logger.exception(
                "friction_digest dispatch failed school_id=%s recipients=%s body_chars=%s",
                school.pk, len(recipients), len(body),
            )
