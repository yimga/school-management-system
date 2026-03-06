import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date, parse_datetime

from apps.billing.services import apply_processor_snapshot
from apps.schools.models import School


class Command(BaseCommand):
    help = "Import normalized platform billing processor snapshots from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to a JSON file containing a list of snapshots.")

    def handle(self, *args, **options):
        path = Path(options["file"]).expanduser()
        if not path.exists():
            raise CommandError(f"Snapshot file not found: {path}")

        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshots = payload if isinstance(payload, list) else payload.get("snapshots") or []
        if not isinstance(snapshots, list):
            raise CommandError("Snapshot file must contain a list or a top-level 'snapshots' list.")

        applied = 0
        for item in snapshots:
            school = None
            if item.get("school_id"):
                school = School.objects.filter(pk=item["school_id"]).first()
            elif item.get("school_slug"):
                school = School.objects.filter(slug=item["school_slug"]).first()
            if school is None:
                raise CommandError(f"Unable to resolve school for snapshot: {item}")

            apply_processor_snapshot(
                school=school,
                processor_code=str(item.get("processor_code") or "").strip() or "manual",
                event_type=str(item.get("event_type") or "snapshot").strip(),
                account_status=item.get("account_status"),
                subscription_status=item.get("subscription_status"),
                external_customer_ref=str(item.get("external_customer_ref") or "").strip(),
                external_subscription_ref=str(item.get("external_subscription_ref") or "").strip(),
                currency_code=item.get("currency_code"),
                billed_amount=item.get("billed_amount"),
                current_period_start=parse_datetime(item["current_period_start"]) if item.get("current_period_start") else None,
                current_period_end=parse_datetime(item["current_period_end"]) if item.get("current_period_end") else None,
                trial_end_date=parse_date(item["trial_end_date"]) if item.get("trial_end_date") else None,
                happened_at=parse_datetime(item["happened_at"]) if item.get("happened_at") else None,
                payload=item,
                message=str(item.get("message") or "").strip(),
            )
            applied += 1

        self.stdout.write(self.style.SUCCESS(f"Imported {applied} platform billing snapshot(s)."))

