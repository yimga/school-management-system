"""Regression seal: broker publish must be BOUNDED, and tasks must still run.

Incident (2026-06-17): the prod 502 crash-loop was worker threads BLOCKED on I/O.
A future Valkey/Redis broker reintroduces that risk — a web request calling
`.delay()` would hang on a slow broker exactly like an un-timed cache read. The
settings broker-resilience block (config/settings.py) must therefore, when a
broker IS configured, set bounded socket timeouts + a fail-fast publish retry so
enqueuing can never block a web thread unboundedly. And when NO broker is
configured, tasks must fall back to eager (inline) execution so deferred work
still runs.

Verified by importing settings in a BARE subprocess (not under pytest, so the
`not RUNNING_TESTS` broker block actually activates) under both env states.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_ROOT = Path(__file__).resolve().parents[2]  # .../school-management-system

_PROBE = (
    "import os, json, django;"
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');"
    "django.setup();"
    "from django.conf import settings as s;"
    "topts = getattr(s, 'CELERY_BROKER_TRANSPORT_OPTIONS', {}) or {};"
    "print('PROBE::' + json.dumps({"
    "'broker': bool(getattr(s, 'CELERY_BROKER_URL', '')),"
    "'eager': bool(getattr(s, 'CELERY_TASK_ALWAYS_EAGER', False)),"
    "'connect_timeout': topts.get('socket_connect_timeout'),"
    "'socket_timeout': topts.get('socket_timeout'),"
    "'publish_retry': getattr(s, 'CELERY_TASK_PUBLISH_RETRY', None),"
    "'retry_on_startup': getattr(s, 'CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP', None),"
    "}))"
)


def _probe(env_extra):
    env = dict(os.environ)
    env.update({"LITELLM_PROXY_URL": "", "LITELLM_API_KEY": ""})
    env.update(env_extra)
    # Ensure no pytest marker leaks in to flip RUNNING_TESTS.
    env.pop("PYTEST_CURRENT_TEST", None)
    out = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    for line in out.stdout.splitlines():
        if line.startswith("PROBE::"):
            return json.loads(line[len("PROBE::"):])
    raise AssertionError(f"probe produced no PROBE:: line.\nSTDOUT:\n{out.stdout}\nSTDERR:\n{out.stderr}")


class CeleryBrokerResilienceSealTests(SimpleTestCase):
    def test_broker_present_bounds_the_publish_path(self):
        data = self._with_redis()
        self.assertTrue(data["broker"], "broker URL should be set")
        self.assertFalse(data["eager"], "must NOT be eager when a broker is configured")
        # The crash-loop guard: bounded socket timeouts + fail-fast publish.
        self.assertEqual(data["connect_timeout"], 2.0)
        self.assertEqual(data["socket_timeout"], 4.0)
        self.assertTrue(data["publish_retry"])
        self.assertTrue(data["retry_on_startup"])

    def test_no_broker_falls_back_to_eager(self):
        data = self._without_redis()
        self.assertFalse(data["broker"], "broker URL should be empty")
        self.assertTrue(data["eager"], "must run tasks inline when no broker exists")
        # No broker → the transport-options block must not have run.
        self.assertIsNone(data["connect_timeout"])

    def _with_redis(self):
        return _probe({"REDIS_URL": "redis://localhost:6379/0", "CELERY_BROKER_URL": ""})

    def _without_redis(self):
        return _probe({
            "REDIS_URL": "",
            "CELERY_BROKER_URL": "",
            "RMC_DISABLE_EAGER_FALLBACK": "",
        })
