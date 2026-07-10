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

from .accelerators import get_accelerator
from .classifiers import classify_domain, classify_source
from .mapper import ColumnMapping, map_artifact
from .models import BundleStatus, MigrationArtifact, MigrationBundle
from .profiler import profile_bundle
from .progress import emit as _emit_progress, refresh_snapshot

logger = logging.getLogger(__name__)


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
        per_artifact: dict[str, dict[str, Any]] = {}
        for artifact in artifacts:
            domain_result = classify_domain(artifact=artifact)
            artifact.inferred_source = source_result["chosen"][:64]
            artifact.inferred_domain = domain_result["candidates"]
            artifact.save(
                update_fields=["inferred_source", "inferred_domain", "updated_at"]
            )
            per_artifact[artifact.path_within_bundle] = {
                "domain": domain_result["chosen"],
                "candidates": domain_result["candidates"],
                "method": domain_result["method"],
            }
            if domain_result["method"] == "ai_bridge":
                summary["ai_calls"] += 1

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
        for artifact in bundle.artifacts.filter(quarantined=False):
            domain_entry = per_artifact_domain.get(artifact.path_within_bundle, {})
            domain = domain_entry.get("domain", "custom_fields")

            mappings = _apply_accelerator_then_map(
                artifact=artifact,
                domain=domain,
                contract=accelerator_contract,
            )
            all_mappings[artifact.path_within_bundle] = [m.__dict__ for m in mappings]
            summary["ai_calls"] += sum(1 for m in mappings if m.method == "ai_bridge")

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
        bundle.refresh_from_db()
        summary["stages_run"].append("map")

    summary["status"] = bundle.status
    refresh_snapshot(bundle=bundle)
    return summary


def _apply_accelerator_then_map(
    *,
    artifact: MigrationArtifact,
    domain: str,
    contract: Any | None,
) -> list[ColumnMapping]:
    """Use accelerator's pre-classified mappings when available, else run universal mapper.

    Even with an accelerator, columns the accelerator didn't pre-map still
    flow through the universal mapper — so custom or non-standard columns
    are never dropped.
    """
    pre = None
    if contract is not None:
        pre = contract.pre_classified_artifacts.get(artifact.path_within_bundle)

    if not pre:
        return map_artifact(artifact=artifact, domain=domain)

    pre_mappings_dict = pre.get("canonical_mappings") or {}
    effective_domain = pre.get("domain", domain)

    # Run the universal mapper to cover columns the accelerator did NOT specify
    # (custom fields the customer added on top of OneRoster, etc.).
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
                    method="accelerator",
                    transformer=None,
                    transformer_options={},
                    reasoning=f"accelerator-supplied mapping ({pre.get('method', 'accelerator')})",
                )
            )
        elif source_name in universal_by_source:
            merged.append(universal_by_source[source_name])
        # else: skipped (no profile column) — universal_by_source covers all profile columns.

    return merged
