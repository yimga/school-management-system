"""Pull the operator's changed records DOWN to the sovereign edge box (Tier 3, box side).

The downstream half the outbox docstring called "a separate poll, out of scope." Edge-
initiated / inbound-pull: the box GETs a signed delta bundle of everything the operator
changed since a cursor and applies it locally, stamping the sync provenance so the next
``post_edge_outbox`` run does NOT echo the just-pulled rows back up.

    python manage.py pull_edge_inbox --slug gilead-tech \
        --operator-base https://gilead-tech.runmycampus.com \
        --pull-cursor-file var/edge-pull.cursor   # token from env RMC_EDGE_CREDENTIAL

Queue-and-forward semantics mirror the outbox: the pull cursor advances ONLY on a
successful, applied bundle, so an offline run leaves the cursor put and the next run
re-pulls the same window (apply is idempotent — updates by pk, inserts upsert by
(school, client_offline_id)). Reachability: the box calls OUT to the operator, so no
inbound port is opened on a box behind a private LAN.
"""
from __future__ import annotations

import urllib.error
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from apps.sync_engine.cloud_endpoints import cloud_endpoint
from django.utils.dateparse import parse_datetime


class Command(BaseCommand):
    help = "Pull the operator's recent changes DOWN and apply them on the edge box."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="", help="School slug.")
        parser.add_argument("--school-id", dest="school_id", default="", help="School UUID (alternative to --slug).")
        parser.add_argument("--endpoint", default="", help="Full URL of the operator download endpoint (overrides --operator-base).")
        parser.add_argument("--operator-base", dest="operator_base", default="", help="Operator base URL; the download path is appended.")
        parser.add_argument("--token", default="", help="Edge bearer credential (default: env RMC_EDGE_CREDENTIAL).")
        parser.add_argument("--since", default="", help="ISO-8601 cursor override (default: read --pull-cursor-file).")
        parser.add_argument("--pull-cursor-file", dest="cursor_file", default="", help="Path to read/persist the PULL cursor (kept separate from the push cursor).")
        parser.add_argument("--entities", default="", help="Comma-separated entity types (default: all supported).")
        parser.add_argument("--as-user", dest="as_user", default="", help="Email of the local principal to apply as (default: the school owner / a superuser).")
        parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds.")

    def handle(self, *args, **options):
        from apps.schools.models import School
        from apps.sync_engine import edge_outbox
        from apps.sync_engine.edge_inbox import apply_pulled_bundle

        slug = (options.get("slug") or "").strip()
        school_id = (options.get("school_id") or "").strip()
        if not slug and not school_id:
            raise CommandError("Provide --slug or --school-id.")
        school = (
            School.objects.filter(slug=slug).first()
            if slug
            else School.objects.filter(pk=school_id).first()
        )
        if school is None:
            raise CommandError(f"School not found ({slug or school_id}).")

        # --token wins (an operator testing a specific credential), then the paired
        # binding, then the environment for a box that was never paired.
        from apps.sync_engine.edge_binding import edge_credential

        token = (options.get("token") or "").strip() or edge_credential()
        if not token:
            raise CommandError(
                "No credential: pair this box (manage.py pair_box), pass --token, "
                "or set RMC_EDGE_CREDENTIAL."
            )

        endpoint = (options.get("endpoint") or "").strip()
        if not endpoint:
            from apps.sync_engine.edge_binding import operator_base

            base = (options.get("operator_base") or "").strip() or operator_base()
            if not base:
                raise CommandError(
                    "No cloud address: pair this box (manage.py pair_box), or pass "
                    "--endpoint / --operator-base."
                )
            endpoint = cloud_endpoint(base, "api:sync-bundle-download")

        cursor_file = (options.get("cursor_file") or "").strip()
        raw_since = (options.get("since") or "").strip()
        if not raw_since and cursor_file and Path(cursor_file).exists():
            raw_since = Path(cursor_file).read_text(encoding="utf-8").strip()
        since = None
        if raw_since:
            since = parse_datetime(raw_since)
            if since is None:
                raise CommandError(f"Could not parse cursor {raw_since!r} (use ISO-8601).")

        user = self._resolve_user(school, (options.get("as_user") or "").strip())
        if user is None:
            raise CommandError("No local principal to apply as (pass --as-user or provision a school owner / superuser).")

        entities = [e.strip().lower() for e in (options.get("entities") or "").split(",") if e.strip()]

        # G8 parity. This command is the pull half of ``edge_sync_cycle``, which is what a
        # box scheduled by CRON runs — a different path from ``sync_runner.run_sync_cycle``
        # (beat / in-process scheduler / autosync middleware / "Sync now"), which keeps its
        # cursors in the database rather than in a file. Without this, a cron-scheduled box
        # would never sweep, and parity would be a feature that silently depends on which
        # scheduler the operator happened to choose.
        #
        # REPORTS, never repairs: this is a single-shot operator command with a file
        # cursor, and a command that quietly re-pulled whole entities would be a surprise.
        # The remediation is printed as the exact command to run.
        parity_header = ""
        try:
            from apps.sync_engine import parity

            if parity.due(school):
                parity_header = parity.encode_digests(parity.parity_digests(school))
        except Exception:  # noqa: BLE001 — a sweep must never cost the box its pull
            parity_header = ""

        collected: dict = {}
        try:
            status, body, high_water = edge_outbox.pull_bundle(
                endpoint,
                token,
                since=since,
                entities=entities,
                timeout=float(options.get("timeout") or 30.0),
                collect=collected,
                parity=parity_header,
            )
        except (urllib.error.URLError, OSError) as exc:
            # Offline / unreachable: cursor stays put so the next run re-pulls this window.
            self.stderr.write(self.style.WARNING(
                f"Operator unreachable ({exc}); pull cursor NOT advanced (will retry next run)."
            ))
            return

        if status != 200:
            raise CommandError(
                f"Operator rejected the pull (HTTP {status}): {body[:200]!r}. Cursor NOT advanced."
            )

        result = apply_pulled_bundle(school, user, body, origin="cloud-pull")
        if not result.get("ok"):
            raise CommandError(
                f"Pulled bundle failed verification: {result.get('errors')}. Cursor NOT advanced."
            )

        self.stdout.write(self.style.SUCCESS(
            f"Pulled {result['received']} row(s) -> applied {result['applied']}, "
            f"created {result['created']}, upserted {result['upserted']}, "
            f"conflicts {result['conflicts']}, malformed {result['malformed']}."
        ))
        # Advance the pull cursor ONLY on a successfully applied bundle. An empty pull
        # (no changes) has no high-water — leave the cursor where it is.
        if cursor_file and high_water:
            Path(cursor_file).write_text(high_water, encoding="utf-8")
            self.stdout.write(f"Pull cursor advanced -> {high_water}")

        # G8: the cloud's answer to this run's digest. Named loudly — the two sides
        # holding different records is a bigger fact than how many rows this pull carried,
        # and an operator who is not told cannot know the box was serving stale data.
        drifted = collected.get("parity_drift") or []
        if drifted:
            advice = (collected.get("parity_advice") or "").strip()
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                advice or f"PARITY DRIFT: {', '.join(drifted)}"
            ))
            self.stdout.write(
                "This box disagrees with the cloud on the entities above. Repair each by "
                "re-pulling it WHOLE (no cursor, so the full entity is offered):"
            )
            for entity_type in drifted:
                self.stdout.write(
                    f"  python manage.py pull_edge_inbox --slug {school.slug} "
                    f"--entities {entity_type} --since 1970-01-01T00:00:00+00:00"
                )

    @staticmethod
    def _resolve_user(school, as_user_email: str):
        """Local principal to apply pulled rows as: explicit --as-user, else the school
        owner, else any superuser. The box applies authoritative operator data, so an
        admin-like principal is required by the apply path's per-entity permission check.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        if as_user_email:
            return User.objects.filter(email__iexact=as_user_email).first()
        # School owner via membership, if the platform exposes one.
        try:
            from apps.schools.models import SchoolMembership

            owner = (
                SchoolMembership.objects.filter(school=school, role="owner")
                .select_related("user")
                .first()
            )
            if owner is not None and getattr(owner, "user", None) is not None:
                return owner.user
        except Exception:  # noqa: BLE001 — membership model shape varies; fall through
            pass
        return User.objects.filter(is_superuser=True).order_by("pk").first()
