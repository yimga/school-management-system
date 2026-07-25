"""Seal: the email-delivery ticker source reads the real model AND only from
the schema that actually has the table.

Plain ``unittest`` (no DB).

History:
  * v1 (pre-2026-06-14): ``_source_email_delivery_events`` imported a
    non-existent ``apps.communications.models.EmailDeliveryEvent`` (plural app,
    wrong module), swallowed the ImportError, so the card never appeared.
  * v2 (2026-06-14): repointed at the real
    ``apps.schoolops.models_email_delivery.EmailDeliveryEvent`` — but on a false
    premise ("platform-level, cross-tenant aggregate by-design"). ``schoolops``
    is a TENANT_APPS app, so its table lives ONLY in tenant schemas. The source
    was wired into ``resolve_manager_ticker_cards()`` (manager host = public
    schema), so it raised ``UndefinedTable`` on every operator page load — a
    traceback storm, still no card.
  * v3 (2026-06-15, this seal): the source is TENANT-scoped. It belongs in
    ``resolve_tenant_ticker_cards()`` where the active tenant schema has the
    table, and must NEVER be wired into the manager resolver again.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent


class EmailTickerSourceModuleTests(unittest.TestCase):

    def test_phantom_communications_import_gone(self) -> None:
        src = (
            REPO / "apps" / "siteconfig" / "cockpit_activity_ticker_realdata.py"
        ).read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("apps.communications.models", src)
        self.assertIn(
            "from apps.schoolops.models_email_delivery import EmailDeliveryEvent",
            src,
        )

    def test_real_model_has_created_at(self) -> None:
        from apps.schoolops.models_email_delivery import EmailDeliveryEvent

        names = {f.name for f in EmailDeliveryEvent._meta.get_fields()}
        self.assertIn("created_at", names)

    def test_source_runs_without_raising(self) -> None:
        from apps.siteconfig.cockpit_activity_ticker_realdata import (
            _source_email_delivery_events,
        )

        # Must return a list (0 rows is fine) — never raise, even when the
        # table is absent on the current schema (UndefinedTable is caught).
        result = _source_email_delivery_events()
        self.assertIsInstance(result, list)
        body = inspect.getsource(_source_email_delivery_events)
        self.assertNotIn("communications", body)

    def test_tenant_scoped_not_manager_scoped(self) -> None:
        """The schoolops table lives only in tenant schemas — this source must be
        wired into the tenant resolver and NEVER the manager (public-schema) one,
        or it raises UndefinedTable on every operator page load."""
        # The per-scope source wiring lives in the resolver-registry helpers;
        # resolve_{manager,tenant}_ticker_cards now delegate to these dicts.
        from apps.siteconfig.cockpit_activity_ticker_realdata import (
            _manager_source_resolvers,
            _tenant_source_resolvers,
        )

        manager_body = inspect.getsource(_manager_source_resolvers)
        tenant_body = inspect.getsource(_tenant_source_resolvers)
        # The resolver registries reference the source callable by name (no call
        # parens — they store the callable, invoked later by the resolver loop).
        self.assertNotIn(
            "_source_email_delivery_events", manager_body,
            msg="email-delivery source must NOT be in the manager resolver "
                "(public schema has no schoolops_email_delivery_event table)",
        )
        self.assertIn(
            "_source_email_delivery_events", tenant_body,
            msg="email-delivery source must be wired into the tenant resolver",
        )

    def test_missing_table_is_caught_quietly(self) -> None:
        """A missing table is an expected degraded state on a freshly-provisioned
        tenant — the source must catch ProgrammingError/OperationalError so it
        degrades silently instead of spamming tracebacks every render."""
        from apps.siteconfig.cockpit_activity_ticker_realdata import (
            _source_email_delivery_events,
        )

        body = inspect.getsource(_source_email_delivery_events)
        self.assertIn("ProgrammingError", body)
        self.assertIn("OperationalError", body)


if __name__ == "__main__":
    unittest.main()
