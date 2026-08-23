"""The batch advancer must sweep tenant schemas, not the schema the cron sits in.

``advance_running_batches`` is the registered periodic entry point
(``people.advance_school_transfer_batches``) and ``periodic.run_job`` calls it
with no schema context — i.e. on ``public``. ``SchoolTransferBatch`` is an
``apps.people`` model and ``apps.people`` is in TENANT_APPS, so under
``USE_DJANGO_TENANTS=1`` ``people_schooltransferbatch`` does not exist in
public: the bare ``.filter(status=RUNNING)`` raised ProgrammingError every tick,
``run_job``'s blanket except recorded a heartbeat error, and a school merge or
cohort split sat at RUNNING forever.

``continue_applying_transfers`` was fixed for exactly this a few registrations
earlier; this pins the same contract for the batch advancer. Both tests are
no-DB — the single-schema (SQLite / RLS edge) happy path stays covered by
``test_school_transfer_batch.test_periodic_entry_advances_running_batches``.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.people.school_batch_service import advance_running_batches


class SchoolBatchAdvancerTenantSafeTests(SimpleTestCase):
    def test_missing_table_is_skipped_not_raised(self):
        from django.db import ProgrammingError

        with patch(
            "apps.people.transfer_service.tenant_sweep_schema_names",
            return_value=[None],
        ), patch(
            "apps.people.models_school_batch.SchoolTransferBatch.objects.filter",
            side_effect=ProgrammingError(
                "relation people_schooltransferbatch does not exist"
            ),
        ):
            out = advance_running_batches()

        self.assertEqual(out.get("advanced"), 0)
        self.assertEqual(out.get("schemas_skipped"), 1)

    def test_sweep_enters_every_tenant_schema(self):
        with patch(
            "apps.people.transfer_service.tenant_sweep_schema_names",
            return_value=["tenant_a", "tenant_b"],
        ), patch(
            "apps.people.models_school_batch.SchoolTransferBatch.objects.filter"
        ) as filt, patch(
            "django_tenants.utils.schema_context"
        ) as schema_context:
            filt.return_value.order_by.return_value.__getitem__.return_value = []
            out = advance_running_batches()

        # The decisive assertion: the RUNNING sweep ran once per tenant schema.
        # Without it the query runs wherever the cron happens to be — public.
        self.assertEqual(
            [call.args[0] for call in schema_context.call_args_list],
            ["tenant_a", "tenant_b"],
        )
        self.assertEqual(out.get("schemas"), 2)
        # Anti-vacuous: the queryset really was built inside each context, so
        # the schemas above are not just an unused enumeration.
        self.assertEqual(filt.call_count, 2)
