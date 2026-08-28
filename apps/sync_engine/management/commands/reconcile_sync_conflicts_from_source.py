"""Adjudicate sync conflicts against the roster the school actually keeps.

WHY THIS EXISTS. ``resolve_identical_sync_conflicts`` closes the conflicts that are not
disagreements. What it leaves behind are the real ones: two nodes holding two values for
one column, with nothing about either row to say which is right. The rail cannot break
that tie. ``updated_at`` is ``auto_now``, so a box's copy is newer than the cloud's by
construction and last-write-wins always elects the box regardless of which is correct.
Field-level merge only helps while the two sides changed DIFFERENT columns.

The evidence is outside the system. A roster is the register the values were typed into
before either node existed -- not a third opinion, but the thing both opinions are supposed
to be copies of. This command joins the conflicted rows to it and writes down what it says.

WHAT IT REFUSES TO DO. A roster settles a field only when it CARRIES that field. Its
``Name`` is one string; ``first_name``/``last_name`` are DERIVED from it by a splitter that
runs per node. Two nodes that ran different variants hold different decompositions of a
string they agree about, and no amount of reading the file will say which token is the
surname, because the file never said. Those are reported, never guessed, and reported as
ONE finding rather than N: when the same value appears under different field names on the
two sides, that is one splitter disagreeing with another, and the operator makes a single
decision about the convention instead of adjudicating hundreds of rows individually.

ALL OR NOTHING PER ROW. A conflict is resolved only when the source settles EVERY field
that differs. Writing the fields it knows about and leaving the conflict PENDING would hand
a human a row that changed underneath them, and the diff they were asked to judge would no
longer be the diff in front of them.

CONVERGENCE. The join and the values are deterministic -- no file order, no clock, no
randomness -- so running this on both nodes against the same file reaches the same values
without the nodes exchanging anything. Run on one node it also converges, one sync later,
because the corrected row travels the rail like any other edit.

SAFETY. Dry run unless ``--apply``. Reads and writes are scoped to the school named on the
command line; a roster belongs to one school and matching across schools would let one
tenant's file rewrite another's rows. Only fields the rail actually syncs may be declared
authoritative -- a local-only correction would never reach the other node, so accepting one
would promise a convergence this cannot deliver.

EXAMPLE. Join on the name tokens each node still holds, and let the roster settle the code:

    python manage.py reconcile_sync_conflicts_from_source \\
        --school 3 --entity student \\
        --source roster.xlsx \\
        --match "Name=first_name+last_name:name_tokens:subset" \\
        --authoritative "Admission Number=student_code"
"""

from __future__ import annotations

import json
import pathlib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

# Outcomes. Only SETTLED and ALREADY_MATCHES ever close a conflict.
SETTLED = "settled"
ALREADY_MATCHES = "already_matches"
PARTIAL = "partial"
SOURCE_SILENT = "source_silent"
DERIVED_SPLIT = "derived_split"
NO_SOURCE_ROW = "no_source_row"
AMBIGUOUS_SOURCE = "ambiguous_source"
CONTESTED_SOURCE = "contested_source"
NO_KEY = "no_key"
ROW_MISSING = "row_missing"
NOT_DIFFERENT = "not_different"
CONVENTION_APPLIED = "convention_applied"

#: What to do with a splitter disagreement the roster cannot speak to. LEAVE is the
#: default because it is the only one that needs no decision; the other two ARE the
#: decision, and the operator makes it explicitly on the command line.
LEAVE = "leave"
KEEP_LOCAL = "keep-local"
KEEP_INCOMING = "keep-incoming"
CONVENTIONS = (LEAVE, KEEP_LOCAL, KEEP_INCOMING)

_CLOSES = (SETTLED, ALREADY_MATCHES, CONVENTION_APPLIED)

_EXPLAIN = {
    SETTLED: "the roster carries every field that differed; its value was written",
    ALREADY_MATCHES: "the row already holds what the roster says; nothing to write",
    PARTIAL: "the roster settles some of the differing fields but not all -- left whole",
    SOURCE_SILENT: "the roster has no column for what differs, so it cannot adjudicate",
    DERIVED_SPLIT: "the same value under different field names -- one splitter vs another",
    NO_SOURCE_ROW: "no line in the roster matches this row",
    AMBIGUOUS_SOURCE: "several roster lines match; the key does not identify a student",
    CONTESTED_SOURCE: "two roster lines claim this value; the register contradicts itself",
    NO_KEY: "the row cannot produce a match key, so the roster was never asked",
    ROW_MISSING: "the row is gone; whether the deletion or the change wins is a decision",
    NOT_DIFFERENT: "nothing differs any more -- resolve_identical_sync_conflicts closes these",
    CONVENTION_APPLIED: "a splitter disagreement closed by the convention you named",
}


def _parse_clause(raw: str, *, with_mode: bool):
    """``column=field[:matcher[:mode]]`` -> parts. Explicit because a typo must not match."""
    text = str(raw).strip()
    if "=" not in text:
        raise CommandError("expected 'column=field', got %r" % raw)
    column, rest = text.split("=", 1)
    bits = [b.strip() for b in rest.split(":")]
    field = bits[0]
    if not column.strip() or not field:
        raise CommandError("both sides of '=' must be non-empty in %r" % raw)
    if not with_mode:
        if len(bits) > 1:
            raise CommandError("--authoritative takes 'column=field' only, got %r" % raw)
        return column, field
    matcher_name = bits[1] if len(bits) > 1 and bits[1] else "exact"
    mode = bits[2] if len(bits) > 2 and bits[2] else "equal"
    return column, field, matcher_name, mode


class Command(BaseCommand):
    help = (
        "Resolve PENDING sync conflicts using an authoritative source roster. "
        "Dry run unless --apply is passed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="School pk. A roster is one school's.")
        parser.add_argument("--entity", required=True, help="entity_type, e.g. student.")
        parser.add_argument("--source", required=True, help="Path to the .xlsx or .csv roster.")
        parser.add_argument(
            "--sheet", default="", help="Worksheet name or index. Default: the first."
        )
        parser.add_argument(
            "--match",
            action="append",
            default=[],
            metavar="COLUMN=FIELD[:MATCHER[:MODE]]",
            help=(
                "How a roster line is joined to a row. Repeatable; every clause must "
                "match. FIELD may join several model attributes with '+'. MATCHER is one "
                "of exact, alnum, digits, name_tokens, date. MODE is equal or subset "
                "(subset needs name_tokens, and is what survives a split disagreement)."
            ),
        )
        parser.add_argument(
            "--authoritative",
            action="append",
            default=[],
            metavar="COLUMN=FIELD",
            help=(
                "A field the roster is allowed to settle. Repeatable. Fields the rail "
                "does not sync are rejected: correcting one would never reach the "
                "other node."
            ),
        )
        parser.add_argument(
            "--derived-split",
            dest="derived_split",
            choices=list(CONVENTIONS),
            default=LEAVE,
            help=(
                "What to do when the roster is silent AND the two sides hold the same "
                "values under different field names -- one splitter variant disagreeing "
                "with another. 'keep-local' keeps the row as it stands; 'keep-incoming' "
                "takes the client's decomposition. Applies ONLY to that class, never to "
                "a genuine disagreement. Default: leave it PENDING."
            ),
        )
        parser.add_argument("--apply", action="store_true", help="Actually write. Off by default.")
        parser.add_argument("--limit", type=int, default=0, help="Examine at most N (0 = all).")
        parser.add_argument("--chunk", type=int, default=500, help="Rows per batch.")
        parser.add_argument(
            "--sample",
            type=int,
            default=0,
            help=(
                "Print N unresolved conflicts in full, INCLUDING VALUES. Tenant data goes "
                "to your terminal -- choose where you run it. 0 = none."
            ),
        )
        parser.add_argument("--json", action="store_true", help="Emit JSON only.")

    # -- helpers ---------------------------------------------------------------

    def _load_rows(self, model, school_id, pks):
        """``{str(pk): instance}`` scoped to the school. Tenant scope is not optional."""
        qs = model._base_manager.filter(pk__in=list(pks))
        if any(
            getattr(f, "name", None) == "school"
            for f in model._meta.get_fields()
            if getattr(f, "concrete", False)
        ):
            qs = qs.filter(school_id=school_id)
        return {str(obj.pk): obj for obj in qs}

    def _differing(self, conflict, instance, allowed):
        from apps.api.sync_services import _same_field_value

        payload = conflict.client_data if isinstance(conflict.client_data, dict) else {}
        comparable = {k: v for k, v in payload.items() if k in allowed}
        return (
            tuple(
                key
                for key, incoming in sorted(comparable.items())
                if not _same_field_value(
                    type(instance), key, getattr(instance, key, None), incoming
                )
            ),
            payload,
        )

    def _derived_split_fields(self, instance, payload, fields):
        """WHICH fields hold the SAME value under DIFFERENT field names on the two sides.

        That is the signature of one splitter disagreeing with another rather than of two
        people editing a record. ``first_last`` and ``last_first`` both put token 0
        somewhere -- one calls it the first name, the other the last -- so the value
        survives and only its label moves. Two independent human edits would not do that.

        It returns the participating fields rather than a yes/no because the answer is
        per-field evidence, and the caller may act only where the evidence reaches. A row
        can differ on a name pair AND on a code the roster left blank; the crossover
        demonstrates something about the names and nothing whatever about the code.
        """
        from apps.sync_engine.source_authority import _m_exact

        involved: set[str] = set()
        for local_field in fields:
            local_value = _m_exact(getattr(instance, local_field, None))
            if local_value is None:
                continue
            for incoming_field in fields:
                if incoming_field == local_field:
                    continue
                if _m_exact(payload.get(incoming_field)) == local_value:
                    involved.add(local_field)
                    involved.add(incoming_field)
        return tuple(sorted(involved))

    def _contested_values(self, rows, specs, authoritative):
        """``{column: {value, ...}}`` the source assigns to more than one distinct line.

        The join already refuses when one row matches several roster lines. This is the
        same defect seen from the other side: one roster VALUE claimed by several lines.
        A real 431-line register did it eight times -- two different students, one
        admission number -- and either way round it is the register contradicting itself,
        so it is evidence for neither student and settles nothing.

        Unchecked, the pleasant failure is an IntegrityError against the unique column
        that rolls back every unrelated row sharing the batch. The unpleasant one is
        quieter: when only ONE of the pair is in conflict there is no collision at all,
        and a contested number is written as though the register had confirmed it.

        Identity is the match KEY, not the line number, so a student listed twice
        identically is one claim, not two.
        """
        from apps.sync_engine.source_authority import is_blank, source_key

        claims: dict[str, dict[str, set]] = {c: {} for c in authoritative.values()}
        for row in rows:
            key = source_key(row, specs)
            if key is None:
                continue  # never returned by a lookup, so it can contest nothing
            for column, by_value in claims.items():
                raw = row.get(column)
                if is_blank(raw):
                    continue
                by_value.setdefault(str(raw).strip().casefold(), set()).add(key)
        return {
            column: frozenset(v for v, keys in by_value.items() if len(keys) > 1)
            for column, by_value in claims.items()
        }

    def _coerce(self, model, field_name, raw):
        """The roster's text as the column's Python type, or None when it will not go."""
        from django.core.exceptions import ValidationError

        from apps.api.sync_services import _concrete_field

        field = _concrete_field(model, field_name)
        if field is None:
            return None
        target = getattr(field, "target_field", None) if field.is_relation else None
        to_python = getattr(target or field, "to_python", None)
        if to_python is None:
            return None
        try:
            return to_python(raw)
        except (ValidationError, TypeError, ValueError, ArithmeticError):
            return None

    # -- main ------------------------------------------------------------------

    def handle(self, *args, **options):
        from apps.api.sync_services import _get_entity_config, _same_field_value
        from apps.siteconfig.models import SyncConflict
        from apps.sync_engine.source_authority import (
            KeySpec,
            SourceIndex,
            is_blank,
            load_source_rows,
            normalise_header,
            source_fingerprint,
        )

        convention = str(options["derived_split"]).strip().lower()
        if convention not in CONVENTIONS:
            # argparse `choices` guards the command line only; call_command passes a
            # keyword straight through. An unrecognised value used to fall through to
            # keep-incoming -- the branch that writes -- so a typo overwrote rows.
            raise CommandError(
                "unknown --derived-split %r; choose one of: %s"
                % (options["derived_split"], ", ".join(CONVENTIONS))
            )

        entity = str(options["entity"]).strip().lower()
        entry = _get_entity_config(include_derived=True).get(entity)
        if entry is None:
            raise CommandError("entity %r is not on the sync rail" % entity)
        model, allowed = entry

        if not options["match"]:
            raise CommandError("at least one --match clause is required")
        if not options["authoritative"]:
            raise CommandError("at least one --authoritative clause is required")

        try:
            specs = [
                KeySpec(*_parse_clause(raw, with_mode=True)) for raw in options["match"]
            ]
        except ValueError as exc:
            raise CommandError(str(exc)) from None

        authoritative = {}
        for raw in options["authoritative"]:
            column, field = _parse_clause(raw, with_mode=False)
            if field not in allowed:
                raise CommandError(
                    "%r is not a field the rail syncs for %r (it syncs: %s). Correcting "
                    "it would never reach the other node."
                    % (field, entity, ", ".join(sorted(allowed)))
                )
            authoritative[field] = normalise_header(column)

        source_path = pathlib.Path(options["source"]).expanduser()
        try:
            rows = load_source_rows(source_path, options["sheet"] or None)
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        if not rows:
            raise CommandError("the source file has no data rows: %s" % source_path)

        missing = sorted(
            {c for c in authoritative.values() if c not in rows[0]}
            | {s.column for s in specs if s.column not in rows[0]}
        )
        if missing:
            raise CommandError(
                "columns not in the source (its columns are: %s): %s"
                % (", ".join(sorted(rows[0])), ", ".join(missing))
            )

        index = SourceIndex(rows, specs)
        # Built once, beside the index, because it is the same question asked the
        # other way round: the index refuses when one row reaches many lines, this
        # refuses when one value is claimed by many lines.
        contested = self._contested_values(rows, specs, authoritative)
        fingerprint = source_fingerprint(source_path)
        note_stem = "source:%s#%s" % (source_path.name[:60], fingerprint)

        pending = SyncConflict.objects.filter(
            status=SyncConflict.Status.PENDING,
            school_id=options["school"],
            entity_type=entity,
        )
        pks = list(pending.order_by("pk").values_list("pk", flat=True))
        limit = max(0, int(options["limit"]))
        if limit:
            pks = pks[:limit]

        outcomes: dict[str, int] = {}
        settled_fields: dict[str, int] = {}
        diagnostics: dict[str, int] = {}
        samples: list = []
        sample_cap = max(0, int(options["sample"]))
        chunk = max(1, int(options["chunk"]))
        examined = 0
        closed = 0

        for start in range(0, len(pks), chunk):
            window = pks[start : start + chunk]
            batch = list(SyncConflict.objects.filter(pk__in=window).order_by("pk"))
            examined += len(batch)
            closed += self._run_batch(
                batch, model, allowed, options["school"], index, authoritative,
                contested, bool(options["apply"]), note_stem, outcomes, settled_fields,
                samples, sample_cap, diagnostics, convention,
                _same_field_value=_same_field_value, _is_blank=is_blank,
            )

        return self._report(
            {
                "school": str(options["school"]),
                "entity": entity,
                "source": str(source_path),
                "source_fingerprint": fingerprint,
                "derived_split": str(options["derived_split"]),
                "source_rows": len(rows),
                "examined": examined,
                "closed": closed,
                "outcomes": outcomes,
                "settled_fields": settled_fields,
                "diagnostics": diagnostics,
                "samples": samples,
            },
            bool(options["apply"]),
            bool(options["json"]),
        )

    def _run_batch(
        self, batch, model, allowed, school_id, index, authoritative, contested, do_apply,
        note_stem, outcomes, settled_fields, samples, sample_cap, diagnostics, convention,
        *, _same_field_value, _is_blank,
    ):
        from apps.siteconfig.models import SyncConflict

        instances = self._load_rows(model, school_id, {c.entity_id for c in batch})
        writes = []  # (conflict, instance, {field: value})

        for conflict in batch:
            instance = instances.get(str(conflict.entity_id))
            if instance is None:
                self._tally(outcomes, ROW_MISSING)
                continue

            fields, payload = self._differing(conflict, instance, allowed)
            if not fields:
                self._tally(outcomes, NOT_DIFFERENT)
                continue

            hits = index.lookup(instance)
            if hits is None:
                self._tally(outcomes, NO_KEY)
                self._sample(samples, sample_cap, NO_KEY, conflict, instance, payload, fields)
                continue
            if not hits:
                self._tally(outcomes, NO_SOURCE_ROW)
                self._sample(samples, sample_cap, NO_SOURCE_ROW, conflict, instance, payload, fields)
                continue
            if len(hits) > 1:
                self._tally(outcomes, AMBIGUOUS_SOURCE)
                self._sample(
                    samples, sample_cap, AMBIGUOUS_SOURCE, conflict, instance, payload, fields
                )
                continue

            row = hits[0]
            # ALL OR NOTHING. A field the roster does not carry -- or carries blank -- is
            # not settled, and one unsettled field means the whole row stays for a human.
            updates = {}
            unsettled = []
            contested_here = []
            for field in fields:
                column = authoritative.get(field)
                raw = row.get(column) if column else None
                if column is None or _is_blank(raw):
                    unsettled.append(field)
                    continue
                if str(raw).strip().casefold() in contested.get(column, ()):
                    # Another line claims this same value. The register is disagreeing
                    # with itself, and an unresolved disagreement is exactly what this
                    # module refuses to launder into an answer.
                    contested_here.append(field)
                    unsettled.append(field)
                    continue
                value = self._coerce(model, field, raw)
                if value is None:
                    unsettled.append(field)
                    continue
                updates[field] = value

            from_convention = ()
            split_like = False
            if unsettled:
                # Ask about the UNSETTLED fields, not all of them. A row whose code the
                # roster settled still has a splitter disagreement in what is left, and
                # that remainder is the SAME single decision as a row where the roster
                # settled nothing. Counting only the latter reports N decisions where
                # there is one -- which is the whole finding, inverted.
                split_fields = self._derived_split_fields(instance, payload, unsettled)
                split_like = bool(split_fields)
                if split_like:
                    diagnostics["derived_split_like"] = (
                        diagnostics.get("derived_split_like", 0) + 1
                    )

                # A CONVENTION, applied only where the two sides demonstrably hold the
                # same values under different field names. That evidence is what makes
                # this safe: it is not "believe one node", which would be the timestamp
                # guess wearing a flag, but "these two rows are one row decomposed twice,
                # and a human has said which decomposition the school uses". A genuine
                # disagreement never reaches here, because its values do not cross over.
                #
                # And ONLY to the fields that demonstrate the crossover. A row can be
                # unsettled on a name pair AND on a code the roster left blank; the
                # evidence for the names says nothing whatever about the code, so
                # deciding the code by a rule about name splits is "believe one node"
                # for a field no evidence covers. Anything left over keeps the row
                # whole, under the same all-or-nothing rule as everything else.
                # The guard is the FIELD SET, not a separate boolean: a genuine
                # disagreement produces no crossing-over fields, so there is nothing
                # here to decide. Asking `split_like` as well would read as a second
                # check while being unable to fail on its own.
                if split_fields and convention != LEAVE:
                    resolved_here = {}
                    for field in split_fields:
                        if convention == KEEP_LOCAL:
                            continue  # the row already holds it; nothing to write
                        value = self._coerce(model, field, payload.get(field))
                        if value is None:
                            resolved_here = None
                            break
                        resolved_here[field] = value
                    if resolved_here is not None:
                        updates.update(resolved_here)
                        from_convention = tuple(split_fields)
                        unsettled = [f for f in unsettled if f not in from_convention]

            if unsettled:
                if contested_here:
                    # Reported ahead of the others because it is the only one naming a
                    # defect in the SOURCE. The rest describe what the register does not
                    # say; this one says the register is wrong, and no amount of
                    # re-running fixes it -- someone has to repair the register.
                    outcome = CONTESTED_SOURCE
                    diagnostics["contested_source"] = (
                        diagnostics.get("contested_source", 0) + 1
                    )
                elif split_like and not updates:
                    outcome = DERIVED_SPLIT
                else:
                    outcome = PARTIAL if updates else SOURCE_SILENT
                self._tally(outcomes, outcome)
                self._sample(samples, sample_cap, outcome, conflict, instance, payload, fields)
                continue

            changed = {
                f: v
                for f, v in updates.items()
                if not _same_field_value(model, f, getattr(instance, f, None), v)
            }
            if from_convention:
                self._tally(outcomes, CONVENTION_APPLIED)
                diagnostics["convention_applied"] = (
                    diagnostics.get("convention_applied", 0) + 1
                )
            else:
                self._tally(outcomes, SETTLED if changed else ALREADY_MATCHES)
            for f in changed:
                settled_fields[f] = settled_fields.get(f, 0) + 1
            roster_settled = tuple(sorted(set(updates) - set(from_convention)))
            writes.append((conflict, instance, changed, from_convention, roster_settled))

        if not do_apply:
            return len(writes)
        if not writes:
            return 0

        now = timezone.now()
        with transaction.atomic():
            for conflict, instance, changed, from_convention, roster_settled in writes:
                if changed:
                    for field, value in changed.items():
                        setattr(instance, field, value)
                    instance.save(update_fields=sorted(changed))

                # The recorded status has to say what actually decided the row, because
                # that is the question someone asks months later. A roster value is a
                # MERGE (neither node won -- an outsider did); a convention that kept the
                # row as it stood is SERVER; one that took the client's decomposition is
                # CLIENT. Recording everything as MERGE would erase the distinction
                # between "the register said so" and "we chose a convention".
                # What DECIDED the field, not what happened to need a write: a roster
                # value equal to the row's current one still adjudicated it, and calling
                # that a convention would credit the policy for the register's work.
                roster_fields = sorted(roster_settled)
                if roster_fields:
                    status = SyncConflict.Status.RESOLVED_MERGE
                elif from_convention and convention == KEEP_INCOMING:
                    status = SyncConflict.Status.RESOLVED_CLIENT
                elif from_convention:
                    status = SyncConflict.Status.RESOLVED_SERVER
                else:
                    status = SyncConflict.Status.RESOLVED_MERGE

                detail = ",".join(roster_fields) or "already-matched"
                if from_convention:
                    # Name the convention AND the fields it decided: a row whose name was
                    # chosen by policy rather than read from a register must say so.
                    detail = "%s convention=%s:%s" % (
                        detail if roster_fields else "",
                        convention,
                        ",".join(sorted(from_convention)),
                    )
                conflict.status = status
                conflict.resolved_at = now
                conflict.resolution_note = ("%s %s" % (note_stem, detail.strip()))[:255]
            SyncConflict.objects.bulk_update(
                [c for c, _i, _u, _p, _r in writes],
                ["status", "resolved_at", "resolution_note"],
                batch_size=len(writes),
            )
        return len(writes)

    def _tally(self, outcomes, key):
        outcomes[key] = outcomes.get(key, 0) + 1

    def _sample(self, samples, cap, outcome, conflict, instance, payload, fields):
        if samples is None or len(samples) >= cap:
            return
        samples.append(
            {
                "outcome": outcome,
                "id": conflict.entity_id,
                "fields": {
                    f: {"incoming": payload.get(f), "local": getattr(instance, f, None)}
                    for f in fields
                },
            }
        )

    def _report(self, summary, do_apply, as_json):
        summary["applied"] = do_apply
        if as_json:
            self.stdout.write(json.dumps(summary, indent=2, sort_keys=True, default=str))
            return

        w = self.stdout.write
        verb = "closed" if do_apply else "would close"
        w("")
        w("source: %s (%d rows, #%s)" % (summary["source"], summary["source_rows"],
                                         summary["source_fingerprint"]))
        w("pending conflicts examined: %d" % summary["examined"])
        w("%s: %d" % (verb, summary["closed"]))
        left = sum(n for k, n in summary["outcomes"].items() if k not in _CLOSES)
        w("left PENDING: %d" % left)

        if summary["outcomes"]:
            w("")
            w("by outcome:")
            for key, n in sorted(summary["outcomes"].items(), key=lambda kv: (-kv[1], kv[0])):
                w("  %-18s %8d   %s" % (key, n, _EXPLAIN.get(key, "")))

        if summary["settled_fields"]:
            w("")
            w("fields the roster settled:")
            for field, n in sorted(summary["settled_fields"].items(), key=lambda kv: (-kv[1], kv[0])):
                w("  %-24s %8d" % (field, n))

        diagnostics = summary.get("diagnostics") or {}
        split = diagnostics.get("derived_split_like", 0)
        applied = diagnostics.get("convention_applied", 0)
        if split:
            w("")
            w("  %d conflict(s) are ONE decision, not %d." % (split, split))
            w("  The same value appears under different field names on the two sides, which")
            w("  is a splitter variant disagreeing with another rather than anyone editing")
            w("  a record. The roster cannot decide it, because it stores the name as a")
            w("  single string -- so the convention is yours to name, not its to reveal.")
            if applied:
                w("  %d of them closed under --derived-split=%s."
                  % (applied, summary.get("derived_split")))
            else:
                w("  Re-run with --derived-split=keep-local (or keep-incoming) to close them")
                w("  once you have decided which decomposition this school uses.")

        for example in summary.get("samples") or []:
            w("")
            w("  [%s] #%s" % (example["outcome"], example["id"]))
            for field, pair in sorted(example["fields"].items()):
                w("    %s: incoming=%r  local=%r" % (field, pair["incoming"], pair["local"]))

        if not do_apply:
            w("")
            w("dry run -- nothing was written. Re-run with --apply to write.")
