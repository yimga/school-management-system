"""Every namespace that mounts a DRF view must be allowed by NamespaceVersioning.

WHY THIS EXISTS
---------------
``DEFAULT_VERSIONING_CLASS`` is ``NamespaceVersioning``. On every DRF request it
reads ``request.resolver_match.namespace``, splits the colon-joined chain, and
raises ``NotFound`` unless SOME part of the chain is in ``ALLOWED_VERSIONS``.

``NotFound`` is a 404. It is raised during dispatch, before the view runs, so
there is no view log line, no exception report, and nothing in the URL conf that
looks wrong -- ``verify_url_name_integrity`` resolves the names happily, because
the routes DO exist. The only symptom is that an API returns 404 to everyone.

``migration_cloud_api`` was missing from the list. Its 92 routes are mounted
twice -- ``migration_cloud_super:migration_cloud_api`` on the manager host and
``migration_cloud_portal:migration_cloud_api`` on the tenant host -- and neither
chain contained an allowed part, so all 184 were dead: bundles, canonical
templates, artifact upload, reconcile, scoped API tokens, webhook subscriptions.

The test walks every host urlconf and applies DRF's own rule to every namespace
chain that actually carries a DRF view, so it fails for the NEXT namespace
somebody mounts, not just for the one that was broken.
"""
from __future__ import annotations

from importlib import import_module

from django.conf import settings
from django.test import SimpleTestCase

HOST_URLCONFS = (
    "config.urls",
    "config.tenant_urls",
    "config.manager_urls",
    "config.public_urls",
    "config.api_urls",
)


def _is_drf(callback) -> bool:
    cls = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
    if cls is None:
        return False
    return any(base.__module__.startswith("rest_framework") for base in cls.__mro__)


def _drf_namespace_chains() -> dict[str, int]:
    """Colon-joined namespace chain -> number of DRF routes under it."""
    chains: dict[str, int] = {}

    def walk(patterns, namespaces):
        for pattern in patterns:
            nested = getattr(pattern, "url_patterns", None)
            if nested is not None:
                walk(
                    nested,
                    namespaces + ([pattern.namespace] if pattern.namespace else []),
                )
                continue
            callback = getattr(pattern, "callback", None)
            if callback is None or not _is_drf(callback):
                continue
            chain = ":".join(namespaces)
            chains[chain] = chains.get(chain, 0) + 1

    for modname in HOST_URLCONFS:
        try:
            module = import_module(modname)
        except Exception:  # noqa: BLE001 - a host urlconf that will not import
            continue        #                is another gate's finding, not this one
        walk(module.urlpatterns, [])
    return chains


class DrfNamespaceVersionTests(SimpleTestCase):
    def test_every_drf_namespace_chain_is_allowed(self):
        """This is DRF's rule verbatim: ANY part of the chain may satisfy it."""
        allowed = set(settings.REST_FRAMEWORK.get("ALLOWED_VERSIONS") or ())
        default = settings.REST_FRAMEWORK.get("DEFAULT_VERSION")
        chains = _drf_namespace_chains()

        self.assertGreater(
            len(chains), 0, "found no DRF routes at all -- the walk is broken"
        )

        dead: list[str] = []
        for chain, count in sorted(chains.items()):
            if not chain:
                # No namespace at all -> DRF falls back to DEFAULT_VERSION.
                if default not in allowed:
                    dead.append(f"<no namespace> falls back to {default!r} ({count})")
                continue
            if not any(part in allowed for part in chain.split(":")):
                dead.append(f"{chain!r} ({count} route(s))")

        self.assertEqual(
            dead,
            [],
            "NamespaceVersioning will raise NotFound -- a 404 before the view "
            "runs, with no log line -- for every route under these namespace "
            "chains. Add the namespace to REST_FRAMEWORK['ALLOWED_VERSIONS']: "
            + "; ".join(dead),
        )

    def test_default_version_is_itself_allowed(self):
        """If the fallback is not allowed, an un-namespaced DRF view 404s too."""
        allowed = set(settings.REST_FRAMEWORK.get("ALLOWED_VERSIONS") or ())
        self.assertIn(settings.REST_FRAMEWORK.get("DEFAULT_VERSION"), allowed)

    def test_migration_cloud_api_routes_are_reachable(self):
        """The specific regression: both host mounts resolve to an allowed version."""
        from rest_framework.versioning import NamespaceVersioning

        class _Match:
            def __init__(self, namespace):
                self.namespace = namespace

        class _Req:
            def __init__(self, namespace):
                self.resolver_match = _Match(namespace)

        versioning = NamespaceVersioning()
        for chain in (
            "migration_cloud_super:migration_cloud_api",
            "migration_cloud_portal:migration_cloud_api",
        ):
            with self.subTest(chain=chain):
                # Raises NotFound if the chain is not allowed.
                self.assertIn(
                    versioning.determine_version(_Req(chain)),
                    set(settings.REST_FRAMEWORK.get("ALLOWED_VERSIONS") or ()),
                )
