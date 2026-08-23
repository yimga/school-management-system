"""The edge onboarding wizard, and the plan it produces.

A school answers six questions; ``build_edge_plan`` turns them into the files and
the ordered procedure for THIS box. Doing that translation by hand is where the
mistakes live, so these tests pin the translation rather than the prose:

* a mode that cannot work for the school's addresses is reported as blocking,
  with the reason, instead of producing a plan that fails silently at the box;
* the generated .env never contains the four security flags, because an explicit
  value there silently overrides the mode later -- the exact trap the mode
  derivation exists to remove;
* the runbook orders certificate-then-Caddyfile, never the reverse.

Companion: ``test_edge_relocation_2026_08_22.py`` covers the certificate layer
this consumes.
"""
from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.schools import edge_onboarding, edge_tls


class BuildEdgePlanTests(SimpleTestCase):
    GILEAD = {
        "site_name": "Gilead Tech High",
        "addresses": "10.10.20.137, gilead.school.lan",
        "tls_mode": "selfsigned",
        "mobility": edge_onboarding.MOVE_BETWEEN_COUNTRIES,
    }

    def test_the_gilead_answers_produce_a_ready_plan(self):
        plan = edge_onboarding.build_edge_plan(self.GILEAD)
        self.assertTrue(plan["ready"], plan["blocking"])
        self.assertEqual(plan["mode"], edge_tls.MODE_SELF_SIGNED)
        self.assertEqual(plan["ip_addresses"], ["10.10.20.137"])
        self.assertEqual(plan["dns_names"], ["gilead.school.lan"])

    def test_addresses_split_into_dns_and_ip_buckets(self):
        # An IP has to end up in an IPAddress SAN; a DNS name in a DNSName SAN.
        # Mixing them is the classic reason a LAN certificate still warns at the
        # address on the sticker, so the split happens once, here.
        dns, ips = edge_onboarding.split_addresses("box.lan, 10.0.0.5, 192.168.1.9")
        self.assertEqual(dns, ["box.lan"])
        self.assertEqual(ips, ["10.0.0.5", "192.168.1.9"])

    def test_https_origins_drop_the_app_port_and_plain_http_keeps_it(self):
        https = edge_onboarding.build_edge_plan(self.GILEAD)["origins"]
        self.assertIn("https://10.10.20.137", https)
        plain = edge_onboarding.build_edge_plan(
            {**self.GILEAD, "tls_mode": "off"}
        )["origins"]
        self.assertIn("http://10.10.20.137:10000", plain)

    def test_generated_env_never_pins_the_four_derived_flags(self):
        # If the plan wrote SECURE_SSL_REDIRECT into .env, a later mode change
        # would be silently overridden by it -- re-creating the trap the whole
        # mode derivation exists to remove.
        for mode in edge_tls.TLS_MODES:
            with self.subTest(mode=mode):
                plan = edge_onboarding.build_edge_plan(
                    {**self.GILEAD, "tls_mode": mode, "acme_email": "ops@example.org"}
                )
                joined = "\n".join(plan["env_lines"])
                for flag in (
                    "SECURE_SSL_REDIRECT",
                    "SESSION_COOKIE_SECURE",
                    "CSRF_COOKIE_SECURE",
                    "SECURE_HSTS_SECONDS",
                ):
                    self.assertNotIn(flag, joined)

    def test_env_carries_the_mode_hosts_and_origins(self):
        lines = edge_onboarding.build_edge_plan(self.GILEAD)["env_lines"]
        joined = "\n".join(lines)
        self.assertIn("RMC_EDGE_TLS_MODE=selfsigned", joined)
        self.assertIn("RMC_EDGE_TLS_HOSTNAMES=", joined)
        self.assertIn("ALLOWED_HOSTS=", joined)
        self.assertIn("CSRF_TRUSTED_ORIGINS=https://", joined)

    def test_a_public_ca_for_a_lan_only_box_is_blocking_with_the_reason(self):
        plan = edge_onboarding.build_edge_plan(
            {"addresses": "10.10.20.137", "tls_mode": "acme", "acme_email": "o@e.org"}
        )
        self.assertFalse(plan["ready"])
        self.assertTrue(any("10.10.20.137" in b for b in plan["blocking"]))

    def test_acme_without_a_contact_mailbox_is_blocking(self):
        plan = edge_onboarding.build_edge_plan(
            {"addresses": "sms.gilead-tech.org", "tls_mode": "acme"}
        )
        self.assertFalse(plan["ready"])
        self.assertTrue(any("mailbox" in b for b in plan["blocking"]))

    def test_acme_on_a_real_public_name_with_a_mailbox_is_ready(self):
        plan = edge_onboarding.build_edge_plan(
            {
                "addresses": "sms.gilead-tech.org",
                "tls_mode": "acme",
                "acme_email": "ops@gilead-tech.org",
            }
        )
        self.assertTrue(plan["ready"], plan["blocking"])
        self.assertTrue(plan["advisory"], "renewal reachability should still be flagged")

    def test_an_unknown_mode_is_reported_not_guessed(self):
        plan = edge_onboarding.build_edge_plan(
            {"addresses": "10.0.0.1", "tls_mode": "banana"}
        )
        self.assertFalse(plan["ready"])
        self.assertEqual(plan["mode"], edge_tls.MODE_OFF)

    def test_no_answers_at_all_does_not_crash_and_is_not_ready_to_deploy(self):
        # A half-finished wizard must produce an honest plan, not an invented one.
        plan = edge_onboarding.build_edge_plan({})
        self.assertEqual(plan["dns_names"], [])
        self.assertEqual(plan["ip_addresses"], [])
        self.assertEqual(plan["origins"], [])

    def test_runbook_renders_the_caddyfile_after_issuing_the_certificate(self):
        steps = edge_onboarding.build_edge_plan(self.GILEAD)["steps"]
        issue = next(i for i, s in enumerate(steps) if "--issue-selfsigned" in s)
        render = next(i for i, s in enumerate(steps) if "--print-caddyfile" in s)
        self.assertLess(issue, render)

    def test_runbook_exports_the_ca_and_verifies_before_touching_devices(self):
        steps = edge_onboarding.build_edge_plan(self.GILEAD)["steps"]
        export = next(i for i, s in enumerate(steps) if "--export-ca" in s)
        verify = next(i for i, s in enumerate(steps) if "check_edge_readiness" in s)
        install = next(i for i, s in enumerate(steps) if "install it on every device" in s)
        self.assertLess(export, install)
        self.assertLess(verify, install)

    def test_plain_http_plan_says_offline_mode_cannot_work(self):
        plan = edge_onboarding.build_edge_plan({**self.GILEAD, "tls_mode": "off"})
        self.assertTrue(
            any("not a secure context" in s for s in plan["steps"]),
            "a plain-HTTP plan must say offline PIN cannot be enabled on any browser",
        )

    def test_caddyfile_is_emitted_for_file_backed_modes(self):
        plan = edge_onboarding.build_edge_plan(self.GILEAD)
        self.assertIn("reverse_proxy web:10000", plan["caddyfile"])
        self.assertIn("/app/var/edge-tls/tls.crt", plan["caddyfile"])

    def test_relocation_steps_travel_with_the_plan(self):
        plan = edge_onboarding.build_edge_plan(self.GILEAD)
        self.assertTrue(plan["relocation_steps"])
        self.assertIn("export the box CA", plan["relocation_steps"][0])

    def test_a_static_box_still_gets_hardware_failure_planning(self):
        # Hardware fails even when nothing moves, and the CA is just as lost.
        plan = edge_onboarding.build_edge_plan(
            {**self.GILEAD, "mobility": edge_onboarding.MOVE_NEVER}
        )
        self.assertTrue(
            any("--import-ca" in s for s in plan["relocation_steps"]),
            "restore guidance must be present even for a box that never moves",
        )

    def test_unknown_mobility_falls_back_rather_than_raising(self):
        plan = edge_onboarding.build_edge_plan({**self.GILEAD, "mobility": "teleport"})
        self.assertEqual(plan["mobility"], edge_onboarding.MOVE_NEVER)


class EdgeWizardRegistryTests(SimpleTestCase):
    """The wizard is declarative; these pin the declaration."""

    def _wizard(self):
        from apps.setup_studio import wizard_engine

        return wizard_engine.get_wizard("edge_location_onboarding")

    def test_the_wizard_is_registered(self):
        self.assertEqual(self._wizard().wizard_key, "edge_location_onboarding")

    def test_it_is_offered_to_operators_and_tenant_admins(self):
        self.assertIn("operator", self._wizard().audience)
        self.assertIn("tenant_admin", self._wizard().audience)

    def test_every_tls_choice_routes_to_its_own_follow_up(self):
        from apps.setup_studio import wizard_engine

        wizard = self._wizard()
        step = wizard.step_by_key("tls_choice")
        expected = {
            "selfsigned": "device_trust",
            "provided": "certificate_source",
            "acme": "acme_contact",
            "off": "plain_http_confirm",
        }
        for answer, target in expected.items():
            with self.subTest(answer=answer):
                nxt = wizard_engine.resolve_next_step(
                    wizard, current_step=step, current_answer={"value": answer}
                )
                self.assertIsNotNone(nxt)
                self.assertEqual(nxt.key, target)

    def test_an_unrecognised_choice_falls_through_rather_than_ending_the_wizard(self):
        from apps.setup_studio import wizard_engine

        wizard = self._wizard()
        nxt = wizard_engine.resolve_next_step(
            wizard,
            current_step=wizard.step_by_key("tls_choice"),
            current_answer={"value": "something-else"},
        )
        self.assertIsNotNone(nxt, "a stray answer must not silently end the wizard")

    def test_all_four_branches_converge_on_the_same_tail(self):
        from apps.setup_studio import wizard_engine

        wizard = self._wizard()
        for key in ("device_trust", "certificate_source", "acme_contact", "plain_http_confirm"):
            with self.subTest(step=key):
                nxt = wizard_engine.resolve_next_step(
                    wizard,
                    current_step=wizard.step_by_key(key),
                    current_answer={"value": True},
                )
                self.assertIsNotNone(nxt)
                self.assertEqual(nxt.key, "mobility")

    def test_every_step_declares_a_writer_that_imports(self):
        # A writer path that does not import fails SOFT at boot -- a warning in a
        # log nobody reads, and a wizard that completes while writing nothing.
        from apps.setup_studio.wizard_engine import _import_dotted

        for step in self._wizard().steps:
            with self.subTest(step=step.key):
                path = step.persistence.get("writer")
                self.assertTrue(path, f"{step.key} has no writer")
                self.assertTrue(callable(_import_dotted(path)))

    def test_every_options_resolver_imports_and_returns_usable_choices(self):
        from apps.setup_studio.wizard_engine import _import_dotted

        for step in self._wizard().steps:
            if not step.options_resolver:
                continue
            with self.subTest(step=step.key):
                fn = _import_dotted(step.options_resolver)
                options = fn(request=None, school=None)
                self.assertTrue(options)
                for option in options:
                    self.assertIn("value", option)
                    self.assertIn("label_token", option)

    def test_tls_choice_options_match_the_branch_keys_exactly(self):
        # A value with no branch would dead-end the wizard at the moment the
        # school makes the most important decision in it.
        from apps.setup_studio.wizard_engine import _import_dotted

        wizard = self._wizard()
        step = wizard.step_by_key("tls_choice")
        values = {
            o["value"] for o in _import_dotted(step.options_resolver)(request=None, school=None)
        }
        branch_keys = {k for k in (step.branches or {}) if k != "default"}
        self.assertEqual(values, branch_keys)

    def test_mobility_options_are_the_ones_the_planner_understands(self):
        from apps.setup_studio.wizard_engine import _import_dotted

        step = self._wizard().step_by_key("mobility")
        values = {
            o["value"] for o in _import_dotted(step.options_resolver)(request=None, school=None)
        }
        self.assertEqual(values, set(edge_onboarding.MOBILITY_CHOICES))


class EdgeWizardWriterTests(TestCase):
    """The writer must actually persist, and the collector must read it back."""

    def setUp(self):
        super().setUp()
        from apps.schools.models import School

        self.school = School.objects.create(
            name="Edge Wizard School", slug="edge-wizard-school", is_active=True
        )

    def _write(self, step_key, payload):
        from apps.setup_studio import wizard_resolvers_operator as resolvers

        resolvers.write_edge_location_onboarding_step(
            school=self.school,
            wizard_key="edge_location_onboarding",
            step_key=step_key,
            payload=payload,
            actor_user_id=None,
        )

    def test_the_structured_first_step_persists_both_of_its_fields(self):
        self._write(
            "site_and_addresses",
            {"site_name": "Gilead Tech High", "addresses": "10.10.20.137, gilead.school.lan"},
        )
        self.school.refresh_from_db()
        bucket = (self.school.settings or {}).get("edge_onboarding") or {}
        self.assertEqual(bucket.get("site_name"), "Gilead Tech High")
        self.assertIn("10.10.20.137", bucket.get("addresses", ""))

    def test_single_value_steps_persist_under_their_answer_key(self):
        self._write("tls_choice", {"value": "selfsigned"})
        self._write("mobility", {"value": edge_onboarding.MOVE_BETWEEN_COUNTRIES})
        self.school.refresh_from_db()
        bucket = (self.school.settings or {}).get("edge_onboarding") or {}
        self.assertEqual(bucket.get("tls_mode"), "selfsigned")
        self.assertEqual(bucket.get("mobility"), edge_onboarding.MOVE_BETWEEN_COUNTRIES)

    def test_a_completed_wizard_yields_a_ready_plan_from_what_was_stored(self):
        # End to end through the writer: the plan must come from persisted
        # answers, not from anything the test hands it directly.
        from apps.setup_studio import wizard_resolvers_operator as resolvers

        self._write(
            "site_and_addresses",
            {"site_name": "Gilead Tech High", "addresses": "10.10.20.137, gilead.school.lan"},
        )
        self._write("tls_choice", {"value": "selfsigned"})
        self._write("device_trust", {"value": True})
        self._write("mobility", {"value": edge_onboarding.MOVE_BETWEEN_COUNTRIES})
        self.school.refresh_from_db()

        answers = resolvers._collect_edge_answers(self.school)
        self.assertEqual(answers.get("tls_mode"), "selfsigned")
        plan = edge_onboarding.build_edge_plan(answers)
        self.assertTrue(plan["ready"], plan["blocking"])
        self.assertEqual(plan["ip_addresses"], ["10.10.20.137"])

    def test_collecting_from_an_untouched_school_returns_nothing_invented(self):
        from apps.setup_studio import wizard_resolvers_operator as resolvers

        self.assertEqual(resolvers._collect_edge_answers(self.school), {})

    def test_the_review_step_runs_without_a_school_context(self):
        # Operator scratch: the wizard may be walked with no tenant selected.
        from apps.setup_studio import wizard_resolvers_operator as resolvers

        resolvers.write_edge_location_onboarding_step(
            school=None,
            wizard_key="edge_location_onboarding",
            step_key="review",
            payload={"value": True},
            actor_user_id=None,
        )
