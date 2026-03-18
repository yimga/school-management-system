"""
Management command to check health of integration APIs (SMS, WhatsApp, etc.)
Usage: python manage.py check_api_health
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import requests
from datetime import datetime


class Command(BaseCommand):
    help = "Health check for external integration APIs"

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=int,
            default=10,
            help="Request timeout in seconds (default: 10)",
        )

    def handle(self, *args, **options):
        timeout = options["timeout"]

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 70))
        self.stdout.write(self.style.SUCCESS("API Health Check"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        )
        self.stdout.write(self.style.SUCCESS("=" * 70 + "\n"))

        results = []
        all_healthy = True

        # Check SMS API
        sms_api = getattr(settings, "SMS_API_URL", None)
        sms_token = getattr(settings, "SMS_API_TOKEN", None)

        if sms_api and sms_token:
            self.stdout.write("Checking SMS API...")
            try:
                response = requests.get(
                    f"{sms_api}/health",
                    headers={"Authorization": f"Bearer {sms_token}"},
                    timeout=timeout,
                )
                if response.status_code == 200:
                    self.stdout.write(self.style.SUCCESS("  ✓ SMS API: HEALTHY"))
                    results.append(("SMS API", "HEALTHY", response.status_code))
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ✗ SMS API: UNHEALTHY (HTTP {response.status_code})"
                        )
                    )
                    results.append(("SMS API", "UNHEALTHY", response.status_code))
                    all_healthy = False
            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f"  ✗ SMS API: ERROR ({str(e)})"))
                results.append(("SMS API", "ERROR", str(e)))
                all_healthy = False
        else:
            self.stdout.write(self.style.WARNING("  ⚠ SMS API: NOT CONFIGURED"))
            results.append(("SMS API", "NOT_CONFIGURED", "N/A"))

        # Check WhatsApp API
        whatsapp_api = getattr(settings, "WHATSAPP_API_URL", None)
        whatsapp_token = getattr(settings, "WHATSAPP_API_TOKEN", None)

        if whatsapp_api and whatsapp_token:
            self.stdout.write("Checking WhatsApp API...")
            try:
                response = requests.get(
                    f"{whatsapp_api}/health",
                    headers={"Authorization": f"Bearer {whatsapp_token}"},
                    timeout=timeout,
                )
                if response.status_code == 200:
                    self.stdout.write(self.style.SUCCESS("  ✓ WhatsApp API: HEALTHY"))
                    results.append(("WhatsApp API", "HEALTHY", response.status_code))
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ✗ WhatsApp API: UNHEALTHY (HTTP {response.status_code})"
                        )
                    )
                    results.append(("WhatsApp API", "UNHEALTHY", response.status_code))
                    all_healthy = False
            except requests.exceptions.RequestException as e:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ WhatsApp API: ERROR ({str(e)})")
                )
                results.append(("WhatsApp API", "ERROR", str(e)))
                all_healthy = False
        else:
            self.stdout.write(self.style.WARNING("  ⚠ WhatsApp API: NOT CONFIGURED"))
            results.append(("WhatsApp API", "NOT_CONFIGURED", "N/A"))

        # Check Slack webhooks
        slack_webhook = getattr(settings, "SLACK_WEBHOOK_URL", None)

        if slack_webhook:
            self.stdout.write("Checking Slack webhook...")
            try:
                # Send a test ping (silent)
                response = requests.post(
                    slack_webhook, json={"text": "Health check ping"}, timeout=timeout
                )
                if response.status_code == 200:
                    self.stdout.write(self.style.SUCCESS("  ✓ Slack Webhook: HEALTHY"))
                    results.append(("Slack Webhook", "HEALTHY", response.status_code))
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ✗ Slack Webhook: UNHEALTHY (HTTP {response.status_code})"
                        )
                    )
                    results.append(("Slack Webhook", "UNHEALTHY", response.status_code))
                    all_healthy = False
            except requests.exceptions.RequestException as e:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Slack Webhook: ERROR ({str(e)})")
                )
                results.append(("Slack Webhook", "ERROR", str(e)))
                all_healthy = False
        else:
            self.stdout.write(self.style.WARNING("  ⚠ Slack Webhook: NOT CONFIGURED"))
            results.append(("Slack Webhook", "NOT_CONFIGURED", "N/A"))

        # Summary
        self.stdout.write("\n" + "=" * 70)
        if all_healthy:
            self.stdout.write(self.style.SUCCESS("✓ All configured APIs are healthy"))
        else:
            self.stdout.write(
                self.style.ERROR("✗ Some APIs are unhealthy or unreachable")
            )

        self.stdout.write(f"\nTotal APIs checked: {len(results)}")
        healthy_count = sum(1 for r in results if r[1] == "HEALTHY")
        self.stdout.write(f"Healthy: {healthy_count}")
        self.stdout.write(f"Issues: {len(results) - healthy_count}")
        self.stdout.write("=" * 70 + "\n")
