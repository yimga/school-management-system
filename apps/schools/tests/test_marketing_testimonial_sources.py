"""Tests for the multi-source testimonial registry + provider framework.

Covers the three contract guarantees:
  * configured_sources() defaults exclude external review platforms;
  * external providers return [] without credentials;
  * the registry has a badge_label for every model Source choice.
"""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.schools.marketing_testimonial_sources import (
    EXTERNAL_CONNECTORS,
    CapterraConnector,
    G2Connector,
    GoogleBusinessConnector,
    LinkedInConnector,
    ManualDBProvider,
    TestimonialProvider,
    TrustpilotConnector,
    all_sources,
    badge_label_for,
    configured_sources,
    enabled_external_connectors,
    is_source_enabled,
)
from apps.siteconfig.models_marketing_testimonial import MarketingTestimonial


class ConfiguredSourcesDefaultsTests(SimpleTestCase):
    """configured_sources() defaults exclude every external review platform."""

    @override_settings(RMC_MARKETING_TESTIMONIAL_SOURCES="")
    def test_defaults_are_first_party_only(self):
        enabled = configured_sources()
        self.assertIn("DIRECT", enabled)
        self.assertIn("CASE_STUDY", enabled)
        self.assertIn("PRESS", enabled)

    @override_settings(RMC_MARKETING_TESTIMONIAL_SOURCES="")
    def test_external_platforms_off_by_default(self):
        enabled = set(configured_sources())
        for external in ("G2", "CAPTERRA", "GOOGLE", "TRUSTPILOT", "LINKEDIN"):
            self.assertNotIn(external, enabled, f"{external} must default OFF")

    @override_settings(RMC_MARKETING_TESTIMONIAL_SOURCES="DIRECT,G2")
    def test_csv_allowlist_is_authoritative(self):
        enabled = configured_sources()
        self.assertEqual(set(enabled), {"DIRECT", "G2"})
        self.assertNotIn("CASE_STUDY", enabled)

    @override_settings(
        RMC_MARKETING_TESTIMONIAL_SOURCES="",
        RMC_TESTIMONIAL_SOURCE_G2_ENABLED="true",
    )
    def test_per_source_override_enables_external(self):
        self.assertTrue(is_source_enabled("G2"))

    @override_settings(
        RMC_MARKETING_TESTIMONIAL_SOURCES="",
        RMC_TESTIMONIAL_SOURCE_DIRECT_ENABLED="false",
    )
    def test_per_source_override_disables_default(self):
        self.assertFalse(is_source_enabled("DIRECT"))

    @override_settings(RMC_MARKETING_TESTIMONIAL_SOURCES="DIRECT,BOGUS_KEY")
    def test_unknown_csv_keys_ignored(self):
        self.assertEqual(configured_sources(), ["DIRECT"])


class ExternalProviderNoCredentialTests(SimpleTestCase):
    """External providers return [] when enabled but uncredentialed.

    Stays a ``SimpleTestCase``: ``service_integration_config`` lazy-imports the
    model and best-effort-swallows any DB/app-registry error, so the no-op path
    holds without a configured database.
    """

    @override_settings(
        RMC_MARKETING_TESTIMONIAL_SOURCES="G2,CAPTERRA,GOOGLE,TRUSTPILOT,LINKEDIN"
    )
    def test_all_external_connectors_empty_without_credentials(self):
        for connector_cls in (
            G2Connector,
            CapterraConnector,
            GoogleBusinessConnector,
            TrustpilotConnector,
            LinkedInConnector,
        ):
            self.assertEqual(
                connector_cls().fetch(),
                [],
                f"{connector_cls.__name__} must no-op without credentials",
            )

    @override_settings(RMC_MARKETING_TESTIMONIAL_SOURCES="")
    def test_disabled_connector_returns_empty(self):
        # Even with credentials present, a disabled source must not fetch.
        with override_settings(
            RMC_TESTIMONIAL_G2_API_TOKEN="tok",
            RMC_TESTIMONIAL_G2_PRODUCT_ID="123",
        ):
            self.assertEqual(G2Connector().fetch(), [])

    @override_settings(RMC_MARKETING_TESTIMONIAL_SOURCES="")
    def test_enabled_external_connectors_empty_by_default(self):
        self.assertEqual(enabled_external_connectors(), [])

    @override_settings(RMC_MARKETING_TESTIMONIAL_SOURCES="DIRECT,G2,TRUSTPILOT")
    def test_enabled_external_connectors_reflect_config(self):
        keys = {c.source_key for c in enabled_external_connectors()}
        self.assertEqual(keys, {"G2", "TRUSTPILOT"})


class RegistryBadgeCoverageTests(SimpleTestCase):
    """Every model Source choice has a badge_label in the registry."""

    def test_badge_label_for_every_model_source(self):
        for value, _label in MarketingTestimonial.Source.choices:
            badge = badge_label_for(value)
            self.assertTrue(
                badge,
                f"missing/empty badge_label for model Source value {value!r}",
            )

    def test_registry_keys_match_model_sources_exactly(self):
        registry_keys = {s.key for s in all_sources()}
        model_keys = {value for value, _ in MarketingTestimonial.Source.choices}
        self.assertEqual(registry_keys, model_keys)

    def test_every_external_connector_source_in_registry(self):
        registry_keys = {s.key for s in all_sources()}
        for key in EXTERNAL_CONNECTORS:
            self.assertIn(key, registry_keys)


class ProviderProtocolTests(SimpleTestCase):
    """Providers satisfy the TestimonialProvider protocol shape."""

    def test_manual_db_provider_is_a_provider(self):
        self.assertIsInstance(ManualDBProvider(), TestimonialProvider)

    def test_external_connectors_are_providers(self):
        for connector_cls in EXTERNAL_CONNECTORS.values():
            self.assertIsInstance(connector_cls(), TestimonialProvider)

    def test_external_stamp_forces_unapproved(self):
        connector = G2Connector()
        stamped = connector._stamp_unapproved({"quote": "hi"})
        self.assertFalse(stamped["is_approved"])
        self.assertTrue(stamped["ingested_from_source"])
        self.assertEqual(stamped["source"], "G2")
