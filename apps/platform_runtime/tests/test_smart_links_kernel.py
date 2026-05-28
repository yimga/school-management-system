"""Wave T (v3.97.0 — 2026-05-26) — Smart-links kernel tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.smart_links_kernel import (
    ALL_PERSONAS,
    PERSONA_PARENT,
    PERSONA_TENANT_ADMIN,
    STATE_ADMISSION_PENDING,
    STATE_DSL_CONCERN_OPEN,
    STATE_ERROR_403,
    STATE_ERROR_403_CONTROL_PLANE,
    STATE_ERROR_403_STAFF,
    STATE_ERROR_404,
    STATE_ERROR_500,
    STATE_ERROR_503,
    STATE_OFFLINE,
    STATE_FROZEN_BILLING,
    STATE_FROZEN_OTHER,
    STATE_FROZEN_STORAGE,
    STATE_INVOICE_OVERDUE,
    STATE_PHOTO_FEATURE_DISABLED,
    STATE_PHOTO_LINK_EXPIRED,
    STATE_RECORDS_HOLD_ACTIVE,
    SmartLink,
    get_smart_links,
    list_registered_pairs,
    list_registered_states,
)


class SmartLinkDescriptorTests(SimpleTestCase):
    def test_url_name_only_is_valid(self) -> None:
        link = SmartLink(label="Pay", url_name="finance:dashboard")
        self.assertEqual(link.severity, "primary")
        self.assertEqual(link.icon, "bi-arrow-right")

    def test_href_only_is_valid(self) -> None:
        SmartLink(label="Retry", href=".")

    def test_mailto_only_is_valid(self) -> None:
        SmartLink(label="Support", mailto="help@example.com")

    def test_at_least_one_target_required(self) -> None:
        with self.assertRaises(ValueError):
            SmartLink(label="Nowhere")

    def test_severity_must_be_known(self) -> None:
        with self.assertRaises(ValueError):
            SmartLink(label="X", href="/y", severity="catastrophic")

    def test_frozen_dataclass_is_immutable(self) -> None:
        link = SmartLink(label="A", href="/a")
        with self.assertRaises(Exception):
            link.label = "B"  # type: ignore[misc]


class RegistryLookupTests(SimpleTestCase):
    def test_frozen_billing_returns_three_links(self) -> None:
        links = get_smart_links(STATE_FROZEN_BILLING)
        self.assertEqual(len(links), 3)
        # Primary action must be the payment-update link, not "sign out".
        self.assertEqual(links[0].severity, "primary")
        self.assertIn("payment", links[0].label.lower())

    def test_frozen_storage_returns_three_links(self) -> None:
        links = get_smart_links(STATE_FROZEN_STORAGE)
        self.assertEqual(len(links), 3)
        self.assertIn("storage", links[0].label.lower())

    def test_frozen_other_falls_back_to_support(self) -> None:
        links = get_smart_links(STATE_FROZEN_OTHER)
        self.assertGreaterEqual(len(links), 1)
        self.assertTrue(
            any("support" in link.label.lower() for link in links),
            "frozen.other should surface a support escalation",
        )

    def test_photo_expired_offers_new_link(self) -> None:
        links = get_smart_links(STATE_PHOTO_LINK_EXPIRED)
        self.assertGreaterEqual(len(links), 1)
        # First action is "request a new link" — not "go home".
        self.assertIn("new", links[0].label.lower())

    def test_photo_disabled_offers_alternative(self) -> None:
        links = get_smart_links(STATE_PHOTO_FEATURE_DISABLED)
        self.assertGreaterEqual(len(links), 1)
        # Should include either "upload on this device" or contact-admin.
        labels = " ".join(link.label.lower() for link in links)
        self.assertTrue(
            "upload" in labels or "enable" in labels,
            f"photo_feature_disabled should suggest a workaround: {labels!r}",
        )

    def test_404_offers_search(self) -> None:
        links = get_smart_links(STATE_ERROR_404)
        labels = " ".join(link.label.lower() for link in links)
        self.assertIn("search", labels)

    def test_403_control_plane_offers_request_access(self) -> None:
        links = get_smart_links(STATE_ERROR_403_CONTROL_PLANE)
        labels = " ".join(link.label.lower() for link in links)
        self.assertIn("request", labels)

    def test_500_offers_retry(self) -> None:
        links = get_smart_links(STATE_ERROR_500)
        labels = " ".join(link.label.lower() for link in links)
        self.assertIn("retry", labels)

    def test_403_tenant_offers_dashboard(self) -> None:
        links = get_smart_links(STATE_ERROR_403)
        url_names = {link.url_name for link in links}
        self.assertIn("accounts:redirect", url_names)

    def test_403_staff_offers_backend(self) -> None:
        links = get_smart_links(STATE_ERROR_403_STAFF)
        url_names = {link.url_name for link in links}
        self.assertIn("accounts:backend_dashboard", url_names)

    def test_503_offers_retry(self) -> None:
        links = get_smart_links(STATE_ERROR_503)
        labels = " ".join(link.label.lower() for link in links)
        self.assertIn("try again", labels)

    def test_offline_offers_retry(self) -> None:
        links = get_smart_links(STATE_OFFLINE)
        labels = " ".join(link.label.lower() for link in links)
        self.assertIn("retry", labels)

    def test_records_hold_active_routes_parent_to_balance(self) -> None:
        links = get_smart_links(STATE_RECORDS_HOLD_ACTIVE, persona=PERSONA_PARENT)
        self.assertGreaterEqual(len(links), 1)
        self.assertEqual(links[0].url_name, "portal:parent_finance")

    def test_invoice_overdue_pay_now(self) -> None:
        links = get_smart_links(STATE_INVOICE_OVERDUE, persona=PERSONA_PARENT)
        self.assertGreaterEqual(len(links), 1)
        self.assertEqual(links[0].url_name, "portal:parent_finance_pay_all")

    def test_admission_pending_routes_admin_to_queue(self) -> None:
        links = get_smart_links(
            STATE_ADMISSION_PENDING, persona=PERSONA_TENANT_ADMIN,
        )
        self.assertEqual(len(links), 1)
        self.assertIn("admissions", links[0].label.lower())

    def test_dsl_concern_routes_admin_to_workflow(self) -> None:
        links = get_smart_links(
            STATE_DSL_CONCERN_OPEN, persona=PERSONA_TENANT_ADMIN,
        )
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].severity, "danger")

    def test_unknown_state_returns_empty_list(self) -> None:
        # UX-enhancement API: a missing entry must NOT raise; the template
        # just renders nothing extra.
        self.assertEqual(get_smart_links("nonexistent.state"), [])

    def test_unknown_persona_falls_back_to_any(self) -> None:
        # A typo in persona shouldn't kill the page.
        links = get_smart_links(STATE_FROZEN_BILLING, persona="not-a-persona")
        self.assertGreaterEqual(len(links), 1)

    def test_persona_specific_takes_precedence_over_any(self) -> None:
        # records_hold_active is registered for PERSONA_PARENT only;
        # PERSONA_TENANT_ADMIN should fall back to ANY (empty here, since
        # we didn't register an admin variant).
        parent_links = get_smart_links(
            STATE_RECORDS_HOLD_ACTIVE, persona=PERSONA_PARENT,
        )
        any_links = get_smart_links(STATE_RECORDS_HOLD_ACTIVE)
        # PERSONA_ANY for records_hold_active is not registered, so any_links
        # is [] — and that's the contract: don't crash, just don't render.
        self.assertGreaterEqual(len(parent_links), 1)
        self.assertEqual(any_links, [])

    def test_registry_diagnostic_helpers(self) -> None:
        states = list_registered_states()
        pairs = list_registered_pairs()
        self.assertGreater(len(states), 5)
        self.assertGreater(len(pairs), 5)
        # Every registered persona must be a known persona constant.
        for _state, persona in pairs:
            self.assertIn(persona, ALL_PERSONAS)


class RegistryShapeInvariants(SimpleTestCase):
    """Every registered entry must hold to the design invariants."""

    def test_every_link_has_resolvable_target(self) -> None:
        for state, persona in list_registered_pairs():
            for link in get_smart_links(state, persona=persona):
                has_target = bool(link.url_name or link.href or link.mailto)
                self.assertTrue(
                    has_target,
                    f"({state}, {persona}) entry missing target: {link.label!r}",
                )

    def test_no_entry_uses_unknown_severity(self) -> None:
        # __post_init__ already guards this, but a registry change shouldn't
        # silently slip past — this asserts the loaded table is sound.
        valid = {"primary", "secondary", "danger", "success"}
        for state, persona in list_registered_pairs():
            for link in get_smart_links(state, persona=persona):
                self.assertIn(link.severity, valid)

    def test_primary_action_is_first(self) -> None:
        # UX contract: the most consequential action shows up first so the
        # user doesn't have to scan. If a state has any "primary" entries,
        # the very first link must be one of them.
        for state, persona in list_registered_pairs():
            links = get_smart_links(state, persona=persona)
            primaries = [link for link in links if link.severity == "primary"]
            if primaries:
                self.assertEqual(
                    links[0].severity,
                    "primary",
                    f"({state}, {persona}) lists a non-primary action first",
                )
