"""Ask a box whether its tombstones ever had rows to delete.

WHY THIS EXISTS. A box was found holding 39 ``teacher`` tombstones written by a cloud
pull, against a live teacher table of 26 rows. Subtracting one from the other says 13
records were destroyed, and that subtraction was written down and acted on before anybody
checked it. It is not evidence of anything: the tombstones cover pks 28..66 and the live
rows are pks 2..27, which are DISJOINT, so it is equally consistent with 39 deletions that
each found nothing to delete. Both readings fit the counts. Counts cannot separate them.

WHAT CAN. Two instruments, and neither is a subtraction.

1.  THE SEQUENCE. A pk above the table's allocation high-water mark was never handed out
    on this box, so no row here ever had it and nothing here was destroyed by a delete
    naming it. This is decisive when it applies -- but read the caveat the command prints:
    ``pg_dump`` re-seeds sequences to ``max(pk)``, so a restore can lower the high-water
    mark below pks that really were allocated before the dump. The bucket is therefore
    named for what was measured (``pk_above_high_water``) and not for the conclusion.

2.  THE APPLY LEDGER. :class:`apps.sync_engine.models.SyncApplyLedger` carries a row for
    ``(school, entity_type, local_pk)`` whenever the far side addressed that exact pk here
    and this side applied content into it. A tombstoned pk with a ledger row and no live
    row is the one shape that says a row DID exist here and is now gone. That is the
    finding worth paging somebody about, and it is positive evidence rather than a gap.

WHAT IS NOT A BUCKET. Anything the two instruments cannot place stays in ``unknown`` and
is counted in the total. A census that quietly drops what it cannot classify reports its
own blind spot as good news, which is the failure this whole line of work started from:
the buckets must add up to the tombstones considered, and the command asserts that they
do before it prints a verdict.
"""

from __future__ import annotations

import json

from django.core.exceptions import FieldError
from django.core.management.base import BaseCommand, CommandError
from django.db import DataError, OperationalError, ProgrammingError, connection

_DB_READ_ERRORS = (OperationalError, ProgrammingError, DataError, FieldError)


def _entity_models():
    """``entity -> model`` from the rail's own resolver, never from a hand-kept list."""
    from apps.api.sync_services import _get_entity_config

    return {
        entity: model for entity, (model, _fields) in _get_entity_config(include_derived=True).items()
    }


def _allocation_high_water(model):
    """Highest pk this database has ever handed out, or ``None`` if it cannot be asked.

    Postgres keeps it in the pk's sequence. Returning ``None`` -- on SQLite, on a table
    whose pk is not a sequence, on any read that raises -- is the honest answer; a 0 here
    would place every tombstone in ``pk_above_high_water`` and turn an unreadable database
    into a clean bill of health.
    """
    if connection.vendor != "postgresql":
        return None
    pk = model._meta.pk
    if pk is None or not getattr(pk, "get_internal_type", lambda: "")().endswith("AutoField"):
        return None
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT pg_get_serial_sequence(%s, %s)",
                [model._meta.db_table, pk.column],
            )
            row = cur.fetchone()
            seq = row[0] if row else None
            if not seq:
                return None
            cur.execute("SELECT last_value, is_called FROM %s" % seq)  # noqa: S608 - name from pg
            last_value, is_called = cur.fetchone()
            # An uncalled sequence has not issued last_value yet, so the high-water mark
            # is one BELOW it. Off by one here would misfile a real row as never-allocated.
            return int(last_value) if is_called else int(last_value) - 1
    except _DB_READ_ERRORS:
        return None


def _live_pks(model, pks, school_id):
    """Which of ``pks`` are rows right now. ``None`` when the table cannot be read."""
    try:
        qs = model._base_manager.filter(pk__in=sorted(pks))
        if school_id is not None and any(
            getattr(f, "name", "") == "school" for f in model._meta.get_fields()
        ):
            qs = qs.filter(school_id=school_id)
        return {str(v) for v in qs.values_list("pk", flat=True)}
    except _DB_READ_ERRORS:
        return None


def _ledger_hits(entity, pks, school_id):
    """Tombstoned pks the far side has provably addressed here. ``None`` if unreadable."""
    from apps.sync_engine.models import SyncApplyLedger

    try:
        qs = SyncApplyLedger.objects.filter(entity_type=entity, local_pk__in=sorted(pks))
        if school_id is not None:
            qs = qs.filter(school_id=school_id)
        return {str(v) for v in qs.values_list("local_pk", flat=True)}
    except _DB_READ_ERRORS:
        return None


def classify(pks, live, ledger, high_water):
    """Place every pk in exactly one bucket, and never silently drop one.

    Ordering is deliberate. A pk that is live is answered by that fact alone. Among the
    absent, LEDGER EVIDENCE OUTRANKS THE SEQUENCE: the ledger says a row was really here,
    and a high-water mark that disagrees is the restore caveat showing up, not a licence
    to file a destroyed row as never-allocated.
    """
    out = {"live": [], "destroyed": [], "pk_above_high_water": [], "unknown": []}
    for pk in pks:
        if live is None:
            # Absence cannot be established, so neither can anything built on it. A
            # ledger hit for a pk that might still be live is not a destroyed row.
            out["unknown"].append(pk)
        elif pk in live:
            out["live"].append(pk)
        elif ledger is not None and pk in ledger:
            out["destroyed"].append(pk)
        elif ledger is None:
            out["unknown"].append(pk)
        elif high_water is not None and pk.isdigit() and int(pk) > high_water:
            out["pk_above_high_water"].append(pk)
        else:
            out["unknown"].append(pk)
    total = sum(len(v) for v in out.values())
    if total != len(pks):
        raise AssertionError("buckets hold %d of %d pks" % (total, len(pks)))
    return out


class Command(BaseCommand):
    help = "Per entity, say whether tombstoned pks ever named a row on this deployment."

    def add_arguments(self, parser):
        parser.add_argument("--entity", default="", help="restrict to one entity type")
        parser.add_argument("--school-id", type=int, default=None)
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument(
            "--fail-on-destroyed",
            action="store_true",
            help="exit 1 when a tombstoned pk has apply-ledger evidence and no live row",
        )

    def handle(self, *args, **opts):
        from apps.sync_engine.models import SyncTombstone

        models_by_entity = _entity_models()
        qs = SyncTombstone.objects.all()
        if opts["entity"]:
            qs = qs.filter(entity_type=opts["entity"])
        if opts["school_id"] is not None:
            qs = qs.filter(school_id=opts["school_id"])

        by_entity = {}
        for entity, pk in qs.values_list("entity_type", "local_pk"):
            by_entity.setdefault(entity, set()).add(str(pk))

        report = {"entities": {}, "destroyed_total": 0, "unknown_total": 0}
        for entity in sorted(by_entity):
            pks = by_entity[entity]
            model = models_by_entity.get(entity)
            if model is None:
                report["entities"][entity] = {
                    "tombstones": len(pks),
                    "model": None,
                    "note": "entity is not on the rail in this build; nothing to ask",
                    "buckets": {"unknown": len(pks)},
                }
                report["unknown_total"] += len(pks)
                continue
            live = _live_pks(model, pks, opts["school_id"])
            ledger = _ledger_hits(entity, pks, opts["school_id"])
            high_water = _allocation_high_water(model)
            buckets = classify(sorted(pks), live, ledger, high_water)
            report["entities"][entity] = {
                "tombstones": len(pks),
                "model": model._meta.label,
                "high_water": high_water,
                "live_table_readable": live is not None,
                "ledger_readable": ledger is not None,
                "buckets": {k: len(v) for k, v in buckets.items()},
                "destroyed_pks": sorted(buckets["destroyed"])[:50],
            }
            report["destroyed_total"] += len(buckets["destroyed"])
            report["unknown_total"] += len(buckets["unknown"])

        if opts["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        else:
            self._render(report)

        if opts["fail_on_destroyed"] and report["destroyed_total"]:
            raise CommandError(
                "%d tombstoned pk(s) have apply-ledger evidence and no live row"
                % report["destroyed_total"]
            )

    def _render(self, report):
        w = self.stdout.write
        if not report["entities"]:
            w("No tombstones on this deployment. Nothing to explain.")
            return
        w("%-22s %6s %6s %10s %8s %8s  %s" % (
            "ENTITY", "TOMBS", "LIVE", "DESTROYED", "ABOVE-HW", "UNKNOWN", "MODEL"))
        for entity, e in sorted(report["entities"].items()):
            b = e["buckets"]
            w("%-22s %6d %6d %10d %8d %8d  %s" % (
                entity, e["tombstones"], b.get("live", 0), b.get("destroyed", 0),
                b.get("pk_above_high_water", 0), b.get("unknown", 0), e["model"] or "-"))
            if e.get("destroyed_pks"):
                w("    pks with apply-ledger evidence and no live row: %s"
                  % ", ".join(e["destroyed_pks"]))
        w("")
        if report["destroyed_total"]:
            w("%d tombstoned pk(s) had a row here and do not now. That is data loss, and the"
              % report["destroyed_total"])
            w("apply ledger is the evidence -- not a subtraction between two counts.")
        else:
            w("No tombstoned pk has apply-ledger evidence of a row that is now missing.")
        if report["unknown_total"]:
            w("%d pk(s) could not be placed by either instrument. They are NOT a clean result;"
              % report["unknown_total"])
            w("they are the part of the question this deployment cannot answer.")
        w("")
        w("Caveat on ABOVE-HW: pg_dump re-seeds sequences to max(pk), so a database restored")
        w("from a dump can report a high-water mark below pks it really did allocate. Ledger")
        w("evidence outranks it, which is why DESTROYED is decided first.")
