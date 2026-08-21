"""Print this deployment's parity digest, or compare it against a peer's (G8).

Two modes, both READ-ONLY:

    python manage.py verify_sync_parity --school gilead-tech
        Print the digest this deployment would put on the wire. Run it on the box and on
        the cloud and the two lines are directly comparable by eye — which is the whole
        point of a digest that does not depend on ``updated_at`` (see the module docstring
        in ``apps/sync_engine/parity.py`` for why the obvious column is the wrong one).

    python manage.py verify_sync_parity --school gilead-tech --against "<digest string>"
        Compare against a peer's printed digest and report which entities disagree.

Exit code is 0 when the two agree and 1 when they do not, so it can gate a cutover — the
moment parity actually matters, because that is when someone is about to trust the box
with a school's records offline.

Deliberately NOT a repair: the repair runs on the box, inside the ordinary sync cycle,
where the credential and the conflict policy already live. A command that could rewrite
rows from the operator's terminal would be a second write path into tenant data with none
of the guards the rail spent this long earning.
"""
from __future__ import annotations

import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print or compare the edge-sync parity digest for a school (read-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            default="",
            help="School slug. Required when the deployment serves more than one.",
        )
        parser.add_argument(
            "--entities",
            default="",
            help="Comma-separated entity types. Default: every entity on the rail.",
        )
        parser.add_argument(
            "--against",
            default="",
            help="A peer's digest string (as printed by this command) to compare against.",
        )

    def handle(self, *args, **options):
        from apps.schools.models import School
        from apps.sync_engine import parity

        slug = (options.get("school") or "").strip()
        if slug:
            school = School.objects.filter(slug=slug).first()  # tenant-isolation-allow: operator-diagnostic-resolves-the-named-school-explicitly
            if school is None:
                self.stderr.write(self.style.ERROR(f"no school with slug {slug!r}"))
                return sys.exit(1)
        else:
            schools = list(School.objects.all()[:2])  # tenant-isolation-allow: operator-diagnostic-detects-single-tenant-box-before-scoping
            if len(schools) != 1:
                self.stderr.write(
                    self.style.ERROR(
                        "this deployment serves more than one school; pass --school <slug>"
                    )
                )
                return sys.exit(1)
            school = schools[0]

        if not parity.enabled():
            self.stderr.write(
                self.style.WARNING(
                    "RMC_SYNC_PARITY_ENABLED is off, so the digest below is informational "
                    "only — no cycle will compute or act on it."
                )
            )

        entities = [e.strip().lower() for e in (options.get("entities") or "").split(",") if e.strip()]
        digests = parity.parity_digests(school, entities=entities or None)
        if not digests:
            self.stderr.write(self.style.ERROR("no digests could be computed"))
            return sys.exit(1)

        encoded = parity.encode_digests(digests)
        self.stdout.write(f"school: {school.slug}")
        self.stdout.write(f"entities: {len(digests)}")
        self.stdout.write(f"rows: {sum(int(d.get('n') or 0) for d in digests.values())}")
        self.stdout.write("")
        self.stdout.write(encoded)

        against = (options.get("against") or "").strip()
        if not against:
            self.stdout.write("")
            self.stdout.write(
                "Run the same command on the peer and pass its digest back with --against."
            )
            return sys.exit(0)

        comparison = parity.compare_digests(digests, parity.decode_digests(against))
        self.stdout.write("")
        self.stdout.write(f"matched:  {len(comparison['matched'])}")
        self.stdout.write(f"drifted:  {len(comparison['drifted'])}")
        for entity_type in parity.rank_for_flush(comparison):
            d = comparison["detail"].get(entity_type) or {}
            self.stdout.write(
                self.style.WARNING(
                    f"  {entity_type}: here={d.get('local_rows')} there={d.get('remote_rows')} "
                    f"({d.get('kind')})"
                )
            )
        # An entity only one side knows about is reported but is NOT drift: that is a
        # version or registry difference between the two deployments, and re-pulling it
        # would repair nothing.
        for label, key in (("only here", "only_local"), ("only there", "only_remote")):
            if comparison[key]:
                self.stdout.write(f"{label}: {', '.join(comparison[key])}")

        if comparison["drifted"]:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(parity.describe(comparison)))
            return sys.exit(1)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("STATUS_MIRRORED — every shared entity agrees"))
        return sys.exit(0)
