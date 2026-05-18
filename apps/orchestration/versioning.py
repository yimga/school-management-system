"""ProcessDefinition versioning service.

Move 2 of the strategic moves: every workflow / process definition gets a
monotonic version number, and every OrchestrationRun binds to the specific
version that was current at the moment of creation.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max

from apps.orchestration.models import (
    OrchestrationRun,
    ProcessDefinition,
    ProcessDefinitionVersion,
)


@transaction.atomic
def publish_new_version(
    definition: ProcessDefinition,
    *,
    config_snapshot: dict | None = None,
    notes: str = "",
    published_by=None,
) -> ProcessDefinitionVersion:
    """Publish a new version of a process definition.

    Marks any prior current version as stale, creates a new
    ProcessDefinitionVersion, and bumps definition.current_version.
    """

    ProcessDefinitionVersion.objects.filter(
        definition=definition, is_current=True
    ).update(is_current=False)

    last = ProcessDefinitionVersion.objects.filter(definition=definition).aggregate(
        m=Max("version_number")
    )["m"] or 0
    next_no = last + 1
    snap = config_snapshot if config_snapshot is not None else dict(definition.config_schema or {})
    pdv = ProcessDefinitionVersion.objects.create(
        definition=definition,
        version_number=next_no,
        config_snapshot=snap,
        notes=notes,
        is_current=True,
        published_by=published_by if (published_by and getattr(published_by, "is_authenticated", False)) else None,
    )
    definition.current_version = next_no
    definition.save(update_fields=["current_version", "updated_at"])
    return pdv


def current_version_for(definition: ProcessDefinition) -> ProcessDefinitionVersion | None:
    return (
        ProcessDefinitionVersion.objects.filter(definition=definition, is_current=True)
        .first()
    )


@transaction.atomic
def bind_run_to_current_version(run: OrchestrationRun) -> OrchestrationRun:
    """Attach run.definition_version to whatever is currently published.

    Called from run-creation paths; if a version was already bound (e.g. by an
    explicit caller pinning it) this is a no-op.
    """

    if run.definition_version_id:
        return run
    pdv = current_version_for(run.definition)
    if pdv is None:
        # Synthesize an initial v1 if the definition was created before versioning landed.
        pdv = publish_new_version(run.definition, notes="auto-init")
    run.definition_version = pdv
    run.save(update_fields=["definition_version", "updated_at"])
    return run
