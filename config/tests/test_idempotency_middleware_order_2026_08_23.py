"""The base MIDDLEWARE order is load-bearing on self-host boxes.

``config/settings.py`` builds MIDDLEWARE twice and the second build, inside
``if USE_DJANGO_TENANTS and postgresql``, REPLACES the first. The cloud takes that
branch, so most middleware-ordering guards in this repo assert on the tenants list
only. The base list is not dead code: ``deploy/selfhost/.env.edge.example`` sets
``USE_DJANGO_TENANTS=0``, which is exactly the branch that keeps it. Every sovereign
edge box runs the base list.

``IdempotencyKeyMiddleware`` sat at base index 4 -- above SessionMiddleware (10),
TenantMiddleware (16) and AuthenticationMiddleware (36). Its cache key is
``sha256(tenant:user:METHOD:path:header)``, and both ``_tenant_key`` and
``_user_key`` read attributes those three middleware are what SET. Running fourth,
it saw neither, so every key on every edge box degenerated to ``global:anon:...``:
user B POSTing the same path with the same Idempotency-Key within the 24h TTL got
user A's response body back verbatim with ``Idempotent-Replay: 1``, and B's write
was silently dropped.

``apps/billing/tests/test_middleware_known_gap_burndown.py`` already asserts this
ordering -- but only on the tenants list, so it was green throughout.

These live in ``config/tests/`` rather than beside that test because the subject is
``config/settings.py``, and because the assertion must not be able to go green again
by someone fixing only one of the two lists.
"""

from __future__ import annotations

import importlib.util
import pathlib

from django.test import SimpleTestCase

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCANNER = _REPO_ROOT / "scripts" / "verify_middleware_topology_parity.py"
_SETTINGS = _REPO_ROOT / "config" / "settings.py"

_IDEMPOTENCY = "apps.api.middleware_idempotency.IdempotencyKeyMiddleware"
_AUTH = "django.contrib.auth.middleware.AuthenticationMiddleware"
_SESSION = "django.contrib.sessions.middleware.SessionMiddleware"
_TENANT = "apps.schools.middleware.TenantMiddleware"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("_mw_parity_idem", _SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IdempotencyOrderingTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base, cls.tenants = _load_scanner().collect(_SETTINGS)

    def test_the_scanner_found_both_lists(self):
        # Calibration: if collect() silently returned empty lists, every ordering
        # assertion below would pass by vacuum.
        self.assertGreater(len(self.base), 30, self.base)
        self.assertGreater(len(self.tenants), 30, self.tenants)
        for name in (_IDEMPOTENCY, _AUTH, _SESSION, _TENANT):
            self.assertIn(name, self.base, f"{name} missing from the base MIDDLEWARE")

    def test_idempotency_sits_after_auth_in_BOTH_topologies(self):
        """The edge box runs the base list. Ordering it there is not optional."""
        for label, chain in (("base", self.base), ("tenants", self.tenants)):
            with self.subTest(topology=label):
                if _IDEMPOTENCY not in chain:
                    continue
                for dependency in (_SESSION, _TENANT, _AUTH):
                    if dependency not in chain:
                        continue
                    self.assertLess(
                        chain.index(dependency),
                        chain.index(_IDEMPOTENCY),
                        f"In the {label} MIDDLEWARE, {dependency} must run BEFORE "
                        f"{_IDEMPOTENCY}: the idempotency cache key is built from "
                        "request.user and request.school, which that middleware sets. "
                        "Above it, every key collapses to 'global:anon' and one "
                        "user replays another user's response body.",
                    )


class IdempotencyKeyDerivationTests(SimpleTestCase):
    """Prove the ordering is load-bearing rather than cosmetic.

    If ``_cache_key`` did not actually discriminate on user and school, the
    ordering assertion above would be guarding nothing.
    """

    def _key(self, *, user_pk, school_id):
        from apps.api.middleware_idempotency import _cache_key

        class _U:
            is_authenticated = user_pk is not None
            pk = user_pk

        class _S:
            id = school_id

        class _R:
            method = "POST"
            path = "/api/v1/people/students/"
            user = _U()
            school = _S() if school_id is not None else None

        return _cache_key(_R(), "abc")

    def test_two_users_do_not_share_a_key(self):
        self.assertNotEqual(
            self._key(user_pk=1, school_id=7),
            self._key(user_pk=2, school_id=7),
        )

    def test_two_schools_do_not_share_a_key(self):
        self.assertNotEqual(
            self._key(user_pk=1, school_id=7),
            self._key(user_pk=1, school_id=8),
        )

    def test_an_unresolved_request_collapses_to_one_shared_key(self):
        """This is the bug the ordering prevents, stated as an assertion.

        With no user and no school on the request -- which is exactly what
        IdempotencyKeyMiddleware saw when it ran above session/tenant/auth --
        every caller in the deployment computes the SAME key.
        """
        collapsed = self._key(user_pk=None, school_id=None)
        self.assertEqual(collapsed, self._key(user_pk=None, school_id=None))
        self.assertNotEqual(collapsed, self._key(user_pk=1, school_id=7))
