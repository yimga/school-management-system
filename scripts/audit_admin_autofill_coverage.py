#!/usr/bin/env python3
"""Measure what a human actually has to TYPE on a Django admin add form.

This is the instrument behind the auto-fill expansion, and it is deliberately a
*coverage ratchet* rather than a contract check.  Its sibling
``audit_admin_form_intelligence_contract.py`` already proves the classification is
complete and disjoint; that gate can be perfectly green while every add form on the
platform is still an empty grid of required fields.  This one counts the emptiness.

WHY A SOURCE SCAN CANNOT ANSWER THIS
    ``config.admin.BaseRunMyCampusAdminSite.register()`` rebuilds every incoming
    ModelAdmin as ``type(name, (AdminFormAutomationMixin, base), ...)`` at
    registration time.  No admin class in ``apps/`` names the mixin, so an
    AST scan for the base class reports 0 of ~460 and that number is meaningless.
    Coverage here is 100% by construction and is asserted, not searched for: every
    live ``_registry`` entry must carry ``_rmc_admin_form_automation``.

WHAT IT COUNTS, PER SITE
    presented          editable fields the add form actually renders (required +
                       optional, after readonly/system-hidden removal)
    visible            presented MINUS the starting hidden set — what a person
                       actually reads on the page. Reducing this is the second
                       half of the job and the larger number.
    inferred_hidden    fields hidden because this school's own records never use
                       them (see apps/siteconfig/admin_field_usage.py)
    prefilled          presented fields arriving with a non-empty initial value —
                       from a model default, a form initial, or a smart builder
    required           presented fields the form will refuse to submit without
    required_empty     required AND not prefilled: the human's real typing load.
                       THIS IS THE NUMBER THE PROJECT EXISTS TO REDUCE.
    builder_models     models with an entry in ``INITIAL_BUILDERS``
    builder_hits       models whose builder returned at least one value for the
                       audit request (a registered builder that returns ``{}`` for
                       a real tenant is not coverage, and is not counted as such)

RATCHET SEMANTICS — AND WHY IT IGNORES THE HEADLINE NUMBERS
    ``--compare`` fails only on STRUCTURAL metrics: how many registered models a
    resolver or builder can reach, and how many admins fail to resolve at all.
    Those depend on code alone.

    It deliberately does NOT ratchet ``prefilled`` / ``builder_hits`` /
    ``required_empty``, because those depend on the DATABASE.  CI seeds one empty
    school (``ci.yml`` creates ``ci-admin-form-audit`` with no records), so every
    data-dependent count there is near zero — a ratchet on them would either fail
    permanently or be re-baselined to a number that proves nothing.  They are
    measured and printed, and they are the numbers a human reads to judge the work;
    they are not the numbers a machine blocks a merge on.

    A resolver deleted, a builder removed, or an admin that stops resolving all move
    a structural metric, so the regressions this work could actually suffer are the
    ones the gate catches.

HONEST LIMITS — read before believing a number
    * ``required_empty`` counts a field the form declares required.  A field made
      required only by ``Model.clean()`` is not visible here and is undercounted.
    * A ``prefilled`` field is one with a non-empty initial; whether that value is
      CORRECT is not something this script can know.  Correctness is the builder
      tests' job.
    * One request per site is used for every model, so a builder keyed on
      something other than the school will report against that single school.
    * Inline formsets are NOT measured.  Bulk entry mostly happens there, so the
      real typing load on the platform is higher than this reports.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.messages.middleware import MessageMiddleware  # noqa: E402
from django.contrib.sessions.middleware import SessionMiddleware  # noqa: E402
from django.core.exceptions import FieldDoesNotExist  # noqa: E402
from django.db import DatabaseError  # noqa: E402
from django.test import RequestFactory  # noqa: E402

from apps.schools.models import School  # noqa: E402
from apps.siteconfig.admin_form_intelligence import (  # noqa: E402
    build_admin_field_contract,
)
from apps.siteconfig.admin_smart_initials import INITIAL_BUILDERS  # noqa: E402

try:  # The generic resolver layer landed 2026-08-21.
    from apps.siteconfig.admin_smart_initials import (  # noqa: E402
        FIELD_RESOLVERS,
        _all_resolvers,
    )
except ImportError:
    # A tree from before the resolver layer existed. Reporting zero is the honest
    # answer and keeps this instrument runnable against any checkout, which is what
    # makes a before/after comparison with ONE instrument possible at all.
    FIELD_RESOLVERS = ()

    def _all_resolvers():
        return ()
from config.admin import platform_admin_site, tenant_admin_site  # noqa: E402


#: Growth headroom: the platform adds models continuously, and a new model arrives
#: with required fields nobody has written a builder for yet.  Without this the
#: ratchet would turn every new registration into a fake regression.
REQUIRED_EMPTY_GROWTH_ALLOWANCE = 40


def _resolver_reachable(model) -> int:
    """How many of this model's fields a generic resolver could answer for.

    Pure model metadata: no database, no request, no tenant state.  This is the
    number the ratchet guards, because it moves if and only if the CODE changes.
    """
    try:
        resolvers = list(_all_resolvers())
    except (ImportError, TypeError, ValueError):
        return 0
    count = 0
    for model_field in model._meta.get_fields():
        name = getattr(model_field, "name", "")
        if not name or getattr(model_field, "auto_created", False):
            continue
        if not getattr(model_field, "concrete", False):
            continue
        if not getattr(model_field, "editable", False):
            continue
        if any(name in r.names and r.matches(model_field) for r in resolvers):
            count += 1
    return count


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return not value
    return False


def _audit_request(*, host: str, urlconf: str, host_kind: str, school, user):
    request = RequestFactory().get("/admin/", HTTP_HOST=host)
    request.user = user
    request.school = school
    request.public_host_kind = host_kind
    request.urlconf = urlconf
    # Mirror the real middleware contract: a few specialized ModelAdmins read the
    # session or message store while building a form.
    SessionMiddleware(lambda _request: None).process_request(request)
    MessageMiddleware(lambda _request: None).process_request(request)
    return request


def _model_row(*, model, model_admin, request) -> dict[str, Any]:
    """One model's add-form reality, measured the way ``_changeform_view`` builds it."""

    label = model._meta.label_lower
    row: dict[str, Any] = {
        "model": label,
        "tenant_scoped": any(f.name == "school" for f in model._meta.fields),
        "concrete_fields": len(model._meta.fields),
        "has_builder": label in INITIAL_BUILDERS,
        "resolver_reachable": _resolver_reachable(model),
        "builder_returned": 0,
        "presented": 0,
        "visible": 0,
        "inferred_hidden": 0,
        "prefilled": 0,
        "required": 0,
        "required_empty": 0,
        "required_empty_names": [],
        "error": "",
    }

    if not getattr(model_admin, "_rmc_admin_form_automation", False):
        row["error"] = "shared-mixin-missing"
        return row

    try:
        initial = model_admin.get_changeform_initial_data(request)
    except (DatabaseError, TypeError, ValueError) as exc:
        row["error"] = f"initials:{type(exc).__name__}"
        initial = {}
    row["builder_returned"] = len(initial)

    try:
        contract = build_admin_field_contract(
            model_admin, request, obj=None, mode="add"
        )
        form_class = model_admin.get_form(request, obj=None, change=False)
        form = form_class(initial=dict(initial))
    except Exception as exc:  # pragma: no cover - a broken admin is a finding
        row["error"] = f"form:{type(exc).__name__}:{exc}"[:180]
        return row

    required = set(contract.required_fields)
    optional = {item["name"] for item in contract.optional_fields}
    presented = required | optional

    prefilled: set[str] = set()
    for name in presented:
        field = form.fields.get(name)
        if field is None:
            continue
        try:
            value = form.get_initial_for_field(field, name)
        except (DatabaseError, TypeError, ValueError):
            continue
        if not _blank(value):
            prefilled.add(name)
            continue
        # A model default that Django resolves at save time still spares the human
        # from typing, so it counts as prefilled even when the widget renders empty.
        try:
            model_field = model._meta.get_field(name)
        except FieldDoesNotExist:
            continue
        if getattr(model_field, "has_default", None) and model_field.has_default():
            prefilled.add(name)

    empty_required = sorted(required - prefilled)
    hidden = set(contract.hidden_fields)
    row.update(
        {
            "presented": len(presented),
            "visible": len(presented - hidden),
            "inferred_hidden": len(getattr(contract, "inferred_hidden_fields", ()) or ()),
            "prefilled": len(prefilled),
            "required": len(required),
            "required_empty": len(empty_required),
            "required_empty_names": empty_required[:12],
        }
    )
    return row


def audit_site(*, label: str, site, request) -> dict[str, Any]:
    rows = [
        _model_row(model=model, model_admin=model_admin, request=request)
        for model, model_admin in site._registry.items()
    ]
    rows.sort(key=lambda r: (-r["required_empty"], r["model"]))
    totals = {
        "site": label,
        "registered_models": len(rows),
        "models_with_errors": sum(1 for r in rows if r["error"]),
        "builder_models": sum(1 for r in rows if r["has_builder"]),
        "builder_hits": sum(1 for r in rows if r["builder_returned"] > 0),
        # STRUCTURAL: code-only, so these are what --compare ratchets.
        "resolver_reachable_models": sum(1 for r in rows if r["resolver_reachable"]),
        "resolver_reachable_fields": sum(r["resolver_reachable"] for r in rows),
        "presented": sum(r["presented"] for r in rows),
        "visible": sum(r["visible"] for r in rows),
        "inferred_hidden": sum(r["inferred_hidden"] for r in rows),
        "prefilled": sum(r["prefilled"] for r in rows),
        "required": sum(r["required"] for r in rows),
        "required_empty": sum(r["required_empty"] for r in rows),
        "models_fully_prefilled": sum(
            1 for r in rows if r["required"] and not r["required_empty"]
        ),
    }
    totals["prefilled_pct"] = round(
        100.0 * totals["prefilled"] / totals["presented"], 2
    ) if totals["presented"] else 0.0
    return {"totals": totals, "rows": rows}


def run() -> dict[str, Any]:
    User = get_user_model()
    user = User.objects.filter(is_superuser=True, is_active=True).first()
    school = School.objects.filter(is_active=True).order_by("created_at").first()
    if user is None or school is None:
        return {
            "ok": False,
            "error": "no active superuser and/or school; cannot resolve admin forms",
            "sites": {},
        }

    tenant = audit_site(
        label="tenant",
        site=tenant_admin_site,
        request=_audit_request(
            host=f"{school.slug}.runmycampus.com",
            urlconf="config.tenant_urls",
            host_kind="tenant",
            school=school,
            user=user,
        ),
    )
    operator = audit_site(
        label="operator",
        site=platform_admin_site,
        request=_audit_request(
            host="manager.runmycampus.com",
            urlconf="config.manager_urls",
            host_kind="manager",
            school=None,
            user=user,
        ),
    )
    return {
        "ok": True,
        "registry_builders": len(INITIAL_BUILDERS),
        "school_used": school.slug,
        "sites": {"tenant": tenant, "operator": operator},
    }


#: Metrics derived from code alone. Only these can be ratcheted, because they read
#: the same on a developer's populated database and on CI's single empty school.
STRUCTURAL_FLOOR_METRICS = (
    "resolver_reachable_models",
    "resolver_reachable_fields",
    "builder_models",
    "registered_models",
)


def _compare(payload: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    baseline_builders = baseline.get("registry_builders")
    if baseline_builders is not None and payload["registry_builders"] < baseline_builders:
        problems.append(
            f"INITIAL_BUILDERS shrank {baseline_builders} -> "
            f"{payload['registry_builders']}"
        )
    for site in ("tenant", "operator"):
        now = payload["sites"].get(site, {}).get("totals", {})
        was = baseline.get("sites", {}).get(site, {}).get("totals", {})
        if not was:
            continue
        for key in STRUCTURAL_FLOOR_METRICS:
            if key not in was:
                continue
            if now.get(key, 0) < was.get(key, 0):
                problems.append(
                    f"{site}:{key} REGRESSED {was.get(key)} -> {now.get(key)}"
                )
        # An admin that stops resolving is a broken add form, and that IS
        # environment-independent enough to block a merge on.
        if now.get("models_with_errors", 0) > was.get("models_with_errors", 0):
            problems.append(
                f"{site}:models_with_errors {was.get('models_with_errors')} -> "
                f"{now.get('models_with_errors')}"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, help="write the full payload here")
    parser.add_argument(
        "--slim",
        action="store_true",
        help=(
            "omit per-model rows from --json. The ratchet reads only totals, and a "
            "baseline carrying 478 rows churns on every model the platform adds."
        ),
    )
    parser.add_argument(
        "--compare",
        type=Path,
        help="baseline JSON; exit 1 when coverage regresses",
    )
    parser.add_argument("--top", type=int, default=20, help="worst-N models to print")
    args = parser.parse_args()

    payload = run()
    if not payload["ok"]:
        print(json.dumps(payload, indent=2))
        return 1

    if args.json:
        path = args.json if args.json.is_absolute() else ROOT / args.json
        path.parent.mkdir(parents=True, exist_ok=True)
        written = payload
        if args.slim:
            written = dict(payload)
            written["sites"] = {
                site: {"totals": data["totals"]}
                for site, data in payload["sites"].items()
            }
            written["note"] = (
                "Totals only. --compare reads sites.*.totals and registry_builders; "
                "per-model rows are reporting detail, not baseline state."
            )
        path.write_text(
            json.dumps(written, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    print("=" * 84)
    print("ADMIN ADD-FORM TYPING LOAD")
    print("=" * 84)
    print(f"  INITIAL_BUILDERS entries: {payload['registry_builders']}")
    print(f"  generic field resolvers : {len(list(_all_resolvers()))}")
    print(f"  school used for tenant resolution: {payload['school_used']}")
    print()
    header = (
        f"{'site':>9} {'models':>7} {'presented':>10} {'visible':>8} {'infHid':>7} "
        f"{'prefilled':>10} {'%':>6} {'required':>9} {'req_EMPTY':>10} {'hits':>5} {'err':>4}"
    )
    print(header)
    print("-" * len(header))
    for site in ("tenant", "operator"):
        t = payload["sites"][site]["totals"]
        print(
            f"{site:>9} {t['registered_models']:>7} {t['presented']:>10} "
            f"{t['visible']:>8} {t['inferred_hidden']:>7} {t['prefilled']:>10} "
            f"{t['prefilled_pct']:>5.1f}% {t['required']:>9} "
            f"{t['required_empty']:>10} {t['builder_hits']:>5} "
            f"{t['models_with_errors']:>4}"
        )
    print()
    print("  STRUCTURAL (code-only; these are what --compare ratchets)")
    for site in ("tenant", "operator"):
        t = payload["sites"][site]["totals"]
        print(
            f"    {site:>9}: resolver-reachable "
            f"{t['resolver_reachable_models']} models / "
            f"{t['resolver_reachable_fields']} fields, "
            f"{t['builder_models']} exact builders"
        )

    for site in ("tenant", "operator"):
        rows = payload["sites"][site]["rows"][: args.top]
        print()
        print(f"-- {site}: heaviest add forms by required-and-empty --")
        for r in rows:
            if not r["required_empty"]:
                continue
            names = ", ".join(r["required_empty_names"])
            print(f"   {r['required_empty']:>3} empty / {r['required']:>3} req  {r['model']}")
            print(f"        {names}")

    if args.compare:
        path = args.compare if args.compare.is_absolute() else ROOT / args.compare
        if not path.is_file():
            print(f"\nbaseline missing: {path}")
            return 1
        problems = _compare(payload, json.loads(path.read_text(encoding="utf-8")))
        print()
        if problems:
            print("COVERAGE RATCHET FAILED")
            for problem in problems:
                print(f"  {problem}")
            return 1
        print("coverage ratchet: OK (no regression vs baseline)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
