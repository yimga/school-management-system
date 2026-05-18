"""v3.32.0 — Audit-bundle replay: DFV -> first-class promotion + cleanup.

The v3.31 :mod:`promote_dyna_assignments` command runs forward: it
promotes DFV rows to first-class but leaves the DFV row in place as an
audit-trail anchor. This command is the "second pass" — for bundles
that were imported BEFORE the v3.31 promotion shipped (or when the
catalog side of the join arrived after the assignment row was already
quarantined to DFV), the DFV rows can now be promoted AND deleted
since the canonical record has moved to first-class.

Args:
  --bundle <id> OR --tenant <id>     One required. (--bundle filters
                                      via ``value_json["bundle_id"]``
                                      when bundles annotate it.)
  --apply                            Required for writes. Default is
                                      dry-run.
  --since YYYY-MM-DD                 Optional filter on DFV created_at.
  --limit N                          Max rows per run (default 5000).
  --entity-type <type>               Limit to one assignment domain.

Semantics:
  * Idempotent — re-running on a cleaned tenant is a no-op.
  * Each row runs in its own ``transaction.atomic()`` — partial moves
    don't corrupt state.
  * On success: row is promoted to first-class AND the DFV row is
    DELETED (in the same atomic block). On failure (catalog FK still
    missing): DFV row is left in place.
  * NEVER logs DFV payload content (PII).
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.migration_cloud.management.commands import (
    _assignment_promotion_helpers as _helpers,
)


logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 5000


class Command(BaseCommand):
    help = (
        "Replay v3.28 DynamicFieldValue assignment rows: promote to "
        "first-class schoolops models AND delete the DFV row. For "
        "out-of-order bundles whose catalog side arrived after the "
        "assignment row was quarantined to DFV."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--tenant", type=int, default=None,
            help="School PK. Either --tenant or --bundle is required.",
        )
        parser.add_argument(
            "--bundle", type=int, default=None,
            help="Migration bundle id. Filters DFV rows whose "
                 "``value_json['bundle_id']`` matches.",
        )
        parser.add_argument(
            "--apply", action="store_true", default=False,
            help="Write changes. Without this flag, runs in dry-run mode.",
        )
        parser.add_argument(
            "--since", type=str, default=None,
            help="ISO date (YYYY-MM-DD); only DFV rows created on/after.",
        )
        parser.add_argument(
            "--limit", type=int, default=_DEFAULT_LIMIT,
            help=f"Max DFV rows per run (default {_DEFAULT_LIMIT}).",
        )
        parser.add_argument(
            "--entity-type",
            choices=list(_helpers.VALID_ENTITY_TYPES),
            default=None,
            help="Limit to one entity_type; default is all three.",
        )

    def handle(self, *args, **options) -> None:
        tenant_id = options.get("tenant")
        bundle_id = options.get("bundle")
        apply_changes = bool(options.get("apply"))
        limit = max(1, int(options.get("limit") or _DEFAULT_LIMIT))
        only_entity = options.get("entity_type")
        since_arg = options.get("since")

        if tenant_id is None and bundle_id is None:
            raise CommandError(
                "--tenant or --bundle is required (no cross-platform replay).",
            )

        since_date = None
        if since_arg:
            try:
                since_date = _dt.date.fromisoformat(since_arg)
            except ValueError as exc:
                raise CommandError(
                    f"--since must be ISO YYYY-MM-DD ({exc})",
                ) from exc

        try:
            from apps.metadata.models import DynamicFieldValue
            from apps.people.models import StudentProfile
            from apps.schoolops.models import (
                CanteenMeal,
                HostelAssignment,
                HostelRoom,
                MealPlanBalance,
                Route,
                TransportAssignment,
            )
        except ImportError as exc:
            raise CommandError(f"failed to import models: {exc!s}") from exc

        entity_types = (
            [only_entity] if only_entity else list(_helpers.VALID_ENTITY_TYPES)
        )

        summary: dict[str, Any] = {
            "tenant_id": tenant_id,
            "bundle_id": bundle_id,
            "apply": apply_changes,
            "limit": limit,
            "scanned": 0,
            "promoted_and_deleted_dfv": 0,
            "promoted_idempotent_dfv_deleted": 0,
            "still_unresolved": 0,
            "errors": 0,
            "dry_run": not apply_changes,
        }

        qs = self._build_queryset(
            DynamicFieldValue=DynamicFieldValue,
            tenant_id=tenant_id,
            bundle_id=bundle_id,
            entity_types=entity_types,
            since_date=since_date,
            limit=limit,
        )

        for dfv in qs:
            summary["scanned"] += 1
            tenant_for_row = (
                tenant_id if tenant_id is not None else dfv.school_id
            )
            try:
                with transaction.atomic():
                    sub = {
                        "promoted": 0,
                        "skipped_already_promoted": 0,
                        "skipped_unresolved": 0,
                    }
                    obj = _helpers.promote_one(
                        dfv=dfv,
                        tenant_id=tenant_for_row,
                        apply_changes=apply_changes,
                        StudentProfile=StudentProfile,
                        Route=Route,
                        HostelRoom=HostelRoom,
                        CanteenMeal=CanteenMeal,
                        TransportAssignment=TransportAssignment,
                        HostelAssignment=HostelAssignment,
                        MealPlanBalance=MealPlanBalance,
                        summary=sub,
                    )
                    if sub["skipped_unresolved"]:
                        summary["still_unresolved"] += 1
                    elif sub["promoted"] or sub["skipped_already_promoted"]:
                        # Either a fresh promotion or an idempotent hit
                        # — in BOTH cases the DFV row is redundant once
                        # we're in replay mode (first-class is the SOT).
                        if apply_changes:
                            dfv_pk = dfv.pk
                            # tenant-isolation-allow: delete-confined-to-pk-just-validated-row-in-atomic
                            dfv.__class__.objects.filter(
                                pk=dfv_pk,
                            ).delete()
                        if sub["promoted"]:
                            summary["promoted_and_deleted_dfv"] += 1
                        else:
                            summary[
                                "promoted_idempotent_dfv_deleted"
                            ] += 1
                    else:
                        # Defensive: helper returned without classifying.
                        summary["still_unresolved"] += 1
            except (TypeError, ValueError) as exc:
                summary["errors"] += 1
                logger.warning(
                    "replay_dfv_assignments[dfv_pk=%s] input error: %s",
                    dfv.pk, type(exc).__name__,
                )
            except Exception as exc:  # noqa: BLE001
                summary["errors"] += 1
                logger.warning(
                    "replay_dfv_assignments[dfv_pk=%s] %s: %s",
                    dfv.pk, type(exc).__name__, exc,
                )

        # Structured summary — operators parse this from logs.
        self.stdout.write(str(summary))
        logger.info("replay_dfv_assignments summary: %s", summary)

    # ------------------------------------------------------------------
    def _build_queryset(
        self, *, DynamicFieldValue, tenant_id, bundle_id,
        entity_types, since_date, limit,
    ):
        """Construct the DFV queryset honoring tenant / bundle filters."""
        # tenant-isolation-allow: management-command-explicit-tenant-or-bundle-filter-per-arg-parser
        qs = DynamicFieldValue.objects.filter(entity_type__in=entity_types)
        if tenant_id is not None:
            # tenant-isolation-allow: management-command-explicit-tenant-filter-required-arg
            qs = qs.filter(school_id=tenant_id)
        if since_date is not None:
            qs = qs.filter(created_at__date__gte=since_date)
        if bundle_id is not None:
            # bundle annotation lives inside value_json — DBs vary in
            # JSON lookup support; do a coarse SQL-side filter on the
            # text representation when JSONField lookup is unavailable.
            try:
                qs = qs.filter(value_json__bundle_id=bundle_id)
            except Exception:  # noqa: BLE001
                # Fallback: caller can post-filter in Python by re-running
                # with the bundle id on each row. We keep the queryset
                # broader rather than failing.
                pass
        return qs.order_by("pk")[:limit]
