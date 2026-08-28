"""Close the sync conflicts that are not disagreements.

WHY THIS EXISTS. ``_apply_changes_inner`` used to grade a conflict on TIMESTAMPS alone,
and it did so before it checked whether the incoming row would change anything. On a box
that comparison is rigged: every local row carries an ``updated_at`` written by the box's
OWN apply (``auto_now``), so it is newer than the cloud stamp on the same row by
construction. A full-corpus re-pull therefore graded row after already-converged row as a
conflict with itself. The engine's provenance guard catches the rows SYNC wrote; it cannot
catch the ones the provisioning CLONE wrote, because those have no ledger entry -- and on a
freshly cloned box that is nearly every row.

The apply path no longer does this: the no-op check now runs BEFORE the grading. But the
records it already wrote do not disappear, and they are not a thing an operator can work
through by hand -- a single sweep produced tens of thousands of them, each asking a human
to choose between a value and that same value.

WHAT THIS DOES. Re-reads every PENDING conflict, compares the client payload against the
row as it stands NOW, and resolves only the ones where every comparable value already
matches. Anything that genuinely differs is left PENDING, untouched, for a human.

It is also the PROOF of that diagnosis rather than an assertion of it. If the sweep
resolves nearly all of them, the conflicts were manufactured. If it leaves thousands
pending, they were real and we learn that instead of having assumed it. The per-entity
breakdown is printed for exactly that reason.

SAFETY. Dry run unless ``--apply`` is passed; reads are scoped to the conflict's own
school, never school-blind; comparison uses the same ``_same_value`` the apply path uses,
which fails toward CHANGED for anything that is not a plain scalar. A row that has been
deleted, an entity the rail does not know, and a payload with nothing comparable in it are
all left PENDING and reported -- this closes the cases it can prove, and says so about the
rest.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

# Outcomes. Only IDENTICAL is ever resolved; the rest are reported and left alone.
IDENTICAL = "identical"
DIFFERS = "differs"
ROW_MISSING = "row_missing"
UNKNOWN_ENTITY = "unknown_entity"
NO_COMPARABLE_FIELDS = "no_comparable_fields"

_LEFT_PENDING = (DIFFERS, ROW_MISSING, UNKNOWN_ENTITY, NO_COMPARABLE_FIELDS)

_EXPLAIN = {
    DIFFERS: "a real disagreement -- the client payload and the live row differ",
    ROW_MISSING: "the row is gone; whether the deletion or the change wins is a decision",
    UNKNOWN_ENTITY: "entity_type is not on the sync rail, so there is nothing to compare",
    NO_COMPARABLE_FIELDS: "the payload carries no field this entity actually syncs",
}

# Written into SyncConflict.resolution_note, which is a CharField(max_length=255).
_NOTE = "auto-resolved: client and server values identical, nothing to adjudicate"


class Command(BaseCommand):
    help = (
        "Resolve PENDING sync conflicts whose client payload already matches the live "
        "row. Dry run unless --apply is passed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            dest="school",
            default="",
            help="Limit to one school (pk). Default: every school with pending conflicts.",
        )
        parser.add_argument(
            "--entity",
            dest="entity",
            default="",
            help="Limit to one entity_type (e.g. subject_assignment).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually resolve. Without it nothing is written.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Examine at most N conflicts (0 = no limit). Useful for a first pass.",
        )
        parser.add_argument(
            "--chunk",
            type=int,
            default=1000,
            help="Rows per batch. Bounds both the row prefetch and the write.",
        )
        parser.add_argument(
            "--explain",
            action="store_true",
            help=(
                "For the conflicts that genuinely DIFFER, tally which fields disagree. "
                "Field names only, no values."
            ),
        )
        parser.add_argument(
            "--sample",
            type=int,
            default=0,
            help=(
                "Print N differing conflicts in full, INCLUDING VALUES. This is tenant "
                "data (names, codes, ids) -- it goes to your terminal, so choose where "
                "you run it. 0 = print none."
            ),
        )
        parser.add_argument("--json", action="store_true", help="Emit JSON only.")

    # -- helpers ---------------------------------------------------------------

    def _config(self):
        from apps.api.sync_services import _get_entity_config

        return _get_entity_config(include_derived=True)

    def _classify(self, conflict, instance, allowed):
        """``(outcome, differing_fields)`` for one conflict against the row as it stands.

        EVERY differing field, not the first. A per-field tally is how you tell a bulk
        cloud operation from a scatter of human edits -- 389 rows all disagreeing about
        ``classroom_id`` is one promotion that never landed, while 389 rows disagreeing
        about a spread of columns is 389 separate decisions. Reporting only the first
        difference would bias that tally toward whichever field sorts earliest, which is
        an artefact of the alphabet rather than a fact about the data.
        """
        # By COLUMN. The scalar-only comparison reported every populated datetime and
        # JSON field as differing, so this command would have reported real disagreement
        # on rows that agreed -- and, being the tool that decides what a human has to
        # adjudicate, it would have sent them to a human to compare a value with itself.
        from apps.api.sync_services import _same_field_value

        if instance is None:
            return ROW_MISSING, ()
        payload = conflict.client_data if isinstance(conflict.client_data, dict) else {}
        comparable = {k: v for k, v in payload.items() if k in allowed}
        if not comparable:
            return NO_COMPARABLE_FIELDS, ()
        differing = tuple(
            key
            for key, incoming in sorted(comparable.items())
            if not _same_field_value(type(instance), key, getattr(instance, key, None), incoming)
        )
        if differing:
            return DIFFERS, differing
        return IDENTICAL, ()

    def _load_rows(self, model, school_id, pks):
        """``{str(pk): instance}``, scoped to ``school_id`` when the model carries it.

        ``_base_manager`` on purpose: a conflict about a soft-deleted row is still a
        conflict about a row that EXISTS, and a default manager that hides it would make
        this command report ROW_MISSING for something that is merely filtered.
        """
        qs = model._base_manager.filter(pk__in=list(pks))
        if any(
            getattr(f, "name", None) == "school"
            for f in model._meta.get_fields()
            if getattr(f, "concrete", False)
        ):
            # Tenant scope is not optional. A conflict names a school; reading its row
            # without that filter would let one school's sweep touch another's record.
            qs = qs.filter(school_id=school_id)
        return {str(obj.pk): obj for obj in qs}

    # -- main ------------------------------------------------------------------

    def handle(self, *args, **options):
        from apps.siteconfig.models import SyncConflict

        chunk = max(1, int(options["chunk"]))
        limit = max(0, int(options["limit"]))
        do_apply = bool(options["apply"])
        as_json = bool(options["json"])
        explain = bool(options["explain"])
        sample_cap = max(0, int(options["sample"]))

        config = self._config()

        pending = SyncConflict.objects.filter(status=SyncConflict.Status.PENDING)
        if options["school"]:
            pending = pending.filter(school_id=options["school"])
        if options["entity"]:
            pending = pending.filter(entity_type=options["entity"].strip().lower())

        # ``.order_by()`` before ``.distinct()`` is load-bearing, not tidiness. SyncConflict
        # declares ``ordering = ["-created_at"]``, so Django adds created_at to the SELECT
        # and DISTINCT then applies to (school, entity_type, created_at) -- one "group" per
        # ROW. Every group re-runs the whole sweep over what is still PENDING, so a backlog
        # of 6 was examined 11 times and the differs count came back as 6 instead of 1.
        groups = sorted(
            pending.order_by().values_list("school_id", "entity_type").distinct(),
            key=lambda g: (str(g[0]), str(g[1])),
        )
        if not groups:
            return self._report(
                {"examined": 0, "resolved": 0, "outcomes": {}, "by_entity": {}},
                do_apply,
                as_json,
            )

        outcomes: dict[str, int] = {}
        by_entity: dict[str, dict] = {}
        # {entity: {field: count}} over the conflicts that genuinely differ, and a bounded
        # list of worked examples. Collected only when asked for: the tally costs nothing,
        # but the samples carry tenant values.
        differing_fields: dict[str, dict] = {}
        samples: list = []
        examined = 0
        resolved = 0

        for school_id, entity_type in groups:
            entity = (entity_type or "").strip().lower()
            entry = config.get(entity)
            group_qs = pending.filter(
                school_id=school_id, entity_type=entity_type
            ).order_by("pk")

            if entry is None:
                # Count them without loading them: there is nothing to compare against.
                n = group_qs.count()
                if limit:
                    n = min(n, max(0, limit - examined))
                examined += n
                outcomes[UNKNOWN_ENTITY] = outcomes.get(UNKNOWN_ENTITY, 0) + n
                slot = by_entity.setdefault(entity or "(blank)", {})
                slot[UNKNOWN_ENTITY] = slot.get(UNKNOWN_ENTITY, 0) + n
                if limit and examined >= limit:
                    break
                continue

            model, allowed = entry
            # Take the ids FIRST, then walk them in slices. Streaming the rows instead
            # would mean mutating `status` inside a loop over a queryset filtered on
            # `status=PENDING`: the resolved rows leave the result set mid-scan and
            # whether that skips their neighbours depends on the backend's cursor
            # behaviour. A list of ints costs little even for a six-figure backlog, and it
            # makes what gets examined independent of what gets written.
            pks = list(group_qs.values_list("pk", flat=True))
            if limit:
                pks = pks[: max(0, limit - examined)]
            for start in range(0, len(pks), chunk):
                window = pks[start : start + chunk]
                batch = list(
                    SyncConflict.objects.filter(pk__in=window).order_by("pk")
                )
                examined += len(batch)
                resolved += self._run_batch(
                    batch, model, allowed, school_id, entity,
                    outcomes, by_entity, do_apply,
                    differing_fields, samples, sample_cap,
                )
            if limit and examined >= limit:
                break

        return self._report(
            {
                "examined": examined,
                "resolved": resolved,
                "outcomes": outcomes,
                "by_entity": by_entity,
                "differing_fields": differing_fields if explain else {},
                "samples": samples,
            },
            do_apply,
            as_json,
        )

    def _run_batch(
        self, batch, model, allowed, school_id, entity, outcomes, by_entity, do_apply,
        differing_fields=None, samples=None, sample_cap=0,
    ):
        from apps.siteconfig.models import SyncConflict

        rows = self._load_rows(model, school_id, {c.entity_id for c in batch})
        slot = by_entity.setdefault(entity, {})
        to_resolve = []
        for conflict in batch:
            instance = rows.get(str(conflict.entity_id))
            outcome, fields = self._classify(conflict, instance, allowed)
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            slot[outcome] = slot.get(outcome, 0) + 1
            if outcome == IDENTICAL:
                to_resolve.append(conflict)
            elif outcome == DIFFERS and differing_fields is not None:
                tally = differing_fields.setdefault(entity, {})
                for field in fields:
                    tally[field] = tally.get(field, 0) + 1
                if samples is not None and len(samples) < sample_cap:
                    payload = (
                        conflict.client_data
                        if isinstance(conflict.client_data, dict)
                        else {}
                    )
                    samples.append(
                        {
                            "entity": entity,
                            "id": conflict.entity_id,
                            "incoming_stamp": (
                                conflict.client_updated_at.isoformat()
                                if conflict.client_updated_at
                                else None
                            ),
                            "local_stamp": (
                                conflict.server_updated_at.isoformat()
                                if conflict.server_updated_at
                                else None
                            ),
                            "fields": {
                                f: {
                                    "incoming": payload.get(f),
                                    "local": getattr(instance, f, None),
                                }
                                for f in fields
                            },
                        }
                    )

        if not do_apply:
            # A dry run still reports what it WOULD close, so the number the operator
            # decides on is the number they will get.
            return len(to_resolve)
        if not to_resolve:
            return 0

        now = timezone.now()
        for conflict in to_resolve:
            conflict.status = SyncConflict.Status.RESOLVED_SERVER
            conflict.resolved_at = now
            conflict.resolution_note = _NOTE
        with transaction.atomic():
            SyncConflict.objects.bulk_update(
                to_resolve,
                ["status", "resolved_at", "resolution_note"],
                batch_size=len(to_resolve),
            )
        return len(to_resolve)

    def _report(self, summary, do_apply, as_json):
        summary["applied"] = bool(do_apply)
        if as_json:
            self.stdout.write(json.dumps(summary, indent=2, sort_keys=True, default=str))
            return

        w = self.stdout.write
        verb = "resolved" if do_apply else "would resolve"
        w("")
        w(f"pending conflicts examined: {summary['examined']}")
        w(f"{verb}: {summary['resolved']}")
        left = sum(
            n for k, n in (summary["outcomes"] or {}).items() if k in _LEFT_PENDING
        )
        w(f"left PENDING for a human: {left}")

        if summary["outcomes"]:
            w("")
            w("by outcome:")
            for key, n in sorted(
                summary["outcomes"].items(), key=lambda kv: (-kv[1], kv[0])
            ):
                why = _EXPLAIN.get(key, "resolved: nothing to adjudicate")
                w(f"  {key:<22} {n:>8}   {why}")

        if summary["by_entity"]:
            w("")
            w("by entity:")
            for entity, counts in sorted(summary["by_entity"].items()):
                parts = ", ".join(
                    f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])
                )
                w(f"  {entity:<22} {parts}")

        if summary.get("differing_fields"):
            w("")
            w("what actually disagrees (real conflicts only, field names):")
            for entity, tally in sorted(summary["differing_fields"].items()):
                total = max(tally.values())
                for field, n in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0])):
                    # A field that disagrees on nearly every conflicted row of an entity is
                    # one bulk operation, not N decisions -- the shape is the finding.
                    shape = "  <-- on nearly every one" if n == total and len(tally) > 1 else ""
                    w(f"  {entity:<22} {field:<24} {n:>8}{shape}")

        for example in summary.get("samples") or []:
            w("")
            w(f"  {example['entity']} #{example['id']}")
            w(f"    incoming stamp {example['incoming_stamp']}")
            w(f"    local stamp    {example['local_stamp']}")
            for field, pair in sorted(example["fields"].items()):
                w(f"    {field}: incoming={pair['incoming']!r}  local={pair['local']!r}")

        if not do_apply:
            w("")
            w("DRY RUN -- nothing was written. Re-run with --apply to resolve.")

    # Django calls handle() and prints whatever it returns; _report writes directly.
    # Returning None keeps a stray "None" off the console.
