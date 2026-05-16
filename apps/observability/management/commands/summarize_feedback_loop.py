"""Print a one-shot text summary of platform feedback signal.

Read-only. Mirrors the data shown on `/feedback-loop/` so operators can run it
from a shell when troubleshooting (or wire it into a daily Slack/email digest).
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Summarize friction events, feedback submissions, and AI interactions for the past 7 days."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)

    def handle(self, *args, **opts):
        days = opts["days"]
        since = timezone.now() - timedelta(days=days)
        self.stdout.write(self.style.NOTICE(f"Feedback loop summary (last {days}d):"))

        friction = self._friction(since)
        feedback = self._feedback(since)
        ai = self._ai(since)
        total = friction + feedback + ai
        if total == 0:
            self.stdout.write(self.style.WARNING("No signal in window. Harness is wired; users haven't generated signal yet."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Total signal: {total}"))

    def _friction(self, since) -> int:
        try:
            from apps.observability.models_friction import FrictionEvent
            # tenant-isolation-allow: operator-level aggregate, no per-tenant rows surfaced
            n = FrictionEvent.objects.filter(last_seen__gte=since).count()
            self.stdout.write(f"  friction_events:        {n}")
            return n
        except (ImportError, RuntimeError) as e:
            self.stdout.write(f"  friction_events:        (unavailable: {e})")
            return 0

    def _feedback(self, since) -> int:
        try:
            from apps.feedback.models import FeedbackSubmission
            # tenant-isolation-allow: operator-level aggregate
            n = FeedbackSubmission.objects.filter(created_at__gte=since).count()
            self.stdout.write(f"  feedback_submissions:   {n}")
            return n
        except (ImportError, RuntimeError) as e:
            self.stdout.write(f"  feedback_submissions:   (unavailable: {e})")
            return 0

    def _ai(self, since) -> int:
        try:
            from apps.compliance.models_audit import AuditLog
            # tenant-isolation-allow: operator-level aggregate
            n = AuditLog.objects.filter(
                app_label="portal", model_name="AICopilot", timestamp__gte=since
            ).count()
            self.stdout.write(f"  ai_interactions:        {n}")
            return n
        except (ImportError, RuntimeError) as e:
            self.stdout.write(f"  ai_interactions:        (unavailable: {e})")
            return 0
