"""Post-apply VERIFICATION — prove uploaded rows actually landed in the tenant.

``reconciliation.py`` historically computed "parity" by comparing the profiler's
source row-count against the **landers' own self-reported** created/updated counts
(pulled from the ``MigrationRun`` audit trail) — it never re-queried the tenant.
So a lander that reported ``created=100`` but whose writes were rolled back,
scoped to the wrong school, or filtered out on save would still show 100% parity.

This module re-queries each domain's REAL tenant model, **under the tenant schema
and scoped to the bundle's school**, so reconciliation can report the honest
chain ``source → landed(self-reported) → visible(actually in the school)`` and
flag drift when creates did not persist.

It mirrors :func:`apps.migration_cloud.guardrails.compute_observed_totals` (same
``schema_context`` + field-aware school scoping) but generalised to every domain
we can confidently map to a concrete model. A domain without a confident model
mapping simply returns no count (honest "not verified") rather than guessing.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


# canonical domain -> (module path, model class name). The count is always scoped
# to the bundle's school: field-aware — a direct ``school`` FK, else
# ``student__school``, else unscoped under ``schema_context`` (which already
# isolates the tenant in schema-per-tenant mode). Add a domain here only once its
# landing model is confirmed; an unmapped domain reports no visible count rather
# than counting the wrong table.
_DOMAIN_MODELS: dict[str, tuple[str, str]] = {
    "students": ("apps.people.models", "StudentProfile"),
    "staff": ("apps.people.models", "TeacherProfile"),
    "guardians": ("apps.people.models", "StudentGuardian"),
    "finance": ("apps.finance.models", "Invoice"),
}


def domains_with_verification() -> set[str]:
    """The set of canonical domains this module can re-query. (For tests/UI.)"""
    return set(_DOMAIN_MODELS)


def _school_scoped_count(model: Any, school: Any) -> int:
    """Count rows of ``model`` visible for ``school`` (field-aware scoping)."""
    field_names = {f.name for f in model._meta.get_fields()}
    if "school" in field_names:
        qs = model.objects.filter(school=school)  # tenant-isolation-allow: scoped by the model's own school FK
    elif "student" in field_names:
        qs = model.objects.filter(student__school=school)  # tenant-isolation-allow: scoped via student__school=school
    else:
        qs = model.objects.all()  # tenant-isolation-allow: no school field; schema_context isolates the tenant
    return qs.count()


def verify_landed_counts(
    bundle: Any, *, domains: list[str] | None = None
) -> dict[str, int]:
    """Re-query the tenant and return ``{domain: rows_visible_in_school}``.

    Only domains we can confidently map to a model are returned (unmapped or
    errored domains are omitted, never guessed). Runs under the bundle's tenant
    schema so counts reflect exactly what the school actually sees. Never raises —
    a bad mapping logs a warning and is skipped so it can't break reconcile.
    """
    school = getattr(bundle, "school", None)
    if school is None:
        return {}
    schema_name = getattr(bundle, "schema_name", "") or ""

    def _run_under_schema(fn: Callable[[], Any]) -> Any:
        if not schema_name:
            return fn()
        try:
            from django_tenants.utils import schema_context
        except ImportError:
            return fn()
        with schema_context(schema_name):
            return fn()

    wanted = set(domains) if domains else None
    out: dict[str, int] = {}
    for domain, (module_path, model_attr) in _DOMAIN_MODELS.items():
        if wanted is not None and domain not in wanted:
            continue
        try:
            module = importlib.import_module(module_path)
            model = getattr(module, model_attr)
        except Exception:  # noqa: BLE001 — model unavailable in this deploy
            continue
        try:
            out[domain] = _run_under_schema(
                lambda m=model: _school_scoped_count(m, school)
            )
        except Exception:  # noqa: BLE001 — a bad mapping must never break reconcile
            logger.warning(
                "migration_cloud.verify: visible-count failed for domain=%s",
                domain,
                exc_info=True,
            )
    return out
