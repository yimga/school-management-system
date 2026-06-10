from django.http import HttpResponseRedirect
from django.test import RequestFactory, SimpleTestCase

from services.post_delete_navigation import (
    append_return_query,
    redirect_after_delete,
    redirect_after_mutation,
    resolve_return_url,
    safe_next_url,
)


class PostDeleteNavigationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, path="/list/", *, post=False, data=None, referer="", query=""):
        target = f"{path}{query}"
        if post:
            request = self.factory.post(target, data=data or {})
        else:
            request = self.factory.get(target)
        request.META["HTTP_HOST"] = "testserver"
        if referer:
            request.META["HTTP_REFERER"] = referer
        return request

    def test_prefers_post_next_over_referer(self):
        request = self._request(
            "/delete/1/",
            post=True,
            data={"next": "/list/?page=2"},
            referer="http://testserver/edit/1/",
        )
        self.assertEqual(
            resolve_return_url(request, "/list/"),
            "/list/?page=2",
        )

    def test_blocks_delete_referer_and_uses_fallback(self):
        request = self._request(
            "/delete/1/",
            post=True,
            referer="http://testserver/delete/1/",
        )
        self.assertEqual(resolve_return_url(request, "/list/"), "/list/")

    def test_uses_safe_referer_when_no_next(self):
        request = self._request(
            "/delete/1/",
            post=True,
            referer="http://testserver/list/?q=alpha",
        )
        self.assertEqual(
            resolve_return_url(request, "/list/"),
            "http://testserver/list/?q=alpha",
        )

    def test_list_url_used_when_referer_blocked(self):
        request = self._request(
            "/delete/1/",
            post=True,
            referer="http://testserver/edit/1/",
        )
        self.assertEqual(
            resolve_return_url(request, "/fallback/", list_url="/list/"),
            "/list/",
        )

    def test_redirect_after_mutation_returns_redirect(self):
        request = self._request("/delete/1/", post=True, data={"next": "/roster/"})
        response = redirect_after_mutation(request, "/list/")
        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertEqual(response.url, "/roster/")

    def test_redirect_after_mutation_htmx_sets_header(self):
        request = self._request("/delete/1/", post=True, data={"next": "/roster/"})
        request.META["HTTP_HX_REQUEST"] = "true"
        response = redirect_after_mutation(request, "/list/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], "/roster/")

    def test_append_return_query_adds_next(self):
        request = self._request("/list/?page=3")
        url = append_return_query("/delete/5/", request, "/list/")
        self.assertIn("next=", url)
        self.assertIn("%2Flist%2F", url)

    def test_safe_next_url_rejects_off_host_candidate(self):
        request = self._request("/here/")
        self.assertEqual(safe_next_url(request, "https://evil.test/x", "/ok/"), "/ok/")

    def test_delete_prefers_list_over_detail_referer(self):
        request = self._request(
            "/offboard/1/",
            post=True,
            referer="http://testserver/super/team/42/",
        )
        response = redirect_after_delete(request, "/roster/", list_url="/roster/")
        self.assertEqual(response.url, "/roster/")
