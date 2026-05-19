"""Append-only model guard — block ORM delete on audit/integration log rows."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import models


class AppendOnlyDeleteError(PermissionDenied):
    """Raised when code attempts to delete an append-only row."""


class AppendOnlyQuerySet(models.QuerySet):
    def delete(self):
        raise AppendOnlyDeleteError(
            f"{self.model.__name__} records are append-only; bulk delete is forbidden."
        )


class AppendOnlyManager(models.Manager.from_queryset(AppendOnlyQuerySet)):  # type: ignore[misc]
    """Default manager that rejects QuerySet.delete()."""


class AppendOnlyModelMixin:
    """
    Mixin for audit/delivery logs that must never be removed via ORM.

    Pair with ``objects = AppendOnlyManager()`` on the model class.
    """

    def delete(self, using=None, keep_parents=False):
        raise AppendOnlyDeleteError(
            f"{self.__class__.__name__} records are append-only and cannot be deleted."
        )
