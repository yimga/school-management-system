"""The bring-up wizard finally asks whether devices can trust the box.

WHAT WAS MISSING. The runbook walked a school from a cloud export all the way to
go-dark without once asking whether the box serves https or whether a single device
trusts it. That is not a cosmetic gap: at a plain-http origin every browser warns on
every page, and offline PIN / local mode cannot be enabled AT ALL -- http is not a
secure context, so the browser withholds the WebCrypto call the PIN vault needs. A
school could tick sixteen steps and still have the one feature it bought the box for
switched off, with nothing in the runbook that would have said so.

WHAT THIS STEP MUST NOT DO, which is most of what is asserted here:

* it must not fail a box that runs plain http ON PURPOSE. A great many do. A step
  that is red on every correct box teaches operators that its colour means nothing,
  and then it is red on the incorrect one too and nobody looks;
* it must not pass QUIETLY on such a box either -- the consequence has to be said;
* its self-heal must never mint a certificate authority. A box whose certificate
  volume was lost would otherwise come up, notice it has no CA, helpfully mint a new
  one and report success -- stranding every device that trusted the old one,
  permanently, with nobody watching;
* it must not claim to have fixed something it cannot finish. A container cannot
  restart a sibling, so a reissued certificate is not necessarily the certificate
  being SERVED, and a box in that state looks healthy in every log it writes;
* it must not need the database. TLS is configured while a box is still coming up,
  which is exactly when a database-backed check is unavailable.

The last one is why every test here is a SimpleTestCase.
"""

from __future__ import annotations

import os
import tempfile
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.lifecycle import edge_onboarding
from apps.lifecycle.edge_onboarding import (
    EDGE_ONBOARDING_STEPS,
    EDGE_ONBOARDING_STEP_KEYS,
)
from apps.schools import edge_tls, edge_trust_state

STEP_KEY = "edge_tls_trust"


class _School:
    """Enough of a School for a step that reads no tenant table at all."""

    id = 1
    pk = 1
    slug = "gilead-tech"
    country_code = "GH"


class TheStepExistsAndSitsInTheRightPlaceTests(SimpleTestCase):
    def _step(self):
        return {s.key: s for s in EDGE_ONBOARDING_STEPS}[STEP_KEY]

    def test_the_runbook_has_a_tls_and_trust_step_at_all(self):
        self.assertIn(STEP_KEY, EDGE_ONBOARDING_STEP_KEYS)

    def test_it_comes_after_the_box_has_names_and_before_go_dark(self):
        # A certificate asserts ADDRESSES, so the names have to exist first; and a
        # box that goes dark without devices trusting it is a box nobody can use
        # offline, which is the thing go-dark is meant to be certifying.
        order = list(EDGE_ONBOARDING_STEP_KEYS)
        self.assertLess(order.index("configure_lan_hostname"), order.index(STEP_KEY))
        self.assertLess(order.index(STEP_KEY), order.index("verify_and_sync_gate"))
        self.assertLess(order.index(STEP_KEY), order.index("go_dark_checklist"))

    def test_it_can_heal_itself(self):
        self.assertIsNotNone(self._step().self_heal)

    def test_it_leads_with_the_one_command_rather_than_the_twelve(self):
        self.assertIn("edge-bootstrap.sh", self._step().command_template)

    def test_it_names_the_managed_route_before_the_per_device_one(self):
        # A school that can push should never visit a device. Reading the per-device
        # route first is how somebody spends an afternoon doing by hand what one
        # console push would have done for the whole fleet.
        template = self._step().command_template
        self.assertLess(template.index("MANAGED FLEET"), template.index("--trust-url"))

    def test_it_points_at_the_runbook_that_explains_the_irreversible_part(self):
        self.assertEqual(self._step().help_doc, "docs/EDGE_TLS_RUNBOOK.md")

    def test_its_fallback_forbids_the_one_action_with_no_undo(self):
        workaround = self._step().workaround
        self.assertIn("import-ca", workaround)
        self.assertIn("stranded permanently", workaround)


class WhatTheStepSaysAboutABoxTests(SimpleTestCase):
    """Five states, and the wrong answer in any of them costs somebody a day."""

    def _validate(self, env, allowed_hosts=None):
        with mock.patch.dict(os.environ, env, clear=False):
            for key in (edge_tls.ENV_MODE, edge_tls.ENV_DIR, edge_tls.ENV_HOSTNAMES):
                if key not in env:
                    os.environ.pop(key, None)
            with override_settings(
                ALLOWED_HOSTS=allowed_hosts or ["gilead-tech.school.lan"]
            ):
                return edge_onboarding._validate_edge_tls_trust(_School())

    def test_a_box_with_no_tls_mode_passes(self):
        ok, _detail = self._validate({})
        self.assertTrue(ok, "plain http is a real choice, not a failure")

    def test_but_it_is_told_exactly_what_that_costs(self):
        # Passing QUIETLY would be the actual defect: the school finds out the
        # feature it bought the box for is unavailable on the day it needs it.
        _ok, detail = self._validate({})
        self.assertIn("offline PIN", detail)
        self.assertIn("secure context", detail)

    def test_a_mode_the_box_cannot_parse_fails_rather_than_falling_back_quietly(self):
        # resolve_mode() falls back to `off` so the box can still boot -- correct --
        # but the box is then serving plain http while its configuration claims
        # otherwise, and nothing else on the runbook would say so.
        ok, detail = self._validate({edge_tls.ENV_MODE: "sortof"})
        self.assertFalse(ok)
        self.assertIn("sortof", detail)

    def test_a_mode_that_promises_https_with_no_certificate_fails(self):
        with tempfile.TemporaryDirectory() as empty:
            ok, detail = self._validate(
                {edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED, edge_tls.ENV_DIR: empty}
            )
        self.assertFalse(ok)
        self.assertIn("edge-bootstrap.sh", detail)

    def test_a_correct_box_passes_and_names_the_anchor_a_device_will_compare(self):
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory,
                dns_names=["gilead-tech.school.lan"],
                ip_addresses=["10.10.20.137"],
                days=825,
            )
            fingerprint = edge_tls.inspect_certificate(
                os.path.join(directory, "ca.crt")
            ).fingerprint
            ok, detail = self._validate(
                {
                    edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
                    edge_tls.ENV_DIR: directory,
                },
                allowed_hosts=["gilead-tech.school.lan", "10.10.20.137"],
            )
        self.assertTrue(ok, detail)
        self.assertIn(fingerprint, detail)
        self.assertIn(edge_tls.TRUST_ENROLMENT_PATH, detail)

    def test_a_certificate_that_misses_an_address_fails_and_names_it(self):
        # The failure a moved box produces: everything works until DHCP hands out a
        # different lease, and then every device errors at an address that no longer
        # exists in the certificate.
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory,
                dns_names=["gilead-tech.school.lan"],
                ip_addresses=[],
                days=825,
            )
            ok, detail = self._validate(
                {
                    edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
                    edge_tls.ENV_DIR: directory,
                },
                allowed_hosts=["gilead-tech.school.lan", "10.10.20.99"],
            )
        self.assertFalse(ok)
        self.assertIn("10.10.20.99", detail)

    def test_a_leaf_that_is_fine_but_an_unreadable_ca_still_fails(self):
        # There is then nothing devices can be given to trust the box with, and the
        # school finds out one device at a time.
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory, dns_names=["gilead-tech.school.lan"], ip_addresses=[], days=825
            )
            with open(os.path.join(directory, "ca.crt"), "wb") as handle:
                handle.write(b"-----BEGIN CERTIFICATE-----\nnope\n")
            ok, detail = self._validate(
                {
                    edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
                    edge_tls.ENV_DIR: directory,
                }
            )
        self.assertFalse(ok)
        self.assertIn("cannot", detail)

    def test_it_never_raises_however_broken_the_box_is(self):
        # Nothing in this module raises to its caller: a validate() that blows up is
        # recorded as a failure, never as an aborted suite. Forced by making the
        # certificate layer itself throw. An earlier draft put a NUL byte in an env
        # var instead -- os.environ rejects that on Windows, so the TEST raised and
        # the function under test was never reached. It looked like a passing guard
        # and was measuring the harness.
        with mock.patch.object(
            edge_tls, "certificate_paths", side_effect=RuntimeError("disk gone")
        ):
            ok, detail = self._validate({edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED})
        self.assertFalse(ok)
        self.assertIn("disk gone", detail)

    def _heal(self, env, allowed_hosts=None):
        with mock.patch.dict(os.environ, env, clear=False):
            for key in (edge_tls.ENV_MODE, edge_tls.ENV_DIR, edge_tls.ENV_HOSTNAMES):
                if key not in env:
                    os.environ.pop(key, None)
            with override_settings(
                ALLOWED_HOSTS=allowed_hosts or ["gilead-tech.school.lan"]
            ):
                return edge_onboarding._heal_edge_tls_trust(_School())

    def test_it_reissues_for_an_address_the_box_has_moved_to(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as state:
            edge_tls.issue_self_signed(
                directory, dns_names=["gilead-tech.school.lan"], ip_addresses=[], days=825
            )
            ca = os.path.join(directory, "ca.crt")
            before = edge_tls.inspect_certificate(ca).fingerprint
            healed, detail = self._heal(
                {
                    edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
                    edge_tls.ENV_DIR: directory,
                    edge_trust_state.ENV_STATE_DIR: state,
                },
                allowed_hosts=["gilead-tech.school.lan", "10.10.20.99"],
            )
            after = edge_tls.inspect_certificate(ca).fingerprint
            leaf = edge_tls.inspect_certificate(os.path.join(directory, "tls.crt"))
        self.assertTrue(healed, detail)
        self.assertIn("10.10.20.99", leaf.ip_addresses)
        self.assertEqual(
            before,
            after,
            "the CA must be reused, or every device has to install one again",
        )

    def test_it_says_the_terminator_still_has_to_be_restarted(self):
        # A container cannot restart a sibling. The file on disk is now right and the
        # thing being SERVED may not be -- and a box in that state looks healthy in
        # every log it writes, which is the worst way for this to be wrong.
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as state:
            edge_tls.issue_self_signed(
                directory, dns_names=["gilead-tech.school.lan"], ip_addresses=[], days=825
            )
            _healed, detail = self._heal(
                {
                    edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
                    edge_tls.ENV_DIR: directory,
                    edge_trust_state.ENV_STATE_DIR: state,
                },
                allowed_hosts=["gilead-tech.school.lan", "10.10.20.99"],
            )
        self.assertIn("restart", detail)

    def test_a_box_that_is_already_right_is_left_alone(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as state:
            edge_tls.issue_self_signed(
                directory, dns_names=["gilead-tech.school.lan"], ip_addresses=[], days=825
            )
            healed, detail = self._heal(
                {
                    edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
                    edge_tls.ENV_DIR: directory,
                    edge_trust_state.ENV_STATE_DIR: state,
                },
                allowed_hosts=["gilead-tech.school.lan"],
            )
        self.assertTrue(healed)
        self.assertIn("no-op", detail)

    def test_a_lost_certificate_volume_is_refused_not_helpfully_replaced(self):
        # THE test in this file. The box records its CA fingerprint in a DIFFERENT
        # volume from the certificates precisely so it can tell "first install" from
        # "the volume is gone" -- and the second one must never be answered by
        # minting a replacement, because there is no undo and no warning.
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as state:
            env = {
                edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
                edge_tls.ENV_DIR: directory,
                edge_trust_state.ENV_STATE_DIR: state,
            }
            with mock.patch.dict(os.environ, env, clear=False):
                edge_tls.issue_self_signed(
                    directory,
                    dns_names=["gilead-tech.school.lan"],
                    ip_addresses=[],
                    days=825,
                )
                ca = os.path.join(directory, "ca.crt")
                edge_trust_state.record(edge_tls.inspect_certificate(ca))
                os.remove(ca)
                os.remove(os.path.join(directory, "tls.crt"))
            healed, detail = self._heal(env)
            minted = os.path.exists(os.path.join(directory, "ca.crt"))
        self.assertFalse(healed)
        self.assertFalse(minted, "a self-heal minted a replacement certificate authority")
        self.assertIn("import-ca", detail)

    def test_turning_tls_on_is_a_decision_and_not_a_repair(self):
        # It changes the origin every device uses and re-enrols offline PIN on all of
        # them. A self-heal that did that unattended would be a surprise, not a fix.
        healed, detail = self._heal({})
        self.assertFalse(healed)
        self.assertIn("decision", detail)

    def test_a_box_with_no_addresses_is_told_so_rather_than_given_a_blank_certificate(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as state:
            healed, detail = self._heal(
                {
                    edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
                    edge_tls.ENV_DIR: directory,
                    edge_trust_state.ENV_STATE_DIR: state,
                },
                # `testserver` is the one entry edge_tls drops on purpose, so
                # this is a box holding no address a device could ever use.
                # `localhost` and `127.0.0.1` would NOT be -- they are valid
                # certificate entries, which is why the first draft of this test
                # sailed through a heal it meant to catch being refused.
                allowed_hosts=["testserver"],
            )
        self.assertFalse(healed)
        self.assertIn("ALLOWED_HOSTS", detail)

    def test_it_never_raises_either(self):
        with mock.patch.object(
            edge_tls, "certificate_paths", side_effect=RuntimeError("disk gone")
        ):
            healed, detail = self._heal({edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED})
        self.assertFalse(healed)
        self.assertIn("disk gone", detail)

    def _step(self, key):
        return {s.key: s for s in EDGE_ONBOARDING_STEPS}[key]

    def test_the_box_env_fallback_no_longer_says_to_pin_the_four_flags(self):
        # SECURE_SSL_REDIRECT / SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE / HSTS are
        # DERIVED from RMC_EDGE_TLS_MODE. An explicit value in .env overrides the
        # mode without saying so, so following the old advice left a box serving
        # cookies without the Secure flag on the day it moved to https -- with
        # nothing anywhere explaining why. That is the exact trap the derived-flags
        # design exists to remove, and the runbook was prescribing it.
        workaround = self._step("configure_box_env").workaround
        self.assertIn("Do NOT pin", workaround)
        self.assertIn("DERIVED", workaround)
        self.assertNotIn("all to 0", workaround)

    def test_it_still_names_the_two_commands_it_is_relied_on_to_name(self):
        # The command-integrity gate reads this prose. Rewriting it must not drop a
        # reference the gate is holding.
        workaround = self._step("configure_box_env").workaround
        self.assertIn("check_edge_readiness", workaround)
        self.assertIn("run_periodic_jobs", workaround)

    def test_the_lan_step_no_longer_insists_the_box_has_no_tls(self):
        with mock.patch.dict(
            os.environ, {edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED}, clear=False
        ):
            self.assertEqual(edge_onboarding._lan_scheme(), "https")
            self.assertEqual(edge_onboarding._lan_port_hint(), "")
            self.assertIn("trust its certificate", edge_onboarding._lan_scheme_reason())

    def test_and_still_tells_a_plain_http_box_the_truth(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(edge_tls.ENV_MODE, None)
            self.assertEqual(edge_onboarding._lan_scheme(), "http")
            self.assertEqual(edge_onboarding._lan_port_hint(), ":<web-port>")
            self.assertIn("no lock", edge_onboarding._lan_scheme_reason())

    def test_the_scheme_helper_never_raises(self):
        # It is called from inside a validate() detail string. Raising there would
        # turn a runbook line into a failed step.
        with mock.patch.object(
            edge_tls, "resolve_mode", side_effect=RuntimeError("boom")
        ):
            self.assertEqual(edge_onboarding._lan_scheme(), "http")
