#!/usr/bin/env python
"""Every TENANT_APPS model must declare an edge-sync rail posture.

Why this gate exists
--------------------
The edge appliance replicates a small fraction of the product. Measured on
2026-08-31: **17 entities ride the delta rail**, of which **15 are tenant
business models**, against **326 models in the 15 apps of ``TENANT_APPS``**
-- about **4.6%**. "The school keeps working offline" therefore
means, precisely: attendance, marks, the academic backbone, the staff roster, and
read-only invoices. A box cannot send a message, produce a report card, log a
behaviour or safeguarding incident, or run payroll and have any of it converge.

That is not automatically a defect. Some absences are correct and argued:
``finance.Payment`` is held out for two independently sufficient reasons
(``docs/EDGE_SYNC_FINANCE_HOLD.md``), and ``policy_registry`` declares
``payment_settlement`` ONLINE_REQUIRED because charging a gateway is a live
transaction. The defect this gate closes is that **most absences carried no
recorded decision at all**, and nothing would notice a new tenant model quietly
joining that silence.

So this is a DECLARATION gate, not a coverage target. It never says "wire more
models onto the rail" -- wiring 300 models onto a rail would be reckless. It says
a tenant model must state where it stands, exactly the way this repo already
forces a model to declare its tenancy.

What counts as a finding
------------------------
Hard failures (never absorbed by a baseline):

* ``undeclared``            -- a tenant model with no posture at all.
* ``held_without_rationale``-- HELD with nothing written down. An unargued hold
                               is a NOT_YET wearing a badge.
* ``held_without_pointer``  -- HELD with no ``argued_in`` reference.
* ``not_yet_with_rationale``-- an argument recorded under NOT_YET. If there is an
                               argument, the posture is HELD.
* ``held_but_riding``       -- declared HELD yet actually registered on the live
                               rail. Somebody wrote "must not ride" and wired it.
* ``invalid_posture``       -- includes hand-writing ``RIDES``, which is DERIVED.
* ``unknown_model``         -- a declaration key matching no live tenant model.
* ``tenant_apps_drift``     -- the settings source and the running settings
                               disagree about TENANT_APPS, so every number here
                               would be measured against the wrong denominator.

Baselined backlog (``--compare``): the ``NOT_YET`` set. The 309 undecided models
that exist today must not block the build, but the backlog may only GROW through
a deliberate ``--update-baseline`` commit, so a new model landing as "nobody has
decided" is visible in the diff instead of invisible.

What RIDES is never asserted here. It is derived from
``apps.api.sync_services``'s live registry on every run, so registering a new
entity changes this report with no edit to the declaration.

Usage
-----
    python scripts/audit_rail_coverage.py                  # report
    python scripts/audit_rail_coverage.py --compare        # CI: fail on NEW findings
    python scripts/audit_rail_coverage.py --update-baseline
    python scripts/audit_rail_coverage.py --json

Declare a posture in ``apps/sync_engine/rail_coverage.py::DECLARATIONS``; the
current state per app is written up in ``docs/EDGE_SYNC_COVERAGE_MATRIX.md``.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.sync_engine import rail_coverage  # noqa: E402

BASELINE = REPO_ROOT / "var" / "edge-sync-rail-coverage-baseline.json"


def _print_report(report) -> None:
    tenant_rides = report.total_rides
    shared_rides = len(report.rides_outside_tenant_apps)
    print("Edge-sync rail coverage")
    print("=" * 72)
    print(
        f"  tenant models (migration state, {len(report.apps)} TENANT_APPS): "
        f"{report.total_models}"
    )
    print(
        f"  RIDES  : {tenant_rides:4d}  ({report.coverage_pct:.1f}% of tenant models)"
    )
    print(f"  HELD   : {report.total_held:4d}  (argued exclusions)")
    print(f"  NOT_YET: {report.total_not_yet:4d}  (undecided backlog)")
    print(f"  UNDECLARED: {report.total_undeclared:4d}")
    if shared_rides:
        print(
            f"  + {shared_rides} rail entit(ies) in SHARED apps, not school data: "
            + ", ".join(
                f"{label} ({entity})"
                for label, entity in report.rides_outside_tenant_apps.items()
            )
        )
    print()
    print(f"  {'app':16s} {'models':>6s} {'RIDES':>6s} {'HELD':>5s} {'NOT_YET':>8s} {'UNDECL':>7s}")
    print("  " + "-" * 54)
    for app in report.apps:
        print(
            f"  {app.label:16s} {app.total:6d} {len(app.rides):6d} "
            f"{len(app.held):5d} {len(app.not_yet):8d} {len(app.undeclared):7d}"
        )
    print()
    zero = [a.label for a in report.apps if not a.rides]
    if zero:
        print(f"  {len(zero)} app(s) with NOTHING on the rail: {', '.join(zero)}")
    if report.stale_not_yet_now_riding:
        # Housekeeping, not a failure: these now RIDE (derived), so the leftover
        # line is superseded rather than contradicted. Delete it when convenient.
        print(
            f"  {len(report.stale_not_yet_now_riding)} model(s) now RIDE but still "
            "carry a NOT_YET line; delete it from DECLARATIONS: "
            + ", ".join(sorted(report.stale_not_yet_now_riding))
        )
    print(f"  violations: {len(report.violations)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--compare", action="store_true", help="fail on NEW findings")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = rail_coverage.evaluate()

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        _print_report(report)

    if args.update_baseline:
        # Refuse to snapshot a declaration that is itself broken. A baseline
        # written over an undeclared or unargued model records the backlog as if
        # the matrix were sound, and the next --compare is then green about a
        # question nobody answered.
        if report.violations:
            print(
                "rail-coverage: refusing to write a baseline while the declaration "
                f"has {len(report.violations)} violation(s). Fix these first:",
                file=sys.stderr,
            )
            for v in report.violations:
                print(f"  [{v['kind']}] {v['model']}: {v['detail']}", file=sys.stderr)
            return 1
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "total_models": report.total_models,
            "rides": report.total_rides,
            "held": report.total_held,
            "not_yet_count": report.total_not_yet,
            "not_yet": report.not_yet_labels,
        }
        BASELINE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote baseline -> {BASELINE.relative_to(REPO_ROOT)}")
        return 0

    failed = False

    if report.violations:
        failed = True
        print("\nrail-coverage: UNDECLARED / malformed rail postures:", file=sys.stderr)
        for v in report.violations:
            print(f"  [{v['kind']}] {v['model']}: {v['detail']}", file=sys.stderr)
        print(
            "\nEvery model in a TENANT_APPS app must declare where it stands on the edge "
            "delta rail. Add an entry to apps/sync_engine/rail_coverage.py::DECLARATIONS:\n"
            '  HELD    -> _held(rationale="...", argued_in="docs/...md")  '
            "(both REQUIRED)\n"
            "  NOT_YET -> _NOT_YET   (honest backlog; carries no rationale)\n"
            "RIDES is never written by hand -- it is derived from the live registry in "
            "apps/api/sync_services.py. See docs/EDGE_SYNC_COVERAGE_MATRIX.md.",
            file=sys.stderr,
        )

    if args.compare:
        if not BASELINE.exists():
            print(
                "rail-coverage: no baseline; run --update-baseline", file=sys.stderr
            )
            return 1
        try:
            known = set(
                json.loads(BASELINE.read_text(encoding="utf-8")).get("not_yet", [])
            )
        except (OSError, ValueError):
            print("rail-coverage: unreadable baseline", file=sys.stderr)
            return 1
        new_backlog = [m for m in report.not_yet_labels if m not in known]
        if new_backlog:
            failed = True
            print(
                "\nNEW NOT_YET tenant model(s) -- the offline backlog grew:",
                file=sys.stderr,
            )
            for m in new_backlog:
                print(f"  {m}", file=sys.stderr)
            print(
                "\nNOT_YET is honest, but it must be a choice someone made on purpose. "
                "Either give the model a posture with an argument (HELD), put it on the "
                "rail, or run --update-baseline so the growth lands in the diff.",
                file=sys.stderr,
            )
        healed = sorted(known - set(report.not_yet_labels))
        if healed and not failed and not args.json:
            print(
                f"\n{len(healed)} model(s) left the NOT_YET backlog since the baseline; "
                "run --update-baseline to lock the improvement in."
            )
        if not failed and not args.json:
            print("\nOK (baseline held): every tenant model declares a rail posture.")
    elif not failed and not args.json:
        print("\nOK: every tenant model declares a rail posture.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
