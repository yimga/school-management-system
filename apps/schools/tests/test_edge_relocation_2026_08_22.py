"""A box is a physical object, and physical objects move.

Rooms, campuses, countries, and -- after a failure -- new hardware entirely.
Exactly ONE thing on the box cannot be regenerated: the box CA's private key.
Everything else (leaf certificate, Caddyfile, ALLOWED_HOSTS, CSRF origins) is
derived and rebuilds in a minute.

That asymmetry is what these tests defend. Preserve the CA and a relocation is a
reissue nobody notices; lose it and every phone, laptop and tablet in the
building must be physically revisited.

Companion: ``test_edge_tls_2026_08_22.py`` covers the four modes themselves.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from apps.schools import edge_tls


class ClassifyHostTests(SimpleTestCase):
    """Which addresses can a public CA ever issue for?

    The answer decides which modes are possible at all, so getting it wrong
    silently offers a school a choice that cannot work.
    """

    def test_public_dns_name_is_publicly_issuable(self):
        self.assertEqual(edge_tls.classify_host("sms.gilead-tech.org"), edge_tls.HOST_PUBLIC_DNS)
        self.assertTrue(edge_tls.publicly_issuable("sms.gilead-tech.org"))

    def test_reserved_suffixes_are_private(self):
        for name in (
            "gilead.school.lan",
            "box.local",
            "thing.internal",
            "a.home.arpa",
            "x.test",
            "y.invalid",
            "z.localhost",
        ):
            with self.subTest(name=name):
                self.assertEqual(edge_tls.classify_host(name), edge_tls.HOST_PRIVATE_DNS)
                self.assertFalse(edge_tls.publicly_issuable(name))

    def test_single_label_name_is_private(self):
        # "gileadbox" resolves to a different machine in every building on earth.
        self.assertEqual(edge_tls.classify_host("gileadbox"), edge_tls.HOST_PRIVATE_DNS)

    def test_rfc1918_and_cgnat_are_private(self):
        for ip in ("10.10.20.137", "192.168.1.50", "172.16.4.4", "100.64.0.9", "169.254.1.1"):
            with self.subTest(ip=ip):
                self.assertEqual(edge_tls.classify_host(ip), edge_tls.HOST_PRIVATE_IP)
                self.assertFalse(edge_tls.publicly_issuable(ip))

    def test_loopback_is_distinguished_from_private(self):
        # Distinct because "you gave me localhost" needs a different sentence
        # than "you gave me a LAN address".
        self.assertEqual(edge_tls.classify_host("127.0.0.1"), edge_tls.HOST_LOOPBACK)
        self.assertEqual(edge_tls.classify_host("::1"), edge_tls.HOST_LOOPBACK)

    def test_public_ip_is_issuable(self):
        self.assertEqual(edge_tls.classify_host("8.8.8.8"), edge_tls.HOST_PUBLIC_IP)

    def test_port_is_stripped_before_classifying(self):
        # CSRF_TRUSTED_ORIGINS entries carry ports; a certificate names the host.
        self.assertEqual(edge_tls.classify_host("10.10.20.137:10000"), edge_tls.HOST_PRIVATE_IP)

    def test_empty_is_treated_as_private_not_crash(self):
        self.assertEqual(edge_tls.classify_host(""), edge_tls.HOST_PRIVATE_DNS)
        self.assertEqual(edge_tls.classify_host(None), edge_tls.HOST_PRIVATE_DNS)


class ModeFeasibilityTests(SimpleTestCase):
    """Is the chosen mode achievable for these addresses?"""

    def test_acme_on_a_lan_only_box_is_a_hard_fail(self):
        findings = edge_tls.mode_feasibility(
            edge_tls.MODE_ACME, ["gilead.school.lan"], ["10.10.20.137"]
        )
        self.assertTrue(findings)
        self.assertEqual(findings[0][0], "fail")
        self.assertIn("10.10.20.137", findings[0][1])

    def test_acme_mixing_public_and_private_still_fails_entirely(self):
        # The subtle one: an ACME order is all-or-nothing. A single private name
        # means NO certificate, not a partial one covering the public name -- and
        # a school that believes otherwise waits for a certificate forever.
        findings = edge_tls.mode_feasibility(
            edge_tls.MODE_ACME, ["sms.gilead-tech.org", "gilead.school.lan"], []
        )
        self.assertEqual([s for s, _ in findings], ["fail"])
        self.assertIn("gilead.school.lan", findings[0][1])
        self.assertNotIn("sms.gilead-tech.org", findings[0][1])

    def test_acme_on_a_public_name_is_allowed_but_warns_about_renewal(self):
        findings = edge_tls.mode_feasibility(
            edge_tls.MODE_ACME, ["sms.gilead-tech.org"], []
        )
        self.assertEqual([s for s, _ in findings], ["warn"])
        self.assertIn("renewal", findings[0][1].lower())

    def test_acme_with_no_addresses_fails(self):
        findings = edge_tls.mode_feasibility(edge_tls.MODE_ACME, [], [])
        self.assertEqual([s for s, _ in findings], ["fail"])

    def test_provided_on_a_private_name_warns_about_needing_an_internal_ca(self):
        findings = edge_tls.mode_feasibility(
            edge_tls.MODE_PROVIDED, ["gilead.school.lan"], []
        )
        self.assertEqual([s for s, _ in findings], ["warn"])
        self.assertIn("internal CA", findings[0][1])

    def test_selfsigned_is_always_feasible_for_real_addresses(self):
        self.assertEqual(
            edge_tls.mode_feasibility(
                edge_tls.MODE_SELF_SIGNED, ["gilead.school.lan"], ["10.10.20.137"]
            ),
            [],
        )

    def test_selfsigned_with_nothing_to_assert_fails(self):
        findings = edge_tls.mode_feasibility(edge_tls.MODE_SELF_SIGNED, [], [])
        self.assertEqual([s for s, _ in findings], ["fail"])

    def test_off_mode_has_no_certificate_opinion(self):
        self.assertEqual(edge_tls.mode_feasibility(edge_tls.MODE_OFF, [], []), [])


class _CertDirMixin:
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="rmc-reloc-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _issue(self, directory=None, dns=None, ips=None):
        return edge_tls.issue_self_signed(
            directory=directory or self.tmp,
            dns_names=dns if dns is not None else ["gilead.school.lan"],
            ip_addresses=ips if ips is not None else ["10.10.20.137"],
        )

    def _ca_fingerprint(self, directory):
        facts = edge_tls.inspect_certificate(os.path.join(directory, "ca.crt"))
        self.assertTrue(facts.exists, "expected a CA at %s" % directory)
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes

        with open(os.path.join(directory, "ca.crt"), "rb") as handle:
            cert = x509.load_pem_x509_certificate(handle.read())
        return cert.fingerprint(hashes.SHA256()).hex()


class ClockTests(_CertDirMixin, SimpleTestCase):
    """A box shipped across a border with a dead RTC rejects its own certificate."""

    def test_clock_before_the_box_ca_existed_is_blamed_on_the_clock(self):
        self._issue()
        leaf = edge_tls.inspect_certificate(os.path.join(self.tmp, "tls.crt"))
        ca = edge_tls.inspect_certificate(os.path.join(self.tmp, "ca.crt"))
        findings = edge_tls.clock_findings(
            leaf, ca, now=datetime(2019, 3, 1, tzinfo=timezone.utc)
        )
        self.assertEqual([s for s, _ in findings], ["fail"])
        # The message must point at the clock, not the certificate: an operator who
        # reissues against a bad clock only bakes the error in.
        self.assertIn("clock is wrong, not the", findings[0][1])

    def test_a_healthy_clock_produces_no_findings(self):
        self._issue()
        leaf = edge_tls.inspect_certificate(os.path.join(self.tmp, "tls.crt"))
        ca = edge_tls.inspect_certificate(os.path.join(self.tmp, "ca.crt"))
        self.assertEqual(edge_tls.clock_findings(leaf, ca), [])

    def test_not_yet_valid_leaf_is_reported_even_without_a_ca_floor(self):
        self._issue()
        leaf = edge_tls.inspect_certificate(os.path.join(self.tmp, "tls.crt"))
        before = datetime.fromisoformat(leaf.not_before) - timedelta(days=2)
        findings = edge_tls.clock_findings(leaf, None, now=before)
        self.assertEqual([s for s, _ in findings], ["fail"])

    def test_missing_ca_facts_do_not_crash(self):
        self._issue()
        leaf = edge_tls.inspect_certificate(os.path.join(self.tmp, "tls.crt"))
        absent = edge_tls.inspect_certificate(os.path.join(self.tmp, "nope.crt"))
        self.assertEqual(edge_tls.clock_findings(leaf, absent), [])


class CaPortabilityTests(_CertDirMixin, SimpleTestCase):
    """The CA is the only irreplaceable thing on the box."""

    PW = b"a-real-passphrase-for-tests"

    def test_export_refuses_without_a_passphrase(self):
        self._issue()
        with self.assertRaises(ValueError):
            edge_tls.export_ca_bundle(passphrase=b"", directory=self.tmp)

    def test_export_refuses_when_there_is_no_ca(self):
        with self.assertRaises(FileNotFoundError):
            edge_tls.export_ca_bundle(passphrase=self.PW, directory=self.tmp)

    def test_relocation_onto_new_hardware_preserves_device_trust(self):
        # The whole point. Ghana box -> export -> new appliance in another country
        # with a different name AND a different IP -> devices notice nothing.
        self._issue()
        original = self._ca_fingerprint(self.tmp)
        bundle = edge_tls.export_ca_bundle(passphrase=self.PW, directory=self.tmp)

        new_box = tempfile.mkdtemp(prefix="rmc-newbox-")
        self.addCleanup(shutil.rmtree, new_box, True)
        edge_tls.import_ca_bundle(bundle, self.PW, directory=new_box)
        self._issue(directory=new_box, dns=["gilead.uk.lan"], ips=["192.168.9.20"])

        self.assertEqual(self._ca_fingerprint(new_box), original)
        leaf = edge_tls.inspect_certificate(os.path.join(new_box, "tls.crt"))
        self.assertIn("gilead.uk.lan", leaf.dns_names)
        self.assertIn("192.168.9.20", leaf.ip_addresses)

    def test_wrong_passphrase_is_rejected(self):
        self._issue()
        bundle = edge_tls.export_ca_bundle(passphrase=self.PW, directory=self.tmp)
        new_box = tempfile.mkdtemp(prefix="rmc-newbox-")
        self.addCleanup(shutil.rmtree, new_box, True)
        with self.assertRaises(Exception):
            edge_tls.import_ca_bundle(bundle, b"not-the-passphrase", directory=new_box)

    def test_a_leaf_bundle_is_not_accepted_as_a_ca(self):
        # Restoring a leaf would appear to work and re-establish nothing.
        self._issue()
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.serialization import pkcs12

        with open(os.path.join(self.tmp, "tls.crt"), "rb") as handle:
            leaf = x509.load_pem_x509_certificates(handle.read())[0]
        with open(os.path.join(self.tmp, "tls.key"), "rb") as handle:
            key = serialization.load_pem_private_key(handle.read(), password=None)
        blob = pkcs12.serialize_key_and_certificates(
            name=b"leaf",
            key=key,
            cert=leaf,
            cas=None,
            encryption_algorithm=serialization.BestAvailableEncryption(self.PW),
        )
        target = tempfile.mkdtemp(prefix="rmc-leaf-")
        self.addCleanup(shutil.rmtree, target, True)
        with self.assertRaises(ValueError) as ctx:
            edge_tls.import_ca_bundle(blob, self.PW, directory=target)
        self.assertIn("not a CA", str(ctx.exception))

    def test_restoring_over_a_different_ca_is_refused_without_force(self):
        # The ordering mistake: a tech issues on the new box FIRST, minting a
        # competing CA, and only then remembers the backup. Overwriting silently
        # would be fine -- but so would NOT overwriting, and one of those strands
        # every device. Refuse and make them say which they mean.
        self._issue()
        bundle = edge_tls.export_ca_bundle(passphrase=self.PW, directory=self.tmp)
        other = tempfile.mkdtemp(prefix="rmc-other-")
        self.addCleanup(shutil.rmtree, other, True)
        self._issue(directory=other, dns=["somewhere.else.lan"], ips=[])
        with self.assertRaises(FileExistsError):
            edge_tls.import_ca_bundle(bundle, self.PW, directory=other)

    def test_force_replaces_a_different_ca_and_says_so(self):
        self._issue()
        bundle = edge_tls.export_ca_bundle(passphrase=self.PW, directory=self.tmp)
        other = tempfile.mkdtemp(prefix="rmc-other-")
        self.addCleanup(shutil.rmtree, other, True)
        self._issue(directory=other, dns=["somewhere.else.lan"], ips=[])
        info = edge_tls.import_ca_bundle(bundle, self.PW, directory=other, force=True)
        self.assertTrue(info["replaced"])
        self.assertEqual(self._ca_fingerprint(other), self._ca_fingerprint(self.tmp))

    def test_reimporting_the_same_ca_is_not_treated_as_a_conflict(self):
        # Re-running a restore must be safe; an idempotent step people repeat.
        self._issue()
        bundle = edge_tls.export_ca_bundle(passphrase=self.PW, directory=self.tmp)
        info = edge_tls.import_ca_bundle(bundle, self.PW, directory=self.tmp)
        self.assertTrue(info["replaced"])

    def test_restored_key_is_loadable_and_actually_signs(self):
        # A bundle that restores files but produces an unusable key would pass a
        # naive existence check and fail at the first reissue.
        self._issue()
        bundle = edge_tls.export_ca_bundle(passphrase=self.PW, directory=self.tmp)
        new_box = tempfile.mkdtemp(prefix="rmc-newbox-")
        self.addCleanup(shutil.rmtree, new_box, True)
        edge_tls.import_ca_bundle(bundle, self.PW, directory=new_box)
        result = self._issue(directory=new_box, dns=["proof.lan"], ips=[])
        self.assertTrue(result.get("reused_ca"))


class RelocationPlanTests(SimpleTestCase):
    """Order is the product here; the steps themselves are the easy part."""

    def test_the_ca_export_is_always_the_first_step_for_selfsigned(self):
        for changes in (
            {edge_tls.CHANGE_ADDRESS},
            {edge_tls.CHANGE_COUNTRY, edge_tls.CHANGE_HARDWARE},
            {edge_tls.CHANGE_SITE},
        ):
            with self.subTest(changes=sorted(changes)):
                steps = edge_tls.relocation_plan(edge_tls.MODE_SELF_SIGNED, changes)
                self.assertIn("export the box CA", steps[0])

    def test_hardware_replacement_restores_the_ca_before_issuing(self):
        steps = edge_tls.relocation_plan(
            edge_tls.MODE_SELF_SIGNED,
            {edge_tls.CHANGE_HARDWARE, edge_tls.CHANGE_ADDRESS},
        )
        restore = next(i for i, s in enumerate(steps) if "--import-ca" in s)
        issue = next(i for i, s in enumerate(steps) if "--issue-selfsigned" in s)
        self.assertLess(restore, issue, "restoring the CA must precede issuing a leaf")

    def test_caddyfile_is_rendered_after_the_certificate_exists(self):
        steps = edge_tls.relocation_plan(
            edge_tls.MODE_SELF_SIGNED, {edge_tls.CHANGE_ADDRESS}
        )
        issue = next(i for i, s in enumerate(steps) if "--issue-selfsigned" in s)
        render = next(i for i, s in enumerate(steps) if "--print-caddyfile" in s)
        self.assertLess(issue, render)

    def test_acme_with_live_hsts_is_warned_before_anything_else_happens(self):
        steps = edge_tls.relocation_plan(
            edge_tls.MODE_ACME, {edge_tls.CHANGE_COUNTRY}, hsts_seconds=31536000
        )
        hsts = next(i for i, s in enumerate(steps) if "HSTS" in s)
        deploy = next(i for i, s in enumerate(steps) if "up -d" in s)
        self.assertLess(hsts, deploy)

    def test_no_hsts_warning_when_hsts_is_already_zero(self):
        steps = edge_tls.relocation_plan(
            edge_tls.MODE_SELF_SIGNED, {edge_tls.CHANGE_COUNTRY}, hsts_seconds=0
        )
        self.assertFalse([s for s in steps if "HSTS" in s])

    def test_acme_move_warns_about_stale_dns_before_deploying(self):
        steps = edge_tls.relocation_plan(edge_tls.MODE_ACME, {edge_tls.CHANGE_COUNTRY})
        self.assertTrue([s for s in steps if "DNS" in s and "renewal" in s])

    def test_country_change_covers_timezone_and_the_clock(self):
        steps = edge_tls.relocation_plan(
            edge_tls.MODE_SELF_SIGNED, {edge_tls.CHANGE_COUNTRY}
        )
        self.assertTrue([s for s in steps if "TIME_ZONE" in s])
        self.assertTrue([s for s in steps if "RTC" in s or "NTP" in s])

    def test_country_change_raises_data_residency_before_the_move(self):
        steps = edge_tls.relocation_plan(
            edge_tls.MODE_SELF_SIGNED, {edge_tls.CHANGE_COUNTRY}
        )
        residency = next(i for i, s in enumerate(steps) if "jurisdiction" in s)
        deploy = next(i for i, s in enumerate(steps) if "up -d" in s)
        self.assertLess(residency, deploy)

    def test_acme_plan_does_not_talk_about_a_box_ca(self):
        # An acme box has no private CA; telling its operator to clean one off
        # devices is advice for a different appliance.
        steps = edge_tls.relocation_plan(
            edge_tls.MODE_ACME, {edge_tls.CHANGE_COUNTRY, edge_tls.CHANGE_SITE}
        )
        self.assertFalse([s for s in steps if "still trust this box's CA" in s])

    def test_selfsigned_site_move_does_flag_devices_left_behind(self):
        steps = edge_tls.relocation_plan(
            edge_tls.MODE_SELF_SIGNED, {edge_tls.CHANGE_SITE}
        )
        self.assertTrue([s for s in steps if "still trust this box's CA" in s])

    def test_provided_mode_says_a_new_address_needs_a_new_certificate(self):
        # There is no local way to add a name to a purchased certificate, and an
        # operator who expects --force to work here loses an afternoon.
        steps = edge_tls.relocation_plan(
            edge_tls.MODE_PROVIDED, {edge_tls.CHANGE_ADDRESS}
        )
        self.assertTrue([s for s in steps if "replacement certificate files" in s])

    def test_every_plan_ends_by_verifying(self):
        for mode in edge_tls.TLS_MODES:
            for changes in ({edge_tls.CHANGE_ADDRESS}, {edge_tls.CHANGE_COUNTRY}):
                with self.subTest(mode=mode, changes=sorted(changes)):
                    steps = edge_tls.relocation_plan(mode, changes)
                    deploy = next(
                        (i for i, s in enumerate(steps) if "check_edge_readiness" in s),
                        None,
                    )
                    self.assertIsNotNone(deploy, f"{mode} plan never verifies")

    def test_unknown_mode_is_rejected_rather_than_silently_planned(self):
        with self.assertRaises(edge_tls.UnknownTlsMode):
            edge_tls.relocation_plan("banana", {edge_tls.CHANGE_ADDRESS})


class LocalAddressDiscoveryTests(SimpleTestCase):
    """What the box thinks its own addresses are."""

    def test_returns_parseable_addresses(self):
        for address in edge_tls.local_addresses():
            with self.subTest(address=address):
                self.assertTrue(str(edge_tls.ipaddress.ip_address(address)))

    def test_loopback_and_link_local_are_excluded_by_default(self):
        # Nobody reaches a school box at 127.0.0.1 or 169.254.x; putting them in a
        # certificate only makes the SAN list harder to read.
        for address in edge_tls.local_addresses():
            parsed = edge_tls.ipaddress.ip_address(address)
            self.assertFalse(parsed.is_loopback)
            self.assertFalse(parsed.is_link_local)

    def test_include_loopback_only_widens_the_result(self):
        # The flag stops loopback being filtered OUT; it does not go looking for it.
        # Whether 127.0.0.1 is discovered at all depends on the host's routing table
        # and resolver, so the contract that always holds is superset-ness.
        narrow = set(edge_tls.local_addresses())
        wide = set(edge_tls.local_addresses(include_loopback=True))
        self.assertTrue(narrow.issubset(wide))
        self.assertFalse(
            any(edge_tls.ipaddress.ip_address(a).is_loopback for a in narrow)
        )

    def test_discovery_never_raises(self):
        # Runs at settings-load time on every box; an exception here is a box that
        # will not start.
        edge_tls.local_addresses()
        edge_tls.local_addresses(include_loopback=True)


class TrustAndRenewalSettingTests(SimpleTestCase):
    def test_trust_local_is_off_unless_asked_for(self):
        self.assertFalse(edge_tls.trust_local_addresses(environ={}))
        for value in ("0", "false", "no", "off", "", "banana"):
            with self.subTest(value=value):
                self.assertFalse(
                    edge_tls.trust_local_addresses(
                        environ={edge_tls.ENV_TRUST_LOCAL: value}
                    )
                )

    def test_trust_local_accepts_the_usual_truthy_spellings(self):
        for value in ("1", "true", "TRUE", "yes", "on"):
            with self.subTest(value=value):
                self.assertTrue(
                    edge_tls.trust_local_addresses(
                        environ={edge_tls.ENV_TRUST_LOCAL: value}
                    )
                )

    def test_renew_window_falls_back_on_nonsense_rather_than_crashing(self):
        self.assertEqual(
            edge_tls.renew_before_days(environ={}), edge_tls.DEFAULT_RENEW_BEFORE_DAYS
        )
        for bad in ("", "soon", "-5", "0"):
            with self.subTest(bad=bad):
                self.assertEqual(
                    edge_tls.renew_before_days(environ={edge_tls.ENV_RENEW_BEFORE: bad}),
                    edge_tls.DEFAULT_RENEW_BEFORE_DAYS,
                )
        self.assertEqual(
            edge_tls.renew_before_days(environ={edge_tls.ENV_RENEW_BEFORE: "45"}), 45
        )


class EffectiveAddressTests(SimpleTestCase):
    def test_without_opt_in_only_the_declared_addresses_are_used(self):
        env = {edge_tls.ENV_HOSTNAMES: "gilead.local,10.10.20.137"}
        dns, ips = edge_tls.effective_addresses(environ=env)
        self.assertEqual(dns, ["gilead.local"])
        self.assertEqual(ips, ["10.10.20.137"])

    def test_with_opt_in_the_boxes_own_addresses_are_folded_in(self):
        env = {
            edge_tls.ENV_HOSTNAMES: "gilead.local,10.10.20.137",
            edge_tls.ENV_TRUST_LOCAL: "1",
        }
        dns, ips = edge_tls.effective_addresses(environ=env)
        self.assertEqual(dns, ["gilead.local"])
        self.assertIn("10.10.20.137", ips)
        for address in edge_tls.local_addresses():
            self.assertIn(address, ips)

    def test_opt_in_does_not_duplicate_an_already_declared_address(self):
        held = edge_tls.local_addresses()
        if not held:
            self.skipTest("no non-loopback address on this host")
        env = {
            edge_tls.ENV_HOSTNAMES: held[0],
            edge_tls.ENV_TRUST_LOCAL: "1",
        }
        _dns, ips = edge_tls.effective_addresses(environ=env)
        self.assertEqual(ips.count(held[0]), 1)


class CertificateNeedsReissueTests(_CertDirMixin, SimpleTestCase):
    def test_missing_certificate_needs_issuing(self):
        facts = edge_tls.inspect_certificate(os.path.join(self.tmp, "tls.crt"))
        needed, reason = edge_tls.certificate_needs_reissue(facts, ["a.local"], [])
        self.assertTrue(needed)
        self.assertIn("no certificate", reason)

    def test_a_covering_current_certificate_needs_nothing(self):
        self._issue(dns=["a.local"], ips=["10.0.0.1"])
        facts = edge_tls.inspect_certificate(os.path.join(self.tmp, "tls.crt"))
        needed, _reason = edge_tls.certificate_needs_reissue(
            facts, ["a.local"], ["10.0.0.1"]
        )
        self.assertFalse(needed)

    def test_an_uncovered_address_names_itself_in_the_reason(self):
        self._issue(dns=["a.local"], ips=["10.0.0.1"])
        facts = edge_tls.inspect_certificate(os.path.join(self.tmp, "tls.crt"))
        needed, reason = edge_tls.certificate_needs_reissue(
            facts, ["a.local"], ["10.0.0.99"]
        )
        self.assertTrue(needed)
        self.assertIn("10.0.0.99", reason)

    def test_a_leaf_dated_in_the_future_is_reissued_not_refused(self):
        # A box whose clock briefly ran 20 years fast leaves behind a leaf that is
        # "not yet valid" once the clock is corrected. Every other check calls that
        # certificate healthy -- it covers everything and is nowhere near expiry --
        # so without this the box would serve an unusable certificate forever.
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=365 * 20)
        stranded = edge_tls.CertificateFacts(
            path="tls.crt",
            exists=True,
            readable=True,
            dns_names=("a.local",),
            ip_addresses=("10.0.0.1",),
            not_before=future.isoformat(),
            not_after=(future + timedelta(days=825)).isoformat(),
            days_remaining=825 + 365 * 20,
        )
        needed, reason = edge_tls.certificate_needs_reissue(
            stranded, ["a.local"], ["10.0.0.1"], _now=now
        )
        self.assertTrue(needed)
        self.assertIn("not valid until", reason)

    def test_near_expiry_triggers_renewal(self):
        edge_tls.issue_self_signed(
            directory=self.tmp, dns_names=["a.local"], ip_addresses=[], days=10
        )
        facts = edge_tls.inspect_certificate(os.path.join(self.tmp, "tls.crt"))
        needed, reason = edge_tls.certificate_needs_reissue(
            facts, ["a.local"], [], renew_before_days=30
        )
        self.assertTrue(needed)
        self.assertIn("expires", reason)


class EnsureCertificateTests(_CertDirMixin, SimpleTestCase):
    """The self-heal. Safe to run on every boot; acts only when something is wrong."""

    def test_first_boot_issues(self):
        result = edge_tls.ensure_certificate(self.tmp, ["a.local"], ["10.0.0.1"])
        self.assertEqual(result["action"], edge_tls.ACTION_ISSUED)

    def test_second_run_with_nothing_changed_does_nothing(self):
        edge_tls.ensure_certificate(self.tmp, ["a.local"], ["10.0.0.1"])
        result = edge_tls.ensure_certificate(self.tmp, ["a.local"], ["10.0.0.1"])
        self.assertEqual(result["action"], edge_tls.ACTION_NOOP)

    def test_a_new_dhcp_lease_reissues_and_keeps_the_ca(self):
        # The whole point: the address moved, and not one device is revisited.
        edge_tls.ensure_certificate(self.tmp, ["a.local"], ["10.0.0.1"])
        before = self._ca_fingerprint(self.tmp)
        result = edge_tls.ensure_certificate(self.tmp, ["a.local"], ["10.0.0.99"])
        self.assertEqual(result["action"], edge_tls.ACTION_REISSUED)
        self.assertTrue(result["reused_ca"])
        self.assertEqual(self._ca_fingerprint(self.tmp), before)
        leaf = edge_tls.inspect_certificate(os.path.join(self.tmp, "tls.crt"))
        self.assertIn("10.0.0.99", leaf.ip_addresses)

    def test_a_campus_move_with_a_new_name_and_subnet_also_keeps_the_ca(self):
        edge_tls.ensure_certificate(self.tmp, ["a.local"], ["10.0.0.1"])
        before = self._ca_fingerprint(self.tmp)
        result = edge_tls.ensure_certificate(
            self.tmp, ["a.local", "new.site.lan"], ["192.168.44.10"]
        )
        self.assertEqual(result["action"], edge_tls.ACTION_REISSUED)
        self.assertEqual(self._ca_fingerprint(self.tmp), before)

    def test_expiry_renews_itself(self):
        edge_tls.issue_self_signed(
            directory=self.tmp, dns_names=["a.local"], ip_addresses=[], days=10
        )
        before = self._ca_fingerprint(self.tmp)
        result = edge_tls.ensure_certificate(
            self.tmp, ["a.local"], [], renew_before_days=30
        )
        self.assertEqual(result["action"], edge_tls.ACTION_REISSUED)
        self.assertEqual(self._ca_fingerprint(self.tmp), before)

    def test_an_impossible_clock_refuses_rather_than_baking_the_error_in(self):
        # A box whose RTC died in transit believes it is years ago. Reissuing then
        # writes a certificate that is genuinely not-yet-valid, turning one
        # recoverable fault into two.
        edge_tls.ensure_certificate(self.tmp, ["a.local"], ["10.0.0.1"])
        leaf_before = edge_tls.inspect_certificate(os.path.join(self.tmp, "tls.crt"))
        result = edge_tls.ensure_certificate(
            self.tmp,
            ["a.local"],
            ["10.0.0.99"],
            now=datetime(2019, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(result["action"], edge_tls.ACTION_REFUSED)
        self.assertIn("clock", result["reason"])
        leaf_after = edge_tls.inspect_certificate(os.path.join(self.tmp, "tls.crt"))
        self.assertEqual(leaf_before.ip_addresses, leaf_after.ip_addresses)

    def test_a_refusal_does_not_destroy_anything(self):
        edge_tls.ensure_certificate(self.tmp, ["a.local"], ["10.0.0.1"])
        edge_tls.ensure_certificate(
            self.tmp, ["a.local"], ["10.0.0.2"],
            now=datetime(2019, 1, 1, tzinfo=timezone.utc),
        )
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "tls.crt")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "ca.crt")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "ca.key")))

    def test_repeated_self_heals_never_mint_a_second_ca(self):
        # A box that flaps between addresses must not accumulate CAs.
        edge_tls.ensure_certificate(self.tmp, ["a.local"], ["10.0.0.1"])
        first = self._ca_fingerprint(self.tmp)
        for octet in range(2, 8):
            edge_tls.ensure_certificate(self.tmp, ["a.local"], [f"10.0.0.{octet}"])
            self.assertEqual(self._ca_fingerprint(self.tmp), first)


class AddressStabilityTests(SimpleTestCase):
    def test_an_ip_only_box_is_warned_about(self):
        findings = edge_tls.stability_findings([], ["10.10.20.137"])
        self.assertEqual([s for s, _ in findings], ["warn"])
        self.assertIn("10.10.20.137", findings[0][1])

    def test_an_mdns_name_is_the_clean_configuration(self):
        self.assertEqual(edge_tls.stability_findings(["gilead.local"], ["10.10.20.137"]), [])

    def test_a_lan_name_needing_dns_is_flagged_as_needing_resolution(self):
        findings = edge_tls.stability_findings(["gilead.school.lan"], ["10.10.20.137"])
        self.assertTrue(findings)
        self.assertIn("resolve", findings[0][1])

    def test_a_public_name_is_not_flagged(self):
        self.assertEqual(
            edge_tls.stability_findings(["sms.gilead-tech.org"], ["8.8.8.8"]), []
        )
