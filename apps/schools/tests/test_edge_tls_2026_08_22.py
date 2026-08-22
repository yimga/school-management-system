"""The sovereign box's TLS decision: modes, derived flags, certificates, transitions.

Item 3 of the 2026-08-22 box report was "what is the purpose of make this device
offline ready when every time I put in the PIN I get 'Local access could not be
enabled on this browser'". The answer is that the box serves plain HTTP, WebCrypto is
withheld outside a secure context, and no browser can help. These tests pin the
policy that lets a school fix that -- and, just as importantly, unfix it.
"""
from __future__ import annotations

import os
import tempfile

from django.test import SimpleTestCase

from apps.schools import edge_tls


class ModeNormalisationTests(SimpleTestCase):
    def test_canonical_modes_round_trip(self):
        for mode in edge_tls.TLS_MODES:
            self.assertEqual(edge_tls.normalize_mode(mode), mode)

    def test_ca_means_provided_not_acme(self):
        # A certificate FROM a certificate authority arrives as files. ACME is a
        # protocol for getting one automatically, not a different kind of authority.
        self.assertEqual(edge_tls.normalize_mode("ca"), edge_tls.MODE_PROVIDED)
        self.assertEqual(edge_tls.normalize_mode("internal-ca"), edge_tls.MODE_PROVIDED)

    def test_operator_spellings(self):
        for raw, expected in (
            ("Self-Signed", edge_tls.MODE_SELF_SIGNED),
            ("SELF_SIGNED", edge_tls.MODE_SELF_SIGNED),
            ("  LetsEncrypt  ", edge_tls.MODE_ACME),
            ("none", edge_tls.MODE_OFF),
            ("", edge_tls.MODE_OFF),
        ):
            self.assertEqual(edge_tls.normalize_mode(raw), expected, raw)

    def test_typo_raises_rather_than_defaulting(self):
        # Silently coercing a typo to `off` would hand a school plain HTTP while its
        # runbook says HTTPS, and nothing downstream would disagree.
        with self.assertRaises(edge_tls.UnknownTlsMode):
            edge_tls.normalize_mode("htps")

    def test_every_mode_has_a_summary(self):
        for mode in edge_tls.TLS_MODES:
            self.assertIn(mode, edge_tls.MODE_SUMMARY)
            self.assertTrue(edge_tls.MODE_SUMMARY[mode].strip())


class ResolutionTests(SimpleTestCase):
    def test_unset_resolves_to_off_from_default(self):
        resolution = edge_tls.resolve_mode({})
        self.assertEqual(resolution.mode, edge_tls.MODE_OFF)
        self.assertEqual(resolution.source, "default")
        self.assertFalse(resolution.error)

    def test_env_wins_and_names_its_source(self):
        resolution = edge_tls.resolve_mode({edge_tls.ENV_MODE: "ca"})
        self.assertEqual(resolution.mode, edge_tls.MODE_PROVIDED)
        self.assertEqual(resolution.source, edge_tls.ENV_MODE)
        self.assertTrue(resolution.serves_https)

    def test_typo_falls_back_to_off_but_CARRIES_the_error(self):
        # Safe to boot, loud to readiness. A box that quietly serves HTTP under a
        # config claiming HTTPS is the failure this guards.
        resolution = edge_tls.resolve_mode({edge_tls.ENV_MODE: "htps"})
        self.assertEqual(resolution.mode, edge_tls.MODE_OFF)
        self.assertIn("htps", resolution.error)


class DerivedFlagTests(SimpleTestCase):
    def test_off_turns_the_lan_http_login_breakers_off(self):
        self.assertEqual(
            edge_tls.derived_security_flags(edge_tls.MODE_OFF),
            {
                "SECURE_SSL_REDIRECT": False,
                "SESSION_COOKIE_SECURE": False,
                "CSRF_COOKIE_SECURE": False,
                "SECURE_HSTS_SECONDS": 0,
            },
        )

    def test_https_modes_turn_them_on(self):
        for mode in (edge_tls.MODE_SELF_SIGNED, edge_tls.MODE_PROVIDED, edge_tls.MODE_ACME):
            flags = edge_tls.derived_security_flags(mode)
            self.assertTrue(flags["SECURE_SSL_REDIRECT"], mode)
            self.assertTrue(flags["SESSION_COOKIE_SECURE"], mode)
            self.assertTrue(flags["CSRF_COOKIE_SECURE"], mode)

    def test_hsts_stays_off_for_every_LAN_mode(self):
        # THE load-bearing assertion. HSTS on a .lan name or an IP tells every browser
        # to refuse plain HTTP to that origin for a year, and a LAN origin is one a
        # DIFFERENT box may hold next term. Turning it on makes the school's choice
        # irreversible from the browser side, with no remedy but per-device surgery.
        for mode in (edge_tls.MODE_SELF_SIGNED, edge_tls.MODE_PROVIDED):
            self.assertEqual(
                edge_tls.derived_security_flags(mode)["SECURE_HSTS_SECONDS"], 0, mode
            )

    def test_only_acme_gets_hsts(self):
        self.assertEqual(
            edge_tls.derived_security_flags(edge_tls.MODE_ACME)["SECURE_HSTS_SECONDS"],
            31536000,
        )


class SanCandidateTests(SimpleTestCase):
    def test_ips_and_names_are_separated(self):
        # An IP placed in a DNSName SAN is ignored by every browser -- the classic
        # reason a hand-rolled LAN certificate still warns at the address on the sticker.
        dns, ips = edge_tls.san_candidates(
            {edge_tls.ENV_HOSTNAMES: "gilead.school.lan, 10.10.20.137"}
        )
        self.assertEqual(dns, ["gilead.school.lan"])
        self.assertEqual(ips, ["10.10.20.137"])

    def test_ports_are_stripped(self):
        dns, ips = edge_tls.san_candidates({edge_tls.ENV_HOSTNAMES: "10.10.20.137:10000"})
        self.assertEqual(ips, ["10.10.20.137"])
        self.assertEqual(dns, [])

    def test_wildcards_are_dropped(self):
        # "*" in ALLOWED_HOSTS means "we did not decide"; a certificate cannot assert it.
        dns, ips = edge_tls.san_candidates({}, allowed_hosts=["*", "box.school.lan"])
        self.assertEqual(dns, ["box.school.lan"])
        self.assertEqual(ips, [])

    def test_env_overrides_allowed_hosts(self):
        dns, _ = edge_tls.san_candidates(
            {edge_tls.ENV_HOSTNAMES: "explicit.school.lan"},
            allowed_hosts=["ignored.school.lan"],
        )
        self.assertEqual(dns, ["explicit.school.lan"])

    def test_duplicates_collapse(self):
        dns, _ = edge_tls.san_candidates(
            {edge_tls.ENV_HOSTNAMES: "a.school.lan, A.SCHOOL.LAN, a.school.lan."}
        )
        self.assertEqual(dns, ["a.school.lan"])


class CertificateIssuanceTests(SimpleTestCase):
    def test_issues_a_chain_with_correct_san_types(self):
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory, ["gilead.school.lan"], ["10.10.20.137"], days=30
            )
            facts = edge_tls.inspect_certificate(os.path.join(directory, "tls.crt"))
            self.assertTrue(facts.readable, facts.error)
            self.assertEqual(facts.dns_names, ("gilead.school.lan",))
            self.assertEqual(facts.ip_addresses, ("10.10.20.137",))
            self.assertEqual(facts.covers(["gilead.school.lan"], ["10.10.20.137"]), [])

    def test_leaf_is_signed_by_the_box_ca_not_itself(self):
        # A bare self-signed LEAF cannot be installed as a trust anchor on Android or
        # in Chrome's own store, so a school that mints one clicks through a warning
        # forever. The two-certificate shape is what makes self-signed survivable.
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(directory, ["box.school.lan"], [], days=30)
            leaf = edge_tls.inspect_certificate(os.path.join(directory, "tls.crt"))
            self.assertFalse(leaf.self_signed)
            self.assertIn("RunMyCampus Edge CA", leaf.issuer)

    def test_reissue_REUSES_the_box_ca(self):
        # The whole promise of installing the CA once. Minting a fresh CA on every
        # issue would silently void the trust install on every device in the building.
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(directory, ["old.school.lan"], [], days=30)
            first = edge_tls.inspect_certificate(os.path.join(directory, "ca.crt"))
            result = edge_tls.issue_self_signed(
                directory, ["new.school.lan"], ["10.0.0.9"], days=30
            )
            second = edge_tls.inspect_certificate(os.path.join(directory, "ca.crt"))
            leaf = edge_tls.inspect_certificate(os.path.join(directory, "tls.crt"))
            self.assertTrue(result["reused_ca"])
            self.assertEqual(first.subject, second.subject)
            self.assertEqual(first.not_after, second.not_after)
            self.assertEqual(leaf.dns_names, ("new.school.lan",))

    def test_refuses_to_issue_a_certificate_that_asserts_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                edge_tls.issue_self_signed(directory, [], [], days=30)

    def test_inspect_reports_missing_and_malformed_without_raising(self):
        # Presence is not usability -- the lesson _fernet_key_defects learned. A
        # parse failure must be a FINDING, never an exception that takes the box down.
        missing = edge_tls.inspect_certificate("/nonexistent/tls.crt")
        self.assertFalse(missing.exists)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "junk.crt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("this is not a certificate")
            facts = edge_tls.inspect_certificate(path)
            self.assertTrue(facts.exists)
            self.assertFalse(facts.readable)
            self.assertTrue(facts.error)

    def test_covers_names_the_certificate_omits(self):
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(directory, ["a.school.lan"], [], days=30)
            facts = edge_tls.inspect_certificate(os.path.join(directory, "tls.crt"))
            self.assertEqual(
                facts.covers(["a.school.lan", "b.school.lan"], ["10.0.0.1"]),
                ["b.school.lan", "10.0.0.1"],
            )


class CaddyfileTests(SimpleTestCase):
    def test_off_emits_no_site_block(self):
        rendered = edge_tls.caddyfile(edge_tls.MODE_OFF, ["a.lan"], [])
        self.assertNotIn("reverse_proxy", rendered)
        self.assertIn("RMC_EDGE_TLS_MODE=off", rendered)

    def test_selfsigned_uses_caddy_internal_ca_when_no_files(self):
        rendered = edge_tls.caddyfile(edge_tls.MODE_SELF_SIGNED, ["a.lan"], ["10.0.0.1"])
        self.assertIn("tls internal", rendered)
        self.assertIn("a.lan, 10.0.0.1 {", rendered)

    def test_selfsigned_prefers_a_pre_minted_pair(self):
        rendered = edge_tls.caddyfile(
            edge_tls.MODE_SELF_SIGNED, ["a.lan"], [], cert_path="/c.pem", key_path="/k.pem"
        )
        self.assertIn("tls /c.pem /k.pem", rendered)

    def test_forwarded_proto_header_is_always_present(self):
        # config/settings.py sets SECURE_PROXY_SSL_HEADER. Without this header every
        # request looks like plain HTTP to Django and SECURE_SSL_REDIRECT loops.
        for mode in (edge_tls.MODE_SELF_SIGNED, edge_tls.MODE_PROVIDED, edge_tls.MODE_ACME):
            rendered = edge_tls.caddyfile(
                mode,
                ["a.lan"],
                [],
                cert_path="/c.pem",
                key_path="/k.pem",
                acme_email="ops@example.test",
            )
            self.assertIn("header_up X-Forwarded-Proto {scheme}", rendered, mode)

    def test_provided_without_files_is_refused(self):
        with self.assertRaises(ValueError):
            edge_tls.caddyfile(edge_tls.MODE_PROVIDED, ["a.lan"], [])

    def test_acme_without_email_is_refused(self):
        with self.assertRaises(ValueError):
            edge_tls.caddyfile(edge_tls.MODE_ACME, ["a.lan"], [])

    def test_no_names_is_refused(self):
        with self.assertRaises(ValueError):
            edge_tls.caddyfile(edge_tls.MODE_SELF_SIGNED, [], [])


class TransitionPlanTests(SimpleTestCase):
    def test_same_mode_is_a_no_op(self):
        steps = edge_tls.transition_plan("off", "off")
        self.assertEqual(len(steps), 1)
        self.assertIn("nothing to do", steps[0])

    def test_going_up_tells_the_school_to_re_enrol_offline_pin(self):
        # https://host is a DIFFERENT origin to a browser; nothing carries over, and
        # local mode could never have sealed on the old one anyway.
        steps = " | ".join(edge_tls.transition_plan("off", "selfsigned"))
        self.assertIn("Re-enrol offline PIN", steps)
        self.assertIn("--issue-selfsigned", steps)

    def test_going_down_clears_hsts_FIRST(self):
        # Order matters: a browser holding a cached HSTS max-age refuses plain HTTP
        # for the full year no matter what the server sends afterwards.
        steps = edge_tls.transition_plan("acme", "off")
        hsts = next(i for i, s in enumerate(steps) if "SECURE_HSTS_SECONDS=0" in s)
        mode = next(i for i, s in enumerate(steps) if f"{edge_tls.ENV_MODE}=off" in s)
        self.assertLess(hsts, mode)

    def test_every_plan_flips_the_csrf_scheme(self):
        # CSRF_TRUSTED_ORIGINS carries a scheme; miss it and the first POST after the
        # switch fails a referer check and login looks broken.
        for target in ("selfsigned", "provided", "acme", "off"):
            steps = " | ".join(edge_tls.transition_plan("off" if target != "off" else "acme", target))
            self.assertIn("CSRF_TRUSTED_ORIGINS", steps, target)

    def test_every_plan_verifies_before_it_finishes(self):
        # Not necessarily the LAST line -- going up ends with "re-enrol offline PIN",
        # which belongs after the box is proven good, not before it.
        for target in ("selfsigned", "provided", "acme", "off"):
            steps = edge_tls.transition_plan("off" if target != "off" else "acme", target)
            check = next(i for i, s in enumerate(steps) if "check_edge_readiness" in s)
            deploy = next(i for i, s in enumerate(steps) if "docker compose" in s)
            self.assertLess(deploy, check, target)

    def test_plan_exists_between_every_pair_of_modes(self):
        for source in edge_tls.TLS_MODES:
            for target in edge_tls.TLS_MODES:
                self.assertTrue(edge_tls.transition_plan(source, target), (source, target))
