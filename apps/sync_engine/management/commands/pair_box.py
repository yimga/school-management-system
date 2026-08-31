"""Pair this box with its cloud tenant — the on-box half, from a shell.

    python manage.py pair_box                  # open a request and show the code
    python manage.py pair_box --wait           # ...then block until approved
    python manage.py pair_box --status         # what is this box bound to?
    python manage.py pair_box --unpair         # forget the binding (needs --yes)

Running a command on the host is itself a credential: whoever can do it can already
read the school's database. That is why ``--unpair`` is available here and nowhere on
the LAN — re-pairing a sealed box demands either an authenticated admin session or
physical/shell access, never merely being on the network.

ONE BOX PER SCHOOL. The cloud refuses to bind a second box to a school that already
has one, and says so here rather than in a logfile: the engine's echo-suppression is
device-blind, so a second box would be silently starved of the first one's changes
instead of failing. Re-pairing the SAME box (same ``RMC_EDGE_DEVICE_ID``, which
defaults to ``edge-<slug>``) is not a second box and is always allowed. To move a
school onto different hardware, release the old box on the cloud first — revoke its
device in the operator console — then pair the new one. See
``docs/EDGE_ONE_BOX_PER_SCHOOL_2026_08_31.md``.
"""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Pair this sovereign box with its cloud tenant using a displayed code."

    def add_arguments(self, parser):
        parser.add_argument(
            "--wait",
            action="store_true",
            help="Block and poll until the request is approved, denied, or expires.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=900,
            help="Seconds to wait with --wait (default 900). The request itself lives much longer.",
        )
        parser.add_argument("--status", action="store_true", help="Show the current binding and exit.")
        parser.add_argument("--unpair", action="store_true", help="Forget the stored binding.")
        parser.add_argument("--yes", action="store_true", help="Confirm --unpair without prompting.")
        parser.add_argument("--base", default="", help="Override the cloud base URL for this attempt.")
        parser.add_argument(
            "--slug",
            default="",
            help=(
                "The school this box serves. Optional — the box resolves it from its "
                "binding or RMC_EDGE_SCHOOL_SLUG — but naming it here lets a technician "
                "pair a box whose environment names neither, and makes a copy-pasted "
                "runbook command unambiguous about WHICH school it adopts."
            ),
        )
        parser.add_argument(
            "--claim",
            default="",
            help=(
                "Redeem a claim ticket minted on the cloud, so the box adopts itself "
                "with no approval step. Single use."
            ),
        )

    def handle(self, *args, **options):
        from apps.sync_engine import pairing_client
        from apps.sync_engine.edge_binding import binding_summary, clear_binding

        if options["status"]:
            return self._print_status(binding_summary(), pairing_client.current_request())

        if options["unpair"]:
            if not options["yes"]:
                raise CommandError(
                    "Refusing to unpair without --yes. This box will stop syncing until "
                    "it is paired again."
                )
            removed = clear_binding()
            pairing_client.clear_state()
            self.stdout.write(
                self.style.WARNING("Binding cleared. This box is no longer paired.")
                if removed
                else "No binding was stored; nothing to clear."
            )
            return

        summary = binding_summary()
        if summary["paired"]:
            self.stdout.write(
                self.style.WARNING(
                    f"This box is already paired to {summary['school_slug'] or '?'} "
                    f"at {summary['operator_base']}.\n"
                    "Run with --unpair --yes first if you really mean to re-pair it."
                )
            )
            return

        result = pairing_client.start(
            base=options["base"],
            claim_ticket=options["claim"],
            school_slug=options["slug"],
        )
        if not result.get("ok"):
            raise CommandError(result.get("message") or result.get("error") or "pairing failed")

        if options["claim"] and result.get("claim_ticket_error"):
            self.stdout.write(self.style.ERROR(
                "That claim ticket was not accepted (invalid, already used, expired, or "
                "issued for a different school). A pairing request was still opened, so "
                "it can be approved normally instead."
            ))
        if result.get("pre_approved"):
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(
                "Claim ticket accepted - this box is pre-approved and will collect "
                "its credential on the next poll. No administrator action is needed."
            ))

        code = result["user_code"]
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"    Pairing code:  {code}"))
        self.stdout.write(f"    Expires:       {result.get('expires_at', '?')}")
        self.stdout.write(f"    Cloud:         {result.get('operator_base', '?')}")
        self.stdout.write("")
        if not result.get("school_resolved", True):
            self.stdout.write(
                self.style.WARNING(
                    "The cloud does not recognise this box's school slug. The request "
                    "was still created, but only platform staff will be able to see it. "
                    "Check RMC_EDGE_SCHOOL_SLUG."
                )
            )
        self.stdout.write(
            "Sign in to the school's cloud Sync Center and enter this code to approve.\n"
            "The code alone grants nothing — approval happens in an authenticated session."
        )

        if not options["wait"]:
            self.stdout.write("\nRun `manage.py pair_box --wait` (or leave the box running) to collect the credential.")
            return

        self._wait(pairing_client, int(options["timeout"]), int(result.get("poll_interval_seconds") or 5))

    def _wait(self, pairing_client, timeout: int, interval: int) -> None:
        self.stdout.write(f"\nWaiting up to {timeout}s for approval…")
        deadline = time.monotonic() + max(1, timeout)
        while time.monotonic() < deadline:
            outcome = pairing_client.poll()
            status = outcome.get("status")
            if status == "paired":
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\nPaired with {outcome.get('school_name') or outcome.get('school_slug')}. "
                        "Sync will start on the next cycle."
                    )
                )
                return
            if status in ("denied", "expired", "already_redeemed", "unknown"):
                raise CommandError(
                    f"Pairing ended: {status}. {outcome.get('reason') or ''}".strip()
                )
            if status == "unreachable":
                self.stdout.write(self.style.WARNING(f"  cloud unreachable ({outcome.get('message', '')}) — retrying"))
            time.sleep(max(1, interval))
        self.stdout.write(
            self.style.WARNING(
                "\nStill waiting for approval. The request stays open — re-run "
                "`manage.py pair_box --wait` or leave the box running."
            )
        )

    def _print_status(self, summary: dict, pending: dict) -> None:
        self.stdout.write("Edge cloud binding")
        self.stdout.write(f"  paired:        {summary['paired']}")
        self.stdout.write(f"  sealed:        {summary['sealed']}")
        self.stdout.write(f"  cloud:         {summary['operator_base'] or '-'}")
        self.stdout.write(f"  school:        {summary['school_slug'] or '-'}")
        self.stdout.write(f"  source:        {summary['source']}")
        self.stdout.write(f"  paired at:     {summary['paired_at'] or '-'}")
        self.stdout.write(f"  cred expires:  {summary['credential_expires_at'] or '-'}")
        if pending:
            self.stdout.write("")
            self.stdout.write(f"Pending pairing request: {pending.get('user_code')} (expires {pending.get('expires_at')})")
