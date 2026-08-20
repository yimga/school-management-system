"""A destination the model invented must resolve before anyone is sent to it.

The command palette falls back to the AI gateway when no deterministic intent
matches, and asks it for an internal path. The only check on the answer was
``url.startswith("/")`` — which proves the path is internal, not that it
exists. ``/finance/outstanding-fees/`` satisfies it perfectly and is a 404.

That is the worst version of the dead end this whole spec is about: the other
dead ends were written by a person once and stayed put, while this one is
generated fresh on every query, in the surface people reach for when they are
already lost.

The rule is the same one the deterministic intents follow — a destination has
to survive the URL resolver. AI is allowed to *choose* among real routes; it is
not allowed to *mint* one.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.portal.views_ai_line import _llm_fallback

TENANT_URLCONF = "config.tenant_urls"


class _Guard:
    allowed = True
    prompt = "prompt"
    metadata: dict = {}


def _request():
    request = RequestFactory().get("/")
    request.urlconf = TENANT_URLCONF
    return request


def _gateway_returns(payload):
    """Patch the gateway so the test drives exactly what the model 'said'."""
    return patch(
        "services.ai_helpers.invoke_with_request",
        return_value=(payload, {}),
    )


@override_settings(ROOT_URLCONF=TENANT_URLCONF)
class AGeneratedDestinationMustResolveTests(SimpleTestCase):
    def setUp(self):
        patcher = patch(
            "services.ai_copilot_rbac.guard_copilot_invoke", return_value=_Guard()
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_plausible_but_nonexistent_path_is_discarded(self):
        """Reads like a real route, resolves nowhere. This is the whole point."""
        with _gateway_returns(
            '{"url": "/finance/outstanding-fees/", "label": "Outstanding fees"}'
        ):
            self.assertIsNone(
                _llm_fallback("show me unpaid fees", _request()),
                "the palette accepted a destination the model invented",
            )

    def test_a_real_route_is_kept(self):
        with _gateway_returns('{"url": "/finance/invoices/", "label": "Invoices"}'):
            result = _llm_fallback("invoices", _request())
        self.assertIsNotNone(result, "a genuine route was thrown away")
        self.assertEqual(result["url"], "/finance/invoices/")

    def test_a_querystring_does_not_defeat_the_check(self):
        with _gateway_returns(
            '{"url": "/finance/invoices/?status=OVERDUE", "label": "Overdue"}'
        ):
            result = _llm_fallback("overdue invoices", _request())
        self.assertIsNotNone(result)
        self.assertIn("status=OVERDUE", result["url"])

    def test_an_external_url_is_still_refused(self):
        with _gateway_returns('{"url": "https://example.com/", "label": "Elsewhere"}'):
            self.assertIsNone(_llm_fallback("anything", _request()))

    def test_an_empty_answer_stays_empty(self):
        with _gateway_returns('{"url": "", "label": ""}'):
            self.assertIsNone(_llm_fallback("hello there", _request()))

    def test_a_route_absent_from_this_host_is_discarded(self):
        """Operator routes are real — just not here. Same 404 to this reader."""
        with _gateway_returns('{"url": "/super/dashboard/", "label": "Operator"}'):
            self.assertIsNone(
                _llm_fallback("operator console", _request()),
                "a route from another host was offered to a tenant reader",
            )
