"""One-shot edge bring-up — run the whole 7-step Edge Onboarding runbook end-to-end.

Executes the input-driven prep commands, runs a REAL validate() per step with
self-healing, and enforces the MANDATORY pre-offline sync gate. Prints a GO / NO-GO
banner; with --require-offline-ready it exits non-zero unless the box is certified
ready to go offline.

    # Full box bring-up from cloud artifacts:
    python manage.py edge_bringup --slug gilead-tech --country CM \
        --bundle /srv/rmc/gilead-tech.rmcbundle \
        --identity /srv/rmc/gilead-tech.rmcidentity \
        --brand /srv/rmc/gilead-tech.rmcbrand \
        --mint-credential --credential-user gilead_owner --require-offline-ready

    # Just re-verify an already-provisioned box (no writes):
    python manage.py edge_bringup --slug gilead-tech --no-prep

    # See the plan without doing anything:
    python manage.py edge_bringup --slug gilead-tech --bundle x.rmcbundle --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "One-shot edge bring-up: run prep + verification + the pre-offline sync gate."

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True, help="Box-side school slug.")
        parser.add_argument("--country", default="", help="ISO country code (for provisioning).")
        parser.add_argument("--owner-email", dest="owner_email", default="", help="Owner email for the shell import.")
        parser.add_argument("--bundle", default="", help="Path to the tenant SHELL .rmcbundle (imported with --fresh).")
        parser.add_argument(
            "--data-bundle",
            dest="data_bundle",
            default="",
            help="Path to the pk-preserving DATA .rmcbundle (import_tenant_bundle, never --fresh).",
        )
        parser.add_argument("--identity", default="", help="Path to the .rmcidentity bundle.")
        parser.add_argument("--brand", default="", help="Path to the .rmcbrand branding bundle.")
        parser.add_argument(
            "--skip-go-dark",
            dest="skip_go_dark",
            action="store_true",
            help=(
                "Stop after the dry sync gate. Skips the live round-trip and the "
                "go-dark checklist (steps 16-17), so the box CANNOT be reported as "
                "converged."
            ),
        )
        parser.add_argument("--mint-credential", action="store_true", help="Mint a per-box edge sync credential.")
        parser.add_argument("--credential-user", dest="credential_user", default="", help="Owner username for the minted credential.")
        parser.add_argument("--credential-days", dest="credential_days", type=int, default=365, help="Credential validity in days.")
        parser.add_argument("--no-prep", action="store_true", help="Skip prep commands; only verify + run the sync gate.")
        parser.add_argument("--skip-sync-gate", action="store_true", help="Skip the sync gate (box cannot be certified offline-ready).")
        parser.add_argument("--no-self-heal", action="store_true", help="Do not attempt self-healing of failing steps.")
        parser.add_argument("--dry-run", action="store_true", help="Print the plan and exit; make no changes.")
        parser.add_argument("--require-offline-ready", action="store_true", help="Exit non-zero unless the box is certified ready to go offline.")

    def handle(self, *args, **options):
        from apps.lifecycle.edge_bringup import (
            BringupInputs,
            plan_prep_actions,
            run_edge_bringup,
        )

        inputs = BringupInputs(
            slug=options["slug"].strip(),
            country=(options.get("country") or "").strip(),
            owner_email=(options.get("owner_email") or "").strip(),
            bundle_path=(options.get("bundle") or "").strip(),
            data_bundle_path=(options.get("data_bundle") or "").strip(),
            identity_path=(options.get("identity") or "").strip(),
            brand_path=(options.get("brand") or "").strip(),
            mint_credential=bool(options.get("mint_credential")),
            credential_user=(options.get("credential_user") or "").strip(),
            credential_days=int(options.get("credential_days") or 365),
        )

        if options["dry_run"]:
            self.stdout.write(self.style.MIGRATE_HEADING(f"Edge bring-up plan for '{inputs.slug}':"))
            actions = plan_prep_actions(inputs) if not options["no_prep"] else []
            if not actions:
                self.stdout.write("  (no prep actions — verification + sync gate only)")
            for i, a in enumerate(actions, 1):
                self.stdout.write(f"  {i}. {a['key']}: manage.py {a['cmd']} {' '.join(a['args'])}")
            self.stdout.write("  -> then: run_verification_suite + MANDATORY sync gate")
            return

        report = run_edge_bringup(
            inputs=inputs,
            do_prep=not options["no_prep"],
            do_sync_gate=not options["skip_sync_gate"],
            do_go_dark=not options["skip_go_dark"],
            self_heal=not options["no_self_heal"],
        )

        for entry in report["prep"]:
            mark = self.style.SUCCESS("OK") if entry["ok"] else self.style.ERROR("FAIL")
            self.stdout.write(f"  prep {entry['key']}: {mark} — {entry['detail']}")

        verification = report.get("verification") or {}
        for step in verification.get("steps", []):
            mark = self.style.SUCCESS("PASS") if step.get("ok") else self.style.ERROR("FAIL")
            self.stdout.write(f"  verify {step.get('key')}: {mark} — {step.get('detail')}")
        if report.get("healed"):
            self.stdout.write(self.style.WARNING(f"  self-healed: {', '.join(report['healed'])}"))

        if report.get("error"):
            self.stdout.write(self.style.ERROR(f"  error: {report['error']}"))

        gate = report.get("sync_gate")
        if report.get("gate_skipped"):
            self.stdout.write(self.style.WARNING("  sync gate: SKIPPED — box cannot be certified for offline until it runs."))
        elif gate is not None:
            mark = self.style.SUCCESS("CLEARED") if gate.get("cleared") else self.style.ERROR("NOT CLEARED")
            self.stdout.write(f"  sync gate: {mark} — {gate.get('detail')}")

        go_dark = report.get("go_dark") or {}
        if go_dark.get("attempted"):
            live = go_dark.get("live") or {}
            live_mark = self.style.SUCCESS("OK") if live.get("healed") else self.style.ERROR("NOT PROVEN")
            self.stdout.write(f"  live round-trip: {live_mark} — {live.get('detail')}")
            checklist = go_dark.get("checklist") or {}
            cl_mark = self.style.SUCCESS("CLEARED") if checklist.get("healed") else self.style.ERROR("NOT CLEARED")
            self.stdout.write(f"  go-dark checklist: {cl_mark} — {checklist.get('detail')}")
        elif go_dark:
            self.stdout.write(self.style.WARNING(f"  go-dark: {go_dark.get('detail')}"))

        if report.get("converged"):
            self.stdout.write(self.style.SUCCESS(
                "\n[GO] Verified, gate cleared, one live round-trip proven, go-dark "
                "checklist cleared. This box is safe to take offline."
            ))
        elif report["offline_ready"]:
            # Deliberately NOT a GO. The dry gate proves the operator is reachable
            # and the credential is accepted; it does not prove this box can complete
            # a round trip and come back. Telling somebody it is safe to unplug on
            # that evidence is the overclaim this line used to make.
            self.stdout.write(self.style.WARNING(
                "\n[HOLD] Verified and the sync gate cleared, but the go-dark checklist "
                "has not. The box works online. Do NOT take it offline until the lines "
                "above are green — read the go-dark detail for what is outstanding."
            ))
        else:
            self.stdout.write(self.style.ERROR("\n[NO-GO] Not certified for offline. Resolve the FAIL/NOT-CLEARED items above and re-run."))
        if options["require_offline_ready"] and not report["offline_ready"]:
            raise CommandError("edge_bringup: box is not offline-ready.")
