"""What an import will land on THIS box, and which of it can never leave.

    python manage.py edge_import_reachability --bundle 84
    python manage.py edge_import_reachability --bundle 84 --json
    python manage.py edge_import_reachability --bundle 84 --accept library --accept health

WHY A COMMAND. An appliance is operated from a shell far more often than from a
browser, and the two postures this guard supports each need an operator affordance:

  * READ. Ask, before pressing anything, what a mapped bundle would strand here. It
    is the same assessment the Review & Import page shows, from the same resolver, so
    the two cannot disagree.

  * ACCEPT. Record the deliberate decision that this box is the system of record for
    a domain. That is a legitimate choice -- a school with no reliable uplink wants
    its library on the appliance -- and the point of this work is that it be CHOSEN
    rather than discovered later. ``--accept`` writes the domain, the time and the
    actor onto the bundle, and under the ``refuse`` policy it is what lets the import
    through.

Accepting is per DOMAIN and per BUNDLE, and additive: accepting ``library`` does not
accept ``health``, and a domain nobody has ruled on keeps warning. A deployment-wide
switch would let one decision, made once, silence every future import of every domain
for every school.

READ-ONLY without ``--accept``.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Report (and optionally accept) the records a Migration Cloud import would "
        "strand on this box."
    )

    def add_arguments(self, parser):
        parser.add_argument("--bundle", type=int, required=True,
                            help="MigrationBundle id to assess.")
        parser.add_argument("--json", action="store_true",
                            help="Machine-readable output.")
        parser.add_argument(
            "--accept", action="append", default=[], metavar="DOMAIN",
            help=(
                "Record that this box is the system of record for DOMAIN on this "
                "bundle. Repeatable. Writes to the bundle."
            ),
        )
        parser.add_argument("--actor", default="",
                            help="Who is accepting; recorded alongside the decision.")

    def handle(self, *args, **options):
        from apps.migration_cloud import edge_reachability as er
        from apps.migration_cloud.models import MigrationBundle

        bundle = MigrationBundle.objects.filter(pk=options["bundle"]).first()  # tenant-isolation-allow: operator-supplied bundle id on a single-school appliance
        if bundle is None:
            raise CommandError("No bundle with id %s on this deployment." % options["bundle"])

        accepted_now: list[str] = []
        if options["accept"]:
            report = er.preview_for_bundle(bundle)
            known = {d.domain for d in report.stranding_domains}
            unknown = [d for d in options["accept"] if d not in known]
            if unknown:
                # Refuse rather than record a decision about something this bundle
                # does not do. An acknowledgement for a domain that is not in the
                # import is not harmless: it reads later as a decision somebody made
                # about this data, and it silences nothing.
                raise CommandError(
                    "This bundle does not strand %s. It strands: %s"
                    % (", ".join(sorted(unknown)), ", ".join(sorted(known)) or "nothing")
                )
            er.acknowledge(bundle, options["accept"], actor=options["actor"])
            bundle.refresh_from_db()
            accepted_now = sorted(options["accept"])

        report = er.preview_for_bundle(bundle)
        payload = report.to_dict()
        payload["bundle"] = bundle.pk
        payload["accepted_this_run"] = accepted_now

        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        w = self.stdout.write
        w("")
        w("IMPORT REACHABILITY -- bundle %s" % bundle.pk)
        w("  edge appliance ............... %s" % ("yes" if report.is_edge else "no"))
        w("  policy ....................... %s" % report.policy)
        if not report.is_edge:
            w("")
            w("  This is not a sovereign box. Everything an import writes here is on the")
            w("  cloud already, so nothing can be stranded.")
            return
        if report.rail_unavailable:
            # Never print a clean-looking zero for a check that did not run.
            w(self.style.ERROR(
                "  THE SYNC RAIL COULD NOT BE READ on this deployment, so no assessment "
                "was possible. This is a check that did not run, not a clean result."
            ))
            return
        if not report.has_finding:
            w("")
            w("  Every model this import writes is carried by the sync rail.")
            return

        if accepted_now:
            w("  accepted this run ............ %s" % ", ".join(accepted_now))
        w("")
        w(self.style.WARNING("  " + report.operator_message()))
        w("")
        w("%-24s %8s %-10s %s" % ("DOMAIN", "ROWS", "ACCEPTED", "CANNOT LEAVE"))
        for d in report.stranding_domains:
            rows = str(d.rows) if d.counts_are_complete else ">=%d" % d.rows
            w("%-24s %8s %-10s %s" % (
                d.domain, rows, "yes" if d.acknowledged else "-",
                ", ".join(d.stranded),
            ))
        if not report.counts_are_complete:
            w("")
            w(self.style.ERROR(
                "  %d file(s) could not be row-counted, so every ROWS figure above is a "
                "FLOOR, not a total." % report.artifacts_without_row_count
            ))
        w("")
        if report.acknowledged:
            w("  Every stranding domain has been accepted. This import will proceed.")
        else:
            w("  Accept the domains this box should own with:")
            w("    manage.py edge_import_reachability --bundle %s --accept <domain> "
              "--actor <you>" % bundle.pk)
