"""Every callout in the runbook that said "be careful", asserted as a refusal.

A warning in a document is a hope. The box is set up at a console, often by someone
who did not write the document, often at the end of a long day, and the four
expensive mistakes in the edge TLS procedure were all ORDERING mistakes -- each
individual step correct, the sequence wrong, and the result invisible until thirty
devices had been touched.

So each of them is a precondition here, and each test below is the machine refusing.
"""

from __future__ import annotations

import os
import shutil
import socket
import ssl
import tempfile
import threading
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from apps.schools import edge_tls, edge_trust_state


class _BoxMixin:
    """A scratch box: a certificate directory and a state directory, kept apart."""

    def setUp(self):
        super().setUp()
        self.certs = tempfile.mkdtemp(prefix="edge-certs-")
        self.state = tempfile.mkdtemp(prefix="edge-state-")
        self.addCleanup(shutil.rmtree, self.certs, True)
        self.addCleanup(shutil.rmtree, self.state, True)

    def env(self, **extra):
        base = {
            edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
            edge_tls.ENV_DIR: self.certs,
            edge_tls.ENV_HOSTNAMES: "gilead.local,10.10.20.137",
            edge_trust_state.ENV_STATE_DIR: self.state,
            edge_tls.ENV_CA_PASSPHRASE: "a-real-passphrase",
        }
        base.update(extra)
        return mock.patch.dict(os.environ, base, clear=False)

    def issue(self, dns=("gilead.local",), ips=("10.10.20.137",)):
        return edge_tls.issue_self_signed(
            directory=self.certs, dns_names=list(dns), ip_addresses=list(ips), days=825
        )

    def ca_facts(self):
        return edge_tls.inspect_certificate(os.path.join(self.certs, "ca.crt"))

    def run_cmd(self, name, *args, **kwargs):
        out, err = StringIO(), StringIO()
        call_command(name, *args, stdout=out, stderr=err, **kwargs)
        return out.getvalue() + err.getvalue()


class TrustAnchorTests(_BoxMixin, SimpleTestCase):
    """What the box remembers about its own certificate authority."""

    def test_a_box_with_no_history_and_no_ca_is_simply_new(self):
        with self.env():
            self.assertEqual(
                edge_trust_state.compare(self.ca_facts())["status"],
                edge_trust_state.ANCHOR_UNKNOWN,
            )

    def test_a_first_ca_is_recognised_as_first_then_recorded(self):
        with self.env():
            self.issue()
            self.assertEqual(
                edge_trust_state.compare(self.ca_facts())["status"],
                edge_trust_state.ANCHOR_FIRST,
            )
            edge_trust_state.record(self.ca_facts())
            self.assertEqual(
                edge_trust_state.compare(self.ca_facts())["status"],
                edge_trust_state.ANCHOR_SAME,
            )

    def test_the_anchor_lives_outside_the_certificate_directory(self):
        # The entire point. State stored beside the certificates disappears in the
        # same accident, and then it can never report the accident.
        with self.env():
            self.issue()
            edge_trust_state.record(self.ca_facts())
            anchor = os.path.abspath(edge_trust_state.anchor_path())
            self.assertFalse(anchor.startswith(os.path.abspath(self.certs)))
            self.assertTrue(os.path.exists(anchor))

    def test_a_lost_certificate_volume_is_detected_not_papered_over(self):
        with self.env():
            self.issue()
            edge_trust_state.record(self.ca_facts())
            shutil.rmtree(self.certs)
            os.makedirs(self.certs, exist_ok=True)
            self.assertEqual(
                edge_trust_state.compare(self.ca_facts())["status"],
                edge_trust_state.ANCHOR_MISSING,
            )

    def test_a_replaced_ca_is_detected(self):
        with self.env():
            self.issue()
            edge_trust_state.record(self.ca_facts())
            shutil.rmtree(self.certs)
            os.makedirs(self.certs, exist_ok=True)
            self.issue()  # a different CA entirely
            verdict = edge_trust_state.compare(self.ca_facts())
            self.assertEqual(verdict["status"], edge_trust_state.ANCHOR_CHANGED)

    def test_the_superseded_fingerprint_is_kept(self):
        # Whoever picks this up afterwards needs to know which CA the devices in the
        # building are still trusting.
        with self.env():
            self.issue()
            first = self.ca_facts().fingerprint
            edge_trust_state.record(self.ca_facts())
            shutil.rmtree(self.certs)
            os.makedirs(self.certs, exist_ok=True)
            self.issue()
            edge_trust_state.record(self.ca_facts())
            history = edge_trust_state.load_state().get("history") or []
            self.assertIn(first, [h.get("fingerprint") for h in history])

    def test_an_unreadable_record_never_reads_as_a_fresh_box(self):
        # Reading a corrupt file as "no CA yet" is the one interpretation that would
        # permit a second CA, so it must not be the fallback.
        with self.env():
            self.issue()
            edge_trust_state.record(self.ca_facts())
            with open(edge_trust_state.anchor_path(), "w", encoding="utf-8") as handle:
                handle.write("{ this is not json")
            allowed, why = edge_trust_state.new_ca_allowed(self.ca_facts())
            self.assertFalse(allowed)
            self.assertIn("cannot be read", why)


class NewCaGuardTests(_BoxMixin, SimpleTestCase):
    """The one action in the whole procedure that cannot be undone."""

    def test_a_genuinely_new_box_may_mint(self):
        with self.env():
            allowed, _why = edge_trust_state.new_ca_allowed(self.ca_facts())
            self.assertTrue(allowed)

    def test_a_box_that_lost_its_volume_may_not(self):
        with self.env():
            self.issue()
            edge_trust_state.record(self.ca_facts())
            shutil.rmtree(self.certs)
            os.makedirs(self.certs, exist_ok=True)
            allowed, why = edge_trust_state.new_ca_allowed(self.ca_facts())
            self.assertFalse(allowed)
            self.assertIn("RESTORE FIRST", why)

    def test_the_boot_time_self_heal_is_not_a_back_door(self):
        # --ensure runs unattended on every container start. Without the guard, a box
        # whose volume was lost comes up at 3am, notices it has no certificate,
        # helpfully mints a new CA and reports success.
        with self.env():
            self.issue()
            edge_trust_state.record(self.ca_facts())
            shutil.rmtree(self.certs)
            os.makedirs(self.certs, exist_ok=True)
            with self.assertRaises(CommandError) as caught:
                self.run_cmd("edge_tls", "--ensure")
            self.assertIn("has issued a CA before", str(caught.exception))
            self.assertEqual(os.listdir(self.certs), [])

    def test_a_refusal_leaves_the_directory_untouched(self):
        with self.env():
            self.issue()
            edge_trust_state.record(self.ca_facts())
            shutil.rmtree(self.certs)
            os.makedirs(self.certs, exist_ok=True)
            with self.assertRaises(CommandError):
                self.run_cmd("edge_tls", "--ensure")
            self.assertFalse(os.path.exists(os.path.join(self.certs, "ca.key")))


class BackupIsNotABeliefTests(_BoxMixin, SimpleTestCase):
    def test_a_backup_into_the_certificate_directory_is_refused_before_writing(self):
        with self.env():
            findings = edge_tls.export_path_findings(
                os.path.join(self.certs, edge_tls.CA_BUNDLE_FILENAME)
            )
            self.assertEqual([s for s, _ in findings], ["fail"])
            self.assertIn("shares a volume with the key it protects", findings[0][1])

    def test_a_path_outside_the_certificate_directory_is_fine(self):
        with self.env():
            self.assertEqual(
                edge_tls.export_path_findings(
                    os.path.join(tempfile.gettempdir(), "box-ca-bundle.p12")
                ),
                [],
            )

    def test_a_directory_is_not_a_destination(self):
        with self.env():
            findings = edge_tls.export_path_findings(tempfile.gettempdir())
            self.assertEqual([s for s, _ in findings], ["fail"])

    def test_an_unbacked_ca_is_a_failure_not_a_reminder(self):
        with self.env():
            self.issue()
            edge_trust_state.record(self.ca_facts())
            findings = edge_trust_state.anchor_findings(self.ca_facts())
            self.assertEqual([s for s, _ in findings], ["fail"])
            self.assertIn("never been backed up", findings[0][1])

    def test_an_unverified_backup_is_only_a_belief(self):
        with self.env():
            self.issue()
            edge_trust_state.record(self.ca_facts())
            edge_trust_state.record_export(
                self.ca_facts().fingerprint, "/tmp/b.p12", verified=False
            )
            self.assertEqual(
                [s for s, _ in edge_trust_state.anchor_findings(self.ca_facts())], ["warn"]
            )

    def test_a_verified_backup_is_the_clean_state(self):
        with self.env():
            self.issue()
            edge_trust_state.record(self.ca_facts())
            edge_trust_state.record_export(
                self.ca_facts().fingerprint, "/tmp/b.p12", verified=True
            )
            self.assertEqual(
                [s for s, _ in edge_trust_state.anchor_findings(self.ca_facts())], ["ok"]
            )


class OrderingIsRefusedNotDocumentedTests(_BoxMixin, SimpleTestCase):
    def test_rendering_before_issuing_is_refused(self):
        # Rendered early it emits `tls internal` -- Caddy's OWN CA -- so the ca.crt
        # distributed to every device matches nothing the box presents, and no error
        # anywhere says so. The output looks completely valid, which is the expensive
        # part.
        with self.env():
            with self.assertRaises(CommandError) as caught:
                self.run_cmd("edge_tls", "--print-caddyfile")
            self.assertIn("tls internal", str(caught.exception))

    def test_rendering_after_issuing_is_fine(self):
        with self.env():
            self.issue()
            output = self.run_cmd("edge_tls", "--print-caddyfile")
            self.assertIn("tls " + self.certs.replace("\\", "/"), output.replace("\\", "/"))
            self.assertNotIn("tls internal", output)


@override_settings(ALLOWED_HOSTS=["localhost", "gilead.local", "10.10.20.137"])
class BootstrapTests(_BoxMixin, SimpleTestCase):
    """The whole procedure as one command that refuses rather than proceeds."""

    def test_a_first_run_issues_records_and_verifies_a_backup(self):
        destination = os.path.join(self.state, "bundle.p12")
        with self.env():
            output = self.run_cmd(
                "edge_bootstrap", "--backup-to", destination, "--terminator", ""
            )
        self.assertIn("issued", output)
        self.assertIn("Trust anchor recorded", output)
        self.assertIn("read back and the CA inside it matches", output)
        self.assertTrue(os.path.exists(destination))
        with self.env():
            self.assertEqual(
                [s for s, _ in edge_trust_state.anchor_findings(self.ca_facts())], ["ok"]
            )

    def test_running_it_again_changes_nothing(self):
        destination = os.path.join(self.state, "bundle.p12")
        with self.env():
            self.run_cmd("edge_bootstrap", "--backup-to", destination, "--terminator", "")
            before = self.ca_facts().fingerprint
            output = self.run_cmd(
                "edge_bootstrap", "--backup-to", destination, "--terminator", ""
            )
            self.assertIn("No change needed", output)
            self.assertEqual(self.ca_facts().fingerprint, before)

    def test_it_refuses_to_back_up_into_the_certificate_directory(self):
        with self.env():
            with self.assertRaises(CommandError) as caught:
                self.run_cmd(
                    "edge_bootstrap",
                    "--backup-to",
                    os.path.join(self.certs, "bundle.p12"),
                    "--terminator",
                    "",
                )
            self.assertIn("shares a volume", str(caught.exception))

    def test_it_refuses_without_a_passphrase(self):
        with self.env(**{edge_tls.ENV_CA_PASSPHRASE: ""}):
            with self.assertRaises(CommandError) as caught:
                self.run_cmd("edge_bootstrap", "--terminator", "")
            self.assertIn(edge_tls.ENV_CA_PASSPHRASE, str(caught.exception))

    def test_it_refuses_to_skip_the_backup_while_the_ca_has_none(self):
        with self.env():
            with self.assertRaises(CommandError) as caught:
                self.run_cmd("edge_bootstrap", "--no-backup", "--terminator", "")
            self.assertIn("no verified backup", str(caught.exception))

    def test_skipping_is_allowed_once_a_verified_backup_exists(self):
        destination = os.path.join(self.state, "bundle.p12")
        with self.env():
            self.run_cmd("edge_bootstrap", "--backup-to", destination, "--terminator", "")
            output = self.run_cmd("edge_bootstrap", "--no-backup", "--terminator", "")
        self.assertIn("already has a verified one", output)

    def test_it_refuses_on_a_box_that_lost_its_certificate_volume(self):
        destination = os.path.join(self.state, "bundle.p12")
        with self.env():
            self.run_cmd("edge_bootstrap", "--backup-to", destination, "--terminator", "")
            shutil.rmtree(self.certs)
            os.makedirs(self.certs, exist_ok=True)
            with self.assertRaises(CommandError) as caught:
                self.run_cmd(
                    "edge_bootstrap", "--backup-to", destination, "--terminator", ""
                )
            self.assertIn("RESTORE FIRST", str(caught.exception))
            self.assertEqual(os.listdir(self.certs), [])

    def test_restoring_then_bootstrapping_keeps_the_original_ca(self):
        # The recovery path the refusal points at, end to end.
        destination = os.path.join(self.state, "bundle.p12")
        with self.env():
            self.run_cmd("edge_bootstrap", "--backup-to", destination, "--terminator", "")
            original = self.ca_facts().fingerprint
            shutil.rmtree(self.certs)
            os.makedirs(self.certs, exist_ok=True)
            with open(destination, "rb") as handle:
                edge_tls.import_ca_bundle(
                    handle.read(), passphrase=b"a-real-passphrase", directory=self.certs
                )
            self.run_cmd("edge_bootstrap", "--backup-to", destination, "--terminator", "")
            self.assertEqual(self.ca_facts().fingerprint, original)

    def test_a_dry_run_changes_nothing(self):
        with self.env():
            self.run_cmd("edge_bootstrap", "--dry-run", "--terminator", "")
            self.assertFalse(os.path.exists(os.path.join(self.certs, "ca.crt")))


class ServedCertificateTests(_BoxMixin, SimpleTestCase):
    """Reissuing is half a heal; this is how the other half becomes visible."""

    def _serve(self, directory):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(
            os.path.join(directory, "tls.crt"), os.path.join(directory, "tls.key")
        )
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(5)
        port = server.getsockname()[1]

        def loop():
            while True:
                try:
                    client, _ = server.accept()
                except OSError:
                    return
                try:
                    context.wrap_socket(client, server_side=True).close()
                except OSError:
                    pass

        threading.Thread(target=loop, daemon=True).start()
        self.addCleanup(server.close)
        return port

    def test_matching_certificates_report_agreement(self):
        self.issue()
        port = self._serve(self.certs)
        findings = edge_tls.terminator_findings(
            os.path.join(self.certs, "tls.crt"), "127.0.0.1", port
        )
        self.assertEqual([s for s, _ in findings], ["ok"])

    def test_a_stale_terminator_is_caught_and_both_sides_are_named(self):
        self.issue(ips=("10.10.20.137",))
        port = self._serve(self.certs)  # terminator holds the OLD certificate
        self.issue(ips=("10.10.20.99",))  # disk healed onto a new address
        findings = edge_tls.terminator_findings(
            os.path.join(self.certs, "tls.crt"), "127.0.0.1", port
        )
        self.assertEqual([s for s, _ in findings], ["fail"])
        message = findings[0][1]
        self.assertIn("10.10.20.99", message)
        self.assertIn("10.10.20.137", message)
        self.assertIn("restart edge-tls", message)

    def test_an_unreachable_terminator_is_a_warning_not_a_failure(self):
        self.issue()
        findings = edge_tls.terminator_findings(
            os.path.join(self.certs, "tls.crt"), "127.0.0.1", 9
        )
        self.assertEqual([s for s, _ in findings], ["warn"])

    def test_no_certificate_means_nothing_to_compare(self):
        self.assertEqual(
            edge_tls.terminator_findings(
                os.path.join(self.certs, "tls.crt"), "127.0.0.1", 9
            ),
            [],
        )


class FingerprintTests(_BoxMixin, SimpleTestCase):
    def test_the_fingerprint_is_the_form_openssl_prints(self):
        # So an operator can compare what this says against what their device shows
        # without converting anything in their head.
        result = self.issue()
        facts = edge_tls.inspect_certificate(result["cert"])
        self.assertRegex(facts.fingerprint, r"^[0-9A-F]{2}(:[0-9A-F]{2}){31}$")

    def test_a_missing_certificate_has_no_fingerprint(self):
        self.assertEqual(
            edge_tls.inspect_certificate(os.path.join(self.certs, "nope.crt")).fingerprint,
            "",
        )


class LeadingDotIsAWildcardTests(SimpleTestCase):
    """Django spells "and every subdomain" with a leading dot."""

    def test_a_leading_dot_entry_is_dropped_like_any_other_wildcard(self):
        # ".local" is the platform default in ALLOWED_HOSTS. Stripping the dot turned
        # it into the bare label "local" and put that in every box's certificate --
        # a name no device ever types.
        for entry in (".local", ".runmycampus.com", ".onrender.com"):
            with self.subTest(entry=entry):
                self.assertEqual(edge_tls.normalize_hostname(entry), "")

    def test_a_trailing_dot_is_only_fqdn_notation_and_is_kept(self):
        self.assertEqual(edge_tls.normalize_hostname("gilead.local."), "gilead.local")

    def test_the_certificate_asserts_only_what_was_actually_named(self):
        dns, ips = edge_tls.san_candidates(
            environ={}, allowed_hosts=[".local", "gilead.local", "10.10.20.137"]
        )
        self.assertEqual(dns, ["gilead.local"])
        self.assertEqual(ips, ["10.10.20.137"])
