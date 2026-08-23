"""Read, issue and switch a sovereign box's TLS posture.

    python manage.py edge_tls                       # what is the box doing today
    python manage.py edge_tls --issue-selfsigned    # mint a box CA + leaf
    python manage.py edge_tls --print-caddyfile     # the terminator config for this mode
    python manage.py edge_tls --plan-to ca          # the ordered steps to switch
    python manage.py edge_tls --json                # machine-readable, for the runbook

The mode itself lives in ``deploy/selfhost/.env`` (``RMC_EDGE_TLS_MODE``) because
Django reads the flags that follow from it while settings load, before any database
connection exists. This command is the operator's window onto that decision: it says
what the box resolved, whether the certificate on disk actually covers the addresses
people type, and exactly what to do to move to a different mode -- in either
direction. See ``apps/schools/edge_tls.py`` and ``docs/EDGE_TLS_RUNBOOK.md``.
"""
from __future__ import annotations

import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.schools import edge_tls


class Command(BaseCommand):
    help = "Show, issue or plan a transition for the sovereign box's TLS certificate."

    def add_arguments(self, parser):
        parser.add_argument(
            "--issue-selfsigned",
            action="store_true",
            help="Mint a box-local CA and a leaf certificate for the names this box answers at.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=edge_tls.DEFAULT_SELF_SIGNED_DAYS,
            help=f"Leaf validity in days (default {edge_tls.DEFAULT_SELF_SIGNED_DAYS}).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite an existing certificate. Without this, issuing is refused.",
        )
        parser.add_argument(
            "--print-caddyfile",
            action="store_true",
            help="Print the TLS terminator config for the resolved mode.",
        )
        parser.add_argument(
            "--plan-to",
            default="",
            help="Print the ordered steps to move this box to another mode.",
        )
        parser.add_argument(
            "--export-ca",
            default="",
            metavar="PATH",
            help=(
                "Write the box CA (certificate + private key) to PATH as encrypted "
                "PKCS#12. The only artefact on this box that cannot be regenerated -- "
                "take it before the box moves or is rebuilt."
            ),
        )
        parser.add_argument(
            "--import-ca",
            default="",
            metavar="PATH",
            help=(
                "Restore a box CA exported earlier. Run BEFORE --issue-selfsigned on "
                "replacement hardware so devices keep their trust."
            ),
        )
        parser.add_argument(
            "--ensure",
            action="store_true",
            help=(
                "Reconcile the certificate with where this box actually lives: issue if "
                "missing, reissue if it no longer covers an address the box answers at "
                "or is near expiry, otherwise do nothing. Reuses the CA, so a self-heal "
                "is invisible to every device. Safe to run on every start."
            ),
        )
        parser.add_argument(
            "--plan-relocation",
            action="store_true",
            help="Print the ordered steps to move this box, for its current mode.",
        )
        parser.add_argument(
            "--changed",
            default="",
            help=(
                "What the move changes, comma separated: "
                + ",".join(edge_tls.RELOCATION_CHANGES)
                + ". Used with --plan-relocation."
            ),
        )
        parser.add_argument("--json", action="store_true", help="Machine-readable output.")

    # -- helpers ---------------------------------------------------------------

    def _facts(self) -> dict:
        resolution = edge_tls.resolve_mode()
        cert_path, key_path, ca_path = edge_tls.certificate_paths()
        dns, ips = edge_tls.san_candidates(
            allowed_hosts=list(getattr(settings, "ALLOWED_HOSTS", []) or [])
        )
        facts = edge_tls.inspect_certificate(cert_path)
        derived = edge_tls.derived_security_flags(resolution.mode)
        actual = {
            name: getattr(settings, name, None) for name in derived
        }
        debug = bool(getattr(settings, "DEBUG", False))
        return {
            "debug": debug,
            "mode": resolution.mode,
            "mode_source": resolution.source,
            "mode_raw": resolution.raw,
            "mode_error": resolution.error,
            "serves_https": resolution.serves_https,
            "summary": edge_tls.MODE_SUMMARY[resolution.mode],
            "cert_path": cert_path,
            "key_path": key_path,
            "ca_path": ca_path,
            "key_present": bool(key_path and os.path.exists(key_path)),
            "dns_names": dns,
            "ip_addresses": ips,
            "certificate": {
                "exists": facts.exists,
                "readable": facts.readable,
                "subject": facts.subject,
                "issuer": facts.issuer,
                "self_signed": facts.self_signed,
                "dns_names": list(facts.dns_names),
                "ip_addresses": list(facts.ip_addresses),
                "not_after": facts.not_after,
                "days_remaining": facts.days_remaining,
                "missing_names": facts.covers(dns, ips) if facts.readable else [],
                "error": facts.error,
            },
            "derived_flags": derived,
            "active_flags": actual,
            # At DEBUG=1 Django's own `and not DEBUG` forces all three booleans off
            # and zeroes HSTS. That is correct and universal, so it is not drift --
            # reporting it as drift on every developer machine is how a real
            # disagreement on a real box gets ignored.
            "flags_agree": debug or all(actual.get(k) == v for k, v in derived.items()),
        }

    # -- entry point -----------------------------------------------------------

    def _passphrase(self) -> bytes:
        raw = os.environ.get(edge_tls.ENV_CA_PASSPHRASE, "")
        if not raw:
            raise CommandError(
                f"Set {edge_tls.ENV_CA_PASSPHRASE} in the environment first. This bundle "
                "carries the CA private key, so it is deliberately not accepted as a "
                "command-line flag: a command line is visible in `ps`, in shell history "
                "and in docker's own event log."
            )
        return raw.encode("utf-8")

    def _ensure(self, facts: dict, options) -> None:
        """Reconcile the certificate with where the box actually lives.

        Cheap and idempotent on purpose: this is meant to run on every container
        start, so the common case (nothing changed) must cost one file read and
        print one line.
        """
        if facts["mode"] != edge_tls.MODE_SELF_SIGNED:
            # Saying nothing here would be the wrong kind of quiet: an operator who
            # wired --ensure into startup deserves to know why it is not acting.
            self.stdout.write(
                f"mode is {facts['mode']}: nothing for --ensure to reconcile. It manages "
                "only a box-minted (selfsigned) certificate -- a provided pair is "
                "replaced by whoever issues it, and acme renews itself."
            )
            return

        directory = os.path.dirname(facts["cert_path"]) or edge_tls.DEFAULT_DIR
        dns, ips = edge_tls.effective_addresses(
            allowed_hosts=list(getattr(settings, "ALLOWED_HOSTS", []) or [])
        )
        if not dns and not ips:
            raise CommandError(
                "No addresses to assert. Set "
                f"{edge_tls.ENV_HOSTNAMES}, fix ALLOWED_HOSTS, or set "
                f"{edge_tls.ENV_TRUST_LOCAL}=1 to let the box use the addresses it "
                "currently holds."
            )

        result = edge_tls.ensure_certificate(
            directory,
            dns,
            ips,
            days=options["days"],
            renew_before_days=edge_tls.renew_before_days(),
        )
        if options["json"]:
            self.stdout.write(json.dumps(result, indent=2))
            if result["action"] == edge_tls.ACTION_REFUSED:
                raise CommandError(result["reason"])
            return

        action = result["action"]
        if action == edge_tls.ACTION_NOOP:
            self.stdout.write(f"no change needed -- {result['reason']}")
            return
        if action == edge_tls.ACTION_REFUSED:
            raise CommandError(
                result["reason"]
                + "\n  Refusing to reissue: a certificate minted against a wrong clock is "
                "genuinely invalid, which turns a recoverable clock problem into a "
                "certificate problem as well. Fix the time first."
            )

        self.stdout.write(
            self.style.SUCCESS(f"{action}: {result['reason']}")
        )
        self.stdout.write("  names  " + ", ".join([*result["dns_names"], *result["ip_addresses"]]))
        if result["reused_ca"]:
            self.stdout.write(
                "  box CA reused -- devices that trust it need nothing done to them."
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "  a NEW box CA was created. Every device must install it again. "
                    "This only happens when ca.key is missing or expired; if you have a "
                    "bundle, restore it with --import-ca and reissue."
                )
            )
        # The terminator reads these files when it loads its config, not on every
        # handshake. Healing the files is therefore only half the job, and the half
        # that leaves no trace: the box logs a successful reissue and keeps serving
        # the certificate for the address it used to have.
        self.stdout.write(
            "  the TLS terminator is still serving the OLD certificate until it is "
            "restarted:"
        )
        self.stdout.write(
            "    docker compose -f deploy/selfhost/docker-compose.yml --profile tls "
            "restart edge-tls"
        )

    def _ca_bundle(self, options: dict) -> None:
        passphrase = self._passphrase()

        if options["export_ca"]:
            try:
                blob = edge_tls.export_ca_bundle(passphrase=passphrase)
            except (FileNotFoundError, ValueError) as exc:
                raise CommandError(str(exc)) from exc
            target = options["export_ca"]
            try:
                with open(target, "wb") as handle:
                    handle.write(blob)
            except OSError as exc:
                raise CommandError(f"cannot write {target}: {exc}") from exc
            try:
                os.chmod(target, 0o600)
            except OSError:
                pass
            self.stdout.write(
                self.style.SUCCESS(
                    f"exported box CA -> {target} ({len(blob)} bytes, encrypted PKCS#12)"
                )
            )
            self.stdout.write(
                "  Store it somewhere that is NOT this box, and not beside the passphrase.\n"
                "  Restoring it onto replacement hardware is the difference between a\n"
                "  five-minute swap and re-installing a CA on every device in the building."
            )
            return

        source = options["import_ca"]
        try:
            with open(source, "rb") as handle:
                blob = handle.read()
        except OSError as exc:
            raise CommandError(f"cannot read {source}: {exc}") from exc
        try:
            info = edge_tls.import_ca_bundle(blob, passphrase, force=options["force"])
        except (ValueError, FileExistsError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"restored box CA -> {info['ca_cert']}"))
        self.stdout.write(f"  subject      {info['subject']}")
        self.stdout.write(f"  fingerprint  {info['fingerprint']}")
        if info["replaced"]:
            self.stdout.write(
                self.style.WARNING("  a DIFFERENT CA was present and has been replaced")
            )
        self.stdout.write(
            "  Now issue the leaf: `edge_tls --issue-selfsigned --force`. It chains to this\n"
            "  CA, so devices that already trust it need nothing done to them."
        )

    def handle(self, *args, **options):
        facts = self._facts()

        if options["export_ca"] and options["import_ca"]:
            raise CommandError("--export-ca and --import-ca are opposites; pick one.")

        if options["export_ca"] or options["import_ca"]:
            self._ca_bundle(options)
            return

        if options["plan_relocation"]:
            changed = {
                token.strip().lower()
                for token in str(options["changed"] or "").split(",")
                if token.strip()
            }
            unknown = changed - set(edge_tls.RELOCATION_CHANGES)
            if unknown:
                raise CommandError(
                    "unknown --changed value(s): "
                    + ", ".join(sorted(unknown))
                    + ". Valid: "
                    + ", ".join(edge_tls.RELOCATION_CHANGES)
                )
            if not changed:
                # The commonest move, and the one people forget to describe.
                changed = {edge_tls.CHANGE_ADDRESS}
            steps = edge_tls.relocation_plan(
                facts["mode"],
                changed,
                hsts_seconds=int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0),
            )
            if options["json"]:
                self.stdout.write(
                    json.dumps(
                        {"mode": facts["mode"], "changed": sorted(changed), "steps": steps},
                        indent=2,
                    )
                )
                return
            joined = ", ".join(sorted(changed))
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"relocating a {facts['mode']} box ({joined})"
                )
            )
            for index, step in enumerate(steps, 1):
                self.stdout.write(f"  {index}. {step}")
            return

        if options["plan_to"]:
            try:
                target = edge_tls.normalize_mode(options["plan_to"])
            except edge_tls.UnknownTlsMode as exc:
                raise CommandError(str(exc)) from exc
            steps = edge_tls.transition_plan(facts["mode"], target)
            if options["json"]:
                self.stdout.write(json.dumps({"from": facts["mode"], "to": target, "steps": steps}, indent=2))
                return
            self.stdout.write(self.style.MIGRATE_HEADING(f"{facts['mode']} -> {target}"))
            for index, step in enumerate(steps, 1):
                self.stdout.write(f"  {index}. {step}")
            return

        if options["ensure"]:
            self._ensure(facts, options)
            return

        if options["issue_selfsigned"]:
            self._issue(facts, options)
            facts = self._facts()

        if options["print_caddyfile"]:
            cert = facts["cert_path"] if facts["certificate"]["exists"] else ""
            key = facts["key_path"] if facts["key_present"] else ""
            try:
                self.stdout.write(
                    edge_tls.caddyfile(
                        facts["mode"],
                        facts["dns_names"],
                        facts["ip_addresses"],
                        upstream=os.getenv("RMC_EDGE_TLS_UPSTREAM", "web:10000"),
                        cert_path=cert,
                        key_path=key,
                        acme_email=os.getenv(edge_tls.ENV_ACME_EMAIL, ""),
                        acme_ca=os.getenv(edge_tls.ENV_ACME_CA, ""),
                        # A box told to trust the addresses it currently holds has
                        # declared that those addresses move. Pinning them into the
                        # terminator's site matcher would then undo the self-heal on
                        # the first DHCP change.
                        address_may_change=edge_tls.trust_local_addresses(),
                    )
                )
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            return

        if options["json"]:
            self.stdout.write(json.dumps(facts, indent=2, default=str))
            return

        self._report(facts)

    # -- actions ---------------------------------------------------------------

    def _issue(self, facts: dict, options) -> None:
        directory = os.path.dirname(facts["cert_path"]) or edge_tls.DEFAULT_DIR
        if facts["certificate"]["exists"] and not options["force"]:
            raise CommandError(
                f"{facts['cert_path']} already exists. --force re-issues the LEAF and "
                "reuses the box CA already on disk, so devices that installed it keep "
                "working; only a missing or expired ca.key forces a new CA (and with "
                "it a re-install everywhere). Pass --force when you mean to reissue."
            )
        if not facts["dns_names"] and not facts["ip_addresses"]:
            raise CommandError(
                "No names to put in the certificate. Set "
                f"{edge_tls.ENV_HOSTNAMES} (comma-separated) or fix ALLOWED_HOSTS -- a "
                "certificate that asserts nothing is rejected by every browser."
            )
        try:
            issued = edge_tls.issue_self_signed(
                directory,
                facts["dns_names"],
                facts["ip_addresses"],
                days=options["days"],
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the operator verbatim
            raise CommandError(f"could not issue certificate: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"issued {issued['cert']}"))
        self.stdout.write(f"  key          {issued['key']}")
        self.stdout.write(
            f"  box CA       {issued['ca']}"
            + ("  (reused - no device re-install needed)" if issued["reused_ca"] else "  (NEW)")
        )
        if not issued["reused_ca"]:
            self.stdout.write(
                self.style.WARNING(
                    f"  ca key       {issued['ca_key']}  <- never copy this off the box; "
                    "whoever holds it can impersonate any name to every device that "
                    "trusts this CA"
                )
            )
        self.stdout.write(
            "  names        "
            + ", ".join(facts["dns_names"] + facts["ip_addresses"])
        )
        self.stdout.write(
            "\nInstall the box CA (NOT the leaf) on every device that will use the box. "
            "Installing the CA is what lets you reissue the leaf later -- new IP, new "
            "hostname, expiry -- without touching those devices again."
        )

    def _report(self, facts: dict) -> None:
        style = self.style
        self.stdout.write(style.MIGRATE_HEADING(f"TLS mode: {facts['mode']}"))
        source = facts["mode_source"]
        if facts["mode_error"]:
            self.stdout.write(
                style.ERROR(f"  {facts['mode_error']} -- falling back to 'off'")
            )
        self.stdout.write(f"  source       {source}" + (f" ({facts['mode_raw']!r})" if facts["mode_raw"] else ""))
        self.stdout.write(f"  {facts['summary']}")

        self.stdout.write("")
        self.stdout.write(style.MIGRATE_HEADING("Addresses this box answers at"))
        for name in facts["dns_names"]:
            self.stdout.write(f"  dns  {name}")
        for name in facts["ip_addresses"]:
            self.stdout.write(f"  ip   {name}")
        if not facts["dns_names"] and not facts["ip_addresses"]:
            self.stdout.write(style.WARNING("  none resolved from ALLOWED_HOSTS"))

        if facts["mode"] in edge_tls.FILE_BACKED_MODES:
            self.stdout.write("")
            self.stdout.write(style.MIGRATE_HEADING("Certificate"))
            cert = facts["certificate"]
            if not cert["exists"]:
                self.stdout.write(style.ERROR(f"  MISSING  {facts['cert_path']}"))
            elif cert["error"]:
                self.stdout.write(style.ERROR(f"  {cert['error']}"))
            else:
                self.stdout.write(f"  subject      {cert['subject']}")
                self.stdout.write(f"  issuer       {cert['issuer']}")
                self.stdout.write(f"  self-signed  {cert['self_signed']}")
                self.stdout.write(f"  expires      {cert['not_after']} ({cert['days_remaining']} days)")
                if cert["missing_names"]:
                    self.stdout.write(
                        style.ERROR(
                            "  NOT COVERED  " + ", ".join(cert["missing_names"])
                            + "  <- browsers will warn at these addresses"
                        )
                    )
                else:
                    self.stdout.write(style.SUCCESS("  covers every address above"))
            if not facts["key_present"]:
                self.stdout.write(style.ERROR(f"  MISSING key  {facts['key_path']}"))

        self.stdout.write("")
        self.stdout.write(style.MIGRATE_HEADING("Django flags that follow from the mode"))
        for name, expected in facts["derived_flags"].items():
            actual = facts["active_flags"].get(name)
            if actual == expected or facts["debug"]:
                self.stdout.write(f"  {name:<26} {actual}")
            else:
                self.stdout.write(
                    style.ERROR(f"  {name:<26} {actual}   <- mode implies {expected}")
                )
        if facts["debug"]:
            self.stdout.write(
                style.WARNING(
                    "  DEBUG=1: Django forces all three booleans off and HSTS to 0 "
                    "regardless of the mode. These values mean nothing here -- read "
                    "them on the box, at DEBUG=0."
                )
            )
        if not facts["flags_agree"]:
            self.stdout.write(
                style.WARNING(
                    "\n  A flag disagrees with the mode. That is legal -- an explicit env "
                    "var wins on purpose, so an operator can pin one value -- but it is "
                    "how a box ends up with Secure cookies on a plain-HTTP origin and a "
                    "login that 302s forever. check_edge_readiness reports it too."
                )
            )
        if facts["mode"] == edge_tls.MODE_OFF:
            self.stdout.write(
                style.WARNING(
                    "\n  Offline PIN / local mode cannot work while the origin is plain "
                    "HTTP: WebCrypto is withheld outside a secure context. "
                    "`--plan-to selfsigned` prints the way out."
                )
            )
