"""Operator entry point for PASS 2 — the cryptographic source-vs-landed check.

``reconciliation.reconcile_bundle`` runs Pass 2 automatically and refuses to seal a
bundle that fails it, but that is the only caller: there was no way for an operator to
ASK "is this migration actually intact?" of a bundle that already sealed, or of one
sitting at APPLIED, or to run the check from a deploy script and have the exit code
mean something. This is that entry point.

Exit codes are three-valued on purpose, because "I proved it is broken" and "I could
not prove anything" are different answers and collapsing them is how a verifier starts
lying::

    0  verified — every compared source record matched its landed row
    1  DIVERGENCE — at least one record differs, is missing, or a domain matched none
    2  NOT VERIFIED — the pass could not run (no schema, unreadable source, error)

Reading the RIGHT schema
------------------------
``MigrationBundle`` is in SHARED_APPS, so it lives in the PUBLIC schema and is found
there. ``StudentProfile`` / ``Subject`` are in TENANT_APPS and live in a per-tenant
schema, of which public holds only a stale copy. A management command runs in public
by default, so a naive read here would compare the source against the stale copy and
could report a false clean — the worst outcome, since a clean reconcile purges the
encrypted source. Three things prevent that:

 1. the landed-row read happens inside ``schema_context(bundle.schema_name)``
    (``verification.verify_bundle_checksums``), never on the ambient connection;
 2. ``verify_bundle_checksums`` REFUSES to verify when ``schema_name`` is blank on a
    schema-per-tenant connection, rather than silently reading public;
 3. this command prints the schema it used, and cross-checks it against
    ``schema_binding.resolve_school_schema_name(school)`` — a bundle stamped with a
    schema the school no longer resolves to is reported, not verified.

Usage::

    python manage.py verify_migration_checksums --bundle 84
    python manage.py verify_migration_checksums --slug buea-campus --latest
    python manage.py verify_migration_checksums --slug buea-campus --all --json
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

EXIT_VERIFIED = 0
EXIT_DIVERGENCE = 1
EXIT_NOT_VERIFIED = 2


class Command(BaseCommand):
    help = (
        "PASS 2: re-read each source record from its encrypted artifact and each landed "
        "row from the tenant schema, compare them by SHA-256, and enumerate every "
        "divergence. Exits 1 on divergence, 2 when the check could not be run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--bundle", type=int, default=None, help="MigrationBundle pk to verify."
        )
        parser.add_argument(
            "--slug",
            default="",
            help="School slug or subdomain; use with --latest or --all.",
        )
        parser.add_argument(
            "--latest",
            action="store_true",
            help="With --slug: verify the most recent APPLIED/RECONCILED bundle.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="With --slug: verify every APPLIED/RECONCILED bundle.",
        )
        parser.add_argument(
            "--domain",
            action="append",
            default=None,
            help="Restrict to this canonical domain (repeatable).",
        )
        parser.add_argument(
            "--json", action="store_true", help="Emit the full report as JSON."
        )

    def handle(self, *args, **options):
        from apps.migration_cloud.models import BundleStatus, MigrationBundle
        from apps.migration_cloud.verification import (
            domains_with_checksum_verification,
            verify_bundle_checksums,
        )

        bundles = self._select_bundles(options, MigrationBundle, BundleStatus)
        domains = options.get("domain") or None
        if domains:
            known = domains_with_checksum_verification()
            unknown = sorted(set(domains) - known)
            if unknown:
                raise CommandError(
                    f"No checksum spec for domain(s) {unknown}. "
                    f"Checksummable domains: {sorted(known)}"
                )

        worst = EXIT_VERIFIED
        payloads = []
        for bundle in bundles:
            report = verify_bundle_checksums(bundle, domains=domains)
            payload = report.as_dict()
            payload["schema_name"] = getattr(bundle, "schema_name", "") or ""
            payload["schema_binding"] = self._schema_binding(bundle)
            payloads.append(payload)
            if not options["json"]:
                self._render(bundle, report, payload)
            worst = max(worst, self._exit_for(report))

        if options["json"]:
            self.stdout.write(json.dumps(payloads, indent=2, default=str))

        # A management command's return value is written to stdout by Django, so the
        # non-zero exit has to come from SystemExit. CommandError would print a
        # traceback-ish "Error:" line for what is a successful RUN with a bad RESULT.
        if worst != EXIT_VERIFIED:
            raise SystemExit(worst)

    # --- selection ---------------------------------------------------------

    def _select_bundles(self, options, MigrationBundle, BundleStatus):
        pk = options.get("bundle")
        slug = (options.get("slug") or "").strip()
        if pk is None and not slug:
            raise CommandError("Pass --bundle <pk>, or --slug <school> with --latest/--all.")
        if pk is not None:
            # tenant-isolation-allow: operator command addressing ONE bundle by its internal pk
            bundle = MigrationBundle.objects.filter(pk=pk).first()
            if bundle is None:
                raise CommandError(f"No MigrationBundle with pk={pk}")
            return [bundle]

        from apps.schools.models import School

        school = (
            School.objects.filter(slug=slug).first()
            or School.objects.filter(subdomain=slug).first()
        )
        if school is None:
            raise CommandError(f"No School with slug/subdomain={slug!r}")
        qs = MigrationBundle.objects.filter(  # tenant-isolation-allow: scoped by the resolved school
            school=school,
            status__in=(BundleStatus.APPLIED, BundleStatus.RECONCILED),
        ).order_by("-created_at")
        if options.get("all"):
            found = list(qs)
        elif options.get("latest"):
            found = list(qs[:1])
        else:
            raise CommandError("--slug needs --latest or --all.")
        if not found:
            raise CommandError(
                f"School {slug!r} has no APPLIED/RECONCILED bundle to verify."
            )
        return found

    def _schema_binding(self, bundle) -> str:
        """Whether the bundle's stamped schema still matches what the school resolves to."""
        school = getattr(bundle, "school", None)
        stamped = (getattr(bundle, "schema_name", "") or "").strip()
        if school is None:
            return "no_school"
        try:
            from apps.migration_cloud.schema_binding import resolve_school_schema_name

            resolved = (resolve_school_schema_name(school) or "").strip()
        except ImportError as exc:
            # ``resolve_school_schema_name`` is TOTAL by construction: each of its
            # three resolution attempts is individually guarded and it returns ""
            # rather than raising (see apps/migration_cloud/schema_binding.py). So
            # the only way this statement fails is the lazy import itself, and a
            # tuple wider than that would swallow a NameError in the resolver --
            # the exact defect class that already cost this repo a lander.
            return f"unresolved:{type(exc).__name__}"
        if not stamped and not resolved:
            return "single_schema"
        if stamped == resolved:
            return "match"
        return f"MISMATCH stamped={stamped!r} resolved={resolved!r}"

    # --- verdict -----------------------------------------------------------

    def _exit_for(self, report) -> int:
        """Map a report onto the three-valued exit code.

        Order matters: a proven divergence outranks an incomplete pass. If one domain
        diverged and another could not be read, the migration IS broken and the
        stronger answer is the true one.
        """
        if not report.ok:
            return EXIT_DIVERGENCE
        if not report.per_domain or any(d.source_error for d in report.per_domain):
            return EXIT_NOT_VERIFIED
        if report.unverifiable_domains:
            # Something in this bundle has no spec, so "verified" would overclaim.
            return EXIT_NOT_VERIFIED
        return EXIT_VERIFIED

    # --- output ------------------------------------------------------------

    def _render(self, bundle, report, payload) -> None:
        self.stdout.write(
            self.style.NOTICE(
                f"bundle={bundle.pk} school={getattr(bundle.school, 'slug', None)!r} "
                f"status={bundle.status} algorithm={report.algorithm}"
            )
        )
        self.stdout.write(
            f"  schema={payload['schema_name']!r} binding={payload['schema_binding']}"
        )

        for d in report.per_domain:
            if d.source_error:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {d.domain}: NOT VERIFIED — source unreadable ({d.source_error})"
                    )
                )
                continue
            # Every source record under a named bucket, and the buckets sum to the
            # total. A breakdown that does not close lets a refusal and a healthy row
            # wear the same shape, so the sum is printed and asserted, not implied.
            line = (
                f"  {d.domain} [{d.depth}]: {d.source_records} source = "
                f"{d.matched} matched + {d.divergent} divergent + "
                f"{d.missing_in_destination} missing + {d.unidentified} unidentified + "
                f"{d.unresolved_identity} unresolved-identity + "
                f"{d.ambiguous_destination} ambiguous-destination + "
                f"{d.skipped_over_cap} over-cap  (sum={d.bucketed})"
            )
            if not d.tally_closes:
                self.stdout.write(self.style.ERROR(line + "  << TALLY DOES NOT CLOSE"))
            elif d.divergent or d.missing_in_destination:
                self.stdout.write(self.style.ERROR(line))
            elif d.source_records and not d.matched:
                self.stdout.write(self.style.ERROR(line + "  << nothing matched"))
            else:
                self.stdout.write(self.style.SUCCESS(line))
            self.stdout.write(
                f"    comparable fields here: {d.comparable_fields or '(none)'}"
            )
            if d.depth == "presence":
                # Say it out loud. This domain has no payload column the lander copies
                # verbatim alongside its key, so the digest covers the key alone: it
                # proves the record REACHED the tenant under its own identity (which a
                # row count cannot), not that its values are right.
                self.stdout.write(
                    "    presence-only: no verbatim payload column here, so arrival "
                    "is proved but values are NOT"
                )
            for div in d.divergences:
                if div.kind == "missing_in_destination":
                    self.stdout.write(f"    MISSING  {div.identity!r}")
                    continue
                self.stdout.write(
                    f"    DIVERGE  {div.identity!r} "
                    f"source={div.source_digest[:12]} landed={div.landed_digest[:12]}"
                )
                for name, (src, landed) in sorted(div.field_diffs.items()):
                    self.stdout.write(
                        f"               {name}: source={src!r} landed={landed!r}"
                    )

        if report.total_presence_matched:
            self.stdout.write(
                f"  of {report.total_matched} matched, "
                f"{report.total_value_matched} had their VALUES proved and "
                f"{report.total_presence_matched} only their PRESENCE."
            )
        if report.unverifiable_domains:
            self.stdout.write(
                self.style.WARNING(
                    "  domains in this bundle with NO checksum spec (not verified, not "
                    f"cleared): {', '.join(report.unverifiable_domains)}"
                )
            )
        for note in report.notes:
            self.stdout.write(self.style.WARNING(f"  note: {note}"))

        verdict = self._exit_for(report)
        if verdict == EXIT_VERIFIED:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  VERIFIED — {report.total_matched}/{report.total_source_records} "
                    "records match their landed rows."
                )
            )
        elif verdict == EXIT_DIVERGENCE:
            self.stdout.write(
                self.style.ERROR(
                    f"  DIVERGENCE — {report.total_divergent} differing, "
                    f"{report.total_missing} missing. This migration is NOT proven."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "  NOT VERIFIED — the check could not cover this bundle; "
                    "absence of a divergence here is not evidence of integrity."
                )
            )
