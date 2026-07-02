"""Bundle ingestion orchestrator (Phase U1).

The single entry point for "I have something to migrate" — regardless of
source shape. Callers (wizard view, management command, API, accelerator)
hand the orchestrator a bundle spec plus a source handle; it creates the
``MigrationBundle``, looks up the right intake adapter, persists every
emitted artifact, and transitions the bundle through its lifecycle.

What this layer does NOT do:
    * Profile artifacts (Phase U2 — ``apps.migration_cloud.profiler``).
    * Classify source / domain (Phase U3 — ``apps.migration_cloud.classifiers``).
    * Map columns to canonical fields (Phase U4 — ``apps.migration_cloud.mapper``).
    * Apply to tenant (Phase U5 — ``apps.migration_cloud.orchestrator``).

Idempotency: ``idempotency_key`` is required and unique. Re-running the same
key against the same bundle is a no-op for already-registered artifacts
(deduped on ``sha256 + path_within_bundle`` per the model's unique
constraint); new artifacts in the same key extend the bundle.
"""

from __future__ import annotations

import logging
import mimetypes
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.db import IntegrityError, transaction

from .artifact_blob_store import capture_artifact_blob
from .intake import IntakeError, get_adapter
from .intake.base import IntakeContext, sha256_of_stream
from .models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
    SlaTier,
)

logger = logging.getLogger(__name__)


@dataclass
class BundleSpec:
    """Minimal description of an arriving bundle.

    ``school`` is optional so signup-time bundles (staged before the tenant
    schema exists) can be accepted; the orchestrator binds the school when
    the tenant is provisioned.
    """

    intake_method: str
    handle: Any
    school_id: int | None = None
    schema_name: str = ""
    label: str = ""
    source_hint: str = ""
    sla_tier: str = SlaTier.SMALL
    idempotency_key: str | None = None
    triggered_by_id: int | None = None
    intake_source_uri: str = ""


@dataclass
class IngestionResult:
    bundle_id: int
    artifacts_registered: int
    artifacts_skipped_duplicate: int
    total_bytes: int
    status: str


class BundleIngestionService:
    """Wraps adapter dispatch + DB writes + lifecycle transitions."""

    def ingest(self, spec: BundleSpec) -> IngestionResult:
        adapter = get_adapter(spec.intake_method)
        bundle = self._get_or_create_bundle(spec)

        ctx = IntakeContext(
            bundle_id=bundle.pk,
            idempotency_key=bundle.idempotency_key,
            schema_name=bundle.schema_name,
            source_hint=bundle.source_hint,
        )

        try:
            adapter.validate_handle(spec.handle, ctx)
        except IntakeError as exc:
            bundle.mark_status(
                BundleStatus.FAILED,
                summary_patch={"error": str(exc), "stage": "validate"},
            )
            raise

        bundle.mark_status(BundleStatus.INGESTING)

        registered = 0
        skipped = 0
        total_bytes = 0
        path_to_archive_artifact: dict[str, MigrationArtifact] = {}

        try:
            if adapter.intake_method == IntakeMethod.ARCHIVE:
                parent_artifact = self._register_archive_parent(bundle, spec.handle)
                if parent_artifact is not None:
                    path_to_archive_artifact[parent_artifact.path_within_bundle] = (
                        parent_artifact
                    )

            for payload in adapter.iter_artifacts(spec.handle, ctx):
                parent_archive = None
                if payload.parent_archive_path:
                    parent_archive = path_to_archive_artifact.get(
                        payload.parent_archive_path
                    )
                try:
                    with transaction.atomic():
                        artifact = MigrationArtifact.objects.create(
                            bundle=bundle,
                            parent_archive=parent_archive,
                            path_within_bundle=payload.path_within_bundle,
                            filename=payload.filename,
                            mime_type=payload.mime_type,
                            byte_size=payload.byte_size,
                            sha256=payload.sha256,
                            encoding=payload.encoding,
                            locale_hints={},
                            profile={},
                        )
                except IntegrityError:
                    # Same (bundle, sha256, path) already registered — idempotent skip.
                    skipped += 1
                    continue

                # Track top-level archives so child members can link to them.
                if payload.parent_archive_path is None and adapter.intake_method == IntakeMethod.ARCHIVE:
                    path_to_archive_artifact[payload.path_within_bundle] = artifact

                # Phase U5 content store: capture the source bytes encrypted-at-rest
                # NOW, while the adapter's ``content_opener`` is still valid — the
                # only moment it is reachable. This is what lets archive members +
                # remote / OAuth-folder pulls profile + apply downstream instead of
                # silently resolving to zero rows. Best-effort: never blocks ingest.
                capture_artifact_blob(artifact, payload)

                registered += 1
                total_bytes += payload.byte_size
        except IntakeError as exc:
            bundle.mark_status(
                BundleStatus.FAILED,
                summary_patch={"error": str(exc), "stage": "iter_artifacts"},
            )
            raise
        except Exception as exc:  # noqa: BLE001 — surface unexpected adapter bugs
            logger.exception(
                "migration_cloud.ingest: adapter raised unexpected error",
                extra={"bundle_id": bundle.pk, "method": spec.intake_method},
            )
            bundle.mark_status(
                BundleStatus.FAILED,
                summary_patch={"error": repr(exc), "stage": "iter_artifacts"},
            )
            raise

        # Phase U1 stops at INGESTING; the profiler in Phase U2 moves the bundle
        # to PROFILED. Update size_summary without changing status.
        bundle.size_summary = {
            **bundle.size_summary,
            "artifact_count": bundle.artifact_count,
            "registered_this_call": registered,
            "skipped_duplicates_this_call": skipped,
            "total_bytes_this_call": total_bytes,
        }
        bundle.save(update_fields=["size_summary", "updated_at"])

        return IngestionResult(
            bundle_id=bundle.pk,
            artifacts_registered=registered,
            artifacts_skipped_duplicate=skipped,
            total_bytes=total_bytes,
            status=bundle.status,
        )

    def _get_or_create_bundle(self, spec: BundleSpec) -> MigrationBundle:
        key = spec.idempotency_key or _new_idempotency_key()
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        existing = MigrationBundle.objects.filter(idempotency_key=key).first()
        if existing is not None:
            return existing

        return MigrationBundle.objects.create(
            school_id=spec.school_id,
            schema_name=spec.schema_name,
            label=spec.label,
            intake_method=spec.intake_method,
            intake_source_uri=spec.intake_source_uri,
            source_hint=spec.source_hint,
            idempotency_key=key,
            sla_tier=spec.sla_tier,
            triggered_by_id=spec.triggered_by_id,
        )

    def _register_archive_parent(
        self, bundle: MigrationBundle, handle: Any
    ) -> MigrationArtifact | None:
        if not isinstance(handle, (str, Path)):
            return None

        path = Path(handle)
        if not path.exists() or not path.is_file():
            return None

        with path.open("rb") as stream:
            digest, byte_size = sha256_of_stream(stream)
        mime_type = mimetypes.guess_type(path.name)[0] or ""

        try:
            with transaction.atomic():
                return MigrationArtifact.objects.create(
                    bundle=bundle,
                    parent_archive=None,
                    path_within_bundle=path.name,
                    filename=path.name,
                    mime_type=mime_type,
                    detected_format=ArtifactFormat.ARCHIVE,
                    byte_size=byte_size,
                    sha256=digest,
                    encoding="",
                    locale_hints={},
                    profile={},
                )
        except IntegrityError:
            return MigrationArtifact.objects.filter(
                bundle=bundle,
                sha256=digest,
                path_within_bundle=path.name,
            ).first()


def _new_idempotency_key() -> str:
    """Generate a random key when the caller did not supply one.

    Callers that genuinely want replay safety must supply their own key
    (a stable hash of the source handle is the usual choice). The random
    fallback exists so ad-hoc operator uploads still work.
    """
    return f"mc-{secrets.token_urlsafe(16)}"
