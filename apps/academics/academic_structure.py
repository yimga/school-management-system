"""Tenant-scoped academic structure tree (bridges to Classroom at leaves)."""

from __future__ import annotations

import uuid

from django.db import models


class AcademicStructureNode(models.Model):
    """
    Recursive academic org tree under a School tenant.

    Not the same as ``apps.governance.GovernanceNode`` (holding-company overlay).
    Leaf nodes may link 1:1 to ``Classroom`` for gradebook/enrollment compatibility.
    """

    class NodeType(models.TextChoices):
        CYCLE = "cycle", "Cycle / stage"
        COHORT = "cohort", "Cohort / stream"
        SHIFT = "shift", "Instruction shift (turno)"
        CLASSROOM_LEAF = "classroom_leaf", "Classroom leaf"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="academic_structure_nodes",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    campus = models.ForeignKey(
        "schoolops.Campus",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="academic_structure_nodes",
    )
    node_type = models.CharField(max_length=32, choices=NodeType.choices)
    local_label = models.CharField(max_length=150)  # magic-number-allow: charfield-max-length
    sort_order = models.PositiveIntegerField(default=0)
    structural_metadata = models.JSONField(default=dict, blank=True)
    classroom = models.OneToOneField(
        "academics.Classroom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="structure_node",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school_id", "sort_order", "local_label"]
        indexes = [
            models.Index(fields=["school", "parent", "node_type"]),
        ]
        verbose_name = "Academic structure node"
        verbose_name_plural = "Academic structure nodes"

    def __str__(self) -> str:
        return f"{self.local_label} ({self.node_type})"
