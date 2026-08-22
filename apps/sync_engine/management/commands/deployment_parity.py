"""Say what this deployment is running, and how it differs from the other side.

    python manage.py deployment_parity
    python manage.py deployment_parity --json
    python manage.py deployment_parity --against https://gilead-tech.runmycampus.com
    python manage.py deployment_parity --against <base> --strict     # exit 1 on drift

WHY THIS EXISTS. ``edge_sync`` reconciles ROWS and says nothing about CODE. On
2026-08-22 a box and a cloud were both serving bugs that ``main`` had fixed on the
19th and the 20th; the fixes were never deployed because CI had not started a job
since the 15th. Everyone was looking at the product. The answer was in the pipeline,
and no command in the system could have said so.

WHAT ``--against`` CAN SEE TODAY. The public ``/-/version/`` endpoint, which reports
the commit, build time, app version and environment. That is the MUST_MATCH dimension
that actually caused this incident, and it needs no new endpoint and no new auth
surface. Schema and settings parity are computed for the LOCAL side and reported, but
cannot be compared remotely until a deployment exposes its fingerprint on the
authenticated edge channel -- see docs/EDGE_UPDATE_PIPELINE.md. This command says so
rather than pretending the comparison was complete.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.core.management.base import BaseCommand

from apps.sync_engine.deployment_parity import compare, local_fingerprint

VERSION_PATH = "/-/version/"


class Command(BaseCommand):
    help = "Report this deployment's code/schema/config fingerprint and diff it against another."

    def add_arguments(self, parser):
        parser.add_argument(
            "--against",
            default="",
            help="Base URL of the other deployment (the cloud, from a box).",
        )
        parser.add_argument("--json", action="store_true", help="Machine-readable output.")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit 1 when any DRIFT or COLLISION is found.",
        )
        parser.add_argument("--timeout", type=float, default=10.0)

    def handle(self, *args, **options):
        local = local_fingerprint().as_dict()
        remote: dict = {}
        remote_error = ""

        base = (options["against"] or "").strip().rstrip("/")
        if base:
            url = f"{base}{VERSION_PATH}"
            try:
                with urllib.request.urlopen(url, timeout=options["timeout"]) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                # /-/version/ reports the code dimension only; say so explicitly rather
                # than letting empty dimensions read as "no drift".
                remote = {"code": payload, "schema": {}, "assets": {}, "settings": {}}
            except (urllib.error.URLError, ValueError, OSError) as exc:
                remote_error = f"{type(exc).__name__}: {exc}"

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "local": local,
                        "remote": remote,
                        "remote_error": remote_error,
                        "findings": [
                            f.__dict__ for f in (compare(local, remote) if remote else [])
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return

        self.stdout.write(self.style.MIGRATE_HEADING("THIS DEPLOYMENT"))
        for key, value in sorted(local["code"].items()):
            self.stdout.write(f"  code    {key:<32} {value}")
        for key, value in sorted(local["assets"].items()):
            self.stdout.write(f"  assets  {key:<32} {value}")
        schema = local["schema"]
        if schema.get("available"):
            self.stdout.write(
                f"  schema  {'applied_migrations':<32} {schema['total']} "
                f"across {len(schema['per_app'])} apps (digest {schema['digest']})"
            )
        else:
            self.stdout.write(
                f"  schema  {'applied_migrations':<32} unavailable: {schema.get('reason')}"
            )

        if not base:
            self.stdout.write(
                "\nPass --against <base-url> to diff this against the other side."
            )
            return

        if remote_error:
            self.stdout.write(self.style.ERROR(f"\nCould not reach {base}{VERSION_PATH}"))
            self.stdout.write(f"  {remote_error}")
            # Unreachable is not "in parity". Say which one it is.
            return 1 if options["strict"] else None

        findings = compare(local, remote)
        defects = [f for f in findings if f.is_defect]
        self.stdout.write(self.style.MIGRATE_HEADING(f"\nAGAINST {base}"))
        if not findings:
            self.stdout.write(self.style.SUCCESS("  no differences in the reported dimensions"))
        for finding in findings:
            line = f"  [{finding.verdict:<9}] {finding.dimension}.{finding.key}: {finding.detail}"
            if finding.verdict == "DRIFT":
                self.stdout.write(self.style.ERROR(line))
            elif finding.verdict == "COLLISION":
                self.stdout.write(self.style.ERROR(line))
            elif finding.verdict == "UNKNOWN":
                self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(line)

        self.stdout.write(
            "\nNOTE: /-/version/ carries the CODE dimension only. Schema and settings "
            "parity are shown for this side but not compared -- that needs the "
            "authenticated edge channel (docs/EDGE_UPDATE_PIPELINE.md)."
        )
        if defects and options["strict"]:
            raise SystemExit(1)
