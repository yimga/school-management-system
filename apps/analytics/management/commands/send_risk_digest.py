"""Send the AI-narrated risk digest to all configured recipients.

For each active school:
  1. Generate the digest text by calling `ai_narrate_risk_digest`
     in-process (we re-import its `Command` class to avoid duplicating
     the formatting logic).
  2. Iterate `RiskDigestRecipient` rows for the school.
  3. For email rows: send via Django mail backend (per-tenant via
     `PerTenantEmailBackend` shipped v2.72).
  4. For slack_webhook rows: POST the digest text as a Slack message
     payload to the webhook URL.
  5. Optionally render via `CommunicationTemplate(key='analytics.risk_digest')`
     when a per-tenant override exists.

Cron suggestion: nightly at 06:00 local time per school's timezone.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from django.core.management.base import BaseCommand
from django.core.mail import EmailMessage
from django.utils import timezone

from apps.analytics.models import RiskDigestRecipient
from apps.schools.models import School

logger = logging.getLogger("apps.analytics.commands.send_risk_digest")

_SLACK_TIMEOUT_SECONDS = 10
_DIGEST_TEMPLATE_KEY = "analytics.risk_digest"


class Command(BaseCommand):
    help = "Render the AI risk digest and fan out to configured recipients."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school", type=str, default=None,
            help="Slug or UUID; omit for all active schools.",
        )
        parser.add_argument("--top-n", type=int, default=5)
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Render digest and list recipients but do not send.",
        )

    def handle(self, *args, **opts):
        schools = School.objects.filter(is_active=True)
        if opts.get("school"):
            schools = schools.filter(slug=opts["school"])
            if not schools.exists():
                schools = School.objects.filter(id=opts["school"])
        if not schools.exists():
            self.stdout.write("No schools to process.")
            return

        sent = 0
        failed = 0
        for school in schools:
            # Check recipients BEFORE generating the digest. _generate_digest
            # runs ai_narrate_risk_digest — an LLM gateway invoke — so narrating
            # a school that never configured a recipient burns spend for output
            # nobody receives. Skipping the narration for opt-out schools bounds
            # LLM cost to schools that actually enabled the digest. (This ordering
            # is what makes the nightly fan-out safe to wake.)
            recipients = list(
                # tenant-isolation-allow: scoped via school= below
                RiskDigestRecipient.objects.filter(school=school, enabled=True)
            )
            if not recipients:
                self.stdout.write(
                    f"{school.slug}: no recipients configured; skipping narration."
                )
                continue
            digest = self._generate_digest(school, top_n=opts["top_n"])
            if not digest:
                continue
            subject = self._resolve_subject(school)
            for recipient in recipients:
                if opts.get("dry_run"):
                    self.stdout.write(
                        f"  [dry] would send to {recipient}"
                    )
                    continue
                ok = self._deliver(school, recipient, subject, digest)
                if ok:
                    sent += 1
                else:
                    failed += 1
        self.stdout.write(self.style.SUCCESS(
            f"Digest delivery: {sent} sent, {failed} failed."
        ))

    def _generate_digest(self, school, *, top_n: int) -> str:
        """Run ai_narrate_risk_digest in-process and capture its stdout.

        The command emits the full digest to stdout; we redirect that
        into a buffer and return it as the message body.
        """
        from io import StringIO
        from apps.analytics.management.commands.ai_narrate_risk_digest import (
            Command as DigestCommand,
        )

        buf = StringIO()
        try:
            cmd = DigestCommand()
            cmd.stdout = buf
            cmd.stderr = buf
            cmd.handle(school=school.slug, top_n=top_n, out=None)
        except Exception as exc:  # noqa: BLE001 — never crash the dispatcher
            logger.warning(
                "send_risk_digest: digest generation failed for %s: %s",
                school.slug, exc,
            )
            return ""
        return buf.getvalue()

    def _resolve_subject(self, school) -> str:
        """Lookup an optional CommunicationTemplate subject; else default."""
        try:
            from apps.communication.models import CommunicationTemplate

            tmpl = (
                CommunicationTemplate.objects.filter(
                    school=school, key=_DIGEST_TEMPLATE_KEY, is_active=True,
                )
                .first()
                or CommunicationTemplate.objects.filter(
                    school__isnull=True, key=_DIGEST_TEMPLATE_KEY,
                    is_active=True,
                ).first()
            )
            if tmpl and tmpl.subject_template:
                return tmpl.subject_template.format(
                    school=school.name,
                    date=timezone.now().strftime("%Y-%m-%d"),
                )
        except (ImportError, AttributeError, ValueError):
            pass
        return f"At-risk digest — {school.name} — {timezone.now():%Y-%m-%d}"

    def _deliver(self, school, recipient, subject: str, body: str) -> bool:
        try:
            if recipient.channel == RiskDigestRecipient.Channel.EMAIL:
                EmailMessage(
                    subject=subject,
                    body=body,
                    to=[recipient.target],
                ).send(fail_silently=False)
                return True
            if recipient.channel == RiskDigestRecipient.Channel.SLACK_WEBHOOK:
                return self._post_slack(recipient.target, subject, body)
            logger.warning(
                "send_risk_digest: unknown channel %s", recipient.channel,
            )
            return False
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning(
                "send_risk_digest: delivery failed for %s: %s",
                recipient, exc,
            )
            return False

    def _post_slack(self, webhook_url: str, subject: str, body: str) -> bool:
        payload = json.dumps({
            "text": f"*{subject}*\n```{body}```",
        }).encode("utf-8")
        req = urllib.request.Request(
            webhook_url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_SLACK_TIMEOUT_SECONDS) as resp:
                return 200 <= resp.status < 300
        except urllib.error.URLError as exc:
            logger.warning("send_risk_digest: slack post failed: %s", exc)
            return False
