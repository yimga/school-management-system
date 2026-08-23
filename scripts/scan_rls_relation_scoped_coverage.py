#!/usr/bin/env python
"""Tenant tables that reach their school through a RELATION still need a policy.

WHY THIS EXISTS
---------------
``scan_rls_table_coverage.py`` decides a model is tenant-scoped by looking for a
field literally named ``school``::

    field_names = {f.name for f in model._meta.get_fields()}
    if "school" not in field_names:
        continue

That is a correct answer to the question it asks, and it currently reports ZERO --
every model carrying a ``school`` FK is enumerated in some ``*rls*`` migration. It
is also structurally blind to the far larger set: a child table holding tenant data
that reaches its school through a parent. ``EventRegistration`` has no ``school``
field; it has ``event``, and ``SchoolEvent`` has the school. Under
``USE_DJANGO_TENANTS=0`` -- the sovereign edge, where RLS *is* the isolation and
every school shares one schema -- such a table has no policy at all, and any tenant
connection can read every school's rows.

That was found the hard way: three school_events tables (ticket tiers, sponsor
commitments, attendee registrations) had no ENABLE, no policy and no FORCE, while
the gate reported 0 findings and was telling the truth. This scan asks the other
question, and the answer at introduction is **121 tables**.

That number is only trustworthy because the detector was calibrated first: a
naive version reported 127, six of which are the FK-scoped children that feedback
/0010 and school_events/0004 already protect -- their tables are dict KEYS, a
shape the shared enumerator does not read. Six known-good tables dropping out is
the evidence the remaining 121 are real.

READ THE SEVERITY CORRECTLY
---------------------------
``should_apply_rls`` returns False under ``USE_DJANGO_TENANTS``, which
``render.yaml`` sets, so RLS is a NO-OP in the deployed schema-per-tenant topology
-- isolation there is Postgres schemas plus service-layer ``school=`` scoping. This
measures **RLS-mode readiness**: work that must land before anyone runs with
``USE_DJANGO_TENANTS=0`` on PostgreSQL. It is not a live cloud exposure, and saying
otherwise would be scaremongering. It is also not nothing: the sovereign edge is a
shipped deployment mode.

RATCHET, NOT ZERO-TOLERANCE, and deliberately. Writing 121 FK-scoped policies is
real per-table work -- each needs the right parent, and a nullable parent needs an
``IS NULL`` arm or the policy hides the table's own unclaimed rows. The point of
this gate is that the number is now VISIBLE and can only go down; a new relation-
scoped tenant table without a policy fails it.

The companion pattern to burn these down is ``apps/feedback/migrations/
0010_rls_fk_scoped_children.py`` (and ``school_events/0004``, written against this
finding): ENABLE + CREATE POLICY + FORCE, with a USING clause that EXISTS-joins the
parent.

Needs Django (the app registry), so it runs in ``ci.yml::django-tests`` and the
``DJANGO_GATES`` phase of ``pre_push_boundary_check.py``, not the deps-free job.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "var" / "security-audit-baseline-rls-relation-coverage.json"

# How far to chase FKs looking for a School. Two hops covers child -> parent ->
# school, which is every real case here; three is slack for one more level of
# nesting without turning the walk into "everything reaches everything".
_MAX_HOPS = 3


def _bootstrap_django():
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _reaches_school(model, school_model, hops: int = _MAX_HOPS) -> str | None:
    """The FK path to a School, or None. Returns the FIRST hop's field name."""
    frontier = [(model, None)]
    seen = set()
    for _ in range(hops):
        nxt = []
        for current, first_hop in frontier:
            if not hasattr(current, "_meta") or current in seen:
                continue
            seen.add(current)
            for field in current._meta.get_fields():
                if not getattr(field, "many_to_one", False):
                    continue
                target = getattr(field, "related_model", None)
                # A lazy relation can still be a string here; it is not resolvable
                # and guessing at it would invent findings.
                if target is None or isinstance(target, str):
                    continue
                hop = first_hop or field.name
                if target is school_model:
                    return hop
                nxt.append((target, hop))
        frontier = nxt
    return None


def _fk_scoped_tables() -> set[str]:
    """Tables enumerated as the KEYS of an FK-scoped RLS map.

    ``scan_rls_table_coverage._enumerated_tables`` recognises ``TABLES = [...]``
    and bare ``ALTER TABLE`` SQL, but not the dict shape the FK-scoped migrations
    use::

        FK_SCOPED_TABLES = {"feedback_feedbackcomment": [("feedback_feedbacksubmission", "feedback_id")]}

    Three migrations already use it (feedback/0010, communication/0031,
    school_events/0004) and every one of their tables would otherwise be reported
    here as uncovered -- inflating this gate's count with tables that are, in fact,
    protected. Reading the keys is what makes the number true.
    """
    found: set[str] = set()
    for mig in sorted((REPO_ROOT / "apps").glob("*/migrations/*.py")):
        if "rls" not in mig.name:
            continue
        try:
            tree = ast.parse(mig.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    token = key.value
                    if "_" in token and token.islower() and " " not in token:
                        found.add(token)
    return found


def scan() -> list[dict]:
    from django.apps import apps as django_apps

    from scan_rls_force_coverage import RLS_OPT_OUT_ALLOWLIST
    from scan_rls_table_coverage import _enumerated_tables

    from apps.schools.models import School

    enumerated = _enumerated_tables() | _fk_scoped_tables()
    findings: list[dict] = []
    for cfg in django_apps.get_app_configs():
        if not cfg.name.startswith("apps."):
            continue
        for model in cfg.get_models():
            dotted = f"{cfg.label}.{model.__name__}"
            if dotted in RLS_OPT_OUT_ALLOWLIST:
                continue
            table = model._meta.db_table
            if table in enumerated:
                continue
            names = {f.name for f in model._meta.get_fields()}
            if "school" in names:
                # scan_rls_table_coverage owns these, and reporting them twice
                # would bury this list under one that is already at zero.
                continue
            via = _reaches_school(model, School)
            if via is None:
                continue
            findings.append(
                {"model": dotted, "table": table, "app": cfg.label, "via": via}
            )
    return sorted(findings, key=lambda f: (f["app"], f["table"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true", help="fail only on NEW findings")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list", action="store_true", help="print every finding")
    args = parser.parse_args(argv)

    _bootstrap_django()
    findings = scan()

    if args.json:
        print(json.dumps({"finding_count": len(findings), "findings": findings}, indent=2))
    else:
        if args.list:
            for f in findings:
                print(f"  {f['app']:22s} {f['table']:46s} via {f['via']}")
        print(
            f"rls-relation-coverage: {len(findings)} tenant table(s) reach a school "
            "only through a relation and are named in no RLS migration."
        )

    if not args.compare:
        return 1 if findings else 0

    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8")).get("finding_count", 0)
    except (OSError, ValueError):
        baseline = 0
    if len(findings) > baseline:
        print(
            f"FAIL: {len(findings)} relation-scoped tables without an RLS policy, "
            f"baseline {baseline}. Add the table to an FK-scoped RLS migration -- see "
            "apps/feedback/migrations/0010_rls_fk_scoped_children.py for the shape.",
            file=sys.stderr,
        )
        return 1
    if len(findings) < baseline:
        print(f"OK: down to {len(findings)} from a baseline of {baseline}. Update the baseline.")
    else:
        print(f"OK: no new relation-scoped RLS gaps (count={len(findings)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
