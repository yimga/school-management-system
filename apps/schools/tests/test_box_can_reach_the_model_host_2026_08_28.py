"""A box that cannot resolve its model host answers every question from rules (2026-08-28).

Reported as "ollama on the local box doesn't work — all it does is a table". It
was not Ollama. `deploy/selfhost/.env.edge.example` ships
`OLLAMA_ENDPOINT=http://host.docker.internal:11434`, and
`deploy/selfhost/docker-compose.yml` shipped no `extra_hosts` mapping for that
name. `host.docker.internal` is a Docker **Desktop** convenience; on a Linux
engine — which is what an appliance is — the name does not exist. So every
discovery candidate failed (`127.0.0.1` and `localhost` are the container
itself), `probe_ai_provider_reachable` returned the rules tier, and the copilot
answered every question with a canned table and *the language model on this
server is offline*.

Two things made it survive:

* `deploy/observability/docker-compose.yml` has carried the `host-gateway` line
  all along, so this was an omission in one stack rather than a policy.
* `check_edge_readiness` reported **OK** for it, because it only checked that
  `OLLAMA_ENDPOINT` was *set*. A set endpoint is not a reachable one, and the
  check that was supposed to catch this was the reason nobody looked.

These tests pin both halves: the compose must map any host the shipped env
example depends on, and the readiness command must fail — not pass — when the
endpoint's host does not resolve.
"""

from __future__ import annotations

import pathlib
from unittest import mock

from django.test import SimpleTestCase

REPO = pathlib.Path(__file__).resolve().parents[3]
COMPOSE = REPO / "deploy" / "selfhost" / "docker-compose.yml"
ENV_EXAMPLE = REPO / "deploy" / "selfhost" / ".env.edge.example"

DESKTOP_ONLY_HOST = "host.docker.internal"
HOST_GATEWAY_MAP = f"{DESKTOP_ONLY_HOST}:host-gateway"


class SelfhostComposeReachesTheHostTests(SimpleTestCase):
    def test_the_shipped_env_example_still_points_at_the_desktop_only_name(self):
        # The premise. If someone repoints the example at a LAN IP, the mapping
        # below stops being load-bearing and this fixture should be revisited
        # rather than silently keeping a rule nothing needs.
        self.assertIn(
            DESKTOP_ONLY_HOST,
            ENV_EXAMPLE.read_text(encoding="utf-8"),
            "the edge env example no longer depends on host.docker.internal",
        )

    def test_every_app_service_maps_the_host_gateway(self):
        import yaml

        compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        services = compose.get("services") or {}
        app_services = [
            name
            for name, body in services.items()
            if isinstance(body, dict) and "runmycampus-selfhost" in str(body.get("image", ""))
        ]
        self.assertTrue(app_services, "no app service found in the selfhost compose")
        for name in app_services:
            with self.subTest(service=name):
                self.assertIn(
                    HOST_GATEWAY_MAP,
                    services[name].get("extra_hosts") or [],
                    f"{name} cannot resolve {DESKTOP_ONLY_HOST} on a Linux box, so the "
                    "copilot will silently answer from rules only",
                )

    def test_the_observability_stack_is_still_the_precedent(self):
        # Cited in the compose comment. If it ever loses the line, the comment
        # becomes misleading and this says so.
        other = REPO / "deploy" / "observability" / "docker-compose.yml"
        self.assertIn(HOST_GATEWAY_MAP, other.read_text(encoding="utf-8"))


class ReadinessProbesTheEndpointTests(SimpleTestCase):
    """`check_edge_readiness` must not call an unreachable endpoint OK."""

    def _module(self):
        from apps.schools.management.commands import check_edge_readiness

        return check_edge_readiness

    def test_it_reads_the_host_out_of_an_endpoint(self):
        mod = self._module()
        self.assertEqual(
            mod._ollama_host("http://host.docker.internal:11434"), DESKTOP_ONLY_HOST
        )
        self.assertEqual(mod._ollama_host("http://10.10.20.137:11434/api/generate"), "10.10.20.137")
        self.assertEqual(mod._ollama_host("not a url"), "")

    def test_an_unanswerable_endpoint_is_not_reachable(self):
        mod = self._module()
        # Port 1 on the loopback: nothing listens, and it fails fast.
        self.assertFalse(mod._ollama_answers("http://127.0.0.1:1", timeout_seconds=1.0))

    def test_a_generate_suffix_is_trimmed_before_probing(self):
        mod = self._module()
        seen: list[str] = []

        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def _fake_urlopen(url, timeout=None):
            seen.append(url)
            return _Resp()

        with mock.patch("urllib.request.urlopen", _fake_urlopen):
            self.assertTrue(mod._ollama_answers("http://box:11434/api/generate"))
        self.assertEqual(seen, ["http://box:11434/api/tags"])
