"""Ingest testimonials from enabled external review-platform connectors.

Loops every enabled external connector
(:func:`apps.schools.marketing_testimonial_sources.enabled_external_connectors`),
fetches normalized candidate rows, and UPSERTS them as UNAPPROVED
``MarketingTestimonial`` rows for an operator approval queue. Deduplication is on
``(source, external_id)``.

HONESTY CONTRACT
----------------
- Every row written/updated here is ``ingested_from_source=True`` and
  ``is_approved=False``. This command NEVER approves and NEVER touches the
  approval flag of an already-approved row (an operator may have approved an
  earlier ingest; we only refresh content, never re-gate it).
- Without credentials, each connector cleanly fetches nothing, so this command
  is a safe no-op on an unconfigured platform.
- Dry-run is the DEFAULT. Pass ``--apply`` to write.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)

# Normalized-dict keys that map directly onto MarketingTestimonial fields when
# upserting. (source / external_id are the dedupe keys, handled separately;
# is_approved / ingested_from_source are forced by the honesty contract.)
_CONTENT_FIELDS = (
    "quote",
    "attribution_name",
    "attribution_role",
    "organization_name",
    "source_url",
    "rating",
    "raw_payload",
)


class Command(BaseCommand):
    help = (
        "Fetch reviews from enabled external testimonial connectors and upsert "
        "them as UNAPPROVED rows for operator approval. Dry-run by default; "
        "pass --apply to write."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write rows to the database. Without it, this is a dry run.",
        )
        parser.add_argument(
            "--source",
            dest="source",
            default="",
            help=(
                "Limit ingest to a single source key (e.g. G2). Must still be "
                "enabled in configuration."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from apps.schools.marketing_testimonial_sources import (
            configured_sources,
            enabled_external_connectors,
        )

        apply = bool(options.get("apply"))
        only_source = str(options.get("source") or "").strip().upper()

        connectors = enabled_external_connectors()
        if only_source:
            connectors = [c for c in connectors if c.source_key == only_source]

        self.stdout.write(
            f"Enabled sources: {', '.join(configured_sources()) or '(none)'}"
        )
        if not connectors:
            self.stdout.write(
                "No enabled external connectors to ingest. Nothing to do."
            )
            return

        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(
            f"[{mode}] ingesting from {len(connectors)} connector(s): "
            f"{', '.join(c.source_key for c in connectors)}"
        )

        total_fetched = 0
        total_created = 0
        total_updated = 0

        for connector in connectors:
            rows = connector.fetch()
            total_fetched += len(rows)
            self.stdout.write(
                f"  {connector.source_key}: fetched {len(rows)} candidate row(s)"
            )
            created, updated = self._upsert_rows(connector.source_key, rows, apply)
            total_created += created
            total_updated += updated

        self.stdout.write(
            f"[{mode}] done. fetched={total_fetched} "
            f"created={total_created} updated={total_updated}"
        )
        if not apply:
            self.stdout.write("Dry run only — no rows written. Re-run with --apply.")

    def _upsert_rows(
        self, source_key: str, rows: List[Dict[str, Any]], apply: bool
    ) -> tuple[int, int]:
        """Upsert candidate rows for one source. Returns ``(created, updated)``."""

        from apps.siteconfig.models_marketing_testimonial import MarketingTestimonial

        created = 0
        updated = 0
        for row in rows:
            external_id = str(row.get("external_id", "") or "").strip()
            if not external_id:
                # Without a stable external id we cannot dedupe safely; skip
                # rather than risk duplicating an operator's queue every run.
                logger.debug(
                    "skipping %s row without external_id: %r",
                    source_key,
                    row.get("attribution_name", ""),
                )
                continue

            defaults = {
                field: row[field] for field in _CONTENT_FIELDS if field in row
            }
            defaults["external_id"] = external_id
            # Honesty invariants — never auto-approve.
            defaults["ingested_from_source"] = True

            if not apply:
                exists = MarketingTestimonial.objects.filter(
                    source=source_key, external_id=external_id
                ).exists()
                if exists:
                    updated += 1
                else:
                    created += 1
                continue

            with transaction.atomic():
                obj, was_created = MarketingTestimonial.objects.get_or_create(
                    source=source_key,
                    external_id=external_id,
                    defaults={**defaults, "is_approved": False},
                )
                if was_created:
                    created += 1
                else:
                    # Refresh content only; NEVER touch is_approved / approved_*.
                    for field, value in defaults.items():
                        setattr(obj, field, value)
                    obj.save(update_fields=list(defaults.keys()) + ["updated_at"])
                    updated += 1

        return created, updated
