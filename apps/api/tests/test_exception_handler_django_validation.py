"""The RFC 7807 handler must turn a Django-core ValidationError into a 400.

DRF's default handler maps only APIException / Http404 / DRF-PermissionDenied, so a
model ``save()``/``full_clean()`` that raises ``django.core.exceptions.ValidationError``
(the shape a plan usage cap in ``apps/schools/plan_limits.py`` raises) fell through to
``return None`` -> a Django 500 + Sentry capture for what is a client input error.

These are ``SimpleTestCase`` (no DB) and call the handler directly, so they prove the
translation without standing up a request cycle. Against the pre-fix handler the first
test FAILS at ``assertIsNotNone`` (it returned ``None``).
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import SimpleTestCase

from apps.api.exception_handler import PROBLEM_CONTENT_TYPE, rfc7807_exception_handler


class _FakeRequest:
    path = "/api/v1/students/"


class DjangoValidationErrorEnvelopeTests(SimpleTestCase):
    def test_single_message_becomes_400_not_500(self):
        exc = DjangoValidationError(
            "Your plan's students limit of 50 has been reached. "
            "Upgrade to add more — everything already set up keeps working."
        )
        response = rfc7807_exception_handler(exc, {"request": _FakeRequest()})

        # Pre-fix: the handler returned None here -> Django rendered a 500.
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 400)
        self.assertIn("50 has been reached", response.data["detail"])
        self.assertEqual(response.data["status"], 400)
        self.assertEqual(response.data["instance"], "/api/v1/students/")
        self.assertEqual(response["Content-Type"], PROBLEM_CONTENT_TYPE)

    def test_multiple_messages_populate_errors_list(self):
        exc = DjangoValidationError(["First problem.", "Second problem."])
        response = rfc7807_exception_handler(exc, {"request": _FakeRequest()})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            [e["message"] for e in response.data["errors"]],
            ["First problem.", "Second problem."],
        )

    def test_missing_request_does_not_crash(self):
        exc = DjangoValidationError("cap reached")
        response = rfc7807_exception_handler(exc, {"request": None})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["instance"], "")

    def test_non_validation_non_drf_exception_still_returns_none(self):
        # A genuine server fault must still fall through to Django's 500 + Sentry.
        response = rfc7807_exception_handler(RuntimeError("boom"), {"request": None})
        self.assertIsNone(response)
