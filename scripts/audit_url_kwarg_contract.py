"""Every view must be able to accept the kwargs its own URL will hand it.

WHY THIS EXISTS. ``include(..., {"shell": "super"})`` injects an extra kwarg into
EVERY view in the included module. Views written for that contract take ``**kwargs``
and read ``kwargs.get("shell", "super")``. Views that were not — because they were
written for a different host and the module was later mounted somewhere new — raise
``TypeError: get() got an unexpected keyword argument 'shell'`` on the first request.

That is a 500 that no import, no check, and no test collection can see: the URL
resolves, the view exists, the permission passes, and the signature mismatch only
happens when Python calls it. Ten operator routes on manager.runmycampus.com were
dead this way, including the whole ``/super/migration/connectors/`` family.

It is also invisible to a route-name gate. ``verify_url_name_integrity`` unions names
across host urlconfs and asks whether they resolve; every one of these DID resolve.

WHAT IT CHECKS. For each urlconf, walk every pattern, collect the kwargs that pattern
will pass (both ``include()`` defaults and named captures), and compare against the
callback's signature. Report any view that cannot accept them.

Zero-tolerance: exit 1 on any finding.

    python scripts/audit_url_kwarg_contract.py
    python scripts/audit_url_kwarg_contract.py --urlconf config.manager_urls
"""
from __future__ import annotations

import argparse
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

URLCONFS = (
    "config.urls",
    "config.tenant_urls",
    "config.manager_urls",
    "config.public_urls",
)


def _accepts(callback, names: set[str]) -> set[str]:
    """Return the subset of `names` the callback cannot accept."""
    target = callback
    # Class-based views: the real signature lives on the handler, and as_view()
    # forwards **kwargs to it, so checking the wrapper alone always passes.
    view_class = getattr(callback, "view_class", None)
    if view_class is not None:
        handlers = [
            getattr(view_class, verb)
            for verb in ("get", "post", "put", "patch", "delete")
            if hasattr(view_class, verb)
        ]
        rejected: set[str] = set()
        for handler in handlers:
            rejected |= _signature_rejects(handler, names)
        return rejected
    # Unwrap decorators so we test the function that actually runs.
    while hasattr(target, "__wrapped__"):
        target = target.__wrapped__
    return _signature_rejects(target, names)


def _signature_rejects(func, names: set[str]) -> set[str]:
    """Names this callable cannot accept, plus names it REQUIRES and will not be given.

    Both directions are the same defect wearing two faces, and one view can carry both:
    ``SocialModerationAPI`` is mounted at a list URL and a detail URL, so its ``get``
    (no ``item_id``) 500s on the detail route while its ``post`` (``item_id`` required)
    500s on the list route. Checking only "can it accept" finds one and misses the other.
    """
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return set()  # builtins / C callables: cannot tell, do not accuse
    params = sig.parameters
    named = {
        name: p
        for name, p in params.items()
        if p.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    # First two positionals are (self, request) or (request,) -- never URL kwargs.
    skip = {"self", "request", "cls"}
    required_unfilled = {
        name
        for name, p in named.items()
        if name not in skip
        and p.default is inspect.Parameter.empty
        and name not in names
    }
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return required_unfilled
    return (names - set(named)) | required_unfilled


def walk(urlconf: str) -> list[tuple[str, str, set[str]]]:
    from django.urls import get_resolver

    findings: list[tuple[str, str, set[str]]] = []

    def visit(node, prefix: str, inherited: dict):
        for pattern in node.url_patterns:
            route = prefix + str(getattr(pattern, "pattern", ""))
            passed = dict(inherited)
            # An include() carries its extras as `default_kwargs` on the URLResolver;
            # a leaf path() carries them as `default_args` on the URLPattern. Reading
            # only one of the two is how the `shell` injection stayed invisible.
            passed.update(getattr(pattern, "default_kwargs", None) or {})
            passed.update(getattr(pattern, "default_args", None) or {})
            if hasattr(pattern, "url_patterns"):
                visit(pattern, route, passed)
                continue
            names = set(passed)
            names |= set(pattern.pattern.regex.groupindex)
            if not names:
                continue
            rejected = _accepts(pattern.callback, names)
            if rejected:
                findings.append(("/" + route, _label(pattern.callback), rejected))

    visit(get_resolver(urlconf), "", {})
    return findings


def _label(callback) -> str:
    cls = getattr(callback, "view_class", None)
    if cls is not None:
        return f"{cls.__module__}.{cls.__name__}"
    return f"{getattr(callback, '__module__', '?')}.{getattr(callback, '__qualname__', callback)}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--urlconf", action="append", default=None)
    args = parser.parse_args()

    import django

    django.setup()

    total = 0
    for urlconf in args.urlconf or URLCONFS:
        findings = walk(urlconf)
        status = "FAIL" if findings else "OK"
        print(f"[{status}] {urlconf}: {len(findings)} view(s) reject their own URL kwargs")
        for route, view, rejected in sorted(findings):
            print(f"        {route}\n            {view} cannot accept {sorted(rejected)}")
        total += len(findings)

    print(f"\nTOTAL: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
