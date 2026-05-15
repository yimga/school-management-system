"""Email-with-attachments intake stub — Phase U7.

Schools forward an email to ``migrate@<tenant>.runmycampus.com``; the inbound
mail handler parses attachments and registers each as an ``ArtifactPayload``.
Until U7, this stub keeps the registry honest.
"""

from __future__ import annotations

from typing import Any, Iterator

from apps.migration_cloud.models import IntakeMethod

from .base import ArtifactPayload, IntakeAdapter, IntakeContext, IntakeError, register_adapter


class EmailIntakeAdapter(IntakeAdapter):
    def iter_artifacts(
        self, handle: Any, ctx: IntakeContext
    ) -> Iterator[ArtifactPayload]:
        raise IntakeError(
            "Email-with-attachments intake lands in Phase U7. Forward the "
            "attachments locally and upload via FILE_UPLOAD for now."
        )


register_adapter(IntakeMethod.EMAIL, EmailIntakeAdapter())
