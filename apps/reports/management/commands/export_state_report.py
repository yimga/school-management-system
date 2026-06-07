"""Export a tenant's state-reporting CSV compliance packet (Wave E).

    python manage.py export_state_report --school <id> [--jurisdiction US_EDFACTS] [--out path.csv]
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.reports.state_reporting import (
    DEFAULT_JURISDICTION,
    available_jurisdictions,
    export_state_report_csv,
)


class Command(BaseCommand):
    help = "Export a state-reporting CSV packet for a school (offline)."

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="School id.")
        parser.add_argument("--jurisdiction", default=DEFAULT_JURISDICTION)
        parser.add_argument("--out", default=None, help="Write CSV to this path instead of stdout.")

    def handle(self, *args, **options):
        jurisdiction = options["jurisdiction"]
        if jurisdiction not in available_jurisdictions():
            raise CommandError(
                f"Unknown jurisdiction {jurisdiction!r}. Available: {', '.join(available_jurisdictions())}"
            )
        csv_text = export_state_report_csv(options["school"], jurisdiction)
        out = options.get("out")
        if out:
            with open(out, "w", encoding="utf-8", newline="") as fh:
                fh.write(csv_text)
            self.stdout.write(self.style.SUCCESS(f"wrote {out} ({jurisdiction})"))
        else:
            self.stdout.write(csv_text)
