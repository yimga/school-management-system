from __future__ import annotations

from django.db import models


class TenantQuerySet(models.QuerySet):
    def for_school(self, school):
        """Return rows owned by ``school``; accepts a School instance or primary key."""
        school_id = getattr(school, "pk", school)
        if not school_id:
            return self.none()
        return self.filter(school_id=school_id)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Manager contract for tenant-owned models."""


class TenantOwnedModel(models.Model):
    """
    Abstract base for new tenant-owned tables.

    Existing models are not bulk-refactored here; new tenant-scoped models should
    inherit this so the school FK and ``objects.for_school(...)`` contract are not
    optional.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = TenantManager()

    class Meta:
        abstract = True
