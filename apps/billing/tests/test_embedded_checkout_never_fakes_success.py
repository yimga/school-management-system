"""Embedded checkout must never report success when no PSP can settle.

Found by an A-Z audit follow-up (2026-07-16).

``/billing/embedded-checkout/session/`` is public, ``csrf_exempt``, and wired
unconditionally in ``config/urls.py`` with no DEBUG gate. It is the endpoint a
school embeds on its own site so a parent can pay fees.

The dispatcher opened with the right instinct -- refuse anything that is not
live::

    _PRODUCTION_STATUSES: frozenset[str] = frozenset({"live"})

...and then never referenced that constant again. The live check that shipped
was instead a *fallthrough into dev mode*::

    if force_dev_mode or row.adapter_status != "live":
        return {"ok": True, "hosted_url": _dev_hosted_url(...), ...}

No row in ``psp_adapter_registry`` is ``live`` (census: 9 in_progress + 3
planned + 0 live -- the only "live" string in that module is in its docstring).
So ``!= "live"`` was unconditionally true, the live-dispatch path below it was
unreachable, and EVERY checkout returned HTTP 200 ``{"ok": true}`` with a
placeholder URL, having contacted no PSP and collected no money. The kernel
then stamped ``metadata["dispatched"] = True`` on the way out -- the one field
a caller would trust to tell it a PSP was actually reached.

Zero live adapters is an honest business state: PSP contracting is real-world
work the registry deliberately tracks. Reporting *payment success* because of
it is not. The kernel already has the correct machinery -- a dispatcher that
returns ``{"ok": False, "error": ...}`` makes ``create_session`` try the next
candidate and finally return ``ok=False`` -> HTTP 422. The dispatcher's own
docstring documents that contract. It just never used it for this case.

So: dev sessions become explicit opt-in (``EMBEDDED_CHECKOUT_DEV_MODE``, off
unless ``RMC_EMBEDDED_CHECKOUT_DEV_MODE=1``). With it off, a checkout that
cannot settle fails loudly instead of handing a parent a URL that takes no money.
"""

from __future__ import annotations

import json

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.billing.embedded_checkout import (
    CheckoutLineItem,
    CheckoutSessionRequest,
)
from apps.billing.embedded_checkout_psp_dispatcher import make_dispatcher
from apps.billing.psp_adapter_registry import iter_psps
from apps.billing.views_embedded_checkout import (
    create_embedded_checkout_session,
)


def _checkout_request() -> CheckoutSessionRequest:
    return CheckoutSessionRequest(
        tenant_id="t1", parent_email="p@e.com", parent_phone="",
        line_items=(CheckoutLineItem(
            sku="TUITION", description="Term 1",
            amount_minor=100000, currency="USD", quantity=1,
        ),),
    )


def _post(body: dict):
    return RequestFactory().post(
        "/billing/embedded-checkout/session/",
        data=json.dumps(body).encode("utf-8"),
        content_type="application/json",
    )


_VALID_BODY = {
    "tenant_id": "t1",
    "parent_email": "parent@example.com",
    "parent_phone": "",
    "line_items": [{
        "sku": "TUITION", "description": "Term 1",
        "amount_minor": 100000, "currency": "USD", "quantity": 1,
    }],
    "purpose": "tuition_fee",
}


class NoLivePSPIsTheCurrentRealityTests(SimpleTestCase):
    """Pins the premise the rest of this file depends on."""

    def test_zero_adapters_are_live(self):
        live = [p.psp_slug for p in iter_psps() if p.adapter_status == "live"]
        self.assertEqual(
            live, [],
            "This suite asserts the no-live-PSP behaviour. If a PSP has gone "
            "live, that is good news -- but re-read these tests rather than "
            "deleting them: the fail-closed contract still has to hold for "
            "every currency no live adapter covers.",
        )


@override_settings(EMBEDDED_CHECKOUT_DEV_MODE=False)
class CheckoutFailsClosedInProductionTests(SimpleTestCase):
    """With no live PSP and dev mode off, the answer must be 'no'."""

    def test_dispatcher_refuses_a_non_live_psp(self):
        dispatcher = make_dispatcher()
        result = dispatcher("stripe", _checkout_request(), "rmc_ck_abc", 100000)
        self.assertFalse(
            result["ok"],
            "a PSP that is not live cannot settle a payment -- the dispatcher "
            "must return ok=False so the kernel falls through to the next "
            "candidate, not hand back a placeholder URL that collects nothing",
        )
        self.assertIn("not live", result["error"])

    def test_public_post_does_not_report_a_fake_payment_session(self):
        """The whole bug, end to end, at the HTTP boundary."""
        resp = create_embedded_checkout_session(_post(_VALID_BODY))
        body = json.loads(resp.content)
        self.assertFalse(
            body["ok"],
            "the endpoint reported a successful checkout session while no PSP "
            "was contacted and no money could be collected",
        )
        self.assertEqual(resp.status_code, 422)

    def test_response_carries_no_placeholder_url(self):
        resp = create_embedded_checkout_session(_post(_VALID_BODY))
        self.assertNotIn(
            b"mode=dev", resp.content,
            "a parent must never be handed a dev placeholder URL by a "
            "production checkout",
        )


@override_settings(EMBEDDED_CHECKOUT_DEV_MODE=True)
class DevModeStillWorksWhenExplicitlyEnabledTests(SimpleTestCase):
    """Opt-in dev mode must keep the tenant-side UI flow renderable."""

    def test_dev_mode_returns_a_placeholder_session(self):
        dispatcher = make_dispatcher()
        result = dispatcher("stripe", _checkout_request(), "rmc_ck_abc", 100000)
        self.assertTrue(result["ok"])
        self.assertIn("mode=dev", result["hosted_url"])

    def test_dev_mode_never_claims_the_session_was_dispatched(self):
        """``dispatched`` is the field a caller trusts. It must stay honest.

        ``create_session`` stamps ``dispatched: True`` for any ok outcome and
        then merges the dispatcher's metadata over it, so the dispatcher gets
        the last word -- and a dev session did not dispatch anything.
        """
        resp = create_embedded_checkout_session(_post(_VALID_BODY))
        body = json.loads(resp.content)
        self.assertTrue(body["ok"])
        self.assertFalse(
            body["metadata"]["dispatched"],
            "a dev-mode session contacted no PSP, so dispatched must be False",
        )
        self.assertEqual(body["metadata"]["mode"], "dev")


@override_settings(EMBEDDED_CHECKOUT_DEV_MODE=False)
class UnknownProcessorStillRejectedTests(SimpleTestCase):
    """The pre-existing registry guard must survive the fix."""

    def test_unknown_processor_returns_error(self):
        dispatcher = make_dispatcher()
        result = dispatcher("fake-psp", _checkout_request(), "rmc_ck_abc", 100000)
        self.assertFalse(result["ok"])
        self.assertIn("not in registry", result["error"])
