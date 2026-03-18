"""
Unauthenticated contract: every named /api/v1/* route (except public manifest)
must not return 2xx for anonymous GET (no open data leakage).
"""

from __future__ import annotations

import re
import uuid

from django.test import TestCase
from django.urls import reverse

from apps.api.urls_v1 import urlpatterns

_PLACEHOLDER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000042")


def _kwargs_for_route(pattern_str: str) -> dict:
    kw: dict = {}
    for m in re.finditer(r"<(uuid|int):(\w+)>", pattern_str):
        typ, name = m.group(1), m.group(2)
        kw[name] = _PLACEHOLDER_UUID if typ == "uuid" else 1
    return kw


class ApiV1RouteContractTests(TestCase):
    """Full v1 named route sweep — extends manifest + spot smoke tests."""

    _allowed_anonymous = frozenset({401, 403, 400, 404, 405, 302, 301, 429})

    def test_named_routes_except_manifest_do_not_return_2xx_anonymous_get(self):
        failures = []
        for p in urlpatterns:
            name = getattr(p, "name", None)
            if not name or name == "manifest":
                continue
            pattern_str = str(p.pattern)
            kws = _kwargs_for_route(pattern_str)
            try:
                url = reverse(f"api_v1:{name}", kwargs=kws)
            except Exception:
                try:
                    url = reverse(f"api_v1:{name}")
                except Exception as exc:
                    failures.append(f"{name}: reverse failed: {exc}")
                    continue
            r = self.client.get(url)
            if 200 <= r.status_code < 300:
                failures.append(
                    f"{name} GET {url} -> {r.status_code} (expected non-2xx for anonymous)"
                )
            elif r.status_code not in self._allowed_anonymous:
                failures.append(
                    f"{name} GET {url} -> {r.status_code} (not in allowed set {self._allowed_anonymous})"
                )
        self.assertEqual(
            failures,
            [],
            msg=";\n".join(failures) if failures else "",
        )
