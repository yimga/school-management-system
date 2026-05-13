from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.siteconfig.tenant_audit import (
    COMMUNICATION_TENANT_MODELS,
    find_missing_explicit_school_fields,
    find_tenant_owned_models_missing_school_fields,
)


class Command(BaseCommand):
    help = "Audit tenant-sensitive models for explicit school ownership fields."

    def add_arguments(self, parser):
        parser.add_argument(
            "--models",
            default="",
            help="Comma-separated model labels (app.Model). Defaults to communication tenant models.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with error if any model is missing an explicit school field.",
        )

    def handle(self, *args, **options):
        model_opt = (options.get("models") or "").strip()
        if model_opt:
            model_labels = [
                item.strip() for item in model_opt.split(",") if item.strip()
            ]
        else:
            model_labels = list(COMMUNICATION_TENANT_MODELS)

        missing = find_missing_explicit_school_fields(model_labels)
        missing.extend(find_tenant_owned_models_missing_school_fields())
        missing = sorted(set(missing))
        if missing:
            self.stdout.write(
                self.style.WARNING("Models missing explicit school field:")
            )
            for label in missing:
                self.stdout.write(f" - {label}")
            if options.get("strict"):
                raise CommandError("Tenant model audit failed.")
        else:
            self.stdout.write(self.style.SUCCESS("Tenant model audit passed."))
