"""
Clone a domain event for replay / debugging (same payload, new outbox row).

Usage::

    python manage.py replay_domain_events <uuid>
    python manage.py replay_domain_events <uuid> --process

``--process`` runs one outbox batch immediately so subscribers and webhooks queue.
"""

from __future__ import annotations

import uuid as uuid_mod

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Replay a domain event by cloning it into the outbox (debug / recovery)."

    def add_arguments(self, parser):
        parser.add_argument(
            "event_id",
            type=str,
            help="UUID of the source DomainEvent",
        )
        parser.add_argument(
            "--process",
            action="store_true",
            help="Process outbox after cloning (single batch).",
        )

    def handle(self, *args, **options):
        from apps.events.models import DomainEvent
        from apps.events.replay_ops import clone_domain_event_for_operator_replay

        raw_id = str(options["event_id"]).strip()
        try:
            pk = uuid_mod.UUID(raw_id)
        except ValueError as exc:
            raise CommandError(f"Invalid UUID: {raw_id}") from exc

        src = DomainEvent.objects.filter(pk=pk).first()
        if src is None:
            raise CommandError(f"DomainEvent not found: {pk}")

        dup = clone_domain_event_for_operator_replay(src, actor=None)
        self.stdout.write(
            self.style.SUCCESS(
                f"Cloned event {src.id} -> new pending event {dup.id} ({dup.event_type})."
            )
        )

        if options["process"]:
            from apps.events.tasks import process_outbox_batch

            n = process_outbox_batch(batch_size=500)
            self.stdout.write(self.style.SUCCESS(f"Processed {n} outbox row(s)."))
