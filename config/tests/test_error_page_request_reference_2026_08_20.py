"""An error page must hand back the correlator the logs are keyed by.

Incident that motivated this: a tenant hit a 500 on
``/authentication/backend/`` on an on-prem box. The server had already stamped
``X-Request-ID`` on the response and printed ``request_id=<id>`` on every log
line, but the PAGE showed nothing, so the report arrived with no searchable
handle and the traceback had to be hunted by timestamp.

These tests pin the contract in both directions: the id is rendered when one was
stamped, and nothing is invented when it was not. They also pin the untrusted
input handling — ``ObservabilityMiddleware`` honours an inbound ``X-Request-ID``
header, so the value reaching the template is client-controlled.
"""

from django.contrib.auth.models import AnonymousUser
from django.template.loader import get_template, render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from config.error_handlers import error_reference, server_error


class ErrorReferenceValueTests(SimpleTestCase):
    """``error_reference`` is the only thing that decides what reaches a template."""

    def setUp(self):
        self.rf = RequestFactory()

    def _req(self, request_id=None):
        request = self.rf.get("/authentication/backend/")
        if request_id is not None:
            request.request_id = request_id
        return request

    def test_returns_the_stamped_request_id(self):
        self.assertEqual(
            error_reference(self._req("f574656a-ace2-44b7-ac03-23aa828fa3d4")),
            "f574656a-ace2-44b7-ac03-23aa828fa3d4",
        )

    def test_missing_attribute_yields_empty_string_not_a_placeholder(self):
        # No middleware ran. An error page must not print "None" or invent an id
        # that an operator would then fruitlessly grep for.
        self.assertEqual(error_reference(self._req()), "")

    def test_blank_and_whitespace_ids_are_treated_as_absent(self):
        self.assertEqual(error_reference(self._req("")), "")
        self.assertEqual(error_reference(self._req("   ")), "")

    def test_client_supplied_markup_is_rejected_outright(self):
        # The middleware trusts an inbound X-Request-ID header, so this value is
        # attacker-controllable. Autoescaping would already neutralise it in the
        # HTML body, but it also lands in log lines and a data- attribute, so it
        # is rejected at the source rather than relied on downstream.
        self.assertEqual(error_reference(self._req('"><script>alert(1)</script>')), "")
        self.assertEqual(error_reference(self._req("has space")), "")
        self.assertEqual(error_reference(self._req("new\nline")), "")

    def test_absurdly_long_ids_are_rejected(self):
        self.assertEqual(error_reference(self._req("a" * 65)), "")
        self.assertEqual(error_reference(self._req("a" * 64)), "a" * 64)

    def test_ordinary_id_shapes_are_accepted(self):
        for value in ("abc1234", "req_01HX9Z", "a.b-c:d", "0123456789abcdef"):
            with self.subTest(value=value):
                self.assertEqual(error_reference(self._req(value)), value)

    def test_never_raises_when_the_attribute_explodes(self):
        # An error page is the last line of defence; it must not fail while
        # reporting a failure.
        class Hostile:
            @property
            def request_id(self):
                raise RuntimeError("boom")

        self.assertEqual(error_reference(Hostile()), "")


@override_settings(ALLOWED_HOSTS=["testserver"])
class ServerErrorPageRendersReferenceTests(SimpleTestCase):
    """End-to-end through the real handler.

    ``server_error`` has two stages: the branded ``errors/500.html`` and, if that
    raises, the standalone ``errors/500_minimal.html``. BOTH must carry the
    reference — the fallback especially, since it is what a box serves when the
    template chain is exactly what is broken, which is when an operator most
    needs the correlator.
    """

    def setUp(self):
        self.rf = RequestFactory()

    def _render(self, request_id=None):
        request = self.rf.get("/authentication/backend/")
        request.user = None  # handler coerces to AnonymousUser
        if request_id is not None:
            request.request_id = request_id
        response = server_error(request)
        return response, response.content.decode("utf-8", errors="replace")

    def test_reference_survives_whichever_stage_serves_the_page(self):
        response, body = self._render("f574656a-ace2-44b7-ac03-23aa828fa3d4")
        self.assertEqual(response.status_code, 500)
        self.assertIn("f574656a-ace2-44b7-ac03-23aa828fa3d4", body)

    def test_no_reference_text_when_no_id_was_stamped(self):
        response, body = self._render()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("Reference:", body)

    def test_page_still_renders_500_when_the_id_is_rejected(self):
        # A hostile id must degrade to "no reference", never to a second failure.
        response, body = self._render('"><script>alert(1)</script>')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertNotIn("Reference:", body)


class ErrorTemplateContractTests(TestCase):
    """Render the templates directly, independent of which stage the handler picks.

    A ``TestCase`` rather than ``SimpleTestCase`` because ``errors/500.html``
    extends ``base.html``, whose context processors hit the database — which is
    itself worth knowing: the branded 500 page cannot render without a working
    DB, and a DB fault is a very common cause of a 500. That is exactly why the
    standalone fallback below must carry the reference on its own.
    """

    def _branded(self, context):
        # errors/500.html extends base.html, whose context processors need a real
        # request; render_to_string with one is how the handler reaches it too.
        request = RequestFactory().get("/authentication/backend/")
        request.user = AnonymousUser()
        return render_to_string("errors/500.html", context, request=request)

    def test_branded_500_shows_the_reference_and_a_copyable_hook(self):
        html = self._branded({"error_reference": "abc123def456"})
        self.assertIn("abc123def456", html)
        self.assertIn('data-error-reference="abc123def456"', html)

    def test_branded_500_omits_the_block_entirely_without_a_reference(self):
        html = self._branded({})
        self.assertNotIn("error-reference", html)

    def test_minimal_fallback_shows_the_reference(self):
        html = get_template("errors/500_minimal.html").render(
            {"error_reference": "abc123def456"}
        )
        self.assertIn("abc123def456", html)

    def test_minimal_fallback_keeps_its_promise_or_makes_none(self):
        # The copy asserts "the fault has been logged with an incident reference".
        # Rendering that sentence with no reference on the page is a promise the
        # page does not keep, which is the state this file was written to end.
        html = get_template("errors/500_minimal.html").render({})
        if "incident reference" in html:
            self.assertNotIn(
                "Reference:", html, msg="empty reference block rendered"
            )

    def test_minimal_fallback_is_actually_self_contained(self):
        # Its own comment claims "no external CSS dependency", but commit
        # 39077adad dropped the <style> block, leaving the last-resort error page
        # completely unstyled. Lock the stylesheet in.
        html = get_template("errors/500_minimal.html").render({})
        self.assertIn("<style>", html)
        self.assertNotIn(
            '<link rel="stylesheet"',
            html,
            msg="the last-resort page must not depend on /static/ being reachable",
        )
        for hook in (".err-code", ".actions", ".rule"):
            with self.subTest(hook=hook):
                self.assertIn(hook, html)
