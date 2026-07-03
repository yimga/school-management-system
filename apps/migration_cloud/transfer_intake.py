"""Internal-tenant transfer intake — sealed student envelope → target bundle.

The missing keystone the transfer design identified
(docs/TRANSFER_MERGE_SPLIT_ORCHESTRATOR_DESIGN.md §2/§5 step 4): every
migration-cloud source adapter reads an EXTERNAL SIS; nothing could feed one
RunMyCampus school's data into another. This module is that bridge — it takes
a checksum-verified student transfer envelope and rides the NORMAL pipeline
(staging CSV → bundle → advance → apply) at the target school, so the transfer
inherits the landers' idempotent upserts, conflict detection, id-mapping,
quarantine, and dry-run preview instead of forking any of it.

Wave A default is ``dry_run=True`` — the real apply is Wave B's go-live, after
the consent artifact and the orchestration runner exist.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from apps.migration_cloud.services.connector_bundle_bridge import (
    ingest_staged_csv_to_bundle,
    run_bundle_pipeline,
    write_staging_csv,
)

logger = logging.getLogger(__name__)

# The staged CSVs ARE the canonical RunMyCampus template format, and
# classify_source honors this operator hint verbatim — which is exactly what
# routes the bundle through the deterministic runmycampus_canonical
# accelerator (identity column mappings, no AI tier) instead of the
# universal mapper. The transfer provenance lives on the bundle LABEL.
TRANSFER_SOURCE_HINT = "runmycampus_canonical"
TRANSFER_LABEL_PREFIX = "RMC transfer"


def _tenant_hash(value: str) -> str:
    """Mirror of the interop envelope's tenant-id hash contract (sha256[:12])."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def ingest_transfer_envelope(
    envelope,
    *,
    target_school,
    triggered_by_id: int | None = None,
    dry_run: bool = True,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Verify + stage + run one student envelope against the target school.

    Returns ``{bundle_id, artifacts_registered, bundle_status, advance, apply}``.
    Idempotent: the bundle key derives from the envelope checksum, so
    re-ingesting the same sealed envelope reuses the same bundle and the
    duplicate CSV artifacts are skipped at registration.
    """
    from apps.interop.transfer_apply import TransferApplyError, verify_envelope_checksum

    if envelope.envelope_kind != "student":
        raise TransferApplyError(
            f"unsupported envelope_kind {envelope.envelope_kind!r} for transfer intake"
        )
    verify_envelope_checksum(envelope)
    expected_target = _tenant_hash(str(target_school.pk))
    if envelope.target_tenant_id_hash != expected_target:
        raise TransferApplyError("envelope target does not match this school")

    domain_rows = dict(getattr(envelope, "domain_rows", None) or {})
    domain_rows = {d: rows for d, rows in domain_rows.items() if rows}
    if not domain_rows:
        raise TransferApplyError("envelope carries no domain rows to apply")

    key = idempotency_key or f"rmc-transfer-{envelope.checksum[:40]}"

    bundle = None
    registered = 0
    for domain in sorted(domain_rows):
        csv_path = write_staging_csv(rows=domain_rows[domain], entity_type=domain)
        bundle, count = ingest_staged_csv_to_bundle(
            csv_path=csv_path,
            school=target_school,
            idempotency_key=key,
            source_hint=TRANSFER_SOURCE_HINT,
            label=f"{TRANSFER_LABEL_PREFIX} {envelope.checksum[:12]}",
            triggered_by_id=triggered_by_id,
        )
        registered += count

    summary = run_bundle_pipeline(
        bundle_id=bundle.pk,
        source_hint=TRANSFER_SOURCE_HINT,
        use_accelerator=True,
        dry_run_apply=dry_run,
    )
    logger.info(
        "transfer_intake.ran bundle=%s school=%s domains=%s dry_run=%s status=%s",
        bundle.pk,
        target_school.pk,
        sorted(domain_rows.keys()),
        dry_run,
        summary.get("bundle_status"),
        extra={"scope": "transfer_intake"},
    )
    return {
        "bundle_id": bundle.pk,
        "artifacts_registered": registered,
        "bundle_status": summary.get("bundle_status"),
        "advance": summary.get("advance"),
        "apply": summary.get("apply"),
    }


__all__ = ["TRANSFER_LABEL_PREFIX", "TRANSFER_SOURCE_HINT", "ingest_transfer_envelope"]
