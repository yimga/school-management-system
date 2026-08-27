"""Compatibility shim for the Phase 9 BI module.

WHAT HAPPENED TO THE MODELS THAT USED TO LIVE HERE
--------------------------------------------------
``reports.0017_remove_adhocreportdefinition_created_by_and_more`` ran
``DeleteModel`` on all six of them -- ``ReportDefinition``, ``ReportExecution``,
``UserDashboard``, ``DashboardWidgetPlacement``, ``ScheduledReport`` and
``MaterializedReportCache`` -- but the class statements were left behind in this
module. They were ordinary managed models with no ``managed = False`` and no
``db_table``, so they stayed in Django's app registry with no table underneath.

WHY THAT WAS WORSE THAN DEAD CODE
---------------------------------
Django auto-imports ``<app>/models.py`` and nothing else, so these six were
registered only once SOMETHING imported this module -- and three modules do
(``apps/api/views_v1.py``, ``apps/reports/adhoc_runner.py``,
``apps/reports/bi_services.py``), all lazily, from inside functions.

That made the app registry depend on import order. ``makemigrations`` reported
"No changes detected in app 'reports'" because this module had not been imported
when the autodetector ran, while any process that had touched one of those three
modules carried six extra registered models. Anything that ENUMERATES models and
queries them then failed, but only sometimes:
``apps/lifecycle/tenant_portability.py`` walks ``config.get_models()`` to export
and re-import a tenant, and died on
``OperationalError: no such table: reports_reportdefinition`` -- taking out the
sovereign-tenant import and the tenant identity-portability path, which are the
local-first / offline pillar, not a side feature.

``ReportCacheManager._store_materialized`` also wrote to
``MaterializedReportCache`` via ``update_or_create``. It had no callers, so it
was not a live 500 -- it was a landmine for whoever wired it up next. It is gone
too; the caching path above it already uses the Django cache and says so.

WHAT REPLACED THEM
------------------
* scheduled delivery -> ``apps.reports.models.TenantReportSchedule`` (see its
  docstring, which names this replacement explicitly)
* report materialisation -> the Django cache, in
  ``ReportCacheManager.get_or_generate``
* the ad-hoc report builder -> ``AdHocReportDefinition`` /
  ``AdHocReportExecution``, which are LIVE, have tables, and are re-exported
  below because callers import them from this module by that path.
"""

from .models import AdHocReportDefinition, AdHocReportExecution  # noqa: F401

__all__ = ["AdHocReportDefinition", "AdHocReportExecution"]
