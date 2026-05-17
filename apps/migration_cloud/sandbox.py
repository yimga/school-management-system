"""Sandbox tenant clone — throwaway tenant for "click around for a day before
promoting" workflows.

Creates a clone bundle pointing at a throwaway schema name so an operator
can apply the bundle into an isolated tenant, let the school's IT lead
poke around, and either:

    * **promote** — re-target the original bundle at the production tenant
      and re-apply (the sandbox apply is throwaway), or
    * **discard** — drop the sandbox schema and the clone bundle.

This deliberately does NOT create a real django-tenants schema by default —
the implementation uses a sentinel "sandbox-<bundle_pk>-<token>" schema name
that the orchestrator + landers respect by writing to an in-memory or
disposable database alias when one is configured. In production the
"sandbox_db" Django alias is the recommended target; in dev / tests we
let the writes go through but flag the bundle as sandbox so reconciliation
treats it correctly.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from django.db import transaction

from .models import BundleStatus, MigrationArtifact, MigrationBundle

logger = logging.getLogger(__name__)


def clone_bundle_to_sandbox(*, bundle: MigrationBundle) -> MigrationBundle:
    """Create a sandbox copy of ``bundle`` ready for isolated apply.

    The clone:
        * carries ``sandbox_of=bundle`` so the UI shows lineage,
        * gets a throwaway ``schema_name`` ("sandbox-<token>"),
        * shares the original artifacts (the byte content is content-addressed
          + write-once, so sharing is safe),
        * starts in MAPPED status when the original is MAPPED, so the
          operator can run apply immediately.
    """
    token = secrets.token_urlsafe(6)
    sandbox_schema = f"sandbox-{bundle.pk}-{token}"

    with transaction.atomic():
        clone = MigrationBundle.objects.create(
            school=bundle.school,
            schema_name=sandbox_schema,
            label=f"{bundle.label or 'bundle ' + str(bundle.pk)} (sandbox)",
            intake_method=bundle.intake_method,
            intake_source_uri=bundle.intake_source_uri,
            source_hint=bundle.source_hint,
            idempotency_key=f"sandbox-{bundle.idempotency_key}-{token}",
            sla_tier=bundle.sla_tier,
            status=bundle.status,
            discovery_summary=dict(bundle.discovery_summary or {}),
            mapping_summary=dict(bundle.mapping_summary or {}),
            expected_totals=dict(bundle.expected_totals or {}),
            sandbox_of=bundle,
            triggered_by=bundle.triggered_by,
        )
        # Copy artifact rows (file paths) — no byte copy needed.
        for artifact in bundle.artifacts.all():
            MigrationArtifact.objects.create(
                bundle=clone,
                parent_archive=None,
                path_within_bundle=artifact.path_within_bundle,
                filename=artifact.filename,
                mime_type=artifact.mime_type,
                detected_format=artifact.detected_format,
                byte_size=artifact.byte_size,
                sha256=artifact.sha256,
                encoding=artifact.encoding,
                row_count=artifact.row_count,
                column_count=artifact.column_count,
                locale_hints=dict(artifact.locale_hints or {}),
                profile=dict(artifact.profile or {}),
                inferred_source=artifact.inferred_source,
                inferred_domain=list(artifact.inferred_domain or []),
            )
    return clone


def promote_sandbox_to_origin(*, sandbox: MigrationBundle) -> dict[str, Any]:
    """Promote a sandbox: reset the origin to MAPPED so the operator can re-apply.

    Does NOT auto-apply — the operator clicks "apply" on the origin manually
    after promotion. The sandbox itself is left in place for audit; the
    operator can ``discard_sandbox`` to free its schema afterward.
    """
    if sandbox.sandbox_of_id is None:
        raise ValueError(f"Bundle {sandbox.pk} is not a sandbox.")
    origin = sandbox.sandbox_of
    # Pull the sandbox's mapping_summary back to origin so the operator's
    # in-sandbox mapping edits don't have to be re-done.
    origin.mapping_summary = dict(sandbox.mapping_summary or {})
    origin.expected_totals = dict(sandbox.expected_totals or {})
    if origin.status not in (BundleStatus.MAPPED, BundleStatus.APPLIED, BundleStatus.RECONCILED):
        origin.mark_status(BundleStatus.MAPPED)
    else:
        origin.save(update_fields=["mapping_summary", "expected_totals", "updated_at"])
    return {
        "origin_bundle_id": origin.pk,
        "origin_status": origin.status,
        "sandbox_bundle_id": sandbox.pk,
    }


def discard_sandbox(*, sandbox: MigrationBundle) -> dict[str, Any]:
    """Drop a sandbox bundle. Marks its schema for teardown by the cleanup task."""
    if sandbox.sandbox_of_id is None:
        raise ValueError(f"Bundle {sandbox.pk} is not a sandbox.")
    schema_name = sandbox.schema_name
    sandbox.delete()
    return {"discarded_sandbox_id": sandbox.pk, "schema_name": schema_name}
