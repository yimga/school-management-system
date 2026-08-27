"""One command that does the certificate work in the only order that is correct.

    python manage.py edge_bootstrap

WHY THIS EXISTS. The edge TLS runbook was twelve steps, and four of them were
ordering traps where each individual step is correct and the sequence is not:

* render the terminator config before the certificate exists and it silently emits
  ``tls internal`` -- so the CA you then install on thirty devices matches nothing
  the box presents, and no error anywhere mentions it;
* issue before restoring, on a box whose certificate volume was lost, and you mint a
  second CA that strands every device that trusted the first -- permanently;
* install the CA on devices before backing it up, and the window where the box's one
  unregenerable artefact has no copy is exactly the window you spend walking around
  the building;
* back the CA up into the certificate directory and it shares a volume with the key
  it protects, so it survives none of the events a backup exists for.

None of those are things an operator should have to remember at a console in a
school office. They are invariants, so they belong in code: this command performs
the whole sequence, refuses rather than proceeds when a precondition is not met, and
is safe to run again on a box that is already working.

It deliberately does NOT touch the database, so it can run at container start and on
a box whose database is down -- which is when the guards matter most.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.schools import edge_tls, edge_trust_state

DEFAULT_BACKUP = "/tmp/" + edge_tls.CA_BUNDLE_FILENAME
DEFAULT_TERMINATOR = "edge-tls:443"


class Command(BaseCommand):
    help = "Bring this box's certificate, its backup and its terminator config into a correct, verified state."

    def add_arguments(self, parser):
        parser.add_argument(
            "--backup-to",
            default=DEFAULT_BACKUP,
            help=(
                "Where to write the encrypted CA bundle. Must NOT be inside the "
                f"certificate directory. Default: {DEFAULT_BACKUP}"
            ),
        )
        parser.add_argument(
            "--no-backup",
            action="store_true",
            help=(
                "Skip the CA backup. Refused unless the CA already has a verified "
                "backup on record -- the point of this command is that the one "
                "unregenerable artefact is never unbacked while devices are being set up."
            ),
        )
        parser.add_argument(
            "--force-new-ca",
            action="store_true",
            help=(
                "Permit minting a NEW certificate authority even though this box has "
                "recorded a different one. Every device that trusted the old CA must "
                "then install the new one by hand. There is no undo."
            ),
        )
        parser.add_argument(
            "--caddyfile",
            default="",
            help=(
                "Also write the rendered terminator config here. Only useful where "
                "that path is writable and mounted into the terminator; on the "
                "standard selfhost layout the host-side wrapper handles this."
            ),
        )
        parser.add_argument(
            "--print-caddyfile",
            action="store_true",
            help="Print the rendered terminator config to stdout and nothing else.",
        )
        parser.add_argument(
            "--terminator",
            default=DEFAULT_TERMINATOR,
            help=(
                "host[:port] of the TLS terminator, so this command can check that "
                f"what is SERVED matches what is on disk. Default: {DEFAULT_TERMINATOR}. "
                "Pass an empty string to skip."
            ),
        )
        parser.add_argument("--days", type=int, default=edge_tls.DEFAULT_SELF_SIGNED_DAYS)
        parser.add_argument("--dry-run", action="store_true", help="Report what would happen; change nothing.")
        parser.add_argument("--json", action="store_true", help="Machine-readable report.")

    # -- reporting -----------------------------------------------------------
    def _say(self, text=""):
        if not self.as_json:
            self.stdout.write(text)

    def _step(self, n, title):
        self._say("")
        self._say(self.style.MIGRATE_HEADING(f"[{n}] {title}"))

    def _ok(self, text):
        self.report["ok"].append(text)
        self._say(self.style.SUCCESS("    ok    ") + text)

    def _warn(self, text):
        self.report["warn"].append(text)
        self._say(self.style.WARNING("    warn  ") + text)

    def _info(self, text):
        self._say("          " + text)

    def _fail(self, text):
        self.report["fail"].append(text)
        self._say(self.style.ERROR("    FAIL  ") + text)

    # -- main ----------------------------------------------------------------
    def handle(self, *args, **options):
        self.as_json = options["json"]
        self.report = {"ok": [], "warn": [], "fail": [], "actions": []}
        dry = options["dry_run"]

        resolution = edge_tls.resolve_mode()
        cert_path, key_path, ca_path = edge_tls.certificate_paths()
        directory = os.path.dirname(cert_path) or edge_tls.DEFAULT_DIR
        allowed = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
        dns, ips = edge_tls.effective_addresses(allowed_hosts=allowed)

        if options["print_caddyfile"]:
            self.stdout.write(self._render_caddyfile(resolution.mode, dns, ips, cert_path, key_path))
            return

        self._say(self.style.MIGRATE_HEADING("edge_bootstrap") + (" (dry run)" if dry else ""))
        self._say(f"  mode      {resolution.mode}")
        self._say(f"  addresses {', '.join([*dns, *ips]) or '(none)'}")
        self._say(f"  certs     {directory}")
        self._say(f"  anchor    {edge_trust_state.anchor_path()}")

        # --- 1. preflight ---------------------------------------------------
        self._step(1, "Preflight")
        if resolution.mode != edge_tls.MODE_SELF_SIGNED:
            raise CommandError(
                f"mode is {resolution.mode}; edge_bootstrap manages a box-minted "
                "(selfsigned) certificate only. A provided pair is replaced by whoever "
                "issues it and acme renews itself; neither needs this."
            )
        if not dns and not ips:
            raise CommandError(
                "No addresses to assert. Set "
                f"{edge_tls.ENV_HOSTNAMES}, fix ALLOWED_HOSTS, or set "
                f"{edge_tls.ENV_TRUST_LOCAL}=1 to use the addresses this box holds."
            )
        blocking = False
        for severity, message in edge_tls.hostname_findings(
            edge_tls.declared_hostnames(allowed_hosts=allowed)
        ):
            (self._fail if severity == "fail" else self._warn)(message)
            blocking = blocking or severity == "fail"
        for severity, message in edge_tls.mode_feasibility(resolution.mode, dns, ips):
            (self._fail if severity == "fail" else self._warn)(message)
            blocking = blocking or severity == "fail"
        for severity, message in edge_tls.stability_findings(dns, ips):
            self._warn(message)
        if blocking:
            raise CommandError(
                "Preflight failed. Nothing has been changed. Fix the findings above "
                "and run this again -- it is safe to repeat."
            )
        self._ok("Mode, addresses and names are all usable.")

        # --- 2. the guard on the one irreversible action ---------------------
        self._step(2, "Trust anchor")
        ca_facts = edge_tls.inspect_certificate(ca_path)
        verdict = edge_trust_state.compare(ca_facts)
        self._info(f"status: {verdict['status']}")
        allowed_new, why = edge_trust_state.new_ca_allowed(ca_facts)
        if not allowed_new and not options["force_new_ca"]:
            raise CommandError(
                why
                + "\n\n  Nothing has been changed. This is the one action in the whole "
                "procedure that cannot be undone, so it refuses rather than guesses."
            )
        if not allowed_new:
            self._warn(
                "--force-new-ca given: proceeding to mint a NEW certificate authority. "
                "Every device that trusted the old one must install the new one by hand."
            )
        elif verdict["status"] == edge_trust_state.ANCHOR_SAME:
            self._ok(f"This box's recorded CA is on disk ({verdict['present_fingerprint'][:17]}...).")
        elif verdict["status"] == edge_trust_state.ANCHOR_UNKNOWN:
            self._info("No CA yet, and none recorded. This is a first install.")

        # --- 3. certificate --------------------------------------------------
        self._step(3, "Certificate")
        if dry:
            needed, reason = edge_tls.certificate_needs_reissue(
                edge_tls.inspect_certificate(cert_path), dns, ips, edge_tls.renew_before_days()
            )
            self._info(("would reissue: " if needed else "no change needed: ") + reason)
        else:
            result = edge_tls.ensure_certificate(
                directory, dns, ips,
                days=options["days"],
                renew_before_days=edge_tls.renew_before_days(),
            )
            self.report["actions"].append(result["action"])
            if result["action"] == edge_tls.ACTION_REFUSED:
                raise CommandError(
                    result["reason"]
                    + "\n  Refusing to reissue against a bad clock: a certificate minted "
                    "then is genuinely invalid, which turns one recoverable fault into two."
                )
            if result["action"] == edge_tls.ACTION_NOOP:
                self._ok(f"No change needed -- {result['reason']}")
            else:
                self._ok(f"{result['action']}: {result['reason']}")
                if result["reused_ca"]:
                    self._info("Box CA reused -- devices that trust it need nothing done.")
            ca_facts = edge_tls.inspect_certificate(ca_path)
            recorded = edge_trust_state.record(ca_facts)
            if recorded.get("ok"):
                self._ok(f"Trust anchor recorded: {ca_facts.fingerprint[:17]}...")
            else:
                self._warn(
                    f"Could not record the trust anchor ({recorded.get('error')}). The "
                    "guard that stops a second CA being minted cannot work without it."
                )

        # --- 4. backup, and read it back -------------------------------------
        self._step(4, "Backup of the box CA")
        self._backup(ca_facts, options, dry)

        # --- 5. terminator config --------------------------------------------
        self._step(5, "Terminator config")
        if dry and not edge_tls.inspect_certificate(cert_path).exists:
            # A dry run must never fail for not having done the thing it deliberately
            # did not do. Rendering requires a certificate, and this run made none.
            self._info(
                "would render once the certificate exists -- "
                + (
                    "address-independent (`:443`), because this box may move"
                    if edge_tls.trust_local_addresses()
                    else "pinned to " + (", ".join([*dns, *ips]) or "no address")
                )
            )
            self._step(6, "What the terminator is serving")
            self._info("skipped on a dry run")
            self._say("")
            self._say(self.style.SUCCESS("edge_bootstrap: dry run, nothing changed"))
            return
        rendered = self._render_caddyfile(resolution.mode, dns, ips, cert_path, key_path)
        site = next((ln for ln in rendered.splitlines() if ln and not ln.startswith("#")), "")
        site_line = site.rstrip(" {")
        self._info(f"site line: {site_line}")
        # Branch on what was RENDERED, not on the flag. The renderer emits the
        # catch-all for two independent reasons -- a box that may move, OR a box that
        # serves an IP at all, because a browser sends no SNI for an IP literal and a
        # host matcher would have nothing to match. Reading only the flag made this
        # print "site line: :443" and then warn that the site line names addresses,
        # telling an operator to fix a box that was already correct.
        if site_line == ":443":
            self._ok("Address-independent (`:443`) -- no regeneration needed when the address changes.")
        else:
            self._warn(
                "The site line names addresses. That is correct only for a box whose "
                "address is pinned: if it moves, the certificate heals and the "
                "terminator answers nothing at the new address. Set "
                f"{edge_tls.ENV_TRUST_LOCAL}=1 for a box that travels."
            )
        target = options["caddyfile"]
        if target and not dry:
            try:
                with open(target, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(rendered)
                self._ok(f"Written to {target}")
            except OSError as exc:
                self._warn(f"Could not write {target}: {exc}. Use the host-side wrapper.")
        elif not target:
            self._info(
                "Not written. On the standard layout the file is bind-mounted from the "
                "host, so deploy/selfhost/edge-bootstrap.sh writes it."
            )

        # --- 6. what is actually being served --------------------------------
        self._step(6, "What the terminator is serving")
        self._check_terminator(options["terminator"], cert_path)

        # --- summary ----------------------------------------------------------
        if self.as_json:
            self.stdout.write(json.dumps(self.report, indent=2))
            if self.report["fail"]:
                raise CommandError("edge_bootstrap finished with failures")
            return
        self._say("")
        counts = f"{len(self.report['ok'])} ok, {len(self.report['warn'])} warn, {len(self.report['fail'])} fail"
        if self.report["fail"]:
            self._say(self.style.ERROR(f"edge_bootstrap: {counts}"))
            raise CommandError("Not ready. Fix the failures above, then run this again.")
        self._say(self.style.SUCCESS(f"edge_bootstrap: {counts}"))
        if not dry:
            self._say("")
            # Only when THIS run verified what the terminator is actually serving.
            # `--terminator ''` means somebody else is doing that check -- which is
            # what deploy/selfhost/edge-bootstrap.sh passes, because it starts and
            # restarts Caddy itself and then checks, several steps after this one.
            #
            # This is an ordering guard, not tidiness. The expensive failure in this
            # whole area is a terminator serving Caddy's OWN certificate authority
            # while every log says healthy; enrolling devices before that check has
            # run is how a school spends an afternoon installing a CA that matches
            # nothing the box presents. If this run cannot vouch for what is served,
            # it does not send anyone anywhere -- the caller that CAN, does.
            checked_terminator = bool(str(options["terminator"] or "").strip())
            trust_url = edge_tls.trust_enrolment_url(dns, ips)
            if trust_url and checked_terminator:
                self._say("Send every device here, on the school network:")
                self._say(self.style.MIGRATE_HEADING(f"  {trust_url}"))
                self._say(
                    "  Fingerprint, QR code, the CA itself and the per-platform "
                    "step people skip.\n  Plain http on purpose: a device "
                    "reaches it BECAUSE it does not trust this\n  box yet. "
                    "Have whoever installs it compare the fingerprint shown there\n"
                    "  against `manage.py edge_tls` -- over http, that comparison "
                    "is the only thing\n  between a school and somebody "
                    "else's certificate authority."
                )
                self._say("")
            self._say("Remaining human steps, and only these:")
            self._say("  1. Move the CA bundle and its passphrase OFF the box, stored apart.")
            self._say("  2. Re-enrol offline PIN on each device at the https origin.")

    # -- pieces ---------------------------------------------------------------
    def _render_caddyfile(self, mode, dns, ips, cert_path, key_path):
        cert = cert_path if edge_tls.inspect_certificate(cert_path).exists else ""
        key = key_path if os.path.exists(key_path) else ""
        if mode in edge_tls.FILE_BACKED_MODES and not (cert and key):
            raise CommandError(
                "Refusing to render a terminator config before the certificate exists. "
                "With no certificate on disk this would emit `tls internal`, which "
                "serves Caddy's OWN certificate authority -- so the ca.crt you then "
                "install on every device would match nothing the box presents, and "
                "nothing in the browser error would say why. Run the certificate step "
                "first (`edge_bootstrap` does both, in order)."
            )
        try:
            return edge_tls.caddyfile(
                mode, dns, ips,
                upstream=os.getenv("RMC_EDGE_TLS_UPSTREAM", "web:10000"),
                cert_path=cert,
                key_path=key,
                acme_email=os.getenv(edge_tls.ENV_ACME_EMAIL, ""),
                acme_ca=os.getenv(edge_tls.ENV_ACME_CA, ""),
                address_may_change=edge_tls.trust_local_addresses(),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

    def _backup(self, ca_facts, options, dry):
        state = edge_trust_state.load_state()
        active = state.get("active") or {}
        already = bool(active.get("export_verified_at")) and active.get("fingerprint") == ca_facts.fingerprint

        if options["no_backup"]:
            if already:
                self._ok(f"Backup skipped; this CA already has a verified one ({active.get('exported_at')}).")
                return
            raise CommandError(
                "--no-backup refused: this CA has no verified backup on record. It is "
                "the only artefact on the box that cannot be rebuilt, and the window "
                "where it has no copy is exactly the afternoon you spend installing it "
                "on devices. Set RMC_EDGE_TLS_CA_PASSPHRASE and let this command back "
                "it up."
            )

        destination = options["backup_to"]
        for severity, message in edge_tls.export_path_findings(destination):
            if severity == "fail":
                raise CommandError(message)
            self._warn(message)

        passphrase = os.environ.get(edge_tls.ENV_CA_PASSPHRASE, "")
        if not passphrase:
            raise CommandError(
                f"Set {edge_tls.ENV_CA_PASSPHRASE} in the environment. The bundle "
                "carries the CA private key, so it is deliberately not a command-line "
                "flag -- a command line is visible in `ps`, in shell history and in "
                "docker's own event log. Pass it with `docker compose exec -e "
                f"{edge_tls.ENV_CA_PASSPHRASE} web ...`."
            )
        if dry:
            self._info(f"would export to {destination} and read it back to verify")
            return

        try:
            blob = edge_tls.export_ca_bundle(passphrase=passphrase.encode("utf-8"))
        except (FileNotFoundError, ValueError) as exc:
            raise CommandError(f"could not export the CA: {exc}") from exc
        try:
            with open(destination, "wb") as handle:
                handle.write(blob)
            os.chmod(destination, 0o600)
        except OSError as exc:
            raise CommandError(f"cannot write {destination}: {exc}") from exc
        self._ok(f"Exported to {destination} ({len(blob)} bytes, encrypted).")

        # Read it back. An unverified backup is a belief, and the failure modes --
        # wrong passphrase, truncated copy -- are discovered years later at the exact
        # moment the backup is needed.
        scratch = tempfile.mkdtemp(prefix="edge-verify-")
        try:
            edge_tls.import_ca_bundle(blob, passphrase=passphrase.encode("utf-8"), directory=scratch)
            restored = edge_tls.inspect_certificate(os.path.join(scratch, "ca.crt"))
            verified = bool(restored.fingerprint) and restored.fingerprint == ca_facts.fingerprint
        except Exception as exc:  # noqa: BLE001 - a failed verify is a finding, loudly
            verified = False
            self._fail(f"The backup could not be read back: {exc}")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

        if verified:
            self._ok("Backup read back and the CA inside it matches. This is a real backup.")
        else:
            self._fail(
                "The backup was written but reading it back did not produce this box's "
                "CA. Do NOT rely on it. Check the passphrase and try again."
            )
        edge_trust_state.record_export(ca_facts.fingerprint, destination, verified)
        self._info("Move it off the box; keep the file and the passphrase apart.")

    def _check_terminator(self, endpoint, cert_path):
        endpoint = (endpoint or "").strip()
        if not endpoint:
            self._info("skipped (--terminator '')")
            return
        host, _, port = endpoint.partition(":")
        try:
            port_number = int(port or "443")
        except ValueError:
            raise CommandError(f"--terminator wants host[:port], got {endpoint!r}")
        for severity, message in edge_tls.terminator_findings(cert_path, host, port_number):
            {"ok": self._ok, "warn": self._warn}.get(severity, self._fail)(message)
