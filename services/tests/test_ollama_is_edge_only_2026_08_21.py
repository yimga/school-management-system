"""Ollama is an edge provider. A cloud host must never be handed an Ollama tier.

The architecture, stated by the platform owner on 2026-08-21:

    OpenAI serves the cloud instance. Ollama is only for edge locations and
    tenants who have offline mode and the infrastructure to host Ollama.

The code did not implement that. ``_ONLINE_CLOUD_CHAIN`` put ``ollama`` between
``litellm`` and ``rules`` on every online deployment, and an online deployment
with no cloud model configured resolved to ``["ollama", "rules"]`` — an
Ollama-first chain on a Render web service, where no Ollama daemon exists and
none can. Every call paid a dead connection attempt before degrading to rules,
and the degradation was silent.

The distinction the fix turns on is that ``online`` covers two different
machines: a hosted cloud service, which can only reach a cloud model, and a
developer or on-prem box that is online *and* runs its own model. Collapsing
them is what produced the dead tier, so ``is_cloud_host()`` separates them.

DB-free.
"""

from django.test import SimpleTestCase, override_settings

from services.ai_deployment_posture import (
    ai_mode_to_allowed_backends,
    default_tier_chain_for_profile,
    is_cloud_host,
)

OPENAI = "https://api.openai.com"


class CloudHostsNeverGetOllamaTests(SimpleTestCase):
    """The defect: an edge-only provider offered on a machine that has none."""

    @override_settings(
        RMC_AI_CLOUD_HOST="1", RMC_DEPLOYMENT_PROFILE="online", LITELLM_PROXY_URL=OPENAI
    )
    def test_the_saas_runs_the_cloud_model_and_nothing_local(self):
        self.assertEqual(default_tier_chain_for_profile(), ["litellm", "rules"])

    @override_settings(
        RMC_AI_CLOUD_HOST="1", RMC_DEPLOYMENT_PROFILE="online", LITELLM_PROXY_URL=""
    )
    def test_a_misconfigured_cloud_host_falls_straight_to_rules(self):
        # Not ["ollama", "rules"]. There is no Ollama here, so offering one only
        # delays the same outcome by one failed connection per call.
        self.assertEqual(default_tier_chain_for_profile(), ["rules"])

    @override_settings(
        RMC_AI_CLOUD_HOST="1", RMC_DEPLOYMENT_PROFILE="online", LITELLM_PROXY_URL=OPENAI
    )
    def test_ollama_appears_nowhere_in_a_hosted_chain(self):
        self.assertNotIn("ollama", default_tier_chain_for_profile())


class EdgeBoxesNeverCallTheCloudTests(SimpleTestCase):
    """The other half of the contract, and the one with a bill attached."""

    @override_settings(RMC_AI_CLOUD_HOST="", RMC_DEPLOYMENT_PROFILE="edge", LITELLM_PROXY_URL="")
    def test_an_edge_box_runs_its_own_model(self):
        self.assertEqual(default_tier_chain_for_profile(), ["ollama", "rules"])

    @override_settings(
        RMC_AI_CLOUD_HOST="", RMC_DEPLOYMENT_PROFILE="edge", LITELLM_PROXY_URL=OPENAI
    )
    def test_a_stray_cloud_key_cannot_pull_an_edge_box_online(self):
        # A tenant who chose offline mode chose it for a reason. An inherited or
        # copy-pasted key must not quietly start shipping their data off-site.
        self.assertEqual(default_tier_chain_for_profile(), ["ollama", "rules"])
        self.assertNotIn("litellm", default_tier_chain_for_profile())


class TheProfilesThatLegitimatelyUseBothTests(SimpleTestCase):
    @override_settings(
        RMC_AI_CLOUD_HOST="1", RMC_DEPLOYMENT_PROFILE="hybrid", LITELLM_PROXY_URL=OPENAI
    )
    def test_hybrid_is_deliberately_both(self):
        # Hybrid means "Render with a LAN hub behind it" — the one profile where
        # a cloud tier and a local tier are both genuinely reachable.
        self.assertEqual(default_tier_chain_for_profile(), ["litellm", "ollama", "rules"])

    @override_settings(
        RMC_AI_CLOUD_HOST="1", RMC_DEPLOYMENT_PROFILE="hybrid", LITELLM_PROXY_URL=""
    )
    def test_hybrid_without_a_cloud_model_is_just_an_edge_box(self):
        self.assertEqual(default_tier_chain_for_profile(), ["ollama", "rules"])

    @override_settings(
        RMC_AI_CLOUD_HOST="", RMC_DEPLOYMENT_PROFILE="online", LITELLM_PROXY_URL=OPENAI
    )
    def test_a_developer_machine_keeps_its_local_model(self):
        # RMC_DEPLOYMENT_PROFILE defaults to "online", so every laptop is
        # "online". Dropping Ollama for all of them would take local AI away
        # from development, which is not what the rule says.
        self.assertEqual(default_tier_chain_for_profile(), ["litellm", "ollama", "rules"])

    @override_settings(
        RMC_AI_CLOUD_HOST="", RMC_DEPLOYMENT_PROFILE="online", LITELLM_PROXY_URL=""
    )
    def test_a_developer_machine_without_a_key_still_has_ollama(self):
        self.assertEqual(default_tier_chain_for_profile(), ["ollama", "rules"])


class TheTenantFacingAiModeFollowsTheSameRuleTests(SimpleTestCase):
    """``ai_mode`` is a per-tenant override layered on the profile chain.

    It had its own hardcoded ``["litellm", "ollama", "rules"]``, so a tenant who
    picked "cloud" on the SaaS got the same dead middle tier by a second route.
    """

    @override_settings(RMC_AI_CLOUD_HOST="1", LITELLM_PROXY_URL=OPENAI)
    def test_cloud_mode_on_a_cloud_host_skips_ollama(self):
        self.assertEqual(ai_mode_to_allowed_backends("cloud"), ["litellm", "rules"])

    @override_settings(RMC_AI_CLOUD_HOST="", LITELLM_PROXY_URL=OPENAI)
    def test_cloud_mode_off_a_cloud_host_may_still_fall_back_locally(self):
        self.assertEqual(
            ai_mode_to_allowed_backends("cloud"), ["litellm", "ollama", "rules"]
        )

    @override_settings(RMC_AI_CLOUD_HOST="1", LITELLM_PROXY_URL=OPENAI)
    def test_local_mode_never_reaches_the_cloud_whatever_the_host(self):
        self.assertEqual(ai_mode_to_allowed_backends("local"), ["ollama", "rules"])
        self.assertNotIn("litellm", ai_mode_to_allowed_backends("local"))

    @override_settings(RMC_AI_CLOUD_HOST="1", LITELLM_PROXY_URL=OPENAI)
    def test_auto_defers_to_the_profile_chain(self):
        self.assertIsNone(ai_mode_to_allowed_backends("auto"))

    @override_settings(RMC_AI_CLOUD_HOST="1", LITELLM_PROXY_URL=OPENAI)
    def test_rules_survives_every_mode_so_degradation_always_works(self):
        for mode in ("cloud", "local"):
            with self.subTest(mode=mode):
                self.assertIn("rules", ai_mode_to_allowed_backends(mode))


class CloudHostDetectionTests(SimpleTestCase):
    @override_settings(RMC_AI_CLOUD_HOST="1")
    def test_the_override_can_declare_a_host_cloud(self):
        self.assertTrue(is_cloud_host())

    @override_settings(RMC_AI_CLOUD_HOST="0")
    def test_the_override_can_declare_a_host_not_cloud(self):
        # An on-prem server that is permanently online but hosts its own model.
        self.assertFalse(is_cloud_host())

    @override_settings(RMC_AI_CLOUD_HOST="", _IS_CLOUD_DEPLOYED=True)
    def test_no_override_on_a_hosted_deploy_detects_cloud(self):
        # THE PRODUCTION PATH. Render sets the env var now, but the inference
        # must stand on its own — a mutation that stubbed this to False escaped
        # every other test in this file, because they all set the override and
        # short-circuit before reaching it.
        self.assertTrue(is_cloud_host())

    @override_settings(RMC_AI_CLOUD_HOST="", _IS_CLOUD_DEPLOYED=False)
    def test_no_override_off_a_hosted_deploy_detects_not_cloud(self):
        self.assertFalse(is_cloud_host())

    @override_settings(
        RMC_AI_CLOUD_HOST="", _IS_CLOUD_DEPLOYED=True,
        RMC_DEPLOYMENT_PROFILE="online", LITELLM_PROXY_URL=OPENAI,
    )
    def test_an_undeclared_render_deploy_still_gets_no_ollama(self):
        # The whole chain, driven only by the inference — no env var set.
        self.assertEqual(default_tier_chain_for_profile(), ["litellm", "rules"])

    @override_settings(RMC_AI_CLOUD_HOST="yes")
    def test_the_override_accepts_the_usual_truthy_spellings(self):
        self.assertTrue(is_cloud_host())
