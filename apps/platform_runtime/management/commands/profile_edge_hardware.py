from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from services.edge_hardware import profile_edge_hardware


class Command(BaseCommand):
    help = "Profile effective edge-host resources without changing runtime settings."

    def add_arguments(self, parser):
        parser.add_argument("--storage-path", default="")
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        profile = profile_edge_hardware(options.get("storage_path") or None)
        self.stdout.write(json.dumps(profile.to_dict(), indent=2, sort_keys=True))
        if options["strict"] and not profile.supports_edge_ai_pilot:
            raise CommandError("Host does not meet the edge-AI pilot resource floor.")
