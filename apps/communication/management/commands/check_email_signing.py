"""Pillar 3 — operator preflight for outbound email DKIM signing.

Wraps :func:`apps.communication.email_signing.email_signing_status`
with operator-friendly output and CI-suitable exit semantics.

Usage:

    # Quick check (exit 0 = signing wired, 1 = not):
    python manage.py check_email_signing

    # Suppress per-row output (rely on exit code in CI):
    python manage.py check_email_signing --quiet

The check is config-only. It does not send a probe email or verify
that the public key actually resolves at
``<selector>._domainkey.<domain>`` — that lives in the operator
runbook (``dig TXT <selector>._domainkey.<domain>`` after DNS push).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Preflight check for outbound email DKIM signing. Verifies the "
        "configured EMAIL_BACKEND routes through a known DKIM-signing "
        "ESP (Mailgun, SendGrid, Postmark, SES, etc.). Exit 0 if "
        "signing wired, 1 if not — suitable for CI deployment gating."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress per-row output; rely on exit code (0=signing, 1=not).",
        )

    def handle(self, *args, **opts):
        from apps.communication.email_signing import email_signing_status

        quiet = bool(opts.get("quiet"))
        status = email_signing_status()

        if not quiet:
            self._render(status)

        if not status["signs_dkim"]:
            raise SystemExit(1)

    def _render(self, status: dict) -> None:
        self.stdout.write("=== Outbound email DKIM signing preflight ===")
        self.stdout.write(f"Backend:           {status['backend'] or '(unset)'}")
        self.stdout.write(f"Provider:          {status['provider']}")
        self.stdout.write(f"Signs DKIM:        {'YES' if status['signs_dkim'] else 'NO'}")
        self.stdout.write(f"Required (env):    {status['required']}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL:{status['default_from'] or '(unset)'}")
        self.stdout.write("")

        if status["signs_dkim"]:
            self.stdout.write(self.style.SUCCESS(
                "READY — backend routes through a known DKIM-signing provider.\n"
                "Verify the provider's public key resolves at "
                "<selector>._domainkey.<sending-domain> via DNS, and that "
                "matching SPF + DMARC records are published."
            ))
            return

        if status["required"]:
            self.stdout.write(self.style.ERROR(
                "!!  EMAIL_SIGNING_REQUIRED=True but the configured backend "
                "does NOT sign DKIM. AppConfig.ready() will raise on the "
                "next process start. Switch EMAIL_BACKEND to an anymail "
                "ESP backend (anymail.backends.<provider>.EmailBackend)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "..  Backend does NOT sign DKIM. Acceptable for development "
                "(EMAIL_SIGNING_REQUIRED=False) but production deploys must "
                "set EMAIL_SIGNING_REQUIRED=1 and use an anymail ESP backend "
                "so transactional mail cannot be spoofed."
            ))
