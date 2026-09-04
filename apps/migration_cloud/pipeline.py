"""End-to-end pipeline advance — wires intake → profile → classify → map.

Why a separate module: ``services.BundleIngestionService.ingest`` is the
single entry point for bringing bytes in, and Phase U1 deliberately stops
at INGESTING. This module is the single entry point for moving a bundle
forward through the AI-assisted phases (U2, U3, U4) and the optional U9
accelerator short-circuit.

Usage::

    from apps.migration_cloud.pipeline import advance_bundle

    summary = advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
    # summary['source']          → chosen source system
    # summary['per_artifact']    → {path: {"domain": ..., "mappings": [...]}}
    # summary['ai_calls']        → count of LLM tiebreaker invocations
    # bundle.status              → MAPPED on success, FAILED on hard error

The advance function is idempotent: a bundle that's already MAPPED is a
no-op. A bundle that's been partially advanced (e.g. PROFILED but not
CLASSIFIED) picks up from the next step.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.utils import timezone

from .accelerators import get_accelerator
from .classifiers import classify_domain, classify_source
from .mapper import ColumnMapping, map_artifact
from .models import BundleStatus, MigrationArtifact, MigrationBundle
from .profiler import profile_bundle
from .progress import emit as _emit_progress, refresh_snapshot

logger = logging.getLogger(__name__)


def _operator_domain_for(operator_domains: dict, artifact) -> str:
    """The operator's per-file domain tag for this artifact, if any.

    Matches by ``path_within_bundle`` first (exact) then the bare ``filename``
    (the tagger keys by upload filename). Validated against the canonical domain
    registry so a stale/garbage tag can never route an artifact to a bogus
    lander. Returns '' when the operator did not tag this file.
    """
    if not operator_domains:
        return ""
    from .accelerators.runmycampus_canonical import is_valid_canonical_domain

    for key in (artifact.path_within_bundle, artifact.filename):
        val = (operator_domains.get(key) or "").strip()
        if val and is_valid_canonical_domain(val):
            return val
    return ""


def _coerce_secret(value: Any) -> dict[str, Any]:
    """Normalise a bundle's ``connector_secret`` to a plain dict.

    ``EncryptedJSONField`` returns the *literal string* ``"{}"`` for its empty
    fast-path (it is never re-parsed to a dict on read), so ``dict(value)`` would
    raise ``ValueError`` on a reloaded, unattached connector bundle — and
    ``advance_bundle`` always reloads the bundle from the DB before calling this.
    Coerce defensively: anything that is not a real mapping becomes ``{}``.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def build_connector_handle(bundle: MigrationBundle):
    """Reconstruct the intake-adapter handle for a connector bundle.

    Combines the bundle's decrypted ``connector_secret`` (API bearer / OAuth
    access tokens, Fernet-encrypted at rest) with ``intake_source_uri`` into the
    method-specific handle shape each adapter's ``iter_artifacts`` expects.
    Returns ``None`` when the method is not a connector method OR the required
    pieces are missing — so the caller cleanly skips ingest rather than raising.

    NEVER logs the secret.
    """
    from .models import IntakeMethod

    method = bundle.intake_method
    secret = _coerce_secret(bundle.connector_secret)
    uri = (bundle.intake_source_uri or "").strip()

    if method == IntakeMethod.API_PULL:
        url = secret.get("url") or uri
        token = secret.get("api_token") or ""
        if not url or not token:
            return None
        return {
            "url": url,
            "api_token": token,
            "artifact_name": secret.get("artifact_name") or "api_export.json",
        }
    if method == IntakeMethod.OAUTH_FOLDER:
        if not (
            secret.get("provider")
            and secret.get("folder_id")
            and secret.get("access_token")
        ):
            return None
        return {
            "provider": secret["provider"],
            "folder_id": secret["folder_id"],
            "access_token": secret["access_token"],
        }
    if method == IntakeMethod.DATABASE:
        # SQLite file path — no credential; the file must be locally readable.
        return uri or None
    return None


def advance_bundle(*, bundle_id: int, use_accelerator: bool = True) -> dict[str, Any]:
    """Move a bundle forward (INGESTING → … → MAPPED), tracked as a WorkflowRun.

    The thin wrapper exists so a wedged advance is VISIBLE to the stuck / abandoned
    watchdogs. The durable HeavyWorkOutbox drain (production path) calls this
    directly — bypassing the ``@track_workflow``-decorated Celery task — so without
    the wrap no WorkflowRun exists and every watchdog is blind. The inner body
    already pulses "profile"/"classify"/"map" against ``active_workflow_run()``;
    this gives those pulses a run to land on. ``ensure_workflow_run`` is a no-op
    when the decorated task already opened a run of the same key (no double track).
    """
    from apps.platform_runtime.workflow_tracker import ensure_workflow_run

    with ensure_workflow_run(
        "migration_bundle_advance",
        steps=("profile", "classify", "map"),
        expected_duration_seconds=900,  # magic-number-allow: workflow-expected-duration-seconds (matches celery_tasks.advance_bundle_task)
        payload={"bundle_id": bundle_id},
    ):
        return _advance_bundle_inner(bundle_id=bundle_id, use_accelerator=use_accelerator)


def _advance_bundle_inner(*, bundle_id: int, use_accelerator: bool = True) -> dict[str, Any]:
    """Move a bundle as far forward as possible: INGESTING → PROFILED → CLASSIFIED → MAPPED.

    Stops at the first hard failure; the bundle's status reflects how far
    it got. Always returns a summary dict so callers (wizard, API,
    management command) can render progress without re-querying.
    """
    bundle = MigrationBundle.objects.get(pk=bundle_id)  # tenant-isolation-allow: PK lookup by internal bundle id
    summary: dict[str, Any] = {
        "bundle_id": bundle_id,
        "stages_run": [],
        "ai_calls": 0,
    }

    # --- Phase U1: ingest from an attached connector source ----------------
    # Connector methods (DATABASE / API_PULL / OAUTH_FOLDER) stage an EMPTY
    # bundle; the operator attaches a live source afterward. Pull its artifacts
    # here, before profiling. FILE_UPLOAD / ARCHIVE bundles already carry their
    # artifacts from intake, so this is a no-op for them (artifacts exist).
    if not bundle.artifacts.exists():
        from .intake import IntakeError, get_adapter

        handle = build_connector_handle(bundle)
        adapter_available = False
        if handle is not None:
            try:
                get_adapter(bundle.intake_method)
                adapter_available = True
            except KeyError:
                adapter_available = False
        if handle is not None and adapter_available:
            _emit_progress(
                bundle_id=bundle_id, kind="stage_started", stage="INGESTING",
                message="Pulling artifacts from the attached source",
            )
            from .services import BundleIngestionService, BundleSpec

            try:
                ingest_result = BundleIngestionService().ingest(
                    BundleSpec(
                        intake_method=bundle.intake_method,
                        handle=handle,
                        school_id=bundle.school_id,
                        schema_name=bundle.schema_name,
                        source_hint=bundle.source_hint,
                        idempotency_key=bundle.idempotency_key,  # reuse THIS bundle
                        intake_source_uri=bundle.intake_source_uri,
                    )
                )
            except IntakeError as exc:
                # ingest() already marked the bundle FAILED with the reason.
                summary["stages_run"].append("ingest")
                summary["stage_failed"] = "ingest"
                summary["error"] = str(exc)
                return summary
            summary["stages_run"].append("ingest")
            summary["artifacts_ingested"] = ingest_result.artifacts_registered
            bundle.refresh_from_db()
            _emit_progress(
                bundle_id=bundle_id, kind="stage_finished", stage="INGESTING",
                message=f"Ingested {ingest_result.artifacts_registered} artifact(s)",
            )

    # --- Phase U2: profile -------------------------------------------------
    if bundle.status in (BundleStatus.INGESTING, BundleStatus.PENDING):
        _emit_progress(bundle_id=bundle_id, kind="stage_started", stage="PROFILED",
                       message="Profiling artifacts")
        try:
            from apps.platform_runtime.workflow_tracker import active_workflow_run, pulse_workflow_step

            pulse_workflow_step(active_workflow_run(), "profile")
        except Exception:
            pass
        profiled = profile_bundle(bundle)
        summary["stages_run"].append("profile")
        summary["artifacts_profiled"] = profiled
        bundle.refresh_from_db()
        _emit_progress(bundle_id=bundle_id, kind="stage_finished", stage="PROFILED",
                       message=f"Profiled {profiled} artifact(s)",
                       detail={"rows": profiled})

    # --- Phase U3: source classification ----------------------------------
    if bundle.status == BundleStatus.PROFILED:
        try:
            from apps.platform_runtime.workflow_tracker import active_workflow_run, pulse_workflow_step

            pulse_workflow_step(active_workflow_run(), "classify")
        except Exception:
            pass
        artifacts = list(bundle.artifacts.filter(quarantined=False))
        source_result = classify_source(bundle=bundle, artifacts=artifacts)
        bundle.discovery_summary = {
            **(bundle.discovery_summary or {}),
            "source": source_result,
        }
        bundle.save(update_fields=["discovery_summary", "updated_at"])
        summary["stages_run"].append("classify_source")
        summary["source"] = source_result["chosen"]
        if source_result["method"] == "ai_bridge":
            summary["ai_calls"] += 1

        # --- Phase U3: per-artifact domain classification -----------------
        # Operator per-file tags (from the multi-file canonical-CSV upload
        # tagger) OVERRIDE inference — the operator explicitly said "this file
        # is X", which is more authoritative than any content/filename guess.
        operator_domains = (
            (bundle.discovery_summary or {}).get("operator_assigned_domains") or {}
        )
        per_artifact: dict[str, dict[str, Any]] = {}
        artifacts_total = max(len(artifacts), 1)
        for index, artifact in enumerate(artifacts, start=1):
            domain_result = classify_domain(artifact=artifact)
            assigned = _operator_domain_for(operator_domains, artifact)
            artifact.inferred_source = source_result["chosen"][:64]
            artifact.inferred_domain = domain_result["candidates"]
            update_fields = ["inferred_source", "inferred_domain", "updated_at"]
            if assigned:
                artifact.assigned_domain = assigned
                update_fields.append("assigned_domain")
            artifact.save(update_fields=update_fields)
            chosen = assigned or domain_result["chosen"]
            method = "operator_assigned" if assigned else domain_result["method"]
            per_artifact[artifact.path_within_bundle] = {
                "domain": chosen,
                "candidates": domain_result["candidates"],
                "method": method,
            }
            if not assigned and domain_result["method"] == "ai_bridge":
                summary["ai_calls"] += 1
            try:
                from .unified_progress import pulse_detection_progress

                pulse_detection_progress(
                    bundle_id=bundle_id,
                    stage="CLASSIFIED",
                    message=f"Detected type for {artifact.filename or artifact.path_within_bundle}",
                    artifacts_done=index,
                    artifacts_total=artifacts_total,
                )
            except Exception:  # noqa: BLE001
                logger.debug("pipeline: classify progress pulse failed", exc_info=True)

        bundle.discovery_summary = {
            **bundle.discovery_summary,
            "per_artifact_domain": per_artifact,
        }
        # Same persistence trap as the U4 mapping write: mark_status saves a
        # fixed update_fields list without discovery_summary, and the refresh
        # would drop this assignment — losing per-artifact domains means the
        # apply step falls back to the custom_fields lander for every artifact.
        bundle.save(update_fields=["discovery_summary", "updated_at"])
        bundle.mark_status(BundleStatus.CLASSIFIED)
        bundle.refresh_from_db()
        summary["per_artifact"] = per_artifact

    # --- Phase U9: accelerator short-circuit ------------------------------
    accelerator_contract = None
    chosen_source = (bundle.discovery_summary or {}).get("source", {}).get("chosen", "")
    if use_accelerator and bundle.status == BundleStatus.CLASSIFIED and chosen_source:
        accelerator = get_accelerator(chosen_source)
        if accelerator is not None and accelerator.is_handle_supported(bundle):
            try:
                accelerator_contract = accelerator.execute(
                    bundle_id=bundle.pk, handle=bundle
                )
                summary["stages_run"].append("accelerator")
                summary["accelerator"] = {
                    "source": chosen_source,
                    "version": getattr(accelerator, "version", ""),
                    "pre_classified": list(
                        accelerator_contract.pre_classified_artifacts.keys()
                    ),
                    "notes": accelerator_contract.notes,
                }
                if accelerator_contract.pre_classified_artifacts:
                    # The deterministic accelerator's DOMAIN classification
                    # overrides the fuzzy U3 ontology scoring for the
                    # artifacts it recognises. Before this override the
                    # contract's domain was decorative — _build_jobs reads
                    # only per_artifact_domain — so a canonical-template
                    # artifact could mis-route on raw header overlap (a
                    # transfer bundle's grades.csv scored as "sections" once
                    # it carried academic_year) and every row quarantined in
                    # the wrong lander.
                    discovery = bundle.discovery_summary or {}
                    per_artifact_domain = dict(
                        discovery.get("per_artifact_domain") or {}
                    )
                    for path, entry in (
                        accelerator_contract.pre_classified_artifacts.items()
                    ):
                        domain = (entry or {}).get("domain")
                        if not domain:
                            continue
                        existing = dict(per_artifact_domain.get(path) or {})
                        # An explicit operator tag outranks even the deterministic
                        # accelerator — never override "this file is X".
                        if existing.get("method") == "operator_assigned":
                            continue
                        existing.update(
                            {
                                "domain": domain,
                                "method": (entry or {}).get("method", "accelerator"),
                            }
                        )
                        per_artifact_domain[path] = existing
                    bundle.discovery_summary = {
                        **discovery,
                        "per_artifact_domain": per_artifact_domain,
                    }
                    bundle.save(update_fields=["discovery_summary", "updated_at"])
            except Exception:  # noqa: BLE001 — accelerator failure falls back to universal path
                logger.warning(
                    "migration_cloud.pipeline: accelerator %s failed; falling back to universal map",
                    chosen_source,
                    exc_info=True,
                )

    # --- Phase U4: mapping (per artifact) ---------------------------------
    if bundle.status == BundleStatus.CLASSIFIED:
        try:
            from apps.platform_runtime.workflow_tracker import active_workflow_run, pulse_workflow_step

            pulse_workflow_step(active_workflow_run(), "map")
        except Exception:
            pass
        all_mappings: dict[str, list[dict[str, Any]]] = {}
        per_artifact_domain = (
            (bundle.discovery_summary or {}).get("per_artifact_domain") or {}
        )
        map_artifacts = list(bundle.artifacts.filter(quarantined=False))
        map_total = max(len(map_artifacts), 1)
        for map_index, artifact in enumerate(map_artifacts, start=1):
            domain_entry = per_artifact_domain.get(artifact.path_within_bundle, {})
            domain = domain_entry.get("domain", "custom_fields")

            mappings = _apply_accelerator_then_map(
                artifact=artifact,
                domain=domain,
                contract=accelerator_contract,
                bundle=bundle,
            )
            all_mappings[artifact.path_within_bundle] = [m.__dict__ for m in mappings]
            summary["ai_calls"] += sum(1 for m in mappings if m.method == "ai_bridge")
            try:
                from .unified_progress import pulse_detection_progress

                pulse_detection_progress(
                    bundle_id=bundle_id,
                    stage="CLASSIFIED",
                    message=f"Mapped columns for {artifact.filename or artifact.path_within_bundle}",
                    artifacts_done=map_index,
                    artifacts_total=map_total,
                )
            except Exception:  # noqa: BLE001
                logger.debug("pipeline: map progress pulse failed", exc_info=True)

        bundle.mapping_summary = {
            **(bundle.mapping_summary or {}),
            "per_artifact": all_mappings,
            "vendor_enum_tables": (
                accelerator_contract.vendor_enum_tables
                if accelerator_contract is not None
                else {}
            ),
        }
        # mark_status saves a fixed update_fields list that does NOT include
        # mapping_summary, and the refresh_from_db below would then discard
        # this assignment — persisting here is what lets _build_jobs see the
        # per-artifact mappings at apply time instead of falling back to the
        # custom_fields lander for every artifact.
        bundle.save(update_fields=["mapping_summary", "updated_at"])
        bundle.mark_status(BundleStatus.MAPPED, summary_patch={"ai_calls": summary["ai_calls"]})
        try:
            from .catalog_preflight import persist_catalog_preflight, apply_catalog_recommendations

            persist_catalog_preflight(bundle)
            changed = apply_catalog_recommendations(bundle)
            if changed:
                from .domain_overrides import sync_operator_assigned_domains

                sync_operator_assigned_domains(bundle, rewind_status=False)
                bundle.refresh_from_db()
                refresh_bundle_inference(bundle_id=bundle.pk, use_accelerator=use_accelerator)
                persist_catalog_preflight(bundle)
        except Exception:  # noqa: BLE001 — preflight must never block mapping
            logger.debug("pipeline: catalog preflight persist failed", exc_info=True)
        bundle.refresh_from_db()
        summary["stages_run"].append("map")
        # Partner lifecycle event (G-5): emitted at the SERVICE layer so a
        # connector/customer-UI advance fires the same webhook the REST advance
        # action used to. advance_bundle is idempotent, so this fires once — only
        # when the bundle actually reaches MAPPED.
        try:
            from .services.lifecycle_events import (
                EVENT_BUNDLE_ADVANCED,
                emit_bundle_lifecycle_event,
            )
            emit_bundle_lifecycle_event(
                bundle, EVENT_BUNDLE_ADVANCED, {"status": str(BundleStatus.MAPPED)},
            )
        except Exception:  # noqa: BLE001 — event emission never blocks the pipeline
            pass

    summary["status"] = bundle.status
    refresh_snapshot(bundle=bundle)
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEventType
        from apps.migration_cloud.services.bundle_lifecycle_audit import safe_bundle_audit

        safe_bundle_audit(
            bundle,
            MigrationCloudAuditEventType.BUNDLE_ADVANCED.value,
            payload_summary={
                "bundle_id": str(bundle.pk),
                "status": str(bundle.status),
                "stages_run": list(summary.get("stages_run") or [])[:12],
                "artifact_count": int(bundle.artifacts.count()),
            },
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "migration_cloud.pipeline: advance audit failed bundle_id=%s",
            bundle_id,
            exc_info=True,
        )
    return summary


def refresh_bundle_inference(*, bundle_id: int, use_accelerator: bool = True) -> dict[str, Any]:
    """Re-classify domains and rebuild column mappings before a repair re-apply.

    Bundles that were classified under an older classifier (e.g.
    ``subjects_2026.xlsx`` routed to ``behavior`` instead of ``academics``)
    keep stale ``discovery_summary`` / ``mapping_summary`` until inference is
    refreshed. Repair calls this so the UI re-import uses current rules without
    re-uploading files.
    """
    from .classifiers.domain import classify_domain

    bundle = MigrationBundle.objects.get(pk=bundle_id)  # tenant-isolation-allow: PK lookup by internal bundle id
    artifacts = list(bundle.artifacts.filter(quarantined=False))
    summary: dict[str, Any] = {"bundle_id": bundle_id, "artifacts": len(artifacts), "ai_calls": 0}

    operator_domains = (
        (bundle.discovery_summary or {}).get("operator_assigned_domains") or {}
    )
    per_artifact: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        domain_result = classify_domain(artifact=artifact)
        assigned = _operator_domain_for(operator_domains, artifact)
        chosen = (assigned or domain_result["chosen"] or "custom_fields").strip()
        method = "operator_assigned" if assigned else domain_result["method"]
        per_artifact[artifact.path_within_bundle] = {
            "domain": chosen,
            "candidates": domain_result["candidates"],
            "method": method,
        }
        if not assigned and domain_result["method"] == "ai_bridge":
            summary["ai_calls"] += 1

    accelerator_contract = None
    chosen_source = (bundle.discovery_summary or {}).get("source", {}).get("chosen", "")
    if use_accelerator and chosen_source:
        accelerator = get_accelerator(chosen_source)
        if accelerator is not None and accelerator.is_handle_supported(bundle):
            try:
                accelerator_contract = accelerator.execute(
                    bundle_id=bundle.pk, handle=bundle
                )
                per_artifact_domain = dict(per_artifact)
                for path, entry in (
                    accelerator_contract.pre_classified_artifacts.items()
                ):
                    domain = (entry or {}).get("domain")
                    if not domain:
                        continue
                    existing = dict(per_artifact_domain.get(path) or {})
                    if existing.get("method") == "operator_assigned":
                        continue
                    existing.update(
                        {
                            "domain": domain,
                            "method": (entry or {}).get("method", "accelerator"),
                        }
                    )
                    per_artifact_domain[path] = existing
                per_artifact = per_artifact_domain
                summary["accelerator"] = True
            except Exception:  # noqa: BLE001
                logger.warning(
                    "migration_cloud.pipeline: refresh accelerator failed bundle=%s",
                    bundle_id,
                    exc_info=True,
                )

    all_mappings: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        domain_entry = per_artifact.get(artifact.path_within_bundle) or {}
        domain = domain_entry.get("domain", "custom_fields")
        mappings = _apply_accelerator_then_map(
            artifact=artifact,
            domain=domain,
            contract=accelerator_contract,
            bundle=bundle,
        )
        all_mappings[artifact.path_within_bundle] = [m.__dict__ for m in mappings]
        summary["ai_calls"] += sum(1 for m in mappings if m.method == "ai_bridge")

    bundle.discovery_summary = {
        **(bundle.discovery_summary or {}),
        "per_artifact_domain": per_artifact,
        "inference_refreshed_at": timezone.now().isoformat(),
    }
    bundle.mapping_summary = {
        **(bundle.mapping_summary or {}),
        "per_artifact": all_mappings,
        "vendor_enum_tables": (
            accelerator_contract.vendor_enum_tables
            if accelerator_contract is not None
            else (bundle.mapping_summary or {}).get("vendor_enum_tables") or {}
        ),
    }
    bundle.save(update_fields=["discovery_summary", "mapping_summary", "updated_at"])
    summary["per_artifact"] = per_artifact
    return summary


def _apply_accelerator_then_map(
    *,
    artifact: MigrationArtifact,
    domain: str,
    contract: Any | None,
    bundle: MigrationBundle | None = None,
) -> list[ColumnMapping]:
    """Use accelerator + profile template mappings when available, else universal mapper.

    Even with pre-maps, columns not covered still flow through the universal
    mapper — custom or non-standard columns are never dropped.
    """
    from .mapping_template_registry import merge_template_mappings

    pre = None
    pre_mappings_dict: dict[str, str] = {}
    effective_domain = domain
    pre_method = "accelerator"

    if contract is not None:
        pre = contract.pre_classified_artifacts.get(artifact.path_within_bundle)
    if pre:
        pre_mappings_dict = dict(pre.get("canonical_mappings") or {})
        effective_domain = str(pre.get("domain") or domain)
        pre_method = str(pre.get("method") or "accelerator")

    if bundle is not None:
        pre_mappings_dict, effective_domain, template_method = merge_template_mappings(
            artifact=artifact,
            domain=effective_domain,
            bundle=bundle,
            pre_mappings_dict=pre_mappings_dict,
            pre_domain=effective_domain,
        )
        if template_method:
            pre_method = template_method

    if not pre_mappings_dict:
        return map_artifact(artifact=artifact, domain=domain)

    # Run the universal mapper to cover columns the pre-map did NOT specify.
    universal = map_artifact(artifact=artifact, domain=effective_domain)
    universal_by_source = {m.source_column: m for m in universal}

    merged: list[ColumnMapping] = []
    cols = (artifact.profile or {}).get("columns") or []
    for col in cols:
        source_name = col.get("name", "")
        if source_name in pre_mappings_dict:
            merged.append(
                ColumnMapping(
                    source_column=source_name,
                    canonical_field=pre_mappings_dict[source_name],
                    domain=effective_domain,
                    confidence=0.99,
                    method=pre_method,
                    transformer=None,
                    transformer_options={},
                    reasoning=f"pre-mapped ({pre_method})",
                )
            )
        elif source_name in universal_by_source:
            merged.append(universal_by_source[source_name])

    return merged
