"""Probe box ↔ cloud sync connectivity (env + optional HTTP reachability)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.sync_engine.connectivity_probe import connectivity_snapshot, probe_cloud_http
from apps.sync_engine.edge_scheduler import run_edge_sync_now


class Command(BaseCommand):
    help = (
        "Print edge sync env wiring and optionally probe the cloud pull/push endpoints "
        "or run one dry sync cycle."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--http",
            action="store_true",
            help="Perform live HTTP probes against cloud download + upload endpoints.",
        )
        parser.add_argument(
            "--dry-sync",
            action="store_true",
            help="Run one dry edge sync cycle after env checks (no writes).",
        )

    def handle(self, *args, **options):
        snap = connectivity_snapshot()
        self.stdout.write("Edge sync connectivity snapshot:")
        for key in (
            "edge_sync_enabled",
            "deployment_profile",
            "operator_base",
            "operator_base_configured",
            "credential_configured",
            "school_slug_pin",
            "pull_endpoint",
            "upload_endpoint",
        ):
            self.stdout.write(f"  {key}: {snap.get(key)!r}")

        problems: list[str] = []
        if not snap.get("edge_sync_enabled"):
            problems.append(
                "Edge sync is off: "
                f"{snap.get('edge_sync_enabled_reason') or 'unknown reason'}. "
                "Pair the box (manage.py pair_box) or set RMC_EDGE_SYNC_ENABLED=1."
            )
        if not snap.get("operator_base_configured"):
            problems.append(
                "RMC_EDGE_OPERATOR_BASE is empty — set it to the TENANT host "
                "(e.g. https://gilead-tech.<your-domain>), not manager/marketing."
            )
        if not snap.get("credential_configured"):
            problems.append(
                "RMC_EDGE_CREDENTIAL is missing — mint on cloud: "
                "python manage.py mint_edge_credential --slug <school> --user <admin>"
            )

        if options.get("http"):
            probe = probe_cloud_http()
            self.stdout.write("\nHTTP probes:")
            for phase, row in (probe.get("probes") or {}).items():
                self.stdout.write(
                    f"  {phase}: status={row.get('status')} ok={row.get('ok')} "
                    f"detail={row.get('detail')!r}"
                )
            problems.extend(probe.get("problems") or [])

        if options.get("dry_sync"):
            if not snap.get("operator_base_configured") or not snap.get("credential_configured"):
                problems.append("--dry-sync skipped: operator base or credential not configured")
            else:
                self.stdout.write("\nDry sync cycle:")
                result = run_edge_sync_now(mode="dry")
                self.stdout.write(
                    f"  ok={result.get('ok')} pushed={result.get('pushed')} "
                    f"pulled={result.get('pulled')}"
                )
                for err in (result.get("errors") or []) if isinstance(result.get("errors"), list) else []:
                    problems.append(str(err))
                if result.get("error"):
                    problems.append(str(result.get("error")))

        seen = set()
        for msg in problems:
            if msg in seen:
                continue
            seen.add(msg)
            self.stderr.write(self.style.ERROR(f"FAIL  {msg}"))

        if problems:
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("\nprobe_edge_cloud_sync: OK"))
