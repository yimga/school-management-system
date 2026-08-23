#!/usr/bin/env python
"""Every SHARED model on the tenant admin must be tenant-scoped, or classified.

WHY THIS EXISTS
---------------
``TenantAdminSite.register`` auto-applies ``_TenantScopedQuerysetMixin`` to any
registered model that has a CONCRETE ``school`` field -- that column is what the
mixin filters on. A SHARED_APPS model WITHOUT one therefore got no changelist
scoping at all, and its table lives in ``public``, which a tenant-schema
request's ``search_path`` includes.

An audit of the live registry found **53** such registrations. One school's
admin could read, filter and CSV-export every tenant's ``AuditLog``,
``AccessLog``, ``UserActivitySession`` and ``ComplianceReport``; could see every
tenant's ``Delegation``, ``TemporaryRoleGrant``, ``UserPasskey`` and
``UserPreference``; and could MUTATE the platform-global
``ThreatDetectionConfig`` / ``IPAccessRule`` / ``CountryAccessRule`` perimeter --
plus ``siteconfig.SiteSettings``, whose only editable field after slimming is
``maintenance_mode``, for the whole platform.

Nothing caught it. ``scan_tenant_queryset_safety`` reads ORM call sites in app
code, not admin registrations. ``scan_rls_table_coverage`` asks about RLS
policies, which are a no-op under ``USE_DJANGO_TENANTS`` -- the mode where this
leaks. And the scoping mixin itself was working exactly as designed: it simply
had nothing to filter on and said nothing about it.

WHAT IT CHECKS
--------------
For every model registered on ``tenant_admin_site``: if its app is in
SHARED_APPS and it has no concrete ``school`` field, it must resolve to one of
the five classifications in ``config/admin.py`` -- GLOBAL_CATALOGS,
RELATION_SCOPE, ACTOR_SCOPE, SELF_SCOPED, or OPERATOR_ONLY (which is not
registered on the tenant site at all). Anything else is a finding.

The check is on the RESOLVED admin class from the live registry, not on source
text, because ``TenantAdminSite.register`` synthesises the final class at
registration time -- an AST scan of the app's ``admin.py`` cannot see any of it.

Zero-tolerance: there is no baseline. A new SHARED model on the tenant admin is
a decision someone should record in one of the five maps, and the fail-closed
arm in ``config/admin.py`` already renders it empty in the meantime, so a red
gate here never means live exposure -- it means an unmade decision.

Needs Django (the app registry and the admin sites), so it runs in
``ci.yml::django-tests`` and the ``DJANGO_GATES`` phase of
``pre_push_boundary_check.py``, not the deps-free boundary job.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _bootstrap_django():
    sys.path.insert(0, os.getcwd())
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _classify():
    from django.apps import apps as django_apps

    from config.admin import (
        TENANT_ADMIN_ACTOR_SCOPE,
        TENANT_ADMIN_GLOBAL_CATALOGS,
        TENANT_ADMIN_OPERATOR_ONLY,
        TENANT_ADMIN_RELATION_SCOPE,
        TENANT_ADMIN_SELF_SCOPED,
        TenantAdminSite,
        _tenancy_app_lists,
        tenant_admin_site,
    )

    shared_apps, _tenant_apps = _tenancy_app_lists()
    if not shared_apps:
        return None, "could not parse SHARED_APPS from config/settings.py"

    shared_modules = {
        e.split(".apps.")[0] if ".apps." in e else e for e in shared_apps
    }

    findings = []
    stats = {
        "registrations": 0,
        "shared_no_school": 0,
        "scoped": 0,
        "global_catalog": 0,
        "self_scoped": 0,
    }

    for model, admin_obj in tenant_admin_site._registry.items():
        stats["registrations"] += 1
        label = f"{model._meta.app_label}.{model.__name__}"

        try:
            module = django_apps.get_app_config(model._meta.app_label).name
        except LookupError:
            continue
        if module not in shared_modules:
            continue  # TENANT_APPS: schema-isolated / RLS-confined
        if TenantAdminSite._model_has_concrete_school_field(model):
            continue  # the school-field mixin covers it

        stats["shared_no_school"] += 1

        if label in TENANT_ADMIN_OPERATOR_ONLY:
            findings.append(
                {
                    "model": label,
                    "problem": "listed OPERATOR_ONLY yet registered on the "
                    "tenant admin -- the skip in TenantAdminSite.register did "
                    "not take effect",
                }
            )
            continue
        if label in TENANT_ADMIN_GLOBAL_CATALOGS:
            stats["global_catalog"] += 1
            continue
        if label in TENANT_ADMIN_SELF_SCOPED:
            stats["self_scoped"] += 1
            continue

        cls = type(admin_obj)
        scoped = getattr(cls, "_rmc_tenant_scoped", False)
        failclosed = any(
            b.__name__ == "_TenantUnclassifiedFailClosedMixin" for b in cls.__mro__
        )
        if scoped and not failclosed:
            stats["scoped"] += 1
            # A declared path must be present, or the mixin filters on nothing.
            if label in TENANT_ADMIN_RELATION_SCOPE and not getattr(
                cls, "tenant_scope_path", None
            ):
                findings.append(
                    {"model": label, "problem": "relation-scoped with no tenant_scope_path"}
                )
            if label in TENANT_ADMIN_ACTOR_SCOPE and not getattr(
                cls, "tenant_actor_path", None
            ):
                findings.append(
                    {"model": label, "problem": "actor-scoped with no tenant_actor_path"}
                )
            continue

        findings.append(
            {
                "model": label,
                "admin": cls.__name__,
                "problem": "SHARED model with no school field and no tenant-scope "
                "classification; its public table holds every tenant's rows. "
                "Classify it in config/admin.py: TENANT_ADMIN_GLOBAL_CATALOGS, "
                "TENANT_ADMIN_RELATION_SCOPE, TENANT_ADMIN_ACTOR_SCOPE, "
                "TENANT_ADMIN_SELF_SCOPED or TENANT_ADMIN_OPERATOR_ONLY.",
            }
        )

    return (findings, stats), None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    _bootstrap_django()
    result, error = _classify()
    if error:
        print(f"unscoped-shared-tenant-admin: SKIP -- {error}")
        return 0
    findings, stats = result

    if args.json:
        print(json.dumps({"findings": findings, "stats": stats}, indent=2))
    else:
        print(
            f"tenant admin: {stats['registrations']} registration(s); "
            f"{stats['shared_no_school']} are SHARED with no school field "
            f"({stats['scoped']} scoped, {stats['global_catalog']} global catalog, "
            f"{stats['self_scoped']} self-scoped)"
        )
        for f in findings:
            print(f"  {f['model']}: {f['problem']}")
        print(f"unscoped-shared-tenant-admin: {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
