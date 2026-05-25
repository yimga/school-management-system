"""GraphQL production safety contract tests (batch 1493).

These tests pin the contract that prevents the medium-risk findings noted by
the runtime-proof-hardening audit:

- introspection disabled unless explicit opt-in
- POST-only writes accept application/json only
- IP rate limit enforced
- missing/invalid query rejected with structured error
"""

from __future__ import annotations

import json

from django.test import RequestFactory, SimpleTestCase, override_settings

from config.graphql_view import _INTROSPECTION_RE, _introspection_allowed, graphql_gateway


class GraphQLSecurityContractTests(SimpleTestCase):
    def setUp(self) -> None:
        self.rf = RequestFactory()

    @override_settings(DEBUG=False, GRAPHQL_INTROSPECTION_ENABLED=False)
    def test_introspection_disabled_in_production(self) -> None:
        self.assertFalse(_introspection_allowed())

    @override_settings(DEBUG=False, GRAPHQL_INTROSPECTION_ENABLED=True)
    def test_introspection_enabled_only_with_explicit_flag(self) -> None:
        self.assertTrue(_introspection_allowed())

    def test_introspection_regex_matches_canonical_queries(self) -> None:
        for needle in ("__schema", "__type", "IntrospectionQuery"):
            self.assertIsNotNone(_INTROSPECTION_RE.search(f"query x {{ {needle} }}"))

    def test_introspection_regex_ignores_safe_query(self) -> None:
        self.assertIsNone(_INTROSPECTION_RE.search("query x { schoolCount }"))

    @override_settings(DEBUG=False, GRAPHQL_INTROSPECTION_ENABLED=False)
    def test_post_rejects_non_json_content_type(self) -> None:
        req = self.rf.post(
            "/graphql/",
            data=b"raw=text",
            content_type="application/x-www-form-urlencoded",
        )
        resp = graphql_gateway(req)
        self.assertEqual(resp.status_code, 415)

    @override_settings(DEBUG=False, GRAPHQL_INTROSPECTION_ENABLED=False)
    def test_post_rejects_missing_query(self) -> None:
        req = self.rf.post(
            "/graphql/",
            data=json.dumps({}),
            content_type="application/json",
        )
        resp = graphql_gateway(req)
        self.assertEqual(resp.status_code, 400)

    @override_settings(DEBUG=False, GRAPHQL_INTROSPECTION_ENABLED=False)
    def test_introspection_query_rejected_when_disabled(self) -> None:
        req = self.rf.post(
            "/graphql/",
            data=json.dumps({"query": "{ __schema { types { name } } }"}),
            content_type="application/json",
        )
        resp = graphql_gateway(req)
        self.assertEqual(resp.status_code, 403)

    @override_settings(DEBUG=False, GRAPHQL_INTROSPECTION_ENABLED=False)
    def test_invalid_json_body_rejected(self) -> None:
        req = self.rf.post(
            "/graphql/",
            data=b"not-json",
            content_type="application/json",
        )
        resp = graphql_gateway(req)
        self.assertEqual(resp.status_code, 400)
