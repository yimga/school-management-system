"""Drive a staged rollout: nominate a canary, watch it, then widen.

    manage.py ota_rollout --status
    manage.py ota_rollout --ring <school-slug> canary
    manage.py ota_rollout --pause <school-slug>
    manage.py ota_rollout --resume <school-slug>
    manage.py ota_rollout --promote stable

``--promote`` operates on the manifest this operator is CURRENTLY built from, which is
the only manifest it can serve; promoting an arbitrary hash it no longer holds the files
for would be a promise it cannot keep, so the hash is read from the manifest on disk
rather than accepted as an argument.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.sync_engine.models_rollout import (
    EdgeRolloutPolicy,
    ManifestRelease,
    RolloutRing,
    default_release_rings,
    may_receive,
)
from apps.sync_engine.system_manifest import load_manifest

# How many rows `--status` prints. Announced when it binds, never silent.
_STATUS_ROW_CAP = 200  # magic-number-allow: terminal-readable row cap for --status


def _school_by_slug(slug: str):
    from apps.schools.models import School

    school = School.objects.filter(slug=slug).first() or School.objects.filter(name=slug).first()
    if school is None:
        raise CommandError(f"no school matching {slug!r} (tried slug then name)")
    return school


class Command(BaseCommand):
    help = "Inspect and drive the OTA rollout rings."

    def add_arguments(self, parser):
        parser.add_argument("--status", action="store_true", help="Show the current rollout state.")
        parser.add_argument("--ring", nargs=2, metavar=("SCHOOL", "RING"), help="Put a school on canary|stable.")
        parser.add_argument("--pause", metavar="SCHOOL", help="Hold a school back from all upgrades.")
        parser.add_argument("--resume", metavar="SCHOOL", help="Undo --pause.")
        parser.add_argument(
            "--promote",
            nargs="+",
            metavar="RING",
            help="Release the CURRENT manifest to these rings, e.g. --promote canary stable.",
        )
        parser.add_argument("--note", default="", help="Recorded against the promotion.")

    def handle(self, *args, **options):
        manifest = load_manifest() or {}
        digest = str(manifest.get("manifest_hash") or "")

        if options.get("ring"):
            slug, ring = options["ring"]
            ring = ring.strip().lower()
            if ring not in RolloutRing.values:
                raise CommandError(f"ring must be one of {', '.join(RolloutRing.values)}")
            school = _school_by_slug(slug)
            policy, _ = EdgeRolloutPolicy.objects.get_or_create(school=school)
            policy.ring = ring
            policy.paused = False
            policy.note = options.get("note") or policy.note
            policy.save()
            self.stdout.write(self.style.SUCCESS(f"{school} -> ring {ring}"))
            return

        for flag, paused in (("pause", True), ("resume", False)):
            if options.get(flag):
                school = _school_by_slug(options[flag])
                policy, _ = EdgeRolloutPolicy.objects.get_or_create(school=school)
                policy.paused = paused
                policy.note = options.get("note") or policy.note
                policy.save()
                word = "paused" if paused else "resumed"
                self.stdout.write(self.style.SUCCESS(f"{school} {word}"))
                return

        if options.get("promote"):
            if not digest:
                raise CommandError(
                    "this operator has no system manifest, so there is nothing to promote — "
                    "run `manage.py generate_system_manifest` first"
                )
            rings = [r.strip().lower() for r in options["promote"]]
            unknown = [r for r in rings if r not in RolloutRing.values]
            if unknown:
                raise CommandError(f"unknown ring(s): {', '.join(unknown)}")
            row = ManifestRelease.promote(
                digest,
                rings=rings,
                note=options.get("note") or "",
                version_label=str(manifest.get("version_label") or ""),
                channel=str(manifest.get("channel") or "stable"),
            )
            self.stdout.write(
                self.style.SUCCESS(f"manifest {digest[:12]} released to: {', '.join(row.rings)}")
            )
            return

        # Default: --status
        self.stdout.write(f"operator manifest : {digest[:12] or '(none)'}")
        self.stdout.write(f"default rings     : {', '.join(default_release_rings())}")
        if digest:
            self.stdout.write(f"released to       : {', '.join(ManifestRelease.rings_for(digest)) or '(none)'}")
        self.stdout.write("")

        from apps.schools.models import School

        policies = {p.school_id: p for p in EdgeRolloutPolicy.objects.all()}
        released = ManifestRelease.rings_for(digest) if digest else []
        total = School.objects.count()
        # Capped so `--status` on a large fleet stays readable in a terminal. The cap is
        # ANNOUNCED, because a listing that silently stops at 200 reads as "that is the
        # whole fleet" -- and the schools an operator most needs to see during a rollout
        # are exactly the ones a truncation would hide.
        schools = list(School.objects.all().order_by("name")[:_STATUS_ROW_CAP])
        if not schools:
            self.stdout.write("no schools on this deployment")
            return

        self.stdout.write(f"{'school':<34} {'ring':<8} {'state':<9} why")
        for school in schools:
            policy = policies.get(school.pk)
            ring = policy.ring if policy else RolloutRing.STABLE.value
            paused = bool(policy and policy.paused)
            allowed, reason = (
                may_receive(school, digest, ring=ring, paused=paused, released=released)
                if digest
                else (False, "no manifest")
            )
            state = "paused" if paused else ("eligible" if allowed else "waiting")
            self.stdout.write(f"{str(school)[:33]:<34} {ring:<8} {state:<9} {reason}")

        if total > len(schools):
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    f"showing {len(schools)} of {total} schools (alphabetical); "
                    f"{total - len(schools)} not listed"
                )
            )
