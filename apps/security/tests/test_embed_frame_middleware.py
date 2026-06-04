from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.security.embed_frame_middleware import EmbedSameOriginFrameMiddleware


@override_settings(X_FRAME_OPTIONS="DENY")
class EmbedSameOriginFrameMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = EmbedSameOriginFrameMiddleware(
            lambda request: HttpResponse("ok")
        )

    def test_embed_query_sets_sameorigin(self):
        request = self.factory.get("/siteconfig/guided-onboarding/?embed=1")
        response = self.middleware(request)
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")

    def test_non_embed_does_not_force_sameorigin(self):
        request = self.factory.get("/siteconfig/guided-onboarding/")
        response = self.middleware(request)
        self.assertNotEqual(response.get("X-Frame-Options"), "SAMEORIGIN")

    def test_embed_true_alias(self):
        request = self.factory.get("/studio/launch/", {"embed": "true"})
        response = self.middleware(request)
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")
