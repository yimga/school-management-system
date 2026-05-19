"""Google pillar: bounded list search helpers."""

from django.test import SimpleTestCase

from apps.siteconfig.list_search import (
    MIN_LIST_SEARCH_LEN,
    apply_bounded_icontains,
    normalize_list_search_query,
)


class ListSearchHelperTests(SimpleTestCase):
    def test_normalize_strips_wildcards_and_caps_length(self):
        raw = "a%" + ("b" * 200)
        out = normalize_list_search_query(raw)
        self.assertNotIn("%", out)
        self.assertLessEqual(len(out), 128)

    def test_short_query_is_noop(self):
        class _QS:
            def filter(self, *a, **k):
                raise AssertionError("filter should not run")

        qs = _QS()
        result = apply_bounded_icontains(qs, "a", "title")
        self.assertIs(result, qs)

    def test_min_length_enforced(self):
        self.assertEqual(MIN_LIST_SEARCH_LEN, 2)

    def test_multi_token_and_semantics(self):
        from apps.siteconfig.list_search import tokenize_list_search

        self.assertEqual(tokenize_list_search("  john   smith "), ["john", "smith"])
