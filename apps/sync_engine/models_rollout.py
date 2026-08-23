"""Who is allowed to move to a new manifest yet.

Without this, "push an upgrade" means "push it to every school at once". The manifest
endpoint served one manifest to whoever asked, so the first box to sync after a deploy
took the new release, and so did every other box behind it. A release that is wrong in a
way no test caught — and the reason this pipeline exists is that some of them are — would
reach the whole fleet before anyone could look at the first one.

So a manifest is not "available" simply because it exists. It is available to a RING, and
rings are widened deliberately.

TWO RECORDS, ONE DELIBERATELY NOT TENANT-SCOPED.

``EdgeRolloutPolicy`` is per school and carries a ``school`` FK, so it is tenant-scoped
and lands in ``scan_rls_table_coverage``; migration ``0019_rollout_rls`` enumerates it.

``ManifestRelease`` has NO ``school`` FK, and that is a decision rather than an omission,
the same one ``EdgeDeploymentHistory`` makes: how far a RELEASE has been promoted is a
property of the release, identical for every school in the fleet. Giving it a school FK
would both misdescribe it and enrol it in the tenant RLS gate for data it does not hold.

WHY A MISSING ROW IS NOT A REFUSAL. A school with no policy row is on the default ring,
and a manifest with no release row is on the rings named by
``RMC_OTA_DEFAULT_RELEASE_RINGS``. Requiring an operator to pre-create a row per school
before anything could ever ship would make a fresh install silently dead — the exact
failure this wave has been removing everywhere else. Nothing here writes on the read
path either: the resolver reads, and rows appear only when an operator actually decides
something.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class RolloutRing(models.TextChoices):
    # Deliberately two. A ring nobody can describe in one sentence is a ring nobody uses
    # correctly, and "canary then everyone" is the shape operators actually run.
    CANARY = "canary", "Canary"
    STABLE = "stable", "Stable"


DEFAULT_RING = RolloutRing.STABLE


def default_release_rings() -> list[str]:
    """Rings a manifest is released to when nobody has said otherwise.

    Defaults to canary only, so a deploy reaches the boxes an operator nominated and
    stops there. Set ``RMC_OTA_DEFAULT_RELEASE_RINGS=canary,stable`` to restore
    release-to-everyone-immediately.
    """
    raw = getattr(settings, "RMC_OTA_DEFAULT_RELEASE_RINGS", "") or ""
    rings = [r.strip().lower() for r in str(raw).split(",") if r.strip()]
    valid = [r for r in rings if r in RolloutRing.values]
    return valid or [RolloutRing.CANARY.value]


class EdgeRolloutPolicy(models.Model):
    """Which ring this school's box is on, and whether it is held back entirely."""

    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="ota_rollout_policy",
    )
    ring = models.CharField(
        max_length=16, choices=RolloutRing.choices, default=DEFAULT_RING, db_index=True
    )
    # A school mid-term-report, mid-exam, or one an engineer is already debugging. Paused
    # beats "move it to a ring that happens to have nothing in it", because the intent
    # survives the next promotion.
    paused = models.BooleanField(default=False)
    note = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "sync_engine"
        verbose_name = "Edge rollout policy"
        verbose_name_plural = "Edge rollout policies"

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        state = "paused" if self.paused else self.ring
        return f"EdgeRolloutPolicy({self.school_id},{state})"

    @classmethod
    def ring_for(cls, school) -> tuple[str, bool]:
        """``(ring, paused)`` for a school. A school with no row is on the default ring."""
        if school is None:
            return DEFAULT_RING.value, False
        row = cls.objects.filter(school=school).first()
        if row is None:
            return DEFAULT_RING.value, False
        return row.ring, bool(row.paused)


class ManifestRelease(models.Model):
    """How far one manifest has been promoted across the fleet."""

    manifest_hash = models.CharField(max_length=64, unique=True, db_index=True)
    version_label = models.CharField(max_length=64, blank=True, default="")
    channel = models.CharField(max_length=32, blank=True, default="stable")
    # e.g. ["canary"] then ["canary", "stable"]. A list rather than a single "furthest
    # ring" because promotion is not always monotonic: pulling a bad release back to
    # canary while a fix is prepared has to be expressible.
    rings = models.JSONField(default=list, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    first_seen_at = models.DateTimeField(auto_now_add=True)
    promoted_at = models.DateTimeField(null=True, blank=True)
    promoted_by = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        app_label = "sync_engine"
        ordering = ["-first_seen_at"]
        verbose_name = "Manifest release"
        verbose_name_plural = "Manifest releases"

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"ManifestRelease({self.manifest_hash[:12]},{','.join(self.rings or [])})"

    @classmethod
    def rings_for(cls, manifest_hash) -> list[str]:
        """Rings this manifest is released to. NO WRITE — an unseen manifest is a read."""
        digest = str(manifest_hash or "")[:64]
        if not digest:
            return []
        row = cls.objects.filter(manifest_hash=digest).first()
        if row is None:
            return default_release_rings()
        return [str(r).strip().lower() for r in (row.rings or []) if str(r).strip()]

    @classmethod
    def promote(cls, manifest_hash, *, rings, by="", note="", version_label="", channel="stable"):
        """Set the rings a manifest is released to. This is the deliberate widening."""
        digest = str(manifest_hash or "")[:64]
        wanted = [r for r in dict.fromkeys(str(x).strip().lower() for x in rings) if r in RolloutRing.values]
        row, _created = cls.objects.get_or_create(
            manifest_hash=digest,
            defaults={
                "rings": wanted,
                "version_label": str(version_label or "")[:64],
                "channel": str(channel or "stable")[:32],
            },
        )
        row.rings = wanted
        if note:
            row.note = str(note)[:255]
        row.promoted_at = timezone.now()
        row.promoted_by = str(by or "")[:150]
        row.save()
        return row


def may_receive(school, manifest_hash, *, ring=None, paused=None, released=None) -> tuple[bool, str]:
    """``(allowed, reason)`` — may this school be offered this manifest yet?

    The reason is returned even when allowed, because it is what the operator console and
    the handshake advice header show; "no" without a "why" turns every rollout question
    into a code-reading exercise.

    ``ring``/``paused``/``released`` let a caller that has ALREADY loaded those hand them
    in. On the handshake path — one school, one call — the lookups are free and the
    defaults are right. On a fleet-wide listing they are not: without this, the operator
    console did two extra queries per school on top of the policy map it had just built,
    so a 300-school fleet cost 600 avoidable round trips to render one page.
    """
    digest = str(manifest_hash or "")[:64]
    if not digest:
        return False, "no manifest on the operator"

    if ring is None or paused is None:
        ring, paused = EdgeRolloutPolicy.ring_for(school)
    if paused:
        return False, "held: this school is paused for upgrades"

    if released is None:
        released = ManifestRelease.rings_for(digest)
    if ring in released:
        return True, f"released to {ring}"
    return False, f"not yet released to {ring} (currently {', '.join(released) or 'no ring'})"


__all__ = [
    "RolloutRing",
    "DEFAULT_RING",
    "default_release_rings",
    "EdgeRolloutPolicy",
    "ManifestRelease",
    "may_receive",
]
