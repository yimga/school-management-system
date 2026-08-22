"""``EdgeDeploymentHistory`` — the ladder the watchdog climbs back down.

WHY A TABLE AND NOT A FILE. Everything else about an upgrade is transient: the staging
directory is deleted, the cache hold expires, the log rotates. The one fact that must
survive a crash, a power cut and a container replacement is *which manifest this box was
last known to be healthy on*, because that is the only thing a rollback can aim at. A
file on the same volume as the staging tree is exactly the wrong place to keep it — the
failure mode being defended against is a half-written tree.

DELIBERATELY NOT TENANT-SCOPED. There is no ``school`` FK here, and that is a decision
rather than an omission: the code a box runs is a property of the BOX, not of the school
it serves. Adding the FK would also enrol the table in the tenant RLS coverage gate for
data it does not hold.

APPEND-ONLY. A rollback target that can be edited is not a rollback target. Rows are
written once and superseded by a later row, never mutated away or deleted — the same
posture ``migration_cloud`` uses for its delivery log. ``mark_*`` helpers update only the
outcome fields of the row they created, which is how a STAGED row becomes ACTIVE or
FAILED without a second row appearing for the same attempt.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone

from apps.platform_runtime.append_only import AppendOnlyManager, AppendOnlyModelMixin


class DeploymentState(models.TextChoices):
    STAGED = "STAGED", "Staged"
    VERIFIED = "VERIFIED", "Verified"
    ACTIVE = "ACTIVE", "Active"
    SUPERSEDED = "SUPERSEDED", "Superseded"
    ROLLED_BACK = "ROLLED_BACK", "Rolled back"
    FAILED = "FAILED", "Failed"


class EdgeDeploymentHistory(AppendOnlyModelMixin, models.Model):
    """One row per upgrade ATTEMPT on this box — including the ones that failed.

    A failed attempt is the most valuable row in the table. It is what tells a support
    engineer that the box tried, why it stopped, and that it is still serving on the
    manifest named in ``previous_manifest_hash``.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # What was attempted.
    manifest_hash = models.CharField(max_length=64, db_index=True)
    previous_manifest_hash = models.CharField(max_length=64, blank=True, default="")
    version_label = models.CharField(max_length=64, blank=True, default="")
    channel = models.CharField(max_length=32, blank=True, default="stable")
    engine_commit = models.CharField(max_length=64, blank=True, default="")
    release_id = models.CharField(max_length=64, blank=True, default="")
    release_path = models.CharField(max_length=500, blank=True, default="")

    # What the attempt moved.
    files_total = models.IntegerField(default=0)
    files_verified = models.IntegerField(default=0)
    bytes_total = models.BigIntegerField(default=0)
    # Migration labels this attempt applied, e.g. ["finance.0094_ledger_split"]. The
    # rollback floor is the state BEFORE these ran.
    migrations_applied = models.JSONField(default=list, blank=True)
    # True when the whole target manifest was received; False for an asset-only or
    # truncated pass, which must NOT be recorded as reaching the target hash.
    complete = models.BooleanField(default=False)
    # "assets" | "full" — which lane the manager was allowed to use.
    mode = models.CharField(max_length=16, blank=True, default="")
    # "swapped" | "deferred" | "none" — whether the running tree actually changed.
    activation = models.CharField(max_length=16, blank=True, default="")

    # How it ended.
    state = models.CharField(
        max_length=16, choices=DeploymentState.choices, default=DeploymentState.STAGED, db_index=True
    )
    health_ok = models.BooleanField(default=False)
    health_seconds = models.FloatField(default=0.0)
    health_detail = models.CharField(max_length=255, blank=True, default="")
    message = models.TextField(blank=True, default="")
    error = models.TextField(blank=True, default="")

    staged_at = models.DateTimeField(auto_now_add=True, db_index=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    reverted_at = models.DateTimeField(null=True, blank=True)

    objects = AppendOnlyManager()

    class Meta:
        app_label = "sync_engine"
        ordering = ["-staged_at"]
        verbose_name = "Edge deployment history"
        verbose_name_plural = "Edge deployment history"
        indexes = [
            models.Index(fields=["state", "-staged_at"]),
            models.Index(fields=["manifest_hash", "-staged_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"EdgeDeploymentHistory({self.manifest_hash[:12]},{self.state})"

    # ── writers ──────────────────────────────────────────────────────────────
    @classmethod
    def begin(cls, *, manifest_hash, previous_manifest_hash="", version_label="",
              channel="stable", engine_commit="", release_id="", release_path="",
              files_total=0, bytes_total=0, mode="", complete=False, message=""):
        return cls.objects.create(
            manifest_hash=str(manifest_hash or "")[:64],
            previous_manifest_hash=str(previous_manifest_hash or "")[:64],
            version_label=str(version_label or "")[:64],
            channel=str(channel or "stable")[:32],
            engine_commit=str(engine_commit or "")[:64],
            release_id=str(release_id or "")[:64],
            release_path=str(release_path or "")[:500],
            files_total=int(files_total or 0),
            bytes_total=int(bytes_total or 0),
            mode=str(mode or "")[:16],
            complete=bool(complete),
            message=str(message or ""),
            state=DeploymentState.STAGED,
        )

    def mark(self, state, *, message="", error="", **fields):
        """Set the outcome of THIS attempt. Never creates a second row."""
        self.state = state
        if message:
            self.message = message
        if error:
            self.error = str(error)[:4000]
        for key, value in fields.items():
            setattr(self, key, value)
        self.save(update_fields=None)
        return self

    def mark_verified(self, *, files_verified=0, message=""):
        return self.mark(DeploymentState.VERIFIED, message=message, files_verified=int(files_verified or 0))

    def mark_active(self, *, activation="swapped", health_seconds=0.0, health_detail="", message=""):
        # Every earlier ACTIVE row becomes SUPERSEDED, so "which manifest is live" is a
        # single-row question and the revert target is unambiguous.
        type(self).objects.filter(state=DeploymentState.ACTIVE).exclude(pk=self.pk).update(
            state=DeploymentState.SUPERSEDED
        )
        return self.mark(
            DeploymentState.ACTIVE,
            message=message,
            activation=str(activation or "")[:16],
            health_ok=True,
            health_seconds=float(health_seconds or 0.0),
            health_detail=str(health_detail or "")[:255],
            activated_at=timezone.now(),
        )

    def mark_failed(self, error, *, message=""):
        return self.mark(DeploymentState.FAILED, message=message, error=error)

    def mark_rolled_back(self, error, *, message="", health_seconds=0.0, health_detail=""):
        return self.mark(
            DeploymentState.ROLLED_BACK,
            message=message,
            error=error,
            health_ok=False,
            health_seconds=float(health_seconds or 0.0),
            health_detail=str(health_detail or "")[:255],
            reverted_at=timezone.now(),
        )

    # ── readers ──────────────────────────────────────────────────────────────
    @classmethod
    def active(cls):
        """The manifest this box is serving, or ``None`` before the first upgrade."""
        return cls.objects.filter(state=DeploymentState.ACTIVE).order_by("-staged_at").first()

    @classmethod
    def revert_target(cls):
        """The newest row that was healthy and is NOT the current active one.

        A rollback aims here. ``SUPERSEDED`` is the only state that qualifies: it means
        the box booted on that manifest and passed its health gate, which ``STAGED``,
        ``FAILED`` and ``ROLLED_BACK`` do not.
        """
        return cls.objects.filter(state=DeploymentState.SUPERSEDED).order_by("-staged_at").first()

    @classmethod
    def already_applied(cls, manifest_hash) -> bool:
        return cls.objects.filter(
            manifest_hash=str(manifest_hash or "")[:64],
            state__in=[DeploymentState.ACTIVE, DeploymentState.SUPERSEDED],
        ).exists()


__all__ = ["DeploymentState", "EdgeDeploymentHistory"]
