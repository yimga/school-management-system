"""Local-first means every locality is different, and each difference broke something.

A re-audit of the edge TLS path against the ways a school's address is actually
written and actually reached, rather than the way it is written in this repo's own
examples. Every test here corresponds to a defect that was live on ``main``:

* a box named in a script other than Latin got NO certificate at all;
* an IPv6 address written the way Django documents it became a DNS name that
  matches nothing -- the exact silent name-mismatch ``san_candidates`` exists to
  prevent;
* an IPv6 address written by hand made the box re-mint its certificate on EVERY
  boot, forever, because two spellings of one address never compared equal;
* an IPv6-only segment discovered no addresses at all;
* and the certificate healed itself onto a new address while the terminator went
  on answering only at the old one.

The non-ASCII names below are written literally, in French, Chinese and Arabic. That
is deliberate: an escape sequence would test the escape rather than the file, and the
thing under test is what happens when a real school's real name reaches a certificate.
"""

from __future__ import annotations

import os
import shutil
import tempfile

from django.test import SimpleTestCase

from apps.schools import edge_tls


class _CertDirMixin:
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="edge-locality-")
        self.addCleanup(shutil.rmtree, self.tmp, True)


class NonAsciiHostnameTests(_CertDirMixin, SimpleTestCase):
    """A school is entitled to the name on its own building."""

    ECOLE = "écolé.local"
    XUEXIAO = "学校.local"
    MADRASA = "مدرسة.local"

    def test_a_non_ascii_name_is_carried_as_its_a_label(self):
        for name in (self.ECOLE, self.XUEXIAO, self.MADRASA):
            with self.subTest(name=name):
                carried = edge_tls.normalize_hostname(name)
                self.assertTrue(carried.startswith("xn--"), carried)
                self.assertTrue(carried.isascii())
                self.assertTrue(carried.endswith(".local"))

    def test_an_ascii_name_is_left_exactly_alone(self):
        # No round-tripping a name that never needed it.
        for name in ("gilead.local", "gilead.school.lan", "sms.gilead-tech.org"):
            with self.subTest(name=name):
                self.assertEqual(edge_tls.normalize_hostname(name), name)

    def test_the_box_actually_gets_a_certificate(self):
        # Before this fix cryptography raised straight out of issue_self_signed and
        # the box booted with no certificate at all -- on plain HTTP, where the
        # offline PIN vault can never seal.
        result = edge_tls.issue_self_signed(
            directory=self.tmp, dns_names=[self.ECOLE], ip_addresses=[], days=30
        )
        facts = edge_tls.inspect_certificate(result["cert"])
        self.assertTrue(facts.exists)
        self.assertEqual(facts.dns_names, ("xn--col-9lad.local",))

    def test_a_name_no_encoding_can_carry_is_refused_by_name(self):
        # Not a stack trace from four frames down: the operator has to be told WHICH
        # entry in their .env is the problem.
        with self.assertRaises(ValueError) as caught:
            edge_tls.issue_self_signed(
                directory=self.tmp, dns_names=["ＡＢ!!"], ip_addresses=[]
            )
        self.assertIn(edge_tls.ENV_HOSTNAMES, str(caught.exception))

    def test_the_readiness_check_explains_the_xn_form_before_anyone_panics(self):
        findings = edge_tls.hostname_findings([self.ECOLE])
        self.assertEqual([s for s, _ in findings], ["warn"])
        self.assertIn("xn--col-9lad.local", findings[0][1])
        self.assertIn("Do not 'fix' it", findings[0][1])

    def test_an_uncarriable_name_is_reported_as_a_failure_not_dropped_in_silence(self):
        findings = edge_tls.hostname_findings(["ＡＢ!!"])
        self.assertEqual([s for s, _ in findings], ["fail"])

    def test_an_ordinary_name_produces_no_noise(self):
        self.assertEqual(edge_tls.hostname_findings(["gilead.local", "10.0.0.1"]), [])


class IPv6AddressFormTests(SimpleTestCase):
    """Django documents the bracketed form; a certificate cannot use it."""

    def test_a_bracketed_address_becomes_an_ip_san_not_a_dns_name(self):
        dns, ips = edge_tls.san_candidates(environ={}, allowed_hosts=["[fd00::1]"])
        self.assertEqual(dns, [])
        self.assertEqual(ips, ["fd00::1"])

    def test_brackets_and_a_port_together_are_also_understood(self):
        _dns, ips = edge_tls.san_candidates(
            environ={}, allowed_hosts=["[fd00::1]:10000"]
        )
        self.assertEqual(ips, ["fd00::1"])

    def test_an_unbracketed_address_is_not_mistaken_for_a_host_and_port(self):
        _dns, ips = edge_tls.san_candidates(environ={}, allowed_hosts=["fd00::1"])
        self.assertEqual(ips, ["fd00::1"])

    def test_an_ipv4_host_and_port_still_loses_only_the_port(self):
        _dns, ips = edge_tls.san_candidates(
            environ={}, allowed_hosts=["10.10.20.137:10000"]
        )
        self.assertEqual(ips, ["10.10.20.137"])

    def test_a_half_bracketed_entry_is_dropped_rather_than_guessed_at(self):
        self.assertEqual(edge_tls.normalize_hostname("[fd00::1"), "")


class AddressCanonicalisationTests(_CertDirMixin, SimpleTestCase):
    """Two spellings of one address must not read as two addresses."""

    def test_spellings_of_the_same_address_collapse(self):
        for written in ("FD00::0001", "fd00:0000::0001", "[FD00::1]"):
            with self.subTest(written=written):
                self.assertEqual(edge_tls.normalize_hostname(written), "fd00::1")

    def test_the_box_does_not_re_mint_its_certificate_on_every_boot(self):
        # The live bug: the certificate recorded the canonical "fd00::1", the
        # requested list held the operator's "FD00::0001", covers() compared strings,
        # and the box concluded forever that it did not cover its own address. On a
        # box that reboots with the mains that is a fresh keypair several times a day.
        dns, ips = edge_tls.san_candidates(environ={}, allowed_hosts=["FD00::0001"])
        first = edge_tls.ensure_certificate(self.tmp, dns, ips)
        self.assertEqual(first["action"], edge_tls.ACTION_ISSUED)
        for boot in range(2, 5):
            with self.subTest(boot=boot):
                again = edge_tls.ensure_certificate(self.tmp, dns, ips)
                self.assertEqual(again["action"], edge_tls.ACTION_NOOP)

    def test_a_certificate_records_the_canonical_form(self):
        result = edge_tls.issue_self_signed(
            directory=self.tmp, dns_names=[], ip_addresses=["FD00::0001"], days=30
        )
        facts = edge_tls.inspect_certificate(result["cert"])
        self.assertEqual(facts.ip_addresses, ("fd00::1",))


class DeclaredHostnameTests(SimpleTestCase):
    def test_explicit_configuration_wins_over_allowed_hosts(self):
        entries = edge_tls.declared_hostnames(
            environ={edge_tls.ENV_HOSTNAMES: "a.local, b.local"},
            allowed_hosts=["ignored.local"],
        )
        self.assertEqual(entries, ["a.local", "b.local"])

    def test_allowed_hosts_is_the_fallback(self):
        entries = edge_tls.declared_hostnames(environ={}, allowed_hosts=["c.local"])
        self.assertEqual(entries, ["c.local"])

    def test_entries_arrive_uncleaned_so_findings_can_report_what_was_written(self):
        entries = edge_tls.declared_hostnames(
            environ={edge_tls.ENV_HOSTNAMES: "[fd00::1]:10000"}
        )
        self.assertEqual(entries, ["[fd00::1]:10000"])


class LocalAddressDiscoveryFamilyTests(SimpleTestCase):
    """Discovery has to work on a segment that has no IPv4 on it."""

    def test_discovery_probes_both_families(self):
        # An IPv4-only sweep finds nothing on a v6 segment, and a box that discovers
        # nothing quietly asserts nothing.
        import inspect

        source = inspect.getsource(edge_tls.local_addresses)
        self.assertIn("AF_INET6", source)
        self.assertIn("getaddrinfo", source)

    def test_nothing_unroutable_is_ever_returned(self):
        for address in edge_tls.local_addresses(include_loopback=True):
            with self.subTest(address=address):
                parsed = edge_tls.ipaddress.ip_address(address)
                self.assertFalse(parsed.is_link_local)
                self.assertFalse(parsed.is_unspecified)
                self.assertFalse(parsed.is_multicast)

    def test_a_zone_id_does_not_crash_discovery(self):
        # getsockname() on a v6 socket can hand back "fe80::1%eth0"; ipaddress
        # rejects the zone id, and this runs at settings-load time on every box.
        self.assertEqual(edge_tls.normalize_hostname("fe80::1%eth0"), "")
        edge_tls.local_addresses()

    def test_discovery_never_raises(self):
        edge_tls.local_addresses()
        edge_tls.local_addresses(include_loopback=True)


class MobileTerminatorTests(SimpleTestCase):
    """Healing the certificate is half a heal if the site matcher stays pinned."""

    CERT = "/app/var/edge-tls/tls.crt"
    KEY = "/app/var/edge-tls/tls.key"

    def _mobile(self, **kwargs):
        return edge_tls.caddyfile(
            edge_tls.MODE_SELF_SIGNED,
            kwargs.pop("dns", ["gilead.local"]),
            kwargs.pop("ips", ["10.10.20.137"]),
            cert_path=self.CERT,
            key_path=self.KEY,
            address_may_change=True,
            **kwargs,
        )

    def test_a_mobile_box_serves_every_host(self):
        rendered = self._mobile()
        self.assertIn(":443 {", rendered)
        # The old address must not be pinned into the matcher, or the box answers
        # nothing at the address it just healed onto.
        self.assertNotIn("gilead.local, 10.10.20.137 {", rendered)

    def test_the_certificate_is_still_the_one_this_box_minted(self):
        self.assertIn(f"tls {self.CERT} {self.KEY}", self._mobile())

    def test_the_names_are_recorded_as_a_comment_for_whoever_reads_this_later(self):
        self.assertIn("# Names known when this was rendered: gilead.local", self._mobile())

    def test_caddys_internal_ca_cannot_serve_an_unknown_host(self):
        # `tls internal` needs names to issue for. Silently rendering it here would
        # produce a file that loads and then fails every handshake.
        with self.assertRaises(ValueError) as caught:
            edge_tls.caddyfile(
                edge_tls.MODE_SELF_SIGNED,
                ["gilead.local"],
                [],
                address_may_change=True,
            )
        self.assertIn("--issue-selfsigned", str(caught.exception))

    def test_a_mobile_box_still_answers_plain_http_with_a_redirect(self):
        rendered = self._mobile()
        self.assertIn(":80 {", rendered)
        self.assertIn("redir https://{host}{uri} 302", rendered)

    def test_the_redirect_is_never_permanent(self):
        # A 301 on a LAN host is the same one-way door HSTS is: cached by the
        # browser, and un-openable from the box. Assert on the DIRECTIVE -- the
        # comment above it says the word "301" for a reason and always should.
        directives = [
            line.strip()
            for line in self._mobile().splitlines()
            if line.strip().startswith("redir ")
        ]
        self.assertEqual(len(directives), 1)
        self.assertNotIn("301", directives[0])
        self.assertNotIn("permanent", directives[0])
        self.assertTrue(directives[0].endswith("302"))

    def test_a_box_with_no_names_yet_can_still_be_rendered_when_mobile(self):
        # First boot on DHCP: nothing is known about the address, and the file still
        # has to be valid.
        rendered = self._mobile(dns=[], ips=[])
        self.assertIn(":443 {", rendered)

    def test_a_pinned_box_is_completely_unchanged(self):
        rendered = edge_tls.caddyfile(
            edge_tls.MODE_SELF_SIGNED, ["gilead.local"], ["10.10.20.137"]
        )
        self.assertTrue(rendered.startswith("gilead.local, 10.10.20.137 {"))
        self.assertIn("tls internal", rendered)
        self.assertNotIn(":443 {", rendered)
        self.assertNotIn(":80 {", rendered)

    def test_mobility_is_meaningless_for_acme_and_is_ignored(self):
        # A public CA issues for NAMES; there is nothing to be mobile about, and the
        # named site block is what makes the ACME order work at all.
        rendered = edge_tls.caddyfile(
            edge_tls.MODE_ACME,
            ["sms.gilead-tech.org"],
            [],
            acme_email="ops@gilead-tech.org",
            address_may_change=True,
        )
        self.assertTrue(rendered.startswith("sms.gilead-tech.org {"))

    def test_mode_off_says_so_whatever_the_mobility_setting(self):
        rendered = edge_tls.caddyfile(
            edge_tls.MODE_OFF, ["gilead.local"], [], address_may_change=True
        )
        self.assertIn("no TLS terminator", rendered)


class ReissueStillNeedsARestartTests(_CertDirMixin, SimpleTestCase):
    """The terminator reads the files at config load, not per handshake."""

    def test_the_command_says_what_a_reissue_still_needs(self):
        import inspect

        from apps.schools.management.commands import edge_tls as command

        source = inspect.getsource(command.Command._ensure)
        self.assertIn("restart edge-tls", source)
        self.assertIn("OLD certificate", source)

    def test_the_files_themselves_are_healed_regardless(self):
        edge_tls.ensure_certificate(self.tmp, ["a.local"], ["10.0.0.1"])
        result = edge_tls.ensure_certificate(self.tmp, ["a.local"], ["10.0.0.99"])
        self.assertEqual(result["action"], edge_tls.ACTION_REISSUED)
        facts = edge_tls.inspect_certificate(os.path.join(self.tmp, "tls.crt"))
        self.assertIn("10.0.0.99", facts.ip_addresses)


class HostHeaderFormTests(SimpleTestCase):
    """The certificate wants a bare address; Django wants it bracketed."""

    def test_an_ipv6_address_is_bracketed(self):
        self.assertEqual(edge_tls.host_header_form("fd00::1"), "[fd00::1]")

    def test_an_ipv4_address_is_left_bare(self):
        self.assertEqual(edge_tls.host_header_form("10.10.20.137"), "10.10.20.137")

    def test_a_hostname_is_left_alone(self):
        self.assertEqual(edge_tls.host_header_form("gilead.local"), "gilead.local")

    def test_it_is_the_inverse_of_the_certificate_form(self):
        for written in ("[fd00::1]", "FD00::0001", "fd00::1"):
            with self.subTest(written=written):
                bare = edge_tls.normalize_hostname(written)
                self.assertEqual(bare, "fd00::1")
                self.assertEqual(edge_tls.host_header_form(bare), "[fd00::1]")

    def test_django_accepts_the_form_this_produces_and_not_the_other_one(self):
        # The point of the whole helper, asserted against Django itself rather than
        # against a belief about Django: a bare v6 entry in ALLOWED_HOSTS matches
        # nothing, and the request is a 400 that never mentions the address.
        from django.http.request import split_domain_port, validate_host

        domain, _port = split_domain_port("[fd00::1]:10000")
        self.assertFalse(validate_host(domain, ["fd00::1"]))
        self.assertTrue(validate_host(domain, [edge_tls.host_header_form("fd00::1")]))

    def test_settings_uses_it_when_folding_in_discovered_addresses(self):
        import inspect

        import config.settings as settings_module

        source = inspect.getsource(settings_module)
        self.assertIn("_edge_host_form(_edge_addr)", source)
        self.assertNotIn("ALLOWED_HOSTS.append(_edge_addr)", source)


class LocalAdviceTests(SimpleTestCase):
    """Advice that is wrong in a common locality is worse than no advice."""

    def test_the_dot_local_recommendation_carries_its_own_caveats(self):
        findings = edge_tls.stability_findings([], ["10.10.20.137"])
        message = findings[0][1]
        # A Windows domain literally named .local is common in schools, and its
        # domain controller answers instead of the box.
        self.assertIn("Windows domain", message)
        # School wifi with client isolation drops the multicast mDNS depends on.
        self.assertIn("client isolation", message)
