#!/usr/bin/env python3
"""Gate: every FK on the edge sync rail must point at a row the box can actually have.

THE RULE. A delta bundle ships FK columns as raw ids, and the box resolves each id
against its own database. That only works when the parent row exists on both sides
under the SAME pk, which the provisioning clone guarantees for exactly one class of
row: rows a SCHOOL OWNS. The clone is per-school, so it carries what is scoped to that
school and nothing else.

WHAT THE ENGINE USED TO CHECK. ``_derive_sync_fields`` let an FK ride when its target
model lived in a tenant APP. That is a proxy, and it is wrong in one direction: a
tenant app may also hold a SHARED table that no school owns. Three FKs were riding on
that mistake -- ``finance.Invoice.counterparty``, ``finance.Invoice.profile`` and
``people.TeacherProfile.pay_scale`` -- pointing at ``finance.Counterparty``,
``finance.ComplianceProfile`` and ``payroll.PayScale``, none of which has a ``school``
column and none of which rides the rail.

HOW IT FAILED. Not loudly. A parent created on the cloud AFTER a box was cloned simply
does not exist on the box, so the referential preflight refuses the child -- and the
runner reads that refusal as "a parent is behind the cursor" and rewinds the pull
cursor for a full-corpus replay. The replay cannot produce a row the rail does not
carry, so it happens again, every cooldown, forever; and because a full-corpus pull
re-offers every row the box already holds, it also drove waves of avoidable conflict
records through the apply path. One unportable FK, and the symptom was a sync that
looked busy while nothing landed.

THE INVARIANT THIS PINS. Every FK inside a rail entity's allowed field set targets a
TENANT-SCOPED model -- unless it is declared below with a reason.

  ACCEPTED_UNPORTABLE -- rides anyway because the column is NOT NULL, so the row cannot
                         be created without it. Dropping such an FK does not degrade the
                         row, it makes the row impossible. These are real, permanent
                         gaps: the reference resolves only while the parent happens to
                         predate the clone. Closing one for good means giving the parent
                         a tenant scope, or putting it on the rail, or holding the child
                         entity's inserts -- a design change, which is why it is written
                         down here instead of being fixed by another sync.

A NULLABLE unportable FK may NOT be parked on that list. Nullable means dropping it is
free and strictly better -- the row lands, missing one link the box could not render
anyway -- so the fix is to drop it, and this gate says so rather than letting the
easier answer be recorded as a decision.

Runs with no database: model metadata only.

Exit 0 = every rail FK is portable or declared. Exit 1 otherwise.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# FKs that ride despite an unportable target, because the column is NOT NULL.
# Key is "<app>.<Model>.<field>". Add one ONLY after confirming the column really is
# NOT NULL and the child entity really is created on a box (an insert-held entity does
# not need its NOT NULL parent on the rail at all).
ACCEPTED_UNPORTABLE: dict[str, str] = {
    "finance.Invoice.profile":
        "NOT NULL, and `invoice` is not insert-held, so the box does create invoices "
        "from cloud-authored rows -- an invoice with no compliance profile cannot be "
        "written at all. finance.ComplianceProfile is regional accounting configuration "
        "(currency, VAT rate, chart template) with no `school` column, so it is shared "
        "platform data rather than tenant data and cannot be put on a per-school rail "
        "without inventing a tenant scope it does not have. The reference resolves for "
        "every profile the clone carried; an invoice pointing at a profile created after "
        "the clone is refused, reported by name, and no longer rewinds the pull cursor.",
}


def _bootstrap(root: Path) -> None:
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _is_tenant_scoped(model) -> bool:
    return any(
        getattr(f, "name", None) == "school"
        for f in model._meta.get_fields()
        if getattr(f, "concrete", False)
    )


def _survey():
    """``(rows, rail_labels)`` where each row describes one FK on the rail."""
    from apps.api.sync_services import _fk_reference_targets, _get_entity_config

    config = _get_entity_config(include_derived=True)
    rail_labels = {model._meta.label for model, _allowed in config.values()}
    rows = []
    for entity, (model, allowed) in sorted(config.items()):
        for attname, target in sorted(_fk_reference_targets(model, allowed).items()):
            field_name = attname[:-3] if attname.endswith("_id") else attname
            try:
                field = model._meta.get_field(field_name)
            except Exception:  # noqa: BLE001 - report it, do not crash the gate
                field = None
            rows.append(
                {
                    "entity": entity,
                    "attname": attname,
                    "key": f"{model._meta.label}.{field_name}",
                    "target": target._meta.label if target is not None else "",
                    "scoped": bool(target is not None and _is_tenant_scoped(target)),
                    "on_rail": bool(
                        target is not None and target._meta.label in rail_labels
                    ),
                    "nullable": bool(getattr(field, "null", False)) if field else False,
                }
            )
    return rows, rail_labels


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="print every rail FK")
    args = parser.parse_args()

    _bootstrap(Path(__file__).resolve().parents[1])
    rows, _rail = _survey()

    unresolved = [r for r in rows if not r["target"]]
    unportable = [r for r in rows if r["target"] and not r["scoped"]]
    undeclared = [r for r in unportable if r["key"] not in ACCEPTED_UNPORTABLE]
    droppable = [
        r for r in unportable if r["key"] in ACCEPTED_UNPORTABLE and r["nullable"]
    ]
    present = {r["key"] for r in unportable}
    stale = sorted(set(ACCEPTED_UNPORTABLE) - present)

    with_fks = len({r["entity"] for r in rows})
    print(
        f"rail entities carrying an FK: {with_fks}   FK edges on the rail: {len(rows)}"
    )
    if args.verbose:
        for r in rows:
            state = "scoped" if r["scoped"] else "UNSCOPED"
            rail = "on-rail" if r["on_rail"] else "off-rail"
            null = "null=True" if r["nullable"] else "NOT NULL"
            print(
                f"  {r['entity']:<20} {r['attname']:<24} {r['target']:<28} "
                f"{rail:<9} {state:<9} {null}"
            )

    failed = False

    if unresolved:
        failed = True
        print(
            f"\nFAIL: {len(unresolved)} FK on the rail has no resolvable target model. A "
            "reference the gate cannot resolve is one the apply path cannot resolve either:"
        )
        for r in unresolved:
            print(f"  - {r['entity']}.{r['attname']}")

    if undeclared:
        failed = True
        print(
            f"\nFAIL: {len(undeclared)} FK on the rail points at a model with no `school` "
            "column. The provisioning clone is per-school, so it does not carry that "
            "parent, and a parent created on the cloud after the clone can never reach a "
            "box. Drop the field from the rail if it is NULLABLE; if it is NOT NULL, add "
            "it to ACCEPTED_UNPORTABLE with the reason it must keep riding:"
        )
        for r in undeclared:
            verdict = (
                "NULLABLE -> drop it from the rail"
                if r["nullable"]
                else "NOT NULL -> declare it"
            )
            print(f"  - {r['key']} -> {r['target']}   ({verdict})")

    if droppable:
        failed = True
        print(
            f"\nFAIL: {len(droppable)} FK is declared in ACCEPTED_UNPORTABLE but is "
            "NULLABLE. That list is only for columns a row cannot exist without. A "
            "nullable unportable FK must be DROPPED from the rail instead -- keeping it "
            "costs the whole row whenever the parent is absent, and buys a link the box "
            "cannot render:"
        )
        for r in droppable:
            print(f"  - {r['key']} -> {r['target']}")

    if stale:
        failed = True
        print(
            f"\nFAIL: {len(stale)} entry in ACCEPTED_UNPORTABLE no longer describes a "
            "live rail FK. Delete it, so the list can only shrink:"
        )
        for key in stale:
            print(f"  - {key}")

    if not failed:
        declared = len(ACCEPTED_UNPORTABLE)
        print(
            "\nOK: every FK on the rail targets a tenant-scoped model, except "
            f"{declared} declared NOT NULL reference(s)."
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
