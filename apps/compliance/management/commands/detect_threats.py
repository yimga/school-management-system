"""
Detect threats (brute force, after-hours) and optionally alert.
Usage:
    manage.py detect_threats [--window 60] [--no-alert]
"""

from django.core.management.base import BaseCommand

from apps.compliance.threat_detection import detect_threats, alert_findings


class Command(BaseCommand):
    help = "Detect threats and optionally send alerts"

    def add_arguments(self, parser):
        parser.add_argument(
            "--window", type=int, default=None, help="Lookback window in minutes"
        )
        parser.add_argument(
            "--no-alert", action="store_true", help="Do not send alerts, just print"
        )

    def handle(self, *args, **options):
        window = options.get("window")
        findings = detect_threats(window_minutes=window)

        if not findings:
            self.stdout.write(self.style.SUCCESS("No threats detected"))
            return

        for finding in findings:
            self.stdout.write(f"{finding['type']}: {finding.get('description', '')}")

        if not options.get("no_alert"):
            alert_findings(findings)
            self.stdout.write(self.style.SUCCESS("Alerts sent"))
        else:
            self.stdout.write(self.style.WARNING("Alerts suppressed (--no-alert)"))
