"""Studio OS models.

Historically `studio_os` was a deliberately model-less app (views + services
only). The canvas-first Experience builder's #rollout proof-before-publish gate
needs a DURABLE, AUDITABLE approval record — who approved which region, when,
and against which draft — which a session store cannot provide. That is the sole
reason this module exists.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class ExperienceRegionApproval(models.Model):
    """A proof-before-publish approval for one Studio Experience region.

    One row per ``(school, region_key)``. ``draft_fingerprint`` pins the approval
    to the exact live theme values it was granted against (sha256[:16] over the
    region's fields via ``experience_rollout.compute_region_fingerprint``), so an
    approval is automatically stale — and cannot satisfy the publish gate — once
    the draft drifts from what was reviewed.

    Tenant-scoped: `school` FK + PostgreSQL RLS default-deny (migration 0002,
    mirroring the athletics pattern; SQLite skips RLS and relies on the
    always-`school=`-scoped queryset in the service layer).
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="experience_region_approvals",
    )
    region_key = models.CharField(max_length=32)
    draft_fingerprint = models.CharField(max_length=64)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    approved_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Experience region approval"
        verbose_name_plural = "Experience region approvals"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "region_key"],
                name="uniq_experience_region_approval_per_school_region",
            )
        ]
        indexes = [
            models.Index(
                fields=["school", "region_key"],
                name="idx_exp_region_appr_school_key",
            )
        ]

    def __str__(self) -> str:
        return f"{self.region_key} approval (school={self.school_id})"
