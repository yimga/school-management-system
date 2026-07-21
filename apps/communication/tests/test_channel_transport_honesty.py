"""Transport-honesty seals for the channel adapter layer.

Globalization program items 0.2 (SMS is a silent no-op) and 0.3 (USSD/IVR
report success while sending nothing).

Every test here is a MUST-FIRE test: reverting the corresponding fix turns it
RED. The invariants being sealed:

* Under a production-like configuration, a channel with no real transport must
  never yield ``success=True``.
* An adapter whose vendor SDK is absent must not be selectable, and selection
  with no usable adapter must raise ``ChannelUnavailableError`` -- never a
  silent success.
* A send-nothing placeholder must be visible as ``simulated`` in the audit
  trail, and must require an explicit opt-in before it can occupy a registry
  slot in production.

These channels are the ones feature-phone families in Cameroon, Nigeria, Kenya,
Ghana, India, Bangladesh and elsewhere actually depend on, so a phantom
"delivered" here is a family that never learns their child was sent home.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from apps.communication.channel_adapter import (
    ChannelAdapterRegistry,
    ChannelAddress,
    ChannelMessage,
    ChannelUnavailableError,
    LoopbackTestAdapter,
    SmsChannelAdapter,
    _LogOnlyAdapter,
    log_only_adapters_allowed,
    register_log_only_defaults,
    registry,
    send_message,
)
from apps.communication.providers.sms_base import sms_sdk_available

# DEBUG off + RUNNING_TESTS off is what `_is_production_like()` reads, so this
# is the closest a unit test can get to the deployed configuration.
PROD_LIKE = dict(DEBUG=False, RUNNING_TESTS=False)


class _StubSiteSettings:
    """Minimal SiteSettings stand-in with SMS credentials present."""

    sms_provider = "africastalking"
    sms_api_key = "test-key"
    sms_sender_id = "SCHOOL"


class LogOnlyAdapterHonestyTests(SimpleTestCase):
    """Item 0.3 -- a placeholder must never claim delivery."""

    def setUp(self) -> None:
        registry().clear()

    def tearDown(self) -> None:
        registry().clear()

    @override_settings(**PROD_LIKE, COMMS_ALLOW_LOG_ONLY_ADAPTERS=True)
    def test_production_like_send_on_channel_without_transport_is_not_success(self) -> None:
        """ACCEPTANCE 1: no real transport => never success=True."""
        register_log_only_defaults()
        for channel in ("ussd", "ivr", "sms", "whatsapp", "email", "push"):
            with self.subTest(channel=channel):
                result = send_message(
                    tenant_id="tenant-douala-1",
                    address=ChannelAddress(channel=channel, address="+237600000000"),
                    message=ChannelMessage(subject="Fees", body_text="Fees due Friday"),
                )
                self.assertFalse(
                    result.success,
                    f"{channel}: log-only adapter reported a delivery it never made",
                )
                self.assertTrue(result.simulated)
                self.assertIn("no-transport-configured", result.detail)

    @override_settings(**PROD_LIKE)
    def test_log_only_defaults_refused_in_production_without_opt_in(self) -> None:
        self.assertFalse(log_only_adapters_allowed())
        with self.assertRaises(ImproperlyConfigured):
            register_log_only_defaults()
        # ...and with nothing registered, selection is loud rather than silent.
        with self.assertRaises(ChannelUnavailableError):
            send_message(
                tenant_id="tenant-douala-1",
                address=ChannelAddress(channel="ussd", address="+237600000000"),
                message=ChannelMessage(subject="Fees", body_text="Fees due Friday"),
            )

    @override_settings(**PROD_LIKE, COMMS_ALLOW_LOG_ONLY_ADAPTERS=True)
    def test_simulated_hop_is_visible_in_the_audit_trail(self) -> None:
        register_log_only_defaults()
        events: list[dict] = []
        send_message(
            tenant_id="tenant-douala-1",
            address=ChannelAddress(channel="ivr", address="+237600000000"),
            message=ChannelMessage(subject="Fees", body_text="Fees due Friday"),
            audit=events.append,
        )
        self.assertEqual(len(events), 1)
        self.assertIs(events[0]["simulated"], True)
        self.assertIs(events[0]["success"], False)

    @override_settings(**PROD_LIKE)
    def test_loopback_test_double_cannot_be_registered_in_production(self) -> None:
        reg = ChannelAdapterRegistry()
        with self.assertRaises(ImproperlyConfigured):
            reg.register(LoopbackTestAdapter(channel="ussd", adapter_id="loopback:ussd"))

    def test_loopback_test_double_is_allowed_under_test_settings(self) -> None:
        # The fixture stays usable as a test double -- that is legitimate.
        reg = ChannelAdapterRegistry()
        reg.register(LoopbackTestAdapter(channel="ussd", adapter_id="loopback:ussd"))
        entry = reg.select(preferred_channels=["ussd"])
        result = entry.adapter.send(
            tenant_id="t1",
            address=ChannelAddress(channel="ussd", address="+237600000000"),
            message=ChannelMessage(subject="x", body_text="y"),
        )
        self.assertTrue(result.success)
        self.assertTrue(result.simulated)


class SmsSdkAvailabilityTests(SimpleTestCase):
    """Item 0.2 -- a transport whose SDK is absent must be LOUD."""

    def setUp(self) -> None:
        registry().clear()

    def tearDown(self) -> None:
        registry().clear()

    def test_sms_sdk_probe_knows_the_vendor_modules(self) -> None:
        # A key with no SDK requirement is trivially available; the two real
        # ones resolve against the installed environment.
        self.assertTrue(sms_sdk_available("console"))
        self.assertTrue(sms_sdk_available(""))
        self.assertIsInstance(sms_sdk_available("twilio"), bool)
        self.assertIsInstance(sms_sdk_available("africastalking"), bool)

    def test_sms_adapter_unavailable_when_no_sdk_and_selection_raises(self) -> None:
        """ACCEPTANCE 2: SDK absent => adapter not selectable, no silent success."""
        adapter = SmsChannelAdapter(site_settings=_StubSiteSettings())
        self.assertEqual(
            tuple(adapter._provider_keys()),
            ("twilio", "africastalking"),
        )

        # Simulate every SMS SDK being absent from the deployed image.
        import apps.communication.providers.sms_base as sms_base

        original = sms_base.sms_sdk_available
        sms_base.sms_sdk_available = lambda key: False  # type: ignore[assignment]
        try:
            self.assertFalse(adapter.is_available())
            reg = ChannelAdapterRegistry()
            reg.register(adapter)
            # Registered but unusable => skipped, not selected.
            self.assertEqual(reg.for_channels(["sms"]), [])
            with self.assertRaises(ChannelUnavailableError):
                reg.select(preferred_channels=["sms"])
        finally:
            sms_base.sms_sdk_available = original  # type: ignore[assignment]

    def test_sms_provider_send_reports_failure_when_sdk_absent(self) -> None:
        """The provider itself must not report ok when the wheel is missing."""
        from apps.communication.providers import sms_africastalking

        original = sms_africastalking.sms_sdk_available
        sms_africastalking.sms_sdk_available = lambda key: False  # type: ignore[assignment]
        try:
            provider = sms_africastalking.AfricasTalkingSMSProvider(_StubSiteSettings())
            with self.assertLogs("apps.communication.providers.sms_africastalking", level="ERROR"):
                result = provider.send("+237600000000", "Fees due Friday")
            self.assertFalse(result.ok)
            self.assertEqual(result.error, "africastalking_sdk_not_installed")
        finally:
            sms_africastalking.sms_sdk_available = original  # type: ignore[assignment]

    def test_available_sms_adapter_is_selectable(self) -> None:
        # Positive control: the skip logic must not blacklist a healthy adapter.
        adapter = SmsChannelAdapter(site_settings=_StubSiteSettings())
        import apps.communication.providers.sms_base as sms_base

        original = sms_base.sms_sdk_available
        sms_base.sms_sdk_available = lambda key: True  # type: ignore[assignment]
        try:
            reg = ChannelAdapterRegistry()
            reg.register(adapter)
            entry = reg.select(preferred_channels=["sms"])
            self.assertIs(entry.adapter, adapter)
        finally:
            sms_base.sms_sdk_available = original  # type: ignore[assignment]

    def test_unavailable_adapter_never_shadows_an_available_one(self) -> None:
        reg = ChannelAdapterRegistry()

        class _DeadCheapAdapter:
            channel = "sms"
            adapter_id = "dead-cheap"
            cost_rank = 1
            enabled = True

            def is_available(self) -> bool:
                return False

            def send(self, *, tenant_id, address, message):  # pragma: no cover
                raise AssertionError("unavailable adapter must never be selected")

        reg.register(_DeadCheapAdapter())
        reg.register(_LogOnlyAdapter(channel="sms", adapter_id="log-only:sms", cost_rank=20))
        entry = reg.select(preferred_channels=["sms"])
        self.assertEqual(entry.adapter.adapter_id, "log-only:sms")


class SmsSdkPinnedTests(SimpleTestCase):
    """Item 0.2 -- the pin itself, in the file the deployed image installs."""

    def test_sms_sdks_are_pinned_in_the_installed_requirements_file(self) -> None:
        from pathlib import Path

        from django.conf import settings as dj_settings

        req = Path(dj_settings.BASE_DIR) / "requirements.txt"
        text = req.read_text(encoding="utf-8")
        # build.sh (the buildCommand for every Render service) installs
        # requirements.txt ONLY -- requirements_optional.txt is never installed,
        # so a pin there would leave the deployed image unable to send SMS.
        for pkg in ("twilio", "africastalking"):
            self.assertRegex(
                text,
                rf"(?m)^{pkg}[><=~]",
                f"{pkg} must be pinned in requirements.txt (the file build.sh installs)",
            )
