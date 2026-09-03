"""Say what the sync rail carries, what it does not, and how much is stranded here.

    python manage.py edge_rail_coverage
    python manage.py edge_rail_coverage --counts            # census the stranded rows
    python manage.py edge_rail_coverage --counts --slug <school-slug>
    python manage.py edge_rail_coverage --json

WHY THIS EXISTS. "Does the box have parity with the cloud?" was answered three times in
one session by three throwaway scripts, and one of those answers was WRONG in a way that
mattered: it read ``policy_registry.get_policy`` and concluded 13 of 17 entities fell
through to protected manual review, when in fact they are listed in
``_LWW_SAFE_ENTITIES`` and converge two-way. The registry is not the authority --
``sync_services._sync_conflict_policy`` is, and it resolves in THREE tiers. A question
that gets re-derived by hand gets re-derived wrongly; so it is a command.

THE QUESTION IT ACTUALLY ANSWERS. An appliance is only useful if work done on it reaches
the cloud. Two different things can stop that, and they are usually confused:

  * the entity is on the rail but its POLICY holds the change (money, marks) or refuses
    to create it (``teacher``, because minting a login is an authentication decision);
  * the model is not on the rail AT ALL, so nothing it holds will ever travel, silently
    and forever.

The second is the one nobody sees, because it produces no error, no conflict and no
refusal. A row simply exists in one place. ``--counts`` puts a NUMBER on it, per model,
because "344 models are not registered" is architecture and "these 12,481 rows on this
box can never reach the cloud" is a decision an operator can act on.

READ-ONLY. It opens no transaction and writes nothing. Safe to run on a live box.
"""
from __future__ import annotations

import json

from django.core.exceptions import FieldError
from django.core.management.base import BaseCommand
from django.db import DataError, OperationalError, ProgrammingError


def _rail_state():
    """``(entity -> facts)`` for every registered edge entity, asked of the real resolvers."""
    from apps.api.sync_services import (
        _INSERT_HELD_ENTITIES,
        _LWW_SAFE_ENTITIES,
        _get_entity_config,
        _sync_conflict_policy,
    )
    from apps.sync_engine.policy_registry import POLICIES, normalize_entity

    out = {}
    for entity, (model, _fields) in _get_entity_config(include_derived=True).items():
        norm = normalize_entity(entity)
        if norm in POLICIES:
            tier = "POLICIES"
        elif entity in _LWW_SAFE_ENTITIES or norm in _LWW_SAFE_ENTITIES:
            tier = "_LWW_SAFE"
        else:
            # Nobody classified it: behaviour comes from the fail-closed default.
            tier = "UNCLASSIFIED"
        strategy, protected = _sync_conflict_policy(entity)
        anchored = any(
            getattr(f, "name", "") == "client_offline_id" for f in model._meta.get_fields()
        )
        out[entity] = {
            "model": model._meta.label,
            "strategy": strategy,
            "protected": bool(protected),
            "tier": tier,
            "insert_held": entity in _INSERT_HELD_ENTITIES,
            "anchored": anchored,
            # What an operator actually wants to know: can work done HERE get home?
            "box_can_create": anchored and entity not in _INSERT_HELD_ENTITIES,
            "box_edit_is_held": bool(protected),
        }
    return out


def _tenant_models():
    """Every model carrying a ``school`` relation - the rows a tenant owns."""
    from django.apps import apps as django_apps

    models = []
    for model in django_apps.get_models():
        for f in model._meta.get_fields():
            if getattr(f, "name", "") == "school" and getattr(f, "is_relation", False):
                models.append(model)
                break
    return models


def _count(model, school=None):
    """Rows, or ``None`` when this deployment cannot answer.

    A model may be registered in code and absent from THIS database (a migration that has
    not run in this schema, an app installed but never migrated). Returning None is the
    honest answer; reporting 0 would be indistinguishable from an empty table and would
    make a stranded-data census read as reassuring.
    """
    try:
        qs = model._base_manager.all()
        if school is not None:
            qs = qs.filter(school=school)
        return qs.count()
    except (ProgrammingError, OperationalError, DataError, FieldError, ValueError):
        return None


class Command(BaseCommand):
    help = "Report what the edge sync rail carries, and how much tenant data it does not."

    def add_arguments(self, parser):
        parser.add_argument(
            "--counts",
            action="store_true",
            help="Census the rows that cannot travel. Slower: one COUNT per tenant model.",
        )
        parser.add_argument(
            "--slug", default="", help="Scope the census to one school."
        )
        parser.add_argument("--json", action="store_true", help="Machine-readable output.")
        parser.add_argument(
            "--top",
            type=int,
            default=25,
            help="How many stranded models to list, largest first (default 25).",
        )

    def handle(self, *args, **options):
        rail = _rail_state()
        rail_labels = {f["model"] for f in rail.values()}
        tenant = _tenant_models()
        stranded_models = [m for m in tenant if m._meta.label not in rail_labels]

        school = None
        if options["slug"]:
            from apps.schools.models import School

            school = School.objects.filter(slug=options["slug"]).first()
            if school is None:
                self.stderr.write(self.style.ERROR(
                    "No school with slug %r on this deployment." % options["slug"]
                ))
                return

        payload = {
            "registered_entities": len(rail),
            "tenant_scoped_models": len(tenant),
            "models_not_on_rail": len(stranded_models),
            "entities": rail,
            "protected": sorted(e for e, f in rail.items() if f["protected"]),
            "insert_held": sorted(e for e, f in rail.items() if f["insert_held"]),
            "unclassified": sorted(e for e, f in rail.items() if f["tier"] == "UNCLASSIFIED"),
            "school": getattr(school, "slug", None),
        }

        if options["counts"]:
            census, unreadable, total = [], [], 0
            for model in stranded_models:
                n = _count(model, school)
                if n is None:
                    unreadable.append(model._meta.label)
                    continue
                total += n
                if n:
                    census.append((n, model._meta.label))
            census.sort(reverse=True)
            payload["stranded_rows_total"] = total
            payload["stranded_models_with_rows"] = len(census)
            payload["unreadable_models"] = unreadable
            # A consumer of the JSON must be able to tell a real total from a floor
            # without re-deriving it. `stranded_rows_total` is only a TOTAL when this is
            # true; otherwise it is a lower bound over the models that could be read.
            payload["census_complete"] = not unreadable
            payload["stranded_top"] = [
                {"model": lbl, "rows": n} for n, lbl in census[: options["top"]]
            ]

        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        w = self.stdout.write
        w("")
        w("EDGE SYNC RAIL -- what can travel")
        w("  registered entities .......... %d" % payload["registered_entities"])
        w("  a box may CREATE these ....... %d"
          % sum(1 for f in rail.values() if f["box_can_create"]))
        w("  refused on create (identity) . %s"
          % (", ".join(payload["insert_held"]) or "none"))
        w("  a box EDIT is held for review  %s"
          % (", ".join(payload["protected"]) or "none"))
        if payload["unclassified"]:
            w(self.style.WARNING(
                "  UNCLASSIFIED (behaviour comes from the fail-closed default, which "
                "nobody chose for them): %s" % ", ".join(payload["unclassified"])
            ))
        w("")
        w("%-24s %-14s %-10s %-12s %s" % ("ENTITY", "STRATEGY", "PROTECTED", "TIER", "MODEL"))
        for entity in sorted(rail):
            f = rail[entity]
            flag = "HELD" if f["insert_held"] else ("yes" if f["protected"] else "-")
            w("%-24s %-14s %-10s %-12s %s"
              % (entity, f["strategy"], flag, f["tier"], f["model"]))

        w("")
        w("WHAT THE RAIL DOES NOT CARRY")
        w("  tenant-scoped models ......... %d" % payload["tenant_scoped_models"])
        w("  NOT registered on the rail ... %d" % payload["models_not_on_rail"])

        if not options["counts"]:
            w("")
            w("  Re-run with --counts for the rows those models hold on THIS deployment.")
            w("  A model that is not on the rail produces no error and no conflict when it")
            w("  fails to sync -- the rows simply stay where they were written.")
            return

        unreadable = len(payload["unreadable_models"])
        readable = payload["models_not_on_rail"] - unreadable
        w("  models read .................. %d of %d"
          % (readable, payload["models_not_on_rail"]))
        w("  models holding rows .......... %d" % payload["stranded_models_with_rows"])
        scope = "" if school is None else " (school=%s)" % school.slug
        if unreadable:
            # NEVER print a bare total next to a pile of failed reads. A census that could
            # not read 353 of 353 models and prints "0" is not reporting zero stranded
            # rows -- it is reporting that it failed, in the shape of good news. That
            # confusion is the same one that let a delete bundle print `deleted 0`.
            w(self.style.ERROR(
                "  CENSUS INCOMPLETE: %d of %d models could not be read on this "
                "deployment (not migrated here?), so the figure below is a FLOOR, not a "
                "total." % (unreadable, payload["models_not_on_rail"])
            ))
            w(self.style.WARNING(
                "  rows that cannot travel ...... AT LEAST %d%s"
                % (payload["stranded_rows_total"], scope)
            ))
        else:
            w(self.style.WARNING(
                "  ROWS THAT CANNOT TRAVEL ...... %d%s"
                % (payload["stranded_rows_total"], scope)
            ))
        if payload["stranded_top"]:
            w("")
            w("  largest, this deployment:")
            for row in payload["stranded_top"]:
                w("    %10d  %s" % (row["rows"], row["model"]))
